from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

from app.conversation_service import ConversationService
from app.moonshine_service import MoonshineService
from app.transcript_store import TranscriptStore

MCP_SERVER_NAME = "transcriptor"
MCP_RESOURCES = [
    "transcriptor://status",
    "transcriptor://snapshot",
    "transcriptor://latest-user-message",
    "transcriptor://utterances",
    "transcriptor://latest-pending-draft",
]
MCP_TOOLS = [
    "start_transcriber",
    "stop_transcriber",
    "clear_transcript",
    "append_assistant_message",
    "send_latest_draft",
    "send_draft_to_default",
    "route_latest_draft",
    "route_draft",
]


def create_mcp_server(*, store: TranscriptStore, moonshine: MoonshineService, conversation_service: ConversationService) -> FastMCP:
    mcp = FastMCP(MCP_SERVER_NAME)

    @mcp.resource("transcriptor://status")
    def get_status() -> str:
        """Return the current microphone and transcriber status."""
        return _to_json(moonshine.status())

    @mcp.resource("transcriptor://snapshot")
    def get_snapshot() -> str:
        """Return the current transcript and conversation snapshot."""
        return _to_json(store.snapshot())

    @mcp.resource("transcriptor://latest-user-message")
    def get_latest_user_message() -> str:
        """Return the latest finalized user transcript line."""
        snapshot = store.snapshot()
        for event in reversed(snapshot["events"]):
            if event["role"] == "user" and event["is_final"] and event["text"].strip():
                return event["text"]
        return ""

    @mcp.resource("transcriptor://utterances")
    def get_utterances() -> str:
        """Return the current utterance lifecycle snapshot."""
        snapshot = store.snapshot()
        return _to_json(snapshot["utterances"])

    @mcp.resource("transcriptor://latest-pending-draft")
    def get_latest_pending_draft() -> str:
        """Return the latest actionable draft as a list of utterance records."""
        snapshot = store.snapshot()
        drafts: dict[int, list[dict[str, Any]]] = {}
        for utterance in snapshot["utterances"]:
            if utterance["kind"] != "message":
                continue
            if utterance["status"] not in {"pending", "failed"} or not utterance["text"].strip():
                continue
            draft_id = utterance.get("draft_id")
            if not isinstance(draft_id, int):
                continue
            drafts.setdefault(draft_id, []).append(utterance)
        if not drafts:
            return _to_json([])
        latest_draft_id = max(drafts.keys())
        return _to_json(drafts[latest_draft_id])

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
    def append_assistant_message(text: str) -> dict[str, Any]:
        """Append an assistant message to the shared conversation timeline."""
        return store.append_event(
            role="assistant",
            kind="mcp_message",
            text=text,
            is_final=True,
            agent_name="MCP",
        )

    @mcp.tool
    async def send_latest_draft() -> dict[str, Any]:
        """Send the latest actionable draft through the default provider path."""
        return await conversation_service.send_latest()

    @mcp.tool
    async def send_draft_to_default(draft_id: int) -> dict[str, Any]:
        """Send a specific draft through the default provider path."""
        return await conversation_service.submit_draft(draft_id)

    @mcp.tool
    async def route_latest_draft(provider: str) -> dict[str, Any]:
        """Route the latest actionable draft to a specific provider."""
        return await conversation_service.send_latest(provider_override=provider)

    @mcp.tool
    async def route_draft(draft_id: int, provider: str) -> dict[str, Any]:
        """Route a specific draft to a specific provider."""
        return await conversation_service.submit_draft(draft_id, provider_override=provider)

    return mcp


def _to_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
