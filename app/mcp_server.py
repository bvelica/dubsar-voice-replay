from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

from app.conversation_service import ConversationService
from app.moonshine_service import MoonshineService
from app.transcript_store import TranscriptStore

MCP_SERVER_NAME = "dubsar"
MCP_RESOURCES = [
    "dubsar://status",
    "dubsar://snapshot",
    "dubsar://latest-user-message",
    "dubsar://utterances",
    "dubsar://requests",
    "dubsar://queued-drafts",
    "dubsar://queued-requests",
    "dubsar://agent-statuses",
    "dubsar://request-events",
]
MCP_TOOLS = [
    "start_transcriber",
    "stop_transcriber",
    "clear_transcript",
    "set_agent_status",
    "queue_draft",
    "delegate_request",
    "claim_draft",
    "complete_draft",
    "fail_draft",
]


def create_mcp_server(*, store: TranscriptStore, moonshine: MoonshineService, conversation_service: ConversationService) -> FastMCP:
    mcp = FastMCP(MCP_SERVER_NAME)

    @mcp.resource("dubsar://status")
    def get_status() -> str:
        """Return the current microphone and transcriber status."""
        return _to_json(moonshine.status())

    @mcp.resource("dubsar://snapshot")
    def get_snapshot() -> str:
        """Return the current transcript, utterance, and agent snapshot."""
        return _to_json(store.snapshot())

    @mcp.resource("dubsar://latest-user-message")
    def get_latest_user_message() -> str:
        """Return the latest finalized user transcript line."""
        snapshot = store.snapshot()
        for event in reversed(snapshot["events"]):
            if event["role"] == "user" and event["is_final"] and event["text"].strip():
                return event["text"]
        return ""

    @mcp.resource("dubsar://utterances")
    def get_utterances() -> str:
        """Return the current utterance lifecycle snapshot."""
        snapshot = store.snapshot()
        return _to_json(snapshot["utterances"])

    @mcp.resource("dubsar://requests")
    def get_requests() -> str:
        """Return the current request snapshot grouped by request_id."""
        snapshot = store.snapshot()
        return _to_json(snapshot.get("requests", []))

    @mcp.resource("dubsar://queued-drafts")
    def get_queued_drafts() -> str:
        """Return the legacy queued-drafts view for compatibility."""
        snapshot = store.snapshot()
        drafts: dict[int, list[dict[str, Any]]] = {}
        for utterance in snapshot["utterances"]:
            if utterance["kind"] != "message":
                continue
            if utterance["status"] not in {"queued", "claimed"}:
                continue
            draft_id = utterance.get("draft_id")
            if not isinstance(draft_id, int):
                continue
            drafts.setdefault(draft_id, []).append(utterance)
        ordered = [
            {"draft_id": draft_id, "utterances": drafts[draft_id]}
            for draft_id in sorted(drafts.keys())
        ]
        return _to_json(ordered)

    @mcp.resource("dubsar://queued-requests")
    def get_queued_requests() -> str:
        """Return all requests currently queued or claimed for external agents."""
        snapshot = store.snapshot()
        ordered = [
            request
            for request in snapshot.get("requests", [])
            if request.get("status") in {"queued", "claimed"}
        ]
        return _to_json(ordered)

    @mcp.resource("dubsar://agent-statuses")
    def get_agent_statuses() -> str:
        """Return the latest reported statuses for MCP agents."""
        snapshot = store.snapshot()
        return _to_json(snapshot.get("agent_statuses", []))

    @mcp.resource("dubsar://request-events")
    def get_request_events() -> str:
        """Return the explicit request lifecycle event log."""
        snapshot = store.snapshot()
        return _to_json(snapshot.get("request_events", []))

    @mcp.tool
    def start_transcriber() -> dict[str, Any]:
        """Start Moonshine microphone capture."""
        moonshine.start()
        return moonshine.status()

    @mcp.tool
    def stop_transcriber() -> dict[str, Any]:
        """Stop Moonshine microphone capture."""
        moonshine.stop()
        return moonshine.status()

    @mcp.tool
    def clear_transcript() -> dict[str, Any]:
        """Clear the in-memory and persisted transcript timeline."""
        return store.clear()

    @mcp.tool
    def set_agent_status(agent_name: str, status: str, label: str | None = None, detail: str | None = None) -> dict[str, Any]:
        """Report the current status of an external MCP agent."""
        return store.set_agent_status(name=agent_name, status=status, label=label, detail=detail)

    @mcp.tool
    async def queue_draft(draft_id: int) -> dict[str, Any]:
        """Queue a specific request by legacy draft identifier."""
        return await conversation_service.queue_draft(draft_id)

    @mcp.tool
    async def delegate_request(
        request_id: int,
        target_agent_name: str,
        target_agent_label: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        """Create a queued child request for a specific target agent."""
        return await conversation_service.delegate_request(
            request_id,
            target_agent_name=target_agent_name,
            target_agent_label=target_agent_label,
            prompt=prompt,
        )

    @mcp.tool
    async def claim_draft(draft_id: int, agent_name: str, agent_label: str | None = None) -> dict[str, Any]:
        """Claim a queued request by legacy draft identifier."""
        return await conversation_service.claim_draft(draft_id, agent_name=agent_name, agent_label=agent_label)

    @mcp.tool
    async def complete_draft(draft_id: int, agent_name: str, text: str, agent_label: str | None = None) -> dict[str, Any]:
        """Complete a claimed request by appending an agent reply to the timeline."""
        return await conversation_service.complete_draft(
            draft_id,
            agent_name=agent_name,
            agent_label=agent_label,
            text=text,
        )

    @mcp.tool
    async def fail_draft(draft_id: int, agent_name: str, error: str, agent_label: str | None = None) -> dict[str, Any]:
        """Mark a request as failed for a specific external agent."""
        return await conversation_service.fail_draft(
            draft_id,
            agent_name=agent_name,
            agent_label=agent_label,
            error=error,
        )

    return mcp


def _to_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
