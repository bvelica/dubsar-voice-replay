from __future__ import annotations

import asyncio
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import AgentSlotSettings


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


@dataclass
class UtteranceState:
    source_line_id: int
    text: str
    status: str
    kind: str
    request_id: int | None
    created_seq: int
    updated_seq: int
    agent_name: str | None = None
    agent_label: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_line_id": self.source_line_id,
            "text": self.text,
            "status": self.status,
            "kind": self.kind,
            "draft_id": self.request_id,
            "request_id": self.request_id,
            "created_seq": self.created_seq,
            "updated_seq": self.updated_seq,
            "agent_name": self.agent_name,
            "agent_label": self.agent_label,
            "error": self.error,
        }


@dataclass
class RequestState:
    request_id: int
    text: str
    status: str
    created_seq: int
    updated_seq: int
    source_line_ids: list[int]
    parent_request_id: int | None = None
    origin: str = "speech"
    target_agent_name: str | None = None
    target_agent_label: str | None = None
    agent_name: str | None = None
    agent_label: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "text": self.text,
            "status": self.status,
            "created_seq": self.created_seq,
            "updated_seq": self.updated_seq,
            "source_line_ids": list(self.source_line_ids),
            "parent_request_id": self.parent_request_id,
            "origin": self.origin,
            "target_agent_name": self.target_agent_name,
            "target_agent_label": self.target_agent_label,
            "agent_name": self.agent_name,
            "agent_label": self.agent_label,
            "error": self.error,
        }


@dataclass
class AgentState:
    name: str
    status: str
    updated_seq: int
    label: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
            "updated_seq": self.updated_seq,
        }


@dataclass
class RequestEvent:
    event_id: int
    request_id: int
    kind: str
    detail: str
    created_seq: int
    source_line_ids: list[int]
    parent_request_id: int | None = None
    agent_name: str | None = None
    agent_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "request_id": self.request_id,
            "kind": self.kind,
            "detail": self.detail,
            "created_seq": self.created_seq,
            "source_line_ids": list(self.source_line_ids),
            "parent_request_id": self.parent_request_id,
            "agent_name": self.agent_name,
            "agent_label": self.agent_label,
        }


class TranscriptStore:
    def __init__(self, persistence_path: Path, history_limit: int, agent_slots: list[AgentSlotSettings] | None = None) -> None:
        self._persistence_path = persistence_path
        self._history_limit = history_limit
        self._configured_agent_slots = list(agent_slots or [])
        self._lock = threading.Lock()
        self._lines: dict[int, TranscriptLineState] = {}
        self._ordered_ids: list[int] = []
        self._events: dict[int, ConversationEvent] = {}
        self._ordered_event_ids: list[int] = []
        self._line_event_ids: dict[int, int] = {}
        self._utterances: dict[int, UtteranceState] = {}
        self._ordered_utterance_ids: list[int] = []
        self._requests: dict[int, RequestState] = {}
        self._ordered_request_ids: list[int] = []
        self._agent_statuses: dict[str, AgentState] = {}
        self._request_events: dict[int, RequestEvent] = {}
        self._ordered_request_event_ids: list[int] = []
        self._running = False
        self._input_level = 0.0
        self._last_event: dict[str, Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._seq = 0
        self._next_event_id = 0
        self._next_request_id = 0

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
            created_seq = self._lines[line_id].created_seq if line_id in self._lines else self._seq
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
                created_seq=created_seq,
                updated_seq=self._seq,
            )
            payload = {"type": event_type, "line": self._lines[line_id].to_dict(), "running": self._running}
            payloads = [payload, self._upsert_conversation_event_locked(line_id=line_id, text=text, is_complete=is_complete)]
            utterance_payload = self._sync_utterance_locked(line_id=line_id, text=text, is_complete=is_complete)
            if utterance_payload is not None:
                payloads.append(utterance_payload)
                request_payload = self._request_payload_for_line_locked(line_id)
                if request_payload is not None:
                    payloads.append(request_payload)
            self._trim_locked()
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
            return self._snapshot_locked()

    def clear(self) -> dict[str, Any]:
        with self._lock:
            self._lines.clear()
            self._ordered_ids.clear()
            self._events.clear()
            self._ordered_event_ids.clear()
            self._line_event_ids.clear()
            self._utterances.clear()
            self._ordered_utterance_ids.clear()
            self._requests.clear()
            self._ordered_request_ids.clear()
            self._request_events.clear()
            self._ordered_request_event_ids.clear()
            self._next_request_id = 0
            self._last_event = {"type": "cleared", "running": self._running}
            self._persist_locked()
            snapshot = self._snapshot_locked()
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
            payload = {"type": "event_appended", "event": event.to_dict(), "running": self._running}
            self._trim_locked()
            self._last_event = payload
            self._persist_locked()
        self._broadcast(payload)
        return event.to_dict()

    def update_utterance(
        self,
        *,
        source_line_id: int,
        status: str,
        text: str | None = None,
        agent_name: str | None = None,
        agent_label: str | None = None,
        error: str | None = None,
        kind: str | None = None,
        draft_id: int | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            utterance = self._utterances.get(source_line_id)
            if utterance is None:
                line = self._lines.get(source_line_id)
                if line is None or not line.is_complete:
                    return None
                self._seq += 1
                request_id = draft_id if isinstance(draft_id, int) else self._next_open_request_id_locked()
                utterance = UtteranceState(
                    source_line_id=source_line_id,
                    text=line.text,
                    status="pending",
                    kind="message",
                    request_id=request_id,
                    created_seq=self._seq,
                    updated_seq=self._seq,
                )
                self._utterances[source_line_id] = utterance
                self._ordered_utterance_ids.append(source_line_id)
            self._seq += 1
            updated = UtteranceState(
                source_line_id=utterance.source_line_id,
                text=text if text is not None else utterance.text,
                status=status,
                kind=kind if kind is not None else utterance.kind,
                request_id=draft_id if isinstance(draft_id, int) else utterance.request_id,
                created_seq=utterance.created_seq,
                updated_seq=self._seq,
                agent_name=agent_name if agent_name is not None else utterance.agent_name,
                agent_label=agent_label if agent_label is not None else utterance.agent_label,
                error=error,
            )
            self._utterances[source_line_id] = updated
            if updated.kind == "message" and isinstance(updated.request_id, int):
                self._sync_request_from_utterances_locked(updated.request_id)
            payload = {"type": "utterance_updated", "utterance": updated.to_dict(), "running": self._running}
            self._last_event = payload
            self._trim_locked()
            self._persist_locked()
        self._broadcast(payload)
        return updated.to_dict()

    def create_request(
        self,
        *,
        text: str,
        parent_request_id: int | None = None,
        target_agent_name: str | None = None,
        target_agent_label: str | None = None,
        origin: str = "delegation",
        status: str = "queued",
    ) -> dict[str, Any]:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Request text is required.")
        with self._lock:
            self._seq += 1
            self._next_request_id += 1
            request_id = self._next_request_id
            request = RequestState(
                request_id=request_id,
                text=clean_text,
                status=status,
                created_seq=self._seq,
                updated_seq=self._seq,
                source_line_ids=[],
                parent_request_id=parent_request_id,
                origin=origin,
                target_agent_name=target_agent_name,
                target_agent_label=target_agent_label,
            )
            self._requests[request_id] = request
            self._ordered_request_ids.append(request_id)
            self._append_request_event_locked(
                request_id=request_id,
                parent_request_id=parent_request_id,
                kind="subrequest_created" if isinstance(parent_request_id, int) else "request_created",
                detail=(
                    f"Sub-request created for {target_agent_label or target_agent_name or 'an agent'}."
                    if isinstance(parent_request_id, int)
                    else "Request created."
                ),
                source_line_ids=[],
                agent_name=target_agent_name,
                agent_label=target_agent_label,
            )
            if status == "queued":
                self._append_request_event_locked(
                    request_id=request_id,
                    parent_request_id=parent_request_id,
                    kind="request_queued",
                    detail="Request queued for external agents.",
                    source_line_ids=[],
                    agent_name=target_agent_name,
                    agent_label=target_agent_label,
                )
            payload = {"type": "request_updated", "request": request.to_dict(), "running": self._running}
            self._last_event = payload
            self._trim_locked()
            self._persist_locked()
        self._broadcast(payload)
        return request.to_dict()

    def update_request(
        self,
        *,
        request_id: int,
        status: str | None = None,
        text: str | None = None,
        target_agent_name: str | None = None,
        target_agent_label: str | None = None,
        agent_name: str | None = None,
        agent_label: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                return None
            self._seq += 1
            updated = RequestState(
                request_id=request.request_id,
                text=text if text is not None else request.text,
                status=status if status is not None else request.status,
                created_seq=request.created_seq,
                updated_seq=self._seq,
                source_line_ids=list(request.source_line_ids),
                parent_request_id=request.parent_request_id,
                origin=request.origin,
                target_agent_name=target_agent_name if target_agent_name is not None else request.target_agent_name,
                target_agent_label=target_agent_label if target_agent_label is not None else request.target_agent_label,
                agent_name=agent_name if agent_name is not None else request.agent_name,
                agent_label=agent_label if agent_label is not None else request.agent_label,
                error=error,
            )
            self._requests[request_id] = updated
            payload = {"type": "request_updated", "request": updated.to_dict(), "running": self._running}
            self._last_event = payload
            self._persist_locked()
        self._broadcast(payload)
        return updated.to_dict()

    def set_agent_status(self, *, name: str, status: str, label: str | None = None, detail: str | None = None) -> dict[str, Any]:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Agent name is required.")
        with self._lock:
            self._seq += 1
            agent_state = AgentState(
                name=normalized_name,
                label=label.strip() if isinstance(label, str) and label.strip() else normalized_name,
                status=status.strip(),
                detail=detail.strip() if isinstance(detail, str) and detail.strip() else None,
                updated_seq=self._seq,
            )
            self._agent_statuses[normalized_name.lower()] = agent_state
            payload = {"type": "agent_status", "agent": agent_state.to_dict(), "running": self._running}
            self._last_event = payload
            self._persist_locked()
        self._broadcast(payload)
        return agent_state.to_dict()

    def append_request_event(
        self,
        *,
        request_id: int,
        kind: str,
        detail: str,
        source_line_ids: list[int],
        parent_request_id: int | None = None,
        agent_name: str | None = None,
        agent_label: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            self._append_request_event_locked(
                request_id=request_id,
                parent_request_id=parent_request_id,
                kind=kind,
                detail=detail,
                source_line_ids=source_line_ids,
                agent_name=agent_name,
                agent_label=agent_label,
            )
            event = self._request_events[self._ordered_request_event_ids[-1]]
            payload = {"type": "request_event", "request_event": event.to_dict(), "running": self._running}
            self._last_event = payload
            self._trim_locked()
            self._persist_locked()
        self._broadcast(payload)
        return event.to_dict()

    def load(self) -> None:
        if not self._persistence_path.exists():
            return
        payload = json.loads(self._persistence_path.read_text(encoding="utf-8"))
        with self._lock:
            self._restore_payload_locked(payload)
            self._trim_locked()

    def _restore_payload_locked(self, payload: dict[str, Any]) -> None:
        self._lines.clear()
        self._ordered_ids.clear()
        self._events.clear()
        self._ordered_event_ids.clear()
        self._line_event_ids.clear()
        self._utterances.clear()
        self._ordered_utterance_ids.clear()
        self._requests.clear()
        self._ordered_request_ids.clear()
        self._agent_statuses.clear()
        self._request_events.clear()
        self._ordered_request_event_ids.clear()
        self._seq = 0
        self._next_event_id = 0
        self._next_request_id = 0

        for item in payload.get("lines", []):
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
            self._seq = max(self._seq, line.created_seq, line.updated_seq)

        for item in payload.get("events", []):
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
            self._seq = max(self._seq, event.created_seq, event.updated_seq)
            if event.role == "user" and isinstance(event.source_line_id, int):
                self._line_event_ids[event.source_line_id] = event.event_id

        for item in payload.get("utterances", []):
            request_id = item.get("request_id", item.get("draft_id"))
            utterance = UtteranceState(
                source_line_id=int(item["source_line_id"]),
                text=str(item["text"]),
                status=str(item["status"]),
                kind=str(item.get("kind", "message")),
                request_id=int(request_id) if isinstance(request_id, int) else request_id,
                created_seq=int(item["created_seq"]),
                updated_seq=int(item["updated_seq"]),
                agent_name=item.get("agent_name"),
                agent_label=item.get("agent_label"),
                error=item.get("error"),
            )
            self._utterances[utterance.source_line_id] = utterance
            self._ordered_utterance_ids.append(utterance.source_line_id)
            if isinstance(utterance.request_id, int):
                self._next_request_id = max(self._next_request_id, utterance.request_id)
            self._seq = max(self._seq, utterance.created_seq, utterance.updated_seq)

        for item in payload.get("requests", []):
            request = RequestState(
                request_id=int(item["request_id"]),
                text=str(item["text"]),
                status=str(item["status"]),
                created_seq=int(item["created_seq"]),
                updated_seq=int(item["updated_seq"]),
                source_line_ids=[int(value) for value in item.get("source_line_ids", [])],
                parent_request_id=item.get("parent_request_id"),
                origin=str(item.get("origin", "speech")),
                target_agent_name=item.get("target_agent_name"),
                target_agent_label=item.get("target_agent_label"),
                agent_name=item.get("agent_name"),
                agent_label=item.get("agent_label"),
                error=item.get("error"),
            )
            self._requests[request.request_id] = request
            self._ordered_request_ids.append(request.request_id)
            self._next_request_id = max(self._next_request_id, request.request_id)
            self._seq = max(self._seq, request.created_seq, request.updated_seq)

        for item in payload.get("agent_statuses", []):
            agent_state = AgentState(
                name=str(item["name"]),
                label=item.get("label"),
                status=str(item["status"]),
                detail=item.get("detail"),
                updated_seq=int(item["updated_seq"]),
            )
            self._agent_statuses[agent_state.name.lower()] = agent_state
            self._seq = max(self._seq, agent_state.updated_seq)

        for item in payload.get("request_events", []):
            event = RequestEvent(
                event_id=int(item["event_id"]),
                request_id=int(item["request_id"]),
                kind=str(item["kind"]),
                detail=str(item["detail"]),
                created_seq=int(item["created_seq"]),
                source_line_ids=[int(value) for value in item.get("source_line_ids", [])],
                parent_request_id=item.get("parent_request_id"),
                agent_name=item.get("agent_name"),
                agent_label=item.get("agent_label"),
            )
            self._request_events[event.event_id] = event
            self._ordered_request_event_ids.append(event.event_id)
            self._next_event_id = max(self._next_event_id, event.event_id)
            self._seq = max(self._seq, event.created_seq)

        if not self._requests:
            self._rebuild_requests_locked()

    def _persist_locked(self) -> None:
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "lines": [self._lines[line_id].to_dict() for line_id in self._ordered_ids],
            "events": [self._events[event_id].to_dict() for event_id in self._ordered_event_ids],
            "utterances": [self._utterances[source_line_id].to_dict() for source_line_id in self._ordered_utterance_ids],
            "requests": [self._requests[request_id].to_dict() for request_id in self._ordered_request_ids],
            "agent_statuses": [agent.to_dict() for agent in sorted(self._agent_statuses.values(), key=lambda item: item.updated_seq)],
            "request_events": [self._request_events[event_id].to_dict() for event_id in self._ordered_request_event_ids],
        }
        self._persistence_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _trim_locked(self) -> None:
        if self._history_limit <= 0:
            return
        self._ordered_ids.sort(key=lambda line_id: self._lines[line_id].created_seq)
        while len(self._ordered_ids) > self._history_limit:
            removed = self._ordered_ids.pop(0)
            self._lines.pop(removed, None)
        self._ordered_event_ids.sort(key=lambda event_id: self._events[event_id].created_seq)
        while len(self._ordered_event_ids) > self._history_limit * 2:
            removed = self._ordered_event_ids.pop(0)
            removed_event = self._events.pop(removed, None)
            if removed_event and isinstance(removed_event.source_line_id, int):
                if self._line_event_ids.get(removed_event.source_line_id) == removed:
                    self._line_event_ids.pop(removed_event.source_line_id, None)
        self._ordered_utterance_ids.sort(key=lambda source_line_id: self._utterances[source_line_id].created_seq)
        while len(self._ordered_utterance_ids) > self._history_limit:
            removed = self._ordered_utterance_ids.pop(0)
            self._utterances.pop(removed, None)
        self._ordered_request_ids.sort(key=lambda request_id: self._requests[request_id].created_seq)
        while len(self._ordered_request_ids) > self._history_limit * 2:
            removed = self._ordered_request_ids.pop(0)
            self._requests.pop(removed, None)
        self._ordered_request_event_ids.sort(key=lambda event_id: self._request_events[event_id].created_seq)
        while len(self._ordered_request_event_ids) > self._history_limit * 6:
            removed = self._ordered_request_event_ids.pop(0)
            self._request_events.pop(removed, None)

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
        created_seq = self._events[event_id].created_seq if event_id is not None else self._seq
        if event_id is None:
            self._next_event_id += 1
            event_id = self._next_event_id
            self._line_event_ids[line_id] = event_id
            self._ordered_event_ids.append(event_id)
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
        return {"type": "conversation_event", "event": event.to_dict(), "running": self._running}

    def _sync_utterance_locked(self, *, line_id: int, text: str, is_complete: bool) -> dict[str, Any] | None:
        utterance = self._utterances.get(line_id)
        if utterance is None and not is_complete:
            return None
        clean_text, target_agent_name, target_agent_label, explicit_target = self._parse_targeted_text_locked(text)
        if utterance is None:
            request_id = self._next_request_id_locked() if explicit_target else self._next_open_request_id_locked()
            existing_request = request_id in self._requests
            utterance = UtteranceState(
                source_line_id=line_id,
                text=clean_text,
                status="pending",
                kind="message",
                request_id=request_id,
                created_seq=self._seq,
                updated_seq=self._seq,
            )
            self._utterances[line_id] = utterance
            self._ordered_utterance_ids.append(line_id)
            if explicit_target:
                self._requests[request_id] = RequestState(
                    request_id=request_id,
                    text=clean_text,
                    status="pending",
                    created_seq=self._seq,
                    updated_seq=self._seq,
                    source_line_ids=[],
                    origin="speech",
                    target_agent_name=target_agent_name,
                    target_agent_label=target_agent_label,
                )
                self._ordered_request_ids.append(request_id)
            self._sync_request_from_utterances_locked(request_id)
            self._append_request_event_locked(
                request_id=request_id,
                kind="request_updated" if existing_request else "request_created",
                detail=(
                    "Request updated with another finalized speech chunk."
                    if existing_request
                    else (
                        f"Request created from targeted speech for {target_agent_label or target_agent_name}."
                        if explicit_target
                        else "Request created from finalized speech."
                    )
                ),
                source_line_ids=self._request_source_line_ids_locked(request_id),
                agent_name=target_agent_name if explicit_target else None,
                agent_label=target_agent_label if explicit_target else None,
            )
        else:
            updated_status = utterance.status if utterance.status != "failed" else "pending"
            utterance = UtteranceState(
                source_line_id=utterance.source_line_id,
                text=clean_text,
                status=updated_status,
                kind=utterance.kind,
                request_id=utterance.request_id,
                created_seq=utterance.created_seq,
                updated_seq=self._seq,
                agent_name=utterance.agent_name,
                agent_label=utterance.agent_label,
                error=None if utterance.status == "failed" else utterance.error,
            )
            self._utterances[line_id] = utterance
            if isinstance(utterance.request_id, int):
                self._sync_request_from_utterances_locked(utterance.request_id)
                self._append_request_event_locked(
                    request_id=utterance.request_id,
                    kind="request_updated",
                    detail="Request updated with another finalized speech chunk.",
                    source_line_ids=self._request_source_line_ids_locked(utterance.request_id),
                )
        return {"type": "utterance_updated", "utterance": utterance.to_dict(), "running": self._running}

    def _snapshot_locked(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "input_level": self._input_level,
            "lines": [self._lines[line_id].to_dict() for line_id in self._ordered_ids],
            "events": [self._events[event_id].to_dict() for event_id in self._ordered_event_ids],
            "utterances": [self._utterances[source_line_id].to_dict() for source_line_id in self._ordered_utterance_ids],
            "requests": [self._requests[request_id].to_dict() for request_id in self._ordered_request_ids],
            "agent_statuses": [agent.to_dict() for agent in sorted(self._agent_statuses.values(), key=lambda item: item.updated_seq)],
            "request_events": [self._request_events[event_id].to_dict() for event_id in self._ordered_request_event_ids],
            "last_event": self._last_event,
        }

    def _rebuild_requests_locked(self) -> None:
        self._requests.clear()
        self._ordered_request_ids.clear()
        seen: set[int] = set()
        for source_line_id in self._ordered_utterance_ids:
            utterance = self._utterances[source_line_id]
            if utterance.kind != "message" or not isinstance(utterance.request_id, int):
                continue
            if utterance.request_id in seen:
                continue
            seen.add(utterance.request_id)
            self._sync_request_from_utterances_locked(utterance.request_id)

    def _next_open_request_id_locked(self) -> int:
        for source_line_id in reversed(self._ordered_utterance_ids):
            utterance = self._utterances[source_line_id]
            if utterance.kind == "message" and utterance.status == "pending" and isinstance(utterance.request_id, int):
                return utterance.request_id
        return self._next_request_id_locked()

    def _next_request_id_locked(self) -> int:
        self._next_request_id += 1
        return self._next_request_id

    def _request_source_line_ids_locked(self, request_id: int) -> list[int]:
        return [
            source_line_id
            for source_line_id in self._ordered_utterance_ids
            if self._utterances[source_line_id].kind == "message" and self._utterances[source_line_id].request_id == request_id
        ]

    def _sync_request_from_utterances_locked(self, request_id: int) -> None:
        source_line_ids = self._request_source_line_ids_locked(request_id)
        if not source_line_ids:
            return
        utterances = [self._utterances[source_line_id] for source_line_id in source_line_ids]
        text = " ".join(utterance.text.strip() for utterance in utterances if utterance.text.strip()).strip()
        existing = self._requests.get(request_id)
        request = RequestState(
            request_id=request_id,
            text=text,
            status=utterances[-1].status,
            created_seq=existing.created_seq if existing is not None else utterances[0].created_seq,
            updated_seq=self._seq,
            source_line_ids=list(source_line_ids),
            parent_request_id=existing.parent_request_id if existing is not None else None,
            origin=existing.origin if existing is not None else "speech",
            target_agent_name=existing.target_agent_name if existing is not None else None,
            target_agent_label=existing.target_agent_label if existing is not None else None,
            agent_name=utterances[-1].agent_name if utterances[-1].agent_name is not None else (existing.agent_name if existing is not None else None),
            agent_label=utterances[-1].agent_label if utterances[-1].agent_label is not None else (existing.agent_label if existing is not None else None),
            error=utterances[-1].error if utterances[-1].error is not None else (existing.error if existing is not None else None),
        )
        self._requests[request_id] = request
        if request_id not in self._ordered_request_ids:
            self._ordered_request_ids.append(request_id)

    def _parse_targeted_text_locked(self, text: str) -> tuple[str, str | None, str | None, bool]:
        stripped = text.strip()
        if not stripped:
            return "", None, None, False
        for alias, agent_name, agent_label in self._known_agent_targets_locked():
            pattern = rf"^\s*{re.escape(alias)}(?:\s*[,:\-]\s*|\s+)(?P<rest>.+)$"
            match = re.match(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            rest = match.group("rest").strip()
            if not rest:
                continue
            return rest, agent_name, agent_label, True
        return stripped, None, None, False

    def _known_agent_targets_locked(self) -> list[tuple[str, str, str]]:
        known: dict[str, tuple[str, str]] = {}
        for slot in self._configured_agent_slots:
            target_agent_name = slot.target_agent_name.strip().lower()
            label = slot.label.strip() or target_agent_name
            if not target_agent_name:
                continue
            for alias in slot.aliases:
                normalized_alias = alias.strip().lower()
                if normalized_alias:
                    known.setdefault(normalized_alias, (target_agent_name, label))
            spoken_slot_alias = label.strip().lower()
            if spoken_slot_alias:
                known.setdefault(spoken_slot_alias, (target_agent_name, label))
            if target_agent_name:
                known.setdefault(target_agent_name, (target_agent_name, label))
        for agent_state in self._agent_statuses.values():
            normalized_name = agent_state.name.strip().lower()
            if not normalized_name:
                continue
            label = (agent_state.label or agent_state.name).strip() or agent_state.name
            label_lower = label.lower()
            known.setdefault(normalized_name, (normalized_name, label))
            known.setdefault(label_lower, (normalized_name, label))
            if " " in label_lower:
                known.setdefault(label_lower.replace(" ", ""), (normalized_name, label))
                known.setdefault(f"agent {label_lower}", (normalized_name, label))
            known.setdefault(f"agent {normalized_name}", (normalized_name, label))
        return [
            (alias, agent_name, agent_label)
            for alias, (agent_name, agent_label) in sorted(known.items(), key=lambda item: len(item[0]), reverse=True)
        ]

    def _append_request_event_locked(
        self,
        *,
        request_id: int,
        kind: str,
        detail: str,
        source_line_ids: list[int],
        parent_request_id: int | None = None,
        agent_name: str | None = None,
        agent_label: str | None = None,
    ) -> None:
        self._next_event_id += 1
        event = RequestEvent(
            event_id=self._next_event_id,
            request_id=request_id,
            kind=kind,
            detail=detail,
            created_seq=self._seq,
            source_line_ids=list(source_line_ids),
            parent_request_id=parent_request_id,
            agent_name=agent_name,
            agent_label=agent_label,
        )
        self._request_events[event.event_id] = event
        self._ordered_request_event_ids.append(event.event_id)

    def _request_payload_for_line_locked(self, line_id: int) -> dict[str, Any] | None:
        utterance = self._utterances.get(line_id)
        if utterance is None or not isinstance(utterance.request_id, int):
            return None
        request = self._requests.get(utterance.request_id)
        if request is None:
            return None
        return {"type": "request_updated", "request": request.to_dict(), "running": self._running}
