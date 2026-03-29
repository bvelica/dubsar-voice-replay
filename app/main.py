from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from importlib.metadata import PackageNotFoundError, version as package_version

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from app.agent_registry import AgentRegistry, DEFAULT_AGENT_TARGETS
from app.agent_router import AgentRouter
from app.agents import OpenAIProvider
from app.commands import CommandResolver
from app.config import load_settings
from app.conversation_service import ConversationService
from app.mcp_server import MCP_RESOURCES, MCP_SERVER_NAME, MCP_TOOLS, create_mcp_server
from app.moonshine_service import MoonshineService
from app.response_writer import ResponseWriter
from app.transcript_store import TranscriptStore
from app.ui import STATIC_DIR, render_index


settings = load_settings()
app_version = settings.project_root.joinpath("VERSION").read_text(encoding="utf-8").strip()
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
registry = AgentRegistry(DEFAULT_AGENT_TARGETS, providers)
default_provider = registry.normalize(settings.default_provider) or settings.default_provider
router = AgentRouter(
    command_resolver=CommandResolver(
        default_provider=default_provider,
        aliases=registry.alias_map(),
        known_providers=tuple(registry.known_target_names()),
    ),
    providers=registry.configured_providers(),
)
response_writer = ResponseWriter(store=store)
conversation_service = ConversationService(
    store=store,
    router=router,
    response_writer=response_writer,
    history_events=settings.assistant_history_events,
)
mcp_server = create_mcp_server(store=store, moonshine=moonshine, conversation_service=conversation_service)
mcp_app = mcp_server.http_app(path="/")
logger = logging.getLogger(__name__)


def safe_package_version(name: str) -> str | None:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return None


def assistant_status() -> dict[str, object]:
    service_status = conversation_service.status()
    configured_providers = registry.configured_target_names()
    default_ready = default_provider in registry.configured_providers()
    default_error = None
    if not default_ready:
        if default_provider == "openai" and not settings.openai_api_key:
            default_error = "Missing OPENAI_API_KEY"
        else:
            default_error = f"Provider '{default_provider}' is not configured"
    return {
        "default_provider": default_provider,
        "configured_providers": configured_providers,
        "known_providers": registry.known_target_names(),
        "ready": default_ready,
        "error": default_error,
        "processing": service_status["processing"],
        "pending_count": service_status["pending_count"],
    }


def mcp_status() -> dict[str, object]:
    return {
        "name": MCP_SERVER_NAME,
        "mount_path": "/mcp",
        "endpoint": "/mcp/",
        "transport": "FastMCP HTTP app",
        "sdk_version": safe_package_version("fastmcp"),
        "protocol_version": safe_package_version("mcp"),
        "resources": MCP_RESOURCES,
        "tools": MCP_TOOLS,
    }


def app_status() -> dict[str, object]:
    return {
        "name": "transcriptor",
        "version": app_version,
        "fastapi_version": safe_package_version("fastapi"),
        "openai_sdk_version": safe_package_version("openai"),
        "moonshine_version": safe_package_version("moonshine-voice"),
    }


def storage_status() -> dict[str, object]:
    return {
        "history_limit": settings.transcript_history_limit,
        "transcript_store_path": str(settings.transcript_store_path),
        "cache_dir": str(settings.cache_dir),
        "data_dir": str(settings.data_dir),
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
    version=app_version,
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
    transcriber = moonshine.status()
    assistant = assistant_status()
    return {
        **transcriber,
        "assistant": assistant,
        "app": app_status(),
        "mcp": mcp_status(),
        "storage": storage_status(),
    }


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


@app.post("/api/assistant/send-draft/{draft_id}")
async def send_draft(draft_id: int) -> dict[str, object]:
    return await conversation_service.submit_draft(draft_id)


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
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
