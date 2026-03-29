from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse


STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_PATH = STATIC_DIR / "index.html"


def render_index() -> FileResponse:
    return FileResponse(INDEX_PATH)
