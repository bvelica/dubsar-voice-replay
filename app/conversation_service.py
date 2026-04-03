from __future__ import annotations

from app.response_writer import ResponseWriter
from app.transcript_store import TranscriptStore


class ConversationService:
    def __init__(
        self,
        *,
        store: TranscriptStore,
        response_writer: ResponseWriter,
    ) -> None:
        self._store = store
        self._response_writer = response_writer

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

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

    async def queue_draft(self, draft_id: int) -> dict[str, object]:
        request = self._request_by_id(draft_id)
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
        self._store.update_request(request_id=draft_id, status="queued", error=None)
        self._store.append_request_event(
            request_id=draft_id,
            kind="request_queued",
            detail="Request queued for external agents.",
            source_line_ids=list(request.get("source_line_ids", [])),
            parent_request_id=request.get("parent_request_id"),
        )
        return {"queued": True, "request": self._request_by_id(draft_id)}

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
            status="queued",
        )
        self._store.append_request_event(
            request_id=request_id,
            kind="subrequest_queued",
            detail=f"Delegated to {target_agent_label or target_agent_name}.",
            source_line_ids=list(parent.get("source_line_ids", [])),
            parent_request_id=parent.get("parent_request_id"),
            agent_name=target_agent_name,
            agent_label=target_agent_label or target_agent_name,
        )
        return {"delegated": True, "request": child}

    async def claim_draft(self, draft_id: int, *, agent_name: str, agent_label: str | None = None) -> dict[str, object]:
        request = self._request_by_id(draft_id)
        if not request:
            return {"claimed": False, "reason": "Request not found"}
        if request.get("status") not in {"queued", "claimed"}:
            return {"claimed": False, "reason": "Request is not claimable"}
        normalized_agent_name = agent_name.strip()
        target_agent_name = request.get("target_agent_name")
        if target_agent_name and normalized_agent_name != target_agent_name:
            return {"claimed": False, "reason": f"Request is delegated to {request.get('target_agent_label') or target_agent_name}"}
        existing_agent_name = request.get("agent_name")
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
            request_id=draft_id,
            status="claimed",
            agent_name=normalized_agent_name,
            agent_label=agent_label or normalized_agent_name,
            error=None,
        )
        self._store.append_request_event(
            request_id=draft_id,
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
            detail=f"Claimed request {draft_id}",
        )
        return {"claimed": True, "request": self._request_by_id(draft_id)}

    async def complete_draft(
        self,
        draft_id: int,
        *,
        agent_name: str,
        text: str,
        agent_label: str | None = None,
    ) -> dict[str, object]:
        request = self._request_by_id(draft_id)
        if not request:
            return {"completed": False, "reason": "Request not found"}
        clean_text = text.strip()
        if not clean_text:
            return {"completed": False, "reason": "Reply text is empty"}
        latest_source_line_id = self._latest_source_line_id(list(request.get("source_line_ids", [])))
        for source_line_id in request.get("source_line_ids", []):
            self._store.update_utterance(
                source_line_id=source_line_id,
                status="completed",
                agent_name=agent_name,
                agent_label=agent_label or agent_name,
                error=None,
            )
        self._store.update_request(
            request_id=draft_id,
            status="completed",
            agent_name=agent_name,
            agent_label=agent_label or agent_name,
            error=None,
        )
        self._store.append_request_event(
            request_id=draft_id,
            kind="agent_completed",
            detail=f"{agent_label or agent_name} completed the request.",
            source_line_ids=list(request.get("source_line_ids", [])),
            parent_request_id=request.get("parent_request_id"),
            agent_name=agent_name,
            agent_label=agent_label or agent_name,
        )
        self._store.set_agent_status(
            name=agent_name,
            label=agent_label,
            status="ready",
            detail=f"Completed request {draft_id}",
        )
        event = self._response_writer.write_assistant_message(
            text=clean_text,
            source_line_id=latest_source_line_id,
            agent_name=agent_label or agent_name,
        )
        return {"completed": True, "request": self._request_by_id(draft_id), "reply_event": event}

    async def fail_draft(
        self,
        draft_id: int,
        *,
        agent_name: str,
        error: str,
        agent_label: str | None = None,
    ) -> dict[str, object]:
        request = self._request_by_id(draft_id)
        if not request:
            return {"failed": False, "reason": "Request not found"}
        clean_error = error.strip()
        if not clean_error:
            return {"failed": False, "reason": "Error text is empty"}
        latest_source_line_id = self._latest_source_line_id(list(request.get("source_line_ids", [])))
        for source_line_id in request.get("source_line_ids", []):
            self._store.update_utterance(
                source_line_id=source_line_id,
                status="failed",
                agent_name=agent_name,
                agent_label=agent_label or agent_name,
                error=clean_error,
            )
        self._store.update_request(
            request_id=draft_id,
            status="failed",
            agent_name=agent_name,
            agent_label=agent_label or agent_name,
            error=clean_error,
        )
        self._store.append_request_event(
            request_id=draft_id,
            kind="agent_failed",
            detail=f"{agent_label or agent_name} failed the request: {clean_error}",
            source_line_ids=list(request.get("source_line_ids", [])),
            parent_request_id=request.get("parent_request_id"),
            agent_name=agent_name,
            agent_label=agent_label or agent_name,
        )
        self._store.set_agent_status(
            name=agent_name,
            label=agent_label,
            status="error",
            detail=f"Failed request {draft_id}",
        )
        notice = self._response_writer.write_system_notice(
            text=clean_error,
            source_line_id=latest_source_line_id,
            agent_name=agent_label or agent_name,
        )
        return {"failed": True, "request": self._request_by_id(draft_id), "notice": notice}

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
