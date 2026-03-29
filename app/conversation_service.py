from __future__ import annotations

import asyncio
import contextlib
import logging

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
    ) -> None:
        self._store = store
        self._router = router
        self._response_writer = response_writer
        self._history_events = history_events
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
        if not isinstance(source_line_id, int):
            return

        command = self._router.parse_control(str(event.get("text", "")))
        if command is not None:
            await self._execute_control_command(source_line_id=source_line_id, provider_name=command.provider)
        return

    async def send_latest(self, *, provider_override: str | None = None) -> dict[str, object]:
        draft = self._latest_actionable_draft()
        if draft:
            draft_id = draft[-1].get("draft_id")
            if isinstance(draft_id, int):
                return await self.submit_draft(draft_id, provider_override=provider_override)
        return {"sent": False, "reason": "No pending finalized transcript"}

    async def submit_draft(self, draft_id: int, *, provider_override: str | None = None) -> dict[str, object]:
        draft = self._draft_by_id(draft_id)
        if not draft:
            return {"sent": False, "reason": "Draft not found"}
        return await self.submit_utterance(int(draft[-1]["source_line_id"]), provider_override=provider_override)

    def status(self) -> dict[str, object]:
        snapshot = self._store.snapshot()
        pending_count = len({
            utterance["draft_id"]
            for utterance in snapshot["utterances"]
            if utterance["status"] == "pending"
            and utterance.get("kind") != "command"
            and isinstance(utterance.get("draft_id"), int)
        })
        return {"processing": self._inflight_requests > 0, "pending_count": pending_count}

    async def submit_utterance(self, source_line_id: int, *, provider_override: str | None = None) -> dict[str, object]:
        draft = self._draft_for_source_line_id(source_line_id)
        if not draft:
            return {"sent": False, "reason": "Utterance not found"}
        if any(utterance.get("status") not in {"pending", "failed"} for utterance in draft):
            return {"sent": False, "reason": "Draft is not actionable"}
        if any(utterance.get("kind") == "command" for utterance in draft):
            return {"sent": False, "reason": "Command utterances are not sent to providers"}

        prompt = " ".join(
            str(utterance.get("text", "")).strip()
            for utterance in draft
            if str(utterance.get("text", "")).strip()
        ).strip()
        if not prompt:
            return {"sent": False, "reason": "Transcript text is empty"}
        source_line_ids = [int(utterance["source_line_id"]) for utterance in draft if isinstance(utterance.get("source_line_id"), int)]
        latest_source_line_id = source_line_ids[-1]

        try:
            if provider_override:
                routed, provider = self._router.route_to_provider(user_text=prompt, provider_name=provider_override)
            else:
                routed, provider = self._router.route(user_text=prompt)
        except Exception as exc:
            for current_source_line_id in source_line_ids:
                self._store.update_utterance(source_line_id=current_source_line_id, status="failed", error=str(exc))
            return {"sent": False, "error": str(exc)}

        for current_source_line_id in source_line_ids:
            self._store.update_utterance(
                source_line_id=current_source_line_id,
                status="routed",
                provider=routed.provider,
                provider_label=provider.label,
                error=None,
            )
            self._store.update_utterance(
                source_line_id=current_source_line_id,
                status="processing",
                provider=routed.provider,
                provider_label=provider.label,
                error=None,
            )
        history = self._conversation_history(exclude_source_line_ids=set(source_line_ids))
        self._inflight_requests += 1
        try:
            reply = await provider.generate_reply(
                prompt=routed.text,
                conversation=history,
            )
            if reply.text:
                assistant_event = self._response_writer.write_assistant_reply(reply=reply, source_line_id=latest_source_line_id)
                for current_source_line_id in source_line_ids:
                    self._store.update_utterance(
                        source_line_id=current_source_line_id,
                        status="completed",
                        provider=reply.provider,
                        provider_label=reply.provider_label,
                        error=None,
                    )
                return {"sent": True, "draft": self._draft_for_source_line_id(latest_source_line_id), "reply_event": assistant_event}
            for current_source_line_id in source_line_ids:
                self._store.update_utterance(
                    source_line_id=current_source_line_id,
                    status="failed",
                    provider=routed.provider,
                    provider_label=provider.label,
                    error="Provider returned an empty reply",
                )
            return {"sent": False, "reason": "Provider returned an empty reply"}
        except Exception as exc:
            logger.exception("Assistant reply generation failed")
            for current_source_line_id in source_line_ids:
                self._store.update_utterance(
                    source_line_id=current_source_line_id,
                    status="failed",
                    provider=routed.provider,
                    provider_label=provider.label,
                    error=str(exc),
                )
            notice = self._response_writer.write_system_notice(
                text=f"Reply generation failed: {exc}",
                source_line_id=latest_source_line_id,
            )
            return {"sent": False, "error": str(exc), "notice": notice}
        finally:
            self._inflight_requests = max(0, self._inflight_requests - 1)

    async def _execute_control_command(self, *, source_line_id: int, provider_name: str) -> None:
        self._store.update_utterance(
            source_line_id=source_line_id,
            status="completed",
            provider="command",
            provider_label="Command",
            kind="command",
            draft_id=None,
            error=None,
        )
        target = self._latest_actionable_draft(exclude_source_line_ids={source_line_id})
        if not target:
            self._store.update_utterance(
                source_line_id=source_line_id,
                status="failed",
                provider="command",
                provider_label="Command",
                kind="command",
                draft_id=None,
                error="No pending utterance available for command routing",
            )
            return
        target_draft_id = target[-1].get("draft_id")
        if isinstance(target_draft_id, int):
            await self.submit_draft(target_draft_id, provider_override=provider_name)

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

    def _latest_actionable_draft(self, *, exclude_source_line_ids: set[int] | None = None) -> list[dict[str, object]]:
        snapshot = self._store.snapshot()
        drafts: dict[int, list[dict[str, object]]] = {}
        for utterance in snapshot["utterances"]:
            if exclude_source_line_ids and utterance["source_line_id"] in exclude_source_line_ids:
                continue
            if utterance.get("kind") != "message":
                continue
            if utterance["status"] not in {"pending", "failed"} or not utterance["text"].strip():
                continue
            draft_id = utterance.get("draft_id")
            if not isinstance(draft_id, int):
                continue
            drafts.setdefault(draft_id, []).append(utterance)
        if not drafts:
            return []
        latest_draft_id = max(drafts.keys())
        return drafts[latest_draft_id]

    def _draft_for_source_line_id(self, source_line_id: int) -> list[dict[str, object]]:
        utterance = self._utterance_by_source_line_id(source_line_id)
        if utterance is None:
            return []
        draft_id = utterance.get("draft_id")
        if not isinstance(draft_id, int):
            return [utterance]
        return self._draft_by_id(draft_id)

    def _draft_by_id(self, draft_id: int) -> list[dict[str, object]]:
        snapshot = self._store.snapshot()
        return [
            current
            for current in snapshot["utterances"]
            if current.get("kind") == "message" and current.get("draft_id") == draft_id
        ]

    def _utterance_by_source_line_id(self, source_line_id: int) -> dict[str, object] | None:
        snapshot = self._store.snapshot()
        for utterance in snapshot["utterances"]:
            if utterance["source_line_id"] == source_line_id:
                return utterance
        return None
