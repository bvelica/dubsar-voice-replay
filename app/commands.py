from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class RoutedPrompt:
    provider: str
    text: str
    handled: bool = True


@dataclass(frozen=True)
class ControlCommand:
    action: str
    provider: str
    provider_spoken: str


class CommandResolver:
    def __init__(self, default_provider: str, *, aliases: dict[str, str] | None = None, known_providers: tuple[str, ...] = ("openai", "claude", "gemini")) -> None:
        self._default_provider = default_provider
        self._aliases = aliases or {
            "chatgpt": "openai",
            "openai": "openai",
            "claude": "claude",
            "gemini": "gemini",
        }
        self._known_providers = known_providers

    def resolve(self, text: str, *, provider_override: str | None = None) -> RoutedPrompt:
        cleaned = text.strip()
        default_provider = self.normalize_provider(provider_override) or self._default_provider
        if not cleaned:
            return RoutedPrompt(provider=default_provider, text="", handled=False)

        for provider in self._known_providers:
            prefix = f"/{provider}"
            if cleaned.lower().startswith(prefix):
                remainder = cleaned[len(prefix):].strip()
                return RoutedPrompt(provider=self.normalize_provider(provider) or default_provider, text=remainder, handled=bool(remainder))

        if cleaned.lower().startswith("/agent "):
            remainder = cleaned[7:].strip()
            provider, _, prompt = remainder.partition(" ")
            normalized_provider = self.normalize_provider(provider.strip())
            return RoutedPrompt(
                provider=normalized_provider or default_provider,
                text=prompt.strip(),
                handled=bool(prompt.strip()),
            )

        return RoutedPrompt(provider=default_provider, text=cleaned)

    def parse_control(self, text: str) -> ControlCommand | None:
        cleaned = " ".join(text.strip().lower().split())
        if not cleaned:
            return None

        for prefix, action in (
            ("command send to ", "send"),
            ("command send ", "send"),
            ("command sent to ", "send"),
            ("command sent ", "send"),
            ("command execute ", "execute"),
            ("command route to ", "route"),
            ("command route ", "route"),
        ):
            if not cleaned.startswith(prefix):
                continue
            provider_spoken = cleaned[len(prefix):].strip()
            provider = self.normalize_provider(provider_spoken)
            if not provider:
                return None
            return ControlCommand(action=action, provider=provider, provider_spoken=provider_spoken)
        return None

    def normalize_provider(self, name: str | None) -> str | None:
        if not name:
            return None
        lowered = name.strip().lower()
        if lowered in self._aliases:
            return self._aliases[lowered]
        normalized = re.sub(r"[^a-z0-9]+", "", lowered)
        fuzzy_aliases = {
            "chatgpt": "openai",
            "chatgpts": "openai",
            "chatgpt4": "openai",
            "chatgptfive": "openai",
            "chatgptmini": "openai",
            "chatgpto": "openai",
            "chatchpt": "openai",
            "chatgbt": "openai",
            "chatgptt": "openai",
            "openai": "openai",
            "claude": "claude",
            "gemini": "gemini",
        }
        return fuzzy_aliases.get(normalized)
