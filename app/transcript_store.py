from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class TranscriptLineState:
    line_id: int
    text: str
    start_time: float
    duration: float
    is_complete: bool
    speaker_index: int | None
    latency_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "text": self.text,
            "start_time": self.start_time,
            "duration": self.duration,
            "is_complete": self.is_complete,
            "speaker_index": self.speaker_index,
            "latency_ms": self.latency_ms,
        }


class TranscriptStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lines: dict[int, TranscriptLineState] = {}
        self._ordered_ids: list[int] = []
        self._running = False
        self._input_level = 0.0
        self._last_event: dict[str, Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def set_running(self, running: bool) -> None:
        with self._lock:
            self._running = running
        self._broadcast({"type": "status", "running": running})

    def upsert_line(self, *, event_type: str, line_id: int, text: str, start_time: float, duration: float, is_complete: bool, speaker_index: int | None, latency_ms: int) -> None:
        payload: dict[str, Any]
        with self._lock:
            if line_id not in self._lines:
                self._ordered_ids.append(line_id)
            self._lines[line_id] = TranscriptLineState(
                line_id=line_id,
                text=text,
                start_time=start_time,
                duration=duration,
                is_complete=is_complete,
                speaker_index=speaker_index,
                latency_ms=latency_ms,
            )
            payload = {
                "type": event_type,
                "line": self._lines[line_id].to_dict(),
                "running": self._running,
            }
            self._last_event = payload
        self._broadcast(payload)

    def record_error(self, message: str) -> None:
        payload = {"type": "error", "message": message}
        with self._lock:
            self._last_event = payload
        self._broadcast(payload)

    def set_input_level(self, level: float) -> None:
        with self._lock:
            self._input_level = level
            payload = {"type": "input_level", "level": level, "running": self._running}
            self._last_event = payload
        self._broadcast(payload)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "input_level": self._input_level,
                "lines": [self._lines[line_id].to_dict() for line_id in self._ordered_ids],
                "last_event": self._last_event,
            }

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(queue)
        await queue.put({"type": "snapshot", "state": self.snapshot()})
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def _broadcast(self, payload: dict[str, Any]) -> None:
        if not self._subscribers or self._loop is None:
            return
        for queue in list(self._subscribers):
            self._loop.call_soon_threadsafe(queue.put_nowait, payload)
