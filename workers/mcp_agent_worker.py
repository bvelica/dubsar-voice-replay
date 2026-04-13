from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastmcp.client import Client
from mcp.types import TextResourceContents
from openai import AsyncOpenAI


def load_env() -> None:
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")


@dataclass(frozen=True)
class WorkerConfig:
    server_url: str
    agent_name: str
    agent_label: str
    backend: str
    poll_interval_seconds: float
    history_events: int
    model: str
    system_prompt: str
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None


def default_agent_identity(backend: str) -> tuple[str, str]:
    normalized = backend.strip().lower()
    if normalized == "openai":
        return "chatgpt", "ChatGPT"
    if normalized == "anthropic":
        return "claude", "Claude"
    raise ValueError(f"Unsupported backend '{backend}'")


def parse_args() -> WorkerConfig:
    load_env()
    parser = argparse.ArgumentParser(description="External MCP agent worker for Dubsar Voice Relay.")
    parser.add_argument("--server-url", default=os.getenv("DUBSAR_MCP_URL", "http://127.0.0.1:8000/mcp/"))
    parser.add_argument("--backend", choices=("openai", "anthropic"), required=True)
    parser.add_argument("--agent-name")
    parser.add_argument("--agent-label")
    parser.add_argument("--poll-interval", type=float, default=float(os.getenv("DUBSAR_AGENT_POLL_INTERVAL", "2.0")))
    parser.add_argument("--history-events", type=int, default=int(os.getenv("DUBSAR_AGENT_HISTORY_EVENTS", "8")))
    parser.add_argument("--model")
    parser.add_argument("--system-prompt")
    args = parser.parse_args()

    default_name, default_label = default_agent_identity(args.backend)
    if args.backend == "openai":
        model = args.model or os.getenv("OPENAI_MODEL", "gpt-5-mini")
        system_prompt = args.system_prompt or os.getenv(
            "OPENAI_SYSTEM_PROMPT",
            "You are an external MCP agent connected to Dubsar Voice Relay. Reply clearly, directly, and briefly unless the user asks for more detail.",
        )
        return WorkerConfig(
            server_url=args.server_url,
            agent_name=args.agent_name or default_name,
            agent_label=args.agent_label or default_label,
            backend=args.backend,
            poll_interval_seconds=args.poll_interval,
            history_events=args.history_events,
            model=model,
            system_prompt=system_prompt,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )

    model = args.model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    system_prompt = args.system_prompt or os.getenv(
        "ANTHROPIC_SYSTEM_PROMPT",
        "You are an external MCP agent connected to Dubsar Voice Relay. Reply clearly, directly, and briefly unless the user asks for more detail.",
    )
    return WorkerConfig(
        server_url=args.server_url,
        agent_name=args.agent_name or default_name,
        agent_label=args.agent_label or default_label,
        backend=args.backend,
        poll_interval_seconds=args.poll_interval,
        history_events=args.history_events,
        model=model,
        system_prompt=system_prompt,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    )


def parse_json_resource(contents: list[TextResourceContents]) -> Any:
    if not contents:
        return None
    text = "\n".join(item.text for item in contents if isinstance(item, TextResourceContents))
    if not text.strip():
        return None
    return json.loads(text)


def build_prompt(request: dict[str, Any]) -> str:
    text = str(request.get("text", "")).strip()
    if text:
        return text
    utterances = request.get("utterances", [])
    if not isinstance(utterances, list):
        return ""
    return " ".join(
        str(item.get("text", "")).strip()
        for item in utterances
        if isinstance(item, dict) and str(item.get("text", "")).strip()
    ).strip()


def build_conversation(snapshot: dict[str, Any], *, exclude_source_line_ids: set[int], history_events: int) -> list[dict[str, str]]:
    conversation: list[dict[str, str]] = []
    for event in snapshot.get("events", [])[-history_events:]:
        text = str(event.get("text", "")).strip()
        if not text or not event.get("is_final"):
            continue
        if event.get("kind") == "system_notice":
            continue
        if event.get("role") not in {"user", "assistant"}:
            continue
        source_line_id = event.get("source_line_id")
        if isinstance(source_line_id, int) and source_line_id in exclude_source_line_ids:
            continue
        conversation.append({"role": str(event["role"]), "text": text})
    return conversation


async def generate_openai_reply(config: WorkerConfig, *, prompt: str, conversation: list[dict[str, str]]) -> str:
    if not config.openai_api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")
    client = AsyncOpenAI(api_key=config.openai_api_key)
    history = "\n".join(f"{item['role'].upper()}: {item['text']}" for item in conversation)
    input_text = prompt if not history else f"Conversation so far:\n{history}\n\nCurrent user request:\n{prompt}"
    response = await client.responses.create(
        model=config.model,
        instructions=config.system_prompt,
        input=input_text,
    )
    text = response.output_text.strip()
    if not text:
        raise RuntimeError("OpenAI returned an empty reply")
    return text


async def generate_anthropic_reply(config: WorkerConfig, *, prompt: str, conversation: list[dict[str, str]]) -> str:
    if not config.anthropic_api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY")
    messages = [
        {"role": item["role"], "content": item["text"]}
        for item in conversation
    ]
    messages.append({"role": "user", "content": prompt})
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": config.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": config.model,
                "system": config.system_prompt,
                "max_tokens": 1200,
                "messages": messages,
            },
        )
        response.raise_for_status()
        payload = response.json()
    text_parts = [
        block.get("text", "")
        for block in payload.get("content", [])
        if block.get("type") == "text" and block.get("text")
    ]
    text = "\n".join(text_parts).strip()
    if not text:
        raise RuntimeError("Anthropic returned an empty reply")
    return text


async def generate_reply(config: WorkerConfig, *, prompt: str, conversation: list[dict[str, str]]) -> str:
    if config.backend == "openai":
        return await generate_openai_reply(config, prompt=prompt, conversation=conversation)
    if config.backend == "anthropic":
        return await generate_anthropic_reply(config, prompt=prompt, conversation=conversation)
    raise RuntimeError(f"Unsupported backend '{config.backend}'")


async def run_worker(config: WorkerConfig) -> None:
    while True:
        try:
            async with Client(config.server_url) as client:
                await client.call_tool(
                    "set_agent_status",
                    {
                        "agent_name": config.agent_name,
                        "label": config.agent_label,
                        "status": "ready",
                        "detail": f"Connected to {config.server_url}",
                    },
                )
                while True:
                    try:
                        queued_contents = await client.read_resource("dubsar://queued-requests")
                        queued_requests = parse_json_resource(queued_contents) or []
                        if not queued_requests:
                            await asyncio.sleep(config.poll_interval_seconds)
                            continue

                        handled_request = False
                        for request in queued_requests:
                            request_id = request.get("request_id", request.get("draft_id"))
                            if not isinstance(request_id, int):
                                continue
                            claim_result = await client.call_tool(
                                "claim_request",
                                {
                                    "request_id": request_id,
                                    "agent_name": config.agent_name,
                                    "agent_label": config.agent_label,
                                },
                                raise_on_error=False,
                            )
                            claim_payload = claim_result.data or claim_result.structured_content or {}
                            if not claim_payload.get("claimed"):
                                continue

                            handled_request = True
                            await client.call_tool(
                                "set_agent_status",
                                {
                                    "agent_name": config.agent_name,
                                    "label": config.agent_label,
                                    "status": "working",
                                    "detail": f"Claimed request {request_id}",
                                },
                            )
                            prompt = build_prompt(request)
                            source_line_ids = {
                                int(value)
                                for value in request.get("source_line_ids", [])
                                if isinstance(value, int)
                            }
                            snapshot_contents = await client.read_resource("dubsar://snapshot")
                            snapshot = parse_json_resource(snapshot_contents) or {}
                            conversation = build_conversation(
                                snapshot,
                                exclude_source_line_ids=source_line_ids,
                                history_events=config.history_events,
                            )
                            try:
                                reply_text = await generate_reply(config, prompt=prompt, conversation=conversation)
                                await client.call_tool(
                                    "complete_request",
                                    {
                                        "request_id": request_id,
                                        "agent_name": config.agent_name,
                                        "agent_label": config.agent_label,
                                        "text": reply_text,
                                    },
                                )
                                await client.call_tool(
                                    "set_agent_status",
                                    {
                                        "agent_name": config.agent_name,
                                        "label": config.agent_label,
                                        "status": "ready",
                                        "detail": f"Completed request {request_id}",
                                    },
                                )
                            except Exception as exc:
                                await client.call_tool(
                                    "fail_request",
                                    {
                                        "request_id": request_id,
                                        "agent_name": config.agent_name,
                                        "agent_label": config.agent_label,
                                        "error": str(exc),
                                    },
                                    raise_on_error=False,
                                )
                                await client.call_tool(
                                    "set_agent_status",
                                    {
                                        "agent_name": config.agent_name,
                                        "label": config.agent_label,
                                        "status": "error",
                                        "detail": str(exc),
                                    },
                                )
                            break

                        if not handled_request:
                            await asyncio.sleep(config.poll_interval_seconds)
                    except Exception as exc:
                        try:
                            await client.call_tool(
                                "set_agent_status",
                                {
                                    "agent_name": config.agent_name,
                                    "label": config.agent_label,
                                    "status": "error",
                                    "detail": str(exc),
                                },
                                raise_on_error=False,
                            )
                        except Exception:
                            break
                        await asyncio.sleep(config.poll_interval_seconds)
        except Exception:
            await asyncio.sleep(config.poll_interval_seconds)


def main() -> None:
    config = parse_args()
    asyncio.run(run_worker(config))


if __name__ == "__main__":
    main()
