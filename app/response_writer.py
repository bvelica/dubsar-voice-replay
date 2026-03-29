from __future__ import annotations

from app.agents.base import AgentReply
from app.transcript_store import TranscriptStore


class ResponseWriter:
    def __init__(self, store: TranscriptStore) -> None:
        self._store = store

    def write_assistant_reply(self, *, reply: AgentReply, source_line_id: int | None) -> dict[str, object]:
        return self._store.append_event(
            role="assistant",
            kind="assistant_reply",
            text=reply.text,
            is_final=True,
            source_line_id=source_line_id,
            agent_name=reply.provider_label,
        )

    def write_system_notice(self, *, text: str, source_line_id: int | None, agent_name: str | None = None) -> dict[str, object]:
        return self._store.append_event(
            role="assistant",
            kind="system_notice",
            text=text,
            is_final=True,
            source_line_id=source_line_id,
            agent_name=agent_name,
        )
