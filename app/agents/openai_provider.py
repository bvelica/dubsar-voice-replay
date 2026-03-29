from __future__ import annotations

import asyncio
from typing import Any

from openai import OpenAI

from app.agents.base import AgentReply


class OpenAIProvider:
    name = "openai"
    label = "OpenAI"

    def __init__(self, *, api_key: str, model: str, system_prompt: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._system_prompt = system_prompt

    async def generate_reply(self, *, prompt: str, conversation: list[dict[str, str]]) -> AgentReply:
        response = await asyncio.to_thread(
            self._client.responses.create,
            model=self._model,
            instructions=self._system_prompt,
            input=self._build_input(prompt=prompt, conversation=conversation),
        )
        return AgentReply(
            provider=self.name,
            provider_label=self.label,
            model=self._model,
            text=self._extract_output_text(response),
        )

    def _build_input(self, *, prompt: str, conversation: list[dict[str, str]]) -> str:
        transcript_lines: list[str] = []
        for entry in conversation:
            speaker = "User" if entry["role"] == "user" else "Assistant"
            transcript_lines.append(f"{speaker}: {entry['text']}")
        if not transcript_lines or transcript_lines[-1] != f"User: {prompt}":
            transcript_lines.append(f"User: {prompt}")
        transcript_lines.append("Assistant:")
        return "\n".join(transcript_lines)

    def _extract_output_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", "") or ""
        if output_text.strip():
            return output_text.strip()

        fragments: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    fragments.append(str(text))
        return "\n".join(fragment.strip() for fragment in fragments if fragment.strip())
