from __future__ import annotations

from functools import cached_property
from pathlib import Path

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSlotSettings(BaseModel):
    enabled: bool = False
    target_agent_name: str = ""
    label: str = ""
    aliases: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize(self) -> "AgentSlotSettings":
        target_agent_name = self.target_agent_name.strip().lower()
        label = self.label.strip()
        aliases = [alias.strip().lower() for alias in self.aliases if alias.strip()]

        if not self.enabled and not target_agent_name and not label and not aliases:
            self.enabled = False
            self.target_agent_name = ""
            self.label = ""
            self.aliases = []
            return self

        self.enabled = self.enabled or bool(target_agent_name)
        self.target_agent_name = target_agent_name
        self.label = label or target_agent_name
        seen: set[str] = set()
        normalized_aliases: list[str] = []
        for alias in [self.label.lower(), target_agent_name, *aliases]:
            if not alias or alias in seen:
                continue
            seen.add(alias)
            normalized_aliases.append(alias)
        self.aliases = normalized_aliases
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    voice_request_idle_seconds: float = 1.75
    transcript_history_limit: int = 10
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    auto_start_openai_agent: bool = True
    auto_start_anthropic_agent: bool = True
    language: str = "en"
    agent_slot_1: AgentSlotSettings = Field(
        default_factory=lambda: AgentSlotSettings(
            enabled=True,
            target_agent_name="chatgpt",
            label="Agent 1",
            aliases=["agent one", "one", "gpt", "chatgpt", "chat gpt"],
        )
    )
    agent_slot_2: AgentSlotSettings = Field(
        default_factory=lambda: AgentSlotSettings(
            enabled=True,
            target_agent_name="claude",
            label="Agent 2",
            aliases=["agent two", "two", "claude"],
        )
    )
    agent_slot_3: AgentSlotSettings = Field(default_factory=AgentSlotSettings)
    agent_slot_4: AgentSlotSettings = Field(default_factory=AgentSlotSettings)
    agent_slot_5: AgentSlotSettings = Field(default_factory=AgentSlotSettings)

    @cached_property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @cached_property
    def cache_dir(self) -> Path:
        return self.project_root / ".cache"

    @cached_property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @cached_property
    def transcript_store_path(self) -> Path:
        return self.data_dir / "transcript_history.json"

    @property
    def agent_slots(self) -> list[AgentSlotSettings]:
        return [
            slot
            for slot in [
                self.agent_slot_1,
                self.agent_slot_2,
                self.agent_slot_3,
                self.agent_slot_4,
                self.agent_slot_5,
            ]
            if slot.enabled and slot.target_agent_name
        ]


def load_settings() -> Settings:
    return Settings()
