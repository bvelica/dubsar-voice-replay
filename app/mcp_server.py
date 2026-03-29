from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

from app.moonshine_service import MoonshineService
from app.transcript_store import TranscriptStore


def create_mcp_server(*, store: TranscriptStore, moonshine: MoonshineService) -> FastMCP:
    mcp = FastMCP("transcriptor")

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

    return mcp


def _to_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
