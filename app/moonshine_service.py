from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
from moonshine_voice import get_model_for_language
from moonshine_voice.transcriber import TranscriptEventListener, Transcriber

from app.config import Settings
from app.transcript_store import TranscriptStore

logger = logging.getLogger(__name__)


class StoreListener(TranscriptEventListener):
    def __init__(self, store: TranscriptStore) -> None:
        self._store = store

    def on_line_started(self, event) -> None:
        self._sync_line("line_started", event.line)

    def on_line_updated(self, event) -> None:
        self._sync_line("line_updated", event.line)

    def on_line_text_changed(self, event) -> None:
        self._sync_line("line_text_changed", event.line)

    def on_line_completed(self, event) -> None:
        self._sync_line("line_completed", event.line)

    def on_error(self, event) -> None:
        message = str(event)
        logger.exception("Moonshine transcript error: %s", message)
        self._store.record_error(message)

    def _sync_line(self, event_type: str, line) -> None:
        speaker_index = line.speaker_index if line.has_speaker_id else None
        self._store.upsert_line(
            event_type=event_type,
            line_id=line.line_id,
            text=line.text,
            start_time=line.start_time,
            duration=line.duration,
            is_complete=line.is_complete,
            speaker_index=speaker_index,
            latency_ms=line.last_transcription_latency_ms,
        )


class MoonshineService:
    def __init__(self, settings: Settings, store: TranscriptStore) -> None:
        self._settings = settings
        self._store = store
        self._listener = StoreListener(store)
        self._lock = threading.Lock()
        self._transcriber: Transcriber | None = None
        self._stream = None
        self._sd_stream: sd.InputStream | None = None
        self._last_error: str | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self._transcriber is not None

    def start(self) -> None:
        with self._lock:
            if self._transcriber is not None:
                return
        try:
            self._settings.cache_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("XDG_CACHE_HOME", str(self._settings.cache_dir))
            logger.info("Starting Moonshine transcriber with cache dir %s", self._settings.cache_dir)
            model_path, model_arch = get_model_for_language(self._settings.language)
            logger.info("Using Moonshine model path %s and arch %s", model_path, model_arch)
            transcriber = Transcriber(model_path, model_arch)
            stream = transcriber.create_stream(0.5)
            stream.add_listener(self._listener)

            def audio_callback(in_data, frames, time_info, status):
                if status:
                    logger.warning("Microphone callback status: %s", status)
                if in_data is None:
                    return
                audio_data = in_data.astype(np.float32).flatten()
                level = float(np.sqrt(np.mean(np.square(audio_data)))) if len(audio_data) else 0.0
                self._store.set_input_level(level)
                stream.add_audio(audio_data, 16000)

            sd_stream = sd.InputStream(
                samplerate=16000,
                blocksize=1024,
                channels=1,
                dtype="float32",
                callback=audio_callback,
            )
            stream.start()
            sd_stream.start()
        except Exception as exc:
            logger.exception("Failed to start Moonshine transcriber")
            with self._lock:
                self._last_error = str(exc)
            self._store.set_running(False)
            self._store.record_error(f"Failed to start transcriber: {exc}")
            raise
        with self._lock:
            self._transcriber = transcriber
            self._stream = stream
            self._sd_stream = sd_stream
            self._last_error = None
        logger.info("Moonshine transcriber started")
        self._store.set_running(True)

    def stop(self) -> None:
        with self._lock:
            if self._transcriber is None:
                return
            transcriber = self._transcriber
            stream = self._stream
            sd_stream = self._sd_stream
            self._transcriber = None
            self._stream = None
            self._sd_stream = None
        try:
            logger.info("Stopping Moonshine transcriber")
            if sd_stream is not None:
                sd_stream.stop()
                sd_stream.close()
            if stream is not None:
                stream.stop()
                stream.close()
            transcriber.close()
        finally:
            self._store.set_input_level(0.0)
            self._store.set_running(False)

    def status(self) -> dict[str, str | bool | Path]:
        snapshot = self._store.snapshot()
        return {
            "running": self.running,
            "ready": self._last_error is None,
            "language": self._settings.language,
            "cache_dir": str(self._settings.cache_dir),
            "last_error": self._last_error,
            "input_level": snapshot["input_level"],
        }
