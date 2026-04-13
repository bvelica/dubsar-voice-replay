from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from importlib.metadata import PackageNotFoundError, version as package_version

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from app.agent_worker_manager import AgentWorkerManager
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
    agent_slots=settings.agent_slots,
)
moonshine = MoonshineService(settings=settings, store=store)
response_writer = ResponseWriter(store=store)
conversation_service = ConversationService(
    store=store,
    response_writer=response_writer,
    voice_request_idle_seconds=settings.voice_request_idle_seconds,
)
agent_worker_manager = AgentWorkerManager(settings)
mcp_server = create_mcp_server(store=store, moonshine=moonshine, conversation_service=conversation_service)
mcp_app = mcp_server.http_app(path="/")
logger = logging.getLogger(__name__)


def safe_package_version(name: str) -> str | None:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return None


def agent_status() -> dict[str, object]:
    service_status = conversation_service.status()
    snapshot = store.snapshot()
    agent_statuses = snapshot.get("agent_statuses", [])
    connected_agents = [
        agent
        for agent in agent_statuses
        if str(agent.get("status", "")).strip().lower() in {"ready", "working", "error"}
    ]
    current_agent_name = None
    current_agent_label = None
    for utterance in reversed(snapshot["utterances"]):
        if utterance.get("kind") != "message":
            continue
        if utterance.get("status") != "claimed":
            continue
        current_agent_name = utterance.get("agent_name")
        current_agent_label = utterance.get("agent_label")
        break
    return {
        "mode": "mcp-first",
        "ready": bool(connected_agents),
        "active_agents": connected_agents,
        "configured_slots": [
            {
                "label": slot.label,
                "target_agent_name": slot.target_agent_name,
                "aliases": list(slot.aliases),
            }
            for slot in settings.agent_slots
        ],
        "agent_count": len(connected_agents),
        "current_agent_name": current_agent_name,
        "current_agent_label": current_agent_label,
        "processing": service_status["processing"],
        "pending_count": service_status["pending_count"],
        "queued_count": service_status["queued_count"],
        "claimed_count": service_status["claimed_count"],
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
        "name": "Dubsar Voice Relay",
        "version": app_version,
        "fastapi_version": safe_package_version("fastapi"),
        "httpx_version": safe_package_version("httpx"),
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
        await agent_worker_manager.start()
        try:
            moonshine.start()
        except Exception as exc:
            logger.exception("Automatic transcriber startup failed: %s", exc)
            pass
        try:
            yield
        finally:
            await agent_worker_manager.stop()
            await conversation_service.stop()
            moonshine.stop()


app = FastAPI(
    title="Dubsar Voice Relay",
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
    agents = agent_status()
    return {
        **transcriber,
        "agents": agents,
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


@app.post("/api/drafts/{draft_id}/queue")
async def queue_draft(draft_id: int) -> dict[str, object]:
    return await conversation_service.queue_draft(draft_id)


@app.post("/api/requests/{request_id}/delegate/{agent_name}")
async def delegate_request(request_id: int, agent_name: str) -> dict[str, object]:
    return await conversation_service.delegate_request(
        request_id,
        target_agent_name=agent_name,
        target_agent_label=agent_name,
    )


@app.post("/api/assistant/send-draft/{draft_id}")
async def queue_draft_legacy(draft_id: int) -> dict[str, object]:
    return await conversation_service.queue_draft(draft_id)


@app.post("/api/requests/{request_id}/queue")
async def queue_request(request_id: int) -> dict[str, object]:
    return await conversation_service.queue_request(request_id)


@app.websocket("/ws/transcript")
async def transcript_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = await store.subscribe()
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        store.unsubscribe(queue)


app.mount("/mcp", mcp_app)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
