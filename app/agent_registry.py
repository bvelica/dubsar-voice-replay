from __future__ import annotations

from dataclasses import dataclass

from app.agents.base import ProviderAdapter


@dataclass(frozen=True)
class AgentTarget:
    name: str
    label: str
    aliases: tuple[str, ...]


class AgentRegistry:
    def __init__(self, targets: list[AgentTarget], providers: dict[str, ProviderAdapter]) -> None:
        self._targets = {target.name: target for target in targets}
        self._providers = providers
        self._aliases: dict[str, str] = {}
        for target in targets:
            self._aliases[target.name] = target.name
            for alias in target.aliases:
                self._aliases[alias] = target.name

    def normalize(self, name: str | None) -> str | None:
        if not name:
            return None
        return self._aliases.get(name.strip().lower())

    def configured_providers(self) -> dict[str, ProviderAdapter]:
        return dict(self._providers)

    def configured_target_names(self) -> list[str]:
        return sorted(name for name in self._targets if name in self._providers)

    def known_target_names(self) -> list[str]:
        return sorted(self._targets.keys())

    def alias_map(self) -> dict[str, str]:
        return dict(self._aliases)

    def label_for(self, name: str) -> str:
        target = self._targets.get(name)
        return target.label if target else name


DEFAULT_AGENT_TARGETS = [
    AgentTarget(name="openai", label="OpenAI", aliases=("chatgpt",)),
    AgentTarget(name="claude", label="Claude", aliases=()),
    AgentTarget(name="gemini", label="Gemini", aliases=()),
]
