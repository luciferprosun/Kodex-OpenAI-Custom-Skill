"""Launch/connect to App Server and discover live metadata without a model turn."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any

from .model_registry import ModelRegistry
from .policy_mapper import RuntimeRequirements
from .protocol import decode_message, encode_message
from .websocket import WebSocketClosed, WebSocketError, connect_websocket


class BackendError(RuntimeError):
    pass


SUPPORTED_CODEX_VERSION = "codex-cli 0.144.6"


@dataclass(frozen=True)
class DiscoveredBackend:
    registry: ModelRegistry
    requirements: RuntimeRequirements


class BackendProcess:
    def __init__(self, executable: str, url: str):
        resolved = shutil.which(executable) if "/" not in executable else executable
        if not resolved or not Path(resolved).exists():
            raise BackendError("Codex executable was not found")
        self.executable = str(resolved)
        self.url = url
        self.process: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        if self.process is not None:
            raise BackendError("App Server backend is already started")
        self.process = await asyncio.create_subprocess_exec(
            self.executable,
            "app-server",
            "--listen",
            self.url,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

    async def stop(self) -> None:
        process = self.process
        self.process = None
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    def exited(self) -> bool:
        return self.process is not None and self.process.returncode is not None


async def read_codex_version(executable: str) -> str:
    resolved = shutil.which(executable) if "/" not in executable else executable
    if not resolved:
        raise BackendError("Codex executable was not found")
    process = await asyncio.create_subprocess_exec(
        resolved,
        "--version",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        raise BackendError("could not read the installed Codex version")
    return " ".join(stdout.decode("utf-8", errors="replace").split())[:80]


async def discover_backend(
    url: str,
    *,
    codex_version: str,
    attempts: int = 50,
) -> DiscoveredBackend:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return await _discover_once(url, codex_version=codex_version)
        except (OSError, WebSocketError) as exc:
            last_error = exc
            await asyncio.sleep(0.1)
    raise BackendError("App Server metadata discovery failed") from last_error


async def _discover_once(url: str, *, codex_version: str) -> DiscoveredBackend:
    connection = await connect_websocket(url)
    try:
        initialize = await _request(
            connection,
            {
                "method": "initialize",
                "id": "smart-router-initialize",
                "params": {
                    "clientInfo": {
                        "name": "codex_smart_router",
                        "title": "Codex Smart Router",
                        "version": "0.1.0",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            },
        )
        if not isinstance(initialize.get("result"), dict):
            raise BackendError("App Server initialize returned no result")
        await connection.send_text(encode_message({"method": "initialized"}))

        models: list[object] = []
        cursor: str | None = None
        page = 0
        while True:
            page += 1
            if page > 100:
                raise BackendError("model/list pagination did not terminate")
            params: dict[str, object] = {"includeHidden": True, "limit": 100}
            if cursor is not None:
                params["cursor"] = cursor
            response = await _request(
                connection,
                {"method": "model/list", "id": f"smart-router-models-{page}", "params": params},
            )
            result = response.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("data"), list):
                raise BackendError("model/list returned a malformed result")
            models.extend(result["data"])
            next_cursor = result.get("nextCursor")
            if next_cursor is None:
                break
            if not isinstance(next_cursor, str) or not next_cursor:
                raise BackendError("model/list returned a malformed cursor")
            cursor = next_cursor

        requirements_response = await _request(
            connection,
            {"method": "configRequirements/read", "id": "smart-router-requirements"},
        )
        requirements_result = requirements_response.get("result")
        registry = ModelRegistry.from_model_list(models, codex_version=codex_version)
        requirements = RuntimeRequirements.from_response(requirements_result)
        return DiscoveredBackend(registry=registry, requirements=requirements)
    finally:
        await connection.close()


async def _request(connection: Any, request: dict[str, object]) -> dict[str, Any]:
    request_id = request["id"]
    await connection.send_text(encode_message(request))
    while True:
        try:
            raw = await connection.recv_text()
        except WebSocketClosed as exc:
            raise BackendError("App Server closed during metadata discovery") from exc
        response = decode_message(raw)
        if response.get("id") != request_id:
            continue
        if "error" in response:
            error = response.get("error")
            code = error.get("code") if isinstance(error, dict) else "unknown"
            raise BackendError(f"App Server metadata request failed with code {code}")
        return response
