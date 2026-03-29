from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.agent_router import AgentRouter
from app.agents import OpenAIProvider
from app.commands import CommandResolver
from app.config import load_settings
from app.conversation_service import ConversationService
from app.mcp_server import create_mcp_server
from app.moonshine_service import MoonshineService
from app.response_writer import ResponseWriter
from app.transcript_store import TranscriptStore
from app.ui import render_index


settings = load_settings()
store = TranscriptStore(
    persistence_path=settings.transcript_store_path,
    history_limit=settings.transcript_history_limit,
)
moonshine = MoonshineService(settings=settings, store=store)
providers = {}
if settings.openai_api_key:
    providers["openai"] = OpenAIProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        system_prompt=settings.openai_system_prompt,
    )
router = AgentRouter(
    command_resolver=CommandResolver(default_provider=settings.default_provider),
    providers=providers,
)
response_writer = ResponseWriter(store=store)
conversation_service = ConversationService(
    store=store,
    router=router,
    response_writer=response_writer,
    history_events=settings.assistant_history_events,
    auto_submit=settings.assistant_auto_submit,
)
mcp_server = create_mcp_server(store=store, moonshine=moonshine)
mcp_app = mcp_server.http_app(path="/")
logger = logging.getLogger(__name__)


def assistant_status() -> dict[str, object]:
    configured_providers = sorted(providers.keys())
    default_ready = settings.default_provider in providers
    default_error = None
    if not default_ready:
        if settings.default_provider == "openai" and not settings.openai_api_key:
            default_error = "Missing OPENAI_API_KEY"
        else:
            default_error = f"Provider '{settings.default_provider}' is not configured"
    return {
        "default_provider": settings.default_provider,
        "configured_providers": configured_providers,
        "ready": default_ready,
        "error": default_error,
        "auto_submit": settings.assistant_auto_submit,
        "processing": conversation_service.status()["processing"],
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mcp_app.lifespan(app))
        store.set_loop(asyncio.get_running_loop())
        store.load()
        await conversation_service.start()
        try:
            moonshine.start()
        except Exception as exc:
            logger.exception("Automatic transcriber startup failed: %s", exc)
            pass
        try:
            yield
        finally:
            await conversation_service.stop()
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
    status = moonshine.status()
    status["assistant"] = assistant_status()
    return status


@app.get("/api/transcript")
def get_transcript() -> dict[str, object]:
    return store.snapshot()


@app.post("/api/transcript/clear")
def clear_transcript() -> dict[str, object]:
    return store.clear()


@app.post("/api/transcriber/start")
def start_transcriber() -> dict[str, object]:
    moonshine.start()
    return moonshine.status()


@app.post("/api/transcriber/stop")
def stop_transcriber() -> dict[str, object]:
    moonshine.stop()
    return moonshine.status()


@app.post("/api/assistant/send-latest")
async def send_latest_transcript() -> dict[str, object]:
    return await conversation_service.send_latest()


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


app.mount("/mcp", mcp_app)
