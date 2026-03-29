from __future__ import annotations

from app.agents.base import AgentReply, ProviderAdapter
from app.commands import CommandResolver


class AgentRouter:
    def __init__(self, *, command_resolver: CommandResolver, providers: dict[str, ProviderAdapter]) -> None:
        self._command_resolver = command_resolver
        self._providers = providers

    async def generate_reply(self, *, user_text: str, conversation: list[dict[str, str]]) -> AgentReply:
        routed = self._command_resolver.resolve(user_text)
        if not routed.handled:
            raise ValueError("No prompt text was provided.")

        provider = self._providers.get(routed.provider)
        if provider is None:
            raise ValueError(f"Provider '{routed.provider}' is not configured.")

        return await provider.generate_reply(prompt=routed.text, conversation=conversation)
