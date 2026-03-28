from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    cache_dir: Path
    language: str = "en"


def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parent.parent
    return Settings(
        project_root=project_root,
        cache_dir=project_root / ".cache",
    )
