from __future__ import annotations

from app.agents.base import AgentReply, ProviderAdapter
from app.commands import CommandResolver, ControlCommand, RoutedPrompt


class AgentRouter:
    def __init__(self, *, command_resolver: CommandResolver, providers: dict[str, ProviderAdapter]) -> None:
        self._command_resolver = command_resolver
        self._providers = providers

    def route(self, *, user_text: str) -> tuple[RoutedPrompt, ProviderAdapter]:
        routed = self._command_resolver.resolve(user_text)
        if not routed.handled:
            raise ValueError("No prompt text was provided.")

        provider = self._providers.get(routed.provider)
        if provider is None:
            raise ValueError(f"Provider '{routed.provider}' is not configured.")
        return routed, provider

    def route_to_provider(self, *, user_text: str, provider_name: str) -> tuple[RoutedPrompt, ProviderAdapter]:
        routed = self._command_resolver.resolve(user_text, provider_override=provider_name)
        if not routed.handled:
            raise ValueError("No prompt text was provided.")

        provider = self._providers.get(routed.provider)
        if provider is None:
            raise ValueError(f"Provider '{routed.provider}' is not configured.")
        return routed, provider

    def parse_control(self, text: str) -> ControlCommand | None:
        return self._command_resolver.parse_control(text)

    async def generate_reply(self, *, user_text: str, conversation: list[dict[str, str]]) -> AgentReply:
        routed, provider = self.route(user_text=user_text)
        return await provider.generate_reply(prompt=routed.text, conversation=conversation)
