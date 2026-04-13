from __future__ import annotations

import asyncio
from time import monotonic

from app.response_writer import ResponseWriter
from app.transcript_store import TranscriptStore


class ConversationService:
    def __init__(
        self,
        *,
        store: TranscriptStore,
        response_writer: ResponseWriter,
        voice_request_idle_seconds: float,
    ) -> None:
        self._store = store
        self._response_writer = response_writer
        self._voice_request_idle_seconds = voice_request_idle_seconds
        self._auto_queue_task: asyncio.Task[None] | None = None
        self._request_activity: dict[int, tuple[int, float]] = {}

    async def start(self) -> None:
        if self._auto_queue_task is None:
            self._auto_queue_task = asyncio.create_task(self._auto_queue_loop())

    async def stop(self) -> None:
        if self._auto_queue_task is None:
            return
        self._auto_queue_task.cancel()
        try:
            await self._auto_queue_task
        except asyncio.CancelledError:
            pass
        self._auto_queue_task = None

    def status(self) -> dict[str, object]:
        snapshot = self._store.snapshot()
        pending_count = len({
            request["request_id"]
            for request in snapshot["requests"]
            if request["status"] == "pending"
        })
        queued_count = len({
            request["request_id"]
            for request in snapshot["requests"]
            if request["status"] == "queued"
        })
        claimed_count = len({
            request["request_id"]
            for request in snapshot["requests"]
            if request["status"] == "claimed"
        })
        return {
            "processing": claimed_count > 0,
            "pending_count": pending_count,
            "queued_count": queued_count,
            "claimed_count": claimed_count,
        }

    async def queue_request(self, request_id: int) -> dict[str, object]:
        request = self._request_by_id(request_id)
        if not request:
            return {"queued": False, "reason": "Request not found"}
        if request.get("status") not in {"pending", "failed"}:
            return {"queued": False, "reason": "Request is not queueable"}
        for source_line_id in request.get("source_line_ids", []):
            self._store.update_utterance(
                source_line_id=source_line_id,
                status="queued",
                agent_name=None,
                agent_label=None,
                error=None,
            )
        self._store.update_request(request_id=request_id, status="queued", error=None)
        target_label = request.get("target_agent_label") or request.get("target_agent_name")
        self._store.append_request_event(
            request_id=request_id,
            kind="request_queued",
            detail=(
                f"Request queued for {target_label}."
                if target_label
                else "Request queued for external agents."
            ),
            source_line_ids=list(request.get("source_line_ids", [])),
            parent_request_id=request.get("parent_request_id"),
            agent_name=request.get("target_agent_name"),
            agent_label=request.get("target_agent_label"),
        )
        self._request_activity.pop(request_id, None)
        return {"queued": True, "request": self._request_by_id(request_id)}

    async def queue_draft(self, draft_id: int) -> dict[str, object]:
        return await self.queue_request(draft_id)

    async def delegate_request(
        self,
        request_id: int,
        *,
        target_agent_name: str,
        target_agent_label: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, object]:
        parent = self._request_by_id(request_id)
        if not parent:
            return {"delegated": False, "reason": "Request not found"}
        child = self._store.create_request(
            text=prompt or str(parent.get("text", "")),
            parent_request_id=request_id,
            target_agent_name=target_agent_name,
            target_agent_label=target_agent_label or target_agent_name,
            origin="delegation",
            status="pending",
        )
        self._store.append_request_event(
            request_id=request_id,
            kind="subrequest_created",
            detail=f"Follow-up request created for {target_agent_label or target_agent_name}.",
            source_line_ids=list(parent.get("source_line_ids", [])),
            parent_request_id=parent.get("parent_request_id"),
            agent_name=target_agent_name,
            agent_label=target_agent_label or target_agent_name,
        )
        queued = await self.queue_request(int(child["request_id"]))
        return {"delegated": bool(queued.get("queued")), "request": queued.get("request", child)}

    async def claim_request(self, request_id: int, *, agent_name: str, agent_label: str | None = None) -> dict[str, object]:
        request = self._request_by_id(request_id)
        if not request:
            return {"claimed": False, "reason": "Request not found"}
        if request.get("status") not in {"queued", "claimed"}:
            return {"claimed": False, "reason": "Request is not claimable"}
        normalized_agent_name = agent_name.strip().lower()
        target_agent_name = str(request.get("target_agent_name") or "").strip().lower()
        if target_agent_name and normalized_agent_name != target_agent_name:
            return {"claimed": False, "reason": f"Request is routed to {request.get('target_agent_label') or request.get('target_agent_name')}"}
        existing_agent_name = str(request.get("agent_name") or "").strip().lower()
        if request.get("status") == "claimed" and existing_agent_name and existing_agent_name != normalized_agent_name:
            return {"claimed": False, "reason": "Request is already claimed by another agent"}

        for source_line_id in request.get("source_line_ids", []):
            self._store.update_utterance(
                source_line_id=source_line_id,
                status="claimed",
                agent_name=normalized_agent_name,
                agent_label=agent_label or normalized_agent_name,
                error=None,
            )
        self._store.update_request(
            request_id=request_id,
            status="claimed",
            agent_name=normalized_agent_name,
            agent_label=agent_label or normalized_agent_name,
            error=None,
        )
        self._store.append_request_event(
            request_id=request_id,
            kind="agent_claimed",
            detail=f"{agent_label or normalized_agent_name} claimed the request.",
            source_line_ids=list(request.get("source_line_ids", [])),
            parent_request_id=request.get("parent_request_id"),
            agent_name=normalized_agent_name,
            agent_label=agent_label or normalized_agent_name,
        )
        self._store.set_agent_status(
            name=normalized_agent_name,
            label=agent_label,
            status="working",
            detail=f"Claimed request {request_id}",
        )
        return {"claimed": True, "request": self._request_by_id(request_id)}

    async def claim_draft(self, draft_id: int, *, agent_name: str, agent_label: str | None = None) -> dict[str, object]:
        return await self.claim_request(draft_id, agent_name=agent_name, agent_label=agent_label)

    async def complete_request(
        self,
        request_id: int,
        *,
        agent_name: str,
        text: str,
        agent_label: str | None = None,
    ) -> dict[str, object]:
        request = self._request_by_id(request_id)
        if not request:
            return {"completed": False, "reason": "Request not found"}
        normalized_agent_name = agent_name.strip().lower()
        if request.get("status") != "claimed":
            return {"completed": False, "reason": "Request is not claimed"}
        if str(request.get("agent_name") or "").strip().lower() != normalized_agent_name:
            return {"completed": False, "reason": "Request is claimed by another agent"}
        clean_text = text.strip()
        if not clean_text:
            return {"completed": False, "reason": "Reply text is empty"}
        latest_source_line_id = self._latest_source_line_id(list(request.get("source_line_ids", [])))
        for source_line_id in request.get("source_line_ids", []):
            self._store.update_utterance(
                source_line_id=source_line_id,
                status="completed",
                agent_name=normalized_agent_name,
                agent_label=agent_label or normalized_agent_name,
                error=None,
            )
        self._store.update_request(
            request_id=request_id,
            status="completed",
            agent_name=normalized_agent_name,
            agent_label=agent_label or normalized_agent_name,
            error=None,
        )
        self._store.append_request_event(
            request_id=request_id,
            kind="agent_completed",
            detail=f"{agent_label or normalized_agent_name} completed the request.",
            source_line_ids=list(request.get("source_line_ids", [])),
            parent_request_id=request.get("parent_request_id"),
            agent_name=normalized_agent_name,
            agent_label=agent_label or normalized_agent_name,
        )
        self._store.set_agent_status(
            name=normalized_agent_name,
            label=agent_label,
            status="ready",
            detail=f"Completed request {request_id}",
        )
        event = self._response_writer.write_assistant_message(
            text=clean_text,
            source_line_id=latest_source_line_id,
            agent_name=agent_label or normalized_agent_name,
        )
        return {"completed": True, "request": self._request_by_id(request_id), "reply_event": event}

    async def complete_draft(
        self,
        draft_id: int,
        *,
        agent_name: str,
        text: str,
        agent_label: str | None = None,
    ) -> dict[str, object]:
        return await self.complete_request(
            draft_id,
            agent_name=agent_name,
            text=text,
            agent_label=agent_label,
        )

    async def fail_request(
        self,
        request_id: int,
        *,
        agent_name: str,
        error: str,
        agent_label: str | None = None,
    ) -> dict[str, object]:
        request = self._request_by_id(request_id)
        if not request:
            return {"failed": False, "reason": "Request not found"}
        normalized_agent_name = agent_name.strip().lower()
        if request.get("status") != "claimed":
            return {"failed": False, "reason": "Request is not claimed"}
        if str(request.get("agent_name") or "").strip().lower() != normalized_agent_name:
            return {"failed": False, "reason": "Request is claimed by another agent"}
        clean_error = error.strip()
        if not clean_error:
            return {"failed": False, "reason": "Error text is empty"}
        latest_source_line_id = self._latest_source_line_id(list(request.get("source_line_ids", [])))
        for source_line_id in request.get("source_line_ids", []):
            self._store.update_utterance(
                source_line_id=source_line_id,
                status="failed",
                agent_name=normalized_agent_name,
                agent_label=agent_label or normalized_agent_name,
                error=clean_error,
            )
        self._store.update_request(
            request_id=request_id,
            status="failed",
            agent_name=normalized_agent_name,
            agent_label=agent_label or normalized_agent_name,
            error=clean_error,
        )
        self._store.append_request_event(
            request_id=request_id,
            kind="agent_failed",
            detail=f"{agent_label or normalized_agent_name} failed the request: {clean_error}",
            source_line_ids=list(request.get("source_line_ids", [])),
            parent_request_id=request.get("parent_request_id"),
            agent_name=normalized_agent_name,
            agent_label=agent_label or normalized_agent_name,
        )
        self._store.set_agent_status(
            name=normalized_agent_name,
            label=agent_label,
            status="error",
            detail=f"Failed request {request_id}",
        )
        notice = self._response_writer.write_system_notice(
            text=clean_error,
            source_line_id=latest_source_line_id,
            agent_name=agent_label or normalized_agent_name,
        )
        return {"failed": True, "request": self._request_by_id(request_id), "notice": notice}

    async def fail_draft(
        self,
        draft_id: int,
        *,
        agent_name: str,
        error: str,
        agent_label: str | None = None,
    ) -> dict[str, object]:
        return await self.fail_request(
            draft_id,
            agent_name=agent_name,
            error=error,
            agent_label=agent_label,
        )

    async def _auto_queue_loop(self) -> None:
        while True:
            await asyncio.sleep(0.25)
            await self._auto_queue_targeted_requests()

    async def _auto_queue_targeted_requests(self) -> None:
        snapshot = self._store.snapshot()
        now = monotonic()
        active_request_ids: set[int] = set()
        queue_candidates: list[int] = []

        for request in snapshot.get("requests", []):
            request_id = request.get("request_id")
            if not isinstance(request_id, int):
                continue
            if request.get("status") != "pending":
                continue
            if not str(request.get("target_agent_name") or "").strip():
                continue
            active_request_ids.add(request_id)
            updated_seq = int(request.get("updated_seq") or 0)
            current = self._request_activity.get(request_id)
            if current is None or current[0] != updated_seq:
                self._request_activity[request_id] = (updated_seq, now)
                continue
            if now - current[1] >= self._voice_request_idle_seconds:
                queue_candidates.append(request_id)

        self._request_activity = {
            request_id: value
            for request_id, value in self._request_activity.items()
            if request_id in active_request_ids
        }

        for request_id in queue_candidates:
            await self.queue_request(request_id)

    def _request_by_id(self, request_id: int) -> dict[str, object] | None:
        snapshot = self._store.snapshot()
        for request in snapshot["requests"]:
            if request.get("request_id") == request_id:
                return request
        return None

    def _latest_source_line_id(self, source_line_ids: list[int]) -> int | None:
        if not source_line_ids:
            return None
        return source_line_ids[-1]
