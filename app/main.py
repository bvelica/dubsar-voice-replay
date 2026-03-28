from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.config import load_settings
from app.moonshine_service import MoonshineService
from app.transcript_store import TranscriptStore
from app.ui import render_index


settings = load_settings()
store = TranscriptStore()
moonshine = MoonshineService(settings=settings, store=store)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.set_loop(asyncio.get_running_loop())
    try:
        moonshine.start()
    except Exception as exc:
        logger.exception("Automatic transcriber startup failed: %s", exc)
        pass
    yield
    moonshine.stop()


app = FastAPI(
    title="transcriptor",
    version=settings.project_root.joinpath("VERSION").read_text(encoding="utf-8").strip(),
    lifespan=lifespan,
)


@app.get("/")
def root():
    return render_index()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def api_status() -> dict[str, object]:
    return moonshine.status()


@app.get("/api/transcript")
def get_transcript() -> dict[str, object]:
    return store.snapshot()


@app.post("/api/transcriber/start")
def start_transcriber() -> dict[str, object]:
    moonshine.start()
    return moonshine.status()


@app.post("/api/transcriber/stop")
def stop_transcriber() -> dict[str, object]:
    moonshine.stop()
    return moonshine.status()


@app.websocket("/ws/transcript")
async def transcript_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = await store.subscribe()
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        store.unsubscribe(queue)
