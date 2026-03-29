from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from pathlib import Path
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
    created_seq: int
    updated_seq: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "text": self.text,
            "start_time": self.start_time,
            "duration": self.duration,
            "is_complete": self.is_complete,
            "speaker_index": self.speaker_index,
            "latency_ms": self.latency_ms,
            "created_seq": self.created_seq,
            "updated_seq": self.updated_seq,
        }


@dataclass
class ConversationEvent:
    event_id: int
    role: str
    kind: str
    text: str
    is_final: bool
    created_seq: int
    updated_seq: int
    source_line_id: int | None = None
    agent_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "role": self.role,
            "kind": self.kind,
            "text": self.text,
            "is_final": self.is_final,
            "created_seq": self.created_seq,
            "updated_seq": self.updated_seq,
            "source_line_id": self.source_line_id,
            "agent_name": self.agent_name,
        }


class TranscriptStore:
    def __init__(self, persistence_path: Path, history_limit: int) -> None:
        self._persistence_path = persistence_path
        self._history_limit = history_limit
        self._lock = threading.Lock()
        self._lines: dict[int, TranscriptLineState] = {}
        self._ordered_ids: list[int] = []
        self._events: dict[int, ConversationEvent] = {}
        self._ordered_event_ids: list[int] = []
        self._line_event_ids: dict[int, int] = {}
        self._running = False
        self._input_level = 0.0
        self._last_event: dict[str, Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._seq = 0
        self._next_event_id = 0

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def set_running(self, running: bool) -> None:
        with self._lock:
            self._running = running
        self._broadcast({"type": "status", "running": running})

    def upsert_line(self, *, event_type: str, line_id: int, text: str, start_time: float, duration: float, is_complete: bool, speaker_index: int | None, latency_ms: int) -> None:
        payloads: list[dict[str, Any]]
        with self._lock:
            self._seq += 1
            if line_id not in self._lines:
                self._ordered_ids.append(line_id)
                created_seq = self._seq
            else:
                created_seq = self._lines[line_id].created_seq
            self._lines[line_id] = TranscriptLineState(
                line_id=line_id,
                text=text,
                start_time=start_time,
                duration=duration,
                is_complete=is_complete,
                speaker_index=speaker_index,
                latency_ms=latency_ms,
                created_seq=created_seq,
                updated_seq=self._seq,
            )
            self._trim_locked()
            payload = {
                "type": event_type,
                "line": self._lines[line_id].to_dict(),
                "running": self._running,
            }
            payloads = [payload, self._upsert_conversation_event_locked(line_id=line_id, text=text, is_complete=is_complete)]
            self._last_event = payloads[-1]
            self._persist_locked()
        for item in payloads:
            self._broadcast(item)

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
                "events": [self._events[event_id].to_dict() for event_id in self._ordered_event_ids],
                "last_event": self._last_event,
            }

    def clear(self) -> dict[str, Any]:
        with self._lock:
            self._lines.clear()
            self._ordered_ids.clear()
            self._events.clear()
            self._ordered_event_ids.clear()
            self._line_event_ids.clear()
            self._last_event = {"type": "cleared", "running": self._running}
            self._persist_locked()
            snapshot = {
                "running": self._running,
                "input_level": self._input_level,
                "lines": [],
                "events": [],
                "last_event": self._last_event,
            }
        self._broadcast({"type": "snapshot", "state": snapshot})
        return snapshot

    def append_event(self, *, role: str, kind: str, text: str, is_final: bool, source_line_id: int | None = None, agent_name: str | None = None) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            self._next_event_id += 1
            event = ConversationEvent(
                event_id=self._next_event_id,
                role=role,
                kind=kind,
                text=text,
                is_final=is_final,
                created_seq=self._seq,
                updated_seq=self._seq,
                source_line_id=source_line_id,
                agent_name=agent_name,
            )
            self._events[event.event_id] = event
            self._ordered_event_ids.append(event.event_id)
            self._trim_locked()
            payload = {"type": "event_appended", "event": event.to_dict(), "running": self._running}
            self._last_event = payload
            self._persist_locked()
        self._broadcast(payload)
        return event.to_dict()

    def load(self) -> None:
        if not self._persistence_path.exists():
            return
        payload = json.loads(self._persistence_path.read_text(encoding="utf-8"))
        events = payload.get("events", [])
        lines = payload.get("lines", [])
        with self._lock:
            self._lines.clear()
            self._ordered_ids.clear()
            self._events.clear()
            self._ordered_event_ids.clear()
            self._line_event_ids.clear()
            for item in lines:
                line = TranscriptLineState(
                    line_id=int(item["line_id"]),
                    text=str(item["text"]),
                    start_time=float(item["start_time"]),
                    duration=float(item["duration"]),
                    is_complete=bool(item["is_complete"]),
                    speaker_index=item.get("speaker_index"),
                    latency_ms=int(item.get("latency_ms", 0)),
                    created_seq=int(item.get("created_seq", item["line_id"])),
                    updated_seq=int(item.get("updated_seq", item["line_id"])),
                )
                self._lines[line.line_id] = line
                self._ordered_ids.append(line.line_id)
                self._seq = max(self._seq, line.updated_seq, line.created_seq)
                if not events:
                    self._restore_line_as_event_locked(line)
            for item in events:
                event = ConversationEvent(
                    event_id=int(item["event_id"]),
                    role=str(item["role"]),
                    kind=str(item["kind"]),
                    text=str(item["text"]),
                    is_final=bool(item["is_final"]),
                    created_seq=int(item["created_seq"]),
                    updated_seq=int(item["updated_seq"]),
                    source_line_id=item.get("source_line_id"),
                    agent_name=item.get("agent_name"),
                )
                self._events[event.event_id] = event
                self._ordered_event_ids.append(event.event_id)
                self._next_event_id = max(self._next_event_id, event.event_id)
                self._seq = max(self._seq, event.updated_seq, event.created_seq)
                if event.source_line_id is not None and event.role == "user":
                    self._line_event_ids[event.source_line_id] = event.event_id
            self._trim_locked()

    def _persist_locked(self) -> None:
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "lines": [self._lines[line_id].to_dict() for line_id in self._ordered_ids],
            "events": [self._events[event_id].to_dict() for event_id in self._ordered_event_ids],
        }
        self._persistence_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def _trim_locked(self) -> None:
        if self._history_limit <= 0:
            return
        self._ordered_ids.sort(key=lambda line_id: self._lines[line_id].created_seq)
        while len(self._ordered_ids) > self._history_limit:
            removed_id = self._ordered_ids.pop(0)
            self._lines.pop(removed_id, None)
        self._ordered_event_ids.sort(key=lambda event_id: self._events[event_id].created_seq)
        while len(self._ordered_event_ids) > self._history_limit:
            removed_id = self._ordered_event_ids.pop(0)
            removed_event = self._events.pop(removed_id, None)
            if removed_event is None or removed_event.source_line_id is None:
                continue
            if self._line_event_ids.get(removed_event.source_line_id) == removed_id:
                self._line_event_ids.pop(removed_event.source_line_id, None)

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

    def _upsert_conversation_event_locked(self, *, line_id: int, text: str, is_complete: bool) -> dict[str, Any]:
        event_id = self._line_event_ids.get(line_id)
        if event_id is None:
            self._next_event_id += 1
            event_id = self._next_event_id
            self._line_event_ids[line_id] = event_id
            created_seq = self._seq
        else:
            created_seq = self._events[event_id].created_seq
        event = ConversationEvent(
            event_id=event_id,
            role="user",
            kind="transcript",
            text=text,
            is_final=is_complete,
            created_seq=created_seq,
            updated_seq=self._seq,
            source_line_id=line_id,
        )
        self._events[event_id] = event
        if event_id not in self._ordered_event_ids:
            self._ordered_event_ids.append(event_id)
        self._trim_locked()
        return {"type": "conversation_event", "event": event.to_dict(), "running": self._running}

    def _restore_line_as_event_locked(self, line: TranscriptLineState) -> None:
        self._next_event_id += 1
        event = ConversationEvent(
            event_id=self._next_event_id,
            role="user",
            kind="transcript",
            text=line.text,
            is_final=line.is_complete,
            created_seq=line.created_seq,
            updated_seq=line.updated_seq,
            source_line_id=line.line_id,
        )
        self._events[event.event_id] = event
        self._ordered_event_ids.append(event.event_id)
        self._line_event_ids[line.line_id] = event.event_id
