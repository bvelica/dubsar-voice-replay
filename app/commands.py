from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoutedPrompt:
    provider: str
    text: str
    handled: bool = True


class CommandResolver:
    def __init__(self, default_provider: str) -> None:
        self._default_provider = default_provider

    def resolve(self, text: str) -> RoutedPrompt:
        cleaned = text.strip()
        if not cleaned:
            return RoutedPrompt(provider=self._default_provider, text="", handled=False)

        for provider in ("openai", "claude", "gemini"):
            prefix = f"/{provider}"
            if cleaned.lower().startswith(prefix):
                remainder = cleaned[len(prefix):].strip()
                return RoutedPrompt(provider=provider, text=remainder, handled=bool(remainder))

        if cleaned.lower().startswith("/agent "):
            remainder = cleaned[7:].strip()
            provider, _, prompt = remainder.partition(" ")
            normalized_provider = provider.strip().lower()
            return RoutedPrompt(
                provider=normalized_provider or self._default_provider,
                text=prompt.strip(),
                handled=bool(prompt.strip()),
            )

        return RoutedPrompt(provider=self._default_provider, text=cleaned)
