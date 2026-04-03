from __future__ import annotations

from app.transcript_store import TranscriptStore


class ResponseWriter:
    def __init__(self, store: TranscriptStore) -> None:
        self._store = store

    def write_assistant_message(
        self,
        *,
        text: str,
        source_line_id: int | None,
        agent_name: str | None = None,
        kind: str = "assistant_reply",
    ) -> dict[str, object]:
        return self._store.append_event(
            role="assistant",
            kind=kind,
            text=text,
            is_final=True,
            source_line_id=source_line_id,
            agent_name=agent_name,
        )

    def write_system_notice(self, *, text: str, source_line_id: int | None, agent_name: str | None = None) -> dict[str, object]:
        return self.write_assistant_message(
            text=text,
            source_line_id=source_line_id,
            agent_name=agent_name,
            kind="system_notice",
        )
