from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerSpec:
    backend: str
    agent_name: str
    agent_label: str


class AgentWorkerManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def start(self) -> None:
        for spec in self._desired_workers():
            await self._start_worker(spec)

    async def stop(self) -> None:
        for backend, process in list(self._processes.items()):
            if process.returncode is not None:
                self._processes.pop(backend, None)
                continue
            process.terminate()
        for backend, process in list(self._processes.items()):
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
            finally:
                self._processes.pop(backend, None)

    def _desired_workers(self) -> list[WorkerSpec]:
        workers: list[WorkerSpec] = []
        if self._settings.openai_api_key and self._settings.auto_start_openai_agent:
            workers.append(WorkerSpec(backend="openai", agent_name="chatgpt", agent_label="ChatGPT"))
        if self._settings.anthropic_api_key and self._settings.auto_start_anthropic_agent:
            workers.append(WorkerSpec(backend="anthropic", agent_name="claude", agent_label="Claude"))
        return workers

    async def _start_worker(self, spec: WorkerSpec) -> None:
        worker_path = self._settings.project_root / "workers" / "mcp_agent_worker.py"
        cmd = [
            sys.executable,
            str(worker_path),
            "--backend",
            spec.backend,
            "--agent-name",
            spec.agent_name,
            "--agent-label",
            spec.agent_label,
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self._settings.project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._processes[spec.backend] = process
        logger.info("Started MCP agent worker '%s' (%s)", spec.agent_label, spec.backend)
