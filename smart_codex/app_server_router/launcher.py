"""Opt-in launcher for backend, local proxy, and the original Codex TUI."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import shutil
import signal
import socket
import sys
import tempfile
from typing import Callable

from .backend import (
    SUPPORTED_CODEX_VERSION,
    BackendError,
    BackendProcess,
    discover_backend,
    read_codex_version,
)
from .policy_mapper import PolicyMapper
from .protocol import JsonlEventSink
from .proxy import AppServerProxy
from .turn_router import TurnRouter
from smart_codex.runtime.telemetry.collector import TelemetryService


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def build_tui_command(codex_executable: str, proxy_url: str, cwd: Path) -> list[str]:
    resolved = shutil.which(codex_executable) if "/" not in codex_executable else codex_executable
    if not resolved:
        raise BackendError("Codex executable was not found")
    return [str(resolved), "--remote", proxy_url, "-C", str(cwd)]


def default_event_log() -> Path:
    directory = Path(tempfile.gettempdir()) / f"codex-smart-router-{os.getuid()}"
    return directory / f"routes-{os.getpid()}.jsonl"


async def run(
    args: argparse.Namespace,
    *,
    telemetry_service: TelemetryService | None = None,
    research_banner: dict[str, str] | None = None,
    event_preflight: Callable[[], str | None] | None = None,
) -> int:
    cwd = Path(args.cwd).expanduser().resolve()
    if not cwd.is_dir():
        raise BackendError("routed Codex working directory does not exist")
    codex_version = await read_codex_version(args.codex_bin)
    if codex_version != SUPPORTED_CODEX_VERSION:
        raise BackendError(
            "installed Codex version differs from the generated protocol contract; "
            "regenerate and review schemas before routed mode"
        )
    backend_process: BackendProcess | None = None
    if args.backend_url:
        backend_url = args.backend_url
    else:
        backend_port = args.backend_port or _free_port()
        backend_url = f"ws://127.0.0.1:{backend_port}"
        backend_process = BackendProcess(args.codex_bin, backend_url)
        await backend_process.start()

    proxy: AppServerProxy | None = None
    try:
        discovered = await discover_backend(
            backend_url,
            codex_version=codex_version,
        )
        mapper = PolicyMapper(discovered.registry, discovered.requirements)
        router = TurnRouter(mapper)
        event_path = Path(args.event_log).expanduser().resolve() if args.event_log else default_event_log()
        if telemetry_service is None:
            try:
                telemetry_service = TelemetryService.from_default()
            except (OSError, RuntimeError, ValueError):
                telemetry_service = None
        proxy = AppServerProxy(
            backend_url=backend_url,
            turn_router=router,
            port=args.proxy_port,
            events=JsonlEventSink(event_path, preflight=event_preflight),
            telemetry=telemetry_service,
        )
        await proxy.start()
        command = build_tui_command(args.codex_bin, proxy.url, cwd)
        if research_banner is None:
            print("Smart Router ON (WebSocket App Server transport is experimental).")
            print(f"Backend: {backend_url}")
            print(f"Proxy:   {proxy.url}")
            print(f"Events:  {event_path}")
        else:
            print("SMART ROUTER RESEARCH MODE")
            for label, value in research_banner.items():
                print(f"{label}: {value}")
            print("Loopback transport: verified")
        if args.print_command:
            if research_banner is None:
                print("TUI command: " + " ".join(command))
            else:
                print("TUI command: verified (prompt remains inside the TUI)")
            return 0
        if args.manager_only:
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for signum in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(signum, stop.set)
            print("Manager-only mode is running; press Ctrl-C to stop.")
            await stop.wait()
            return 0
        tui = await asyncio.create_subprocess_exec(*command)
        return await tui.wait()
    finally:
        if proxy is not None:
            await proxy.close()
        if backend_process is not None:
            await backend_process.stop()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the original Codex TUI through the opt-in local Smart Router.",
    )
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--backend-url")
    parser.add_argument("--backend-port", type=int, default=0)
    parser.add_argument("--proxy-port", type=int, default=0)
    parser.add_argument("--event-log")
    parser.add_argument("--print-command", action="store_true")
    parser.add_argument("--manager-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(run(parse_args(argv)))
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"Smart Router failed safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
