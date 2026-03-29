from __future__ import annotations

import asyncio
import contextlib
import logging
import re

from app.agent_router import AgentRouter
from app.response_writer import ResponseWriter
from app.transcript_store import TranscriptStore


logger = logging.getLogger(__name__)


class ConversationService:
    def __init__(
        self,
        *,
        store: TranscriptStore,
        router: AgentRouter,
        response_writer: ResponseWriter,
        history_events: int,
        auto_submit: bool,
    ) -> None:
        self._store = store
        self._router = router
        self._response_writer = response_writer
        self._history_events = history_events
        self._auto_submit = auto_submit
        self._processed_line_ids: set[int] = set()
        self._queue: asyncio.Queue[dict[str, object]] | None = None
        self._task: asyncio.Task[None] | None = None
        self._inflight_requests = 0

    async def start(self) -> None:
        if self._task is not None:
            return
        self._queue = await self._store.subscribe()
        self._task = asyncio.create_task(self._run(), name="conversation-service")

    async def stop(self) -> None:
        task = self._task
        queue = self._queue
        self._task = None
        self._queue = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if queue is not None:
            self._store.unsubscribe(queue)

    async def _run(self) -> None:
        assert self._queue is not None
        while True:
            payload = await self._queue.get()
            await self._handle_payload(payload)

    async def _handle_payload(self, payload: dict[str, object]) -> None:
        if payload.get("type") != "conversation_event":
            return
        event = payload.get("event")
        if not isinstance(event, dict):
            return
        if event.get("role") != "user" or not event.get("is_final"):
            return

        source_line_id = event.get("source_line_id")
        if not isinstance(source_line_id, int) or source_line_id in self._processed_line_ids:
            return

        if not self._auto_submit:
            return

        await self._submit_event(event)

    async def send_latest(self) -> dict[str, object]:
        pending_events = self._pending_finalized_user_events()
        if pending_events:
            return await self._submit_events(pending_events)
        return {"sent": False, "reason": "No pending finalized transcript"}

    def status(self) -> dict[str, object]:
        return {"processing": self._inflight_requests > 0}

    async def _submit_event(self, event: dict[str, object]) -> dict[str, object]:
        return await self._submit_events([event])

    async def _submit_events(self, events: list[dict[str, object]]) -> dict[str, object]:
        source_line_ids = self._event_source_line_ids(events)
        if not source_line_ids:
            return {"sent": False, "reason": "Transcript event has no source line id"}
        if any(source_line_id in self._processed_line_ids for source_line_id in source_line_ids):
            return {"sent": False, "reason": "Transcript already submitted"}

        prompt = self._combine_event_text(events)
        if not prompt:
            return {"sent": False, "reason": "Transcript text is empty"}

        self._processed_line_ids.update(source_line_ids)
        latest_source_line_id = source_line_ids[-1]
        history = self._conversation_history(exclude_source_line_ids=set(source_line_ids))
        self._inflight_requests += 1
        try:
            reply = await self._router.generate_reply(
                user_text=prompt,
                conversation=history,
            )
            if reply.text:
                assistant_event = self._response_writer.write_assistant_reply(reply=reply, source_line_id=latest_source_line_id)
                return {"sent": True, "reply_event": assistant_event}
            return {"sent": False, "reason": "Provider returned an empty reply"}
        except Exception as exc:
            logger.exception("Assistant reply generation failed")
            notice = self._response_writer.write_system_notice(
                text=f"Reply generation failed: {exc}",
                source_line_id=latest_source_line_id,
            )
            return {"sent": False, "error": str(exc), "notice": notice}
        finally:
            self._inflight_requests = max(0, self._inflight_requests - 1)

    def _conversation_history(self, *, exclude_source_line_ids: set[int] | None = None) -> list[dict[str, str]]:
        snapshot = self._store.snapshot()
        history: list[dict[str, str]] = []
        for event in snapshot["events"][-self._history_events:]:
            if not event["text"].strip() or not event["is_final"]:
                continue
            if event["role"] not in {"user", "assistant"}:
                continue
            source_line_id = event.get("source_line_id")
            if exclude_source_line_ids and isinstance(source_line_id, int) and source_line_id in exclude_source_line_ids:
                continue
            history.append({"role": event["role"], "text": event["text"]})
        return history

    def _pending_finalized_user_events(self) -> list[dict[str, object]]:
        snapshot = self._store.snapshot()
        pending: list[dict[str, object]] = []
        for event in snapshot["events"]:
            source_line_id = event.get("source_line_id")
            if event.get("role") != "user" or not event.get("is_final"):
                continue
            if not isinstance(source_line_id, int) or source_line_id in self._processed_line_ids:
                continue
            pending.append(event)
        return pending

    def _event_source_line_ids(self, events: list[dict[str, object]]) -> list[int]:
        line_ids: list[int] = []
        for event in events:
            source_line_id = event.get("source_line_id")
            if isinstance(source_line_id, int):
                line_ids.append(source_line_id)
        return line_ids

    def _combine_event_text(self, events: list[dict[str, object]]) -> str:
        fragments = [str(event.get("text", "")).strip() for event in events]
        combined = " ".join(fragment for fragment in fragments if fragment)
        return re.sub(r"\s+", " ", combined).strip()
