from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    project_root: Path
    cache_dir: Path
    data_dir: Path
    transcript_store_path: Path
    transcript_history_limit: int
    default_provider: str
    assistant_history_events: int
    openai_api_key: str | None
    openai_model: str
    openai_system_prompt: str
    language: str = "en"


def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")
    return Settings(
        project_root=project_root,
        cache_dir=project_root / ".cache",
        data_dir=project_root / "data",
        transcript_store_path=project_root / "data" / "transcript_history.json",
        transcript_history_limit=10,
        default_provider=os.getenv("TRANSCRIPTOR_DEFAULT_PROVIDER", "openai"),
        assistant_history_events=int(os.getenv("TRANSCRIPTOR_ASSISTANT_HISTORY_EVENTS", "8")),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        openai_system_prompt=os.getenv(
            "OPENAI_SYSTEM_PROMPT",
            "You are a concise voice assistant inside a local-first transcript UI. "
            "Reply clearly, directly, and briefly unless the user asks for more detail.",
        ),
    )
