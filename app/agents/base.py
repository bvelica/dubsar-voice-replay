from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AgentReply:
    provider: str
    provider_label: str
    model: str
    text: str


class ProviderAdapter(Protocol):
    name: str
    label: str

    async def generate_reply(self, *, prompt: str, conversation: list[dict[str, str]]) -> AgentReply:
        ...
