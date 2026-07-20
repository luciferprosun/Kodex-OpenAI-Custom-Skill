"""Fail-closed dual-window launcher for opt-in telemetry research mode."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import subprocess
import sys

from smart_codex.app_server_router.backend import SUPPORTED_CODEX_VERSION, BackendError, read_codex_version
from smart_codex.app_server_router.launcher import run as run_routed_tui
from smart_codex.policy_version import MODEL_POLICY_VERSION
from smart_codex.runtime.telemetry.collector import TelemetryService
from smart_codex.runtime.telemetry.config import configured_storage, load_external_config
from smart_codex.runtime.telemetry.errors import TelemetryError
from smart_codex.runtime.telemetry.privacy import ensure_installation_salt, private_identifier
from smart_codex.runtime.telemetry.schema import SCHEMA_VERSION


WINDOW_REMOTES = {
    "aoia": "github.com/luciferprosun/AOIA-Core",
    "smart-router": "github.com/luciferprosun/Kodex-OpenAI-Custom-Skill",
}
ROUTER_POLICY_VERSION = MODEL_POLICY_VERSION


def _verify_workspace(window_id: str, cwd: Path) -> None:
    if not cwd.is_dir() or cwd.is_symlink():
        raise BackendError("research workspace is not a safe directory")
    try:
        root = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).stdout.strip()
        remotes = subprocess.run(
            ["git", "-C", str(cwd), "remote", "-v"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise BackendError("research workspace Git identity could not be verified") from exc
    if Path(root).resolve() != cwd:
        raise BackendError("research workspace must be the exact Git root")
    normalized = remotes.replace("https://", "").replace("git@github.com:", "github.com/").replace(".git", "")
    if WINDOW_REMOTES[window_id] not in normalized:
        raise BackendError("research window repository identity mismatch")


async def _run(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).expanduser().resolve()
    _verify_workspace(args.window_id, cwd)
    config = load_external_config()
    if config is None:
        raise BackendError("external telemetry storage is not configured")
    storage = configured_storage(require_external=True)
    if not storage.enabled():
        raise BackendError("telemetry is not explicitly enabled")
    warning = storage.write_preflight()
    if warning is not None:
        raise BackendError(f"telemetry preflight failed: {warning}")
    installed = await read_codex_version(args.codex_bin)
    if installed != SUPPORTED_CODEX_VERSION:
        raise BackendError("installed Codex version differs from the exact reviewed protocol contract")
    salt = ensure_installation_salt(storage.paths.salt)
    workspace_signature = private_identifier(salt, "workspace", str(cwd))
    protocol_value = SUPPORTED_CODEX_VERSION.replace(" ", "_")
    service = TelemetryService(
        storage,
        window_id=args.window_id,
        workspace_signature=workspace_signature,
        router_policy_version=ROUTER_POLICY_VERSION,
        codex_protocol_version=protocol_value,
    )
    events = config.telemetry_root / "runtime-events" / f"routes-{args.window_id}-{os.getpid()}.jsonl"
    routed_args = argparse.Namespace(
        cwd=str(cwd),
        codex_bin=args.codex_bin,
        backend_url=None,
        backend_port=0,
        proxy_port=0,
        event_log=str(events),
        print_command=args.print_command,
        manager_only=args.manager_only,
    )
    banner = {
        "Telemetry": "ACTIVE",
        "Window": args.window_id,
        "Storage filesystem": "VERIFIED",
        "Storage root": "$MOUNT/SmartRouterTelemetry",
        "Schema version": SCHEMA_VERSION,
        "Codex contract": "VERIFIED",
        "Router policy version": ROUTER_POLICY_VERSION,
        "Routing authority": "CURRENT POLICY ONLY",
    }
    return await run_routed_tui(
        routed_args,
        telemetry_service=service,
        research_banner=banner,
        event_preflight=storage.write_preflight,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start one fail-closed SmartRouter research window.")
    parser.add_argument("--window-id", required=True, choices=sorted(WINDOW_REMOTES))
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--print-command", action="store_true")
    parser.add_argument("--manager-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(_run(parse_args(argv)))
    except (BackendError, OSError, RuntimeError, ValueError, TelemetryError) as exc:
        category = getattr(exc, "category", str(exc))
        print(f"Smart Router research mode refused safely: {category}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
