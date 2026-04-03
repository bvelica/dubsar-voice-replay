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
    openai_api_key: str | None
    anthropic_api_key: str | None
    auto_start_openai_agent: bool
    auto_start_anthropic_agent: bool
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
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        auto_start_openai_agent=(os.getenv("AUTO_START_OPENAI_AGENT", "1").strip().lower() not in {"0", "false", "no", "off"}),
        auto_start_anthropic_agent=(os.getenv("AUTO_START_ANTHROPIC_AGENT", "1").strip().lower() not in {"0", "false", "no", "off"}),
    )
