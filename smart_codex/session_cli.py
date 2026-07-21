"""Strict CLI for local Smart Codex session-control state."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Callable, Sequence

from . import __version__ as router_version
from .runtime.telemetry.schema import SCHEMA_VERSION as TELEMETRY_SCHEMA_VERSION
from .session_control import (
    INTEGRATION_MODE,
    STATE_SCHEMA_VERSION,
    SessionControlError,
    SessionControlStore,
    StateSnapshot,
)


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", dest="json_output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smart-routerctl",
        description="Local Smart Router and research telemetry session controls.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="show complete control state")
    _add_json_flag(status)

    reset = commands.add_parser("reset", help="set both controls to their safe defaults")
    _add_json_flag(reset)

    router = commands.add_parser("smart-router", help="control advisory Smart Router hooks")
    router_commands = router.add_subparsers(dest="router_action", required=True)
    router_on = router_commands.add_parser("on")
    router_on.add_argument(
        "--telemetry",
        action="store_true",
        help="transactionally enable research telemetry with the router",
    )
    _add_json_flag(router_on)
    router_off = router_commands.add_parser("off")
    _add_json_flag(router_off)
    router_status = router_commands.add_parser("status")
    _add_json_flag(router_status)

    telemetry = commands.add_parser("telemetry", help="control selective research capture")
    telemetry_commands = telemetry.add_subparsers(dest="telemetry_action", required=True)
    for action in ("start", "stop", "status"):
        child = telemetry_commands.add_parser(action)
        _add_json_flag(child)
    return parser


def status_payload(
    snapshot: StateSnapshot,
    *,
    telemetry_backend: str = "NOT_CHECKED",
) -> dict[str, object]:
    state = snapshot.state
    return {
        "ok": True,
        "state_status": snapshot.status,
        "smart_router": "ON" if state.router_enabled is True else "OFF",
        "research_telemetry": (
            "ON" if state.research_telemetry_enabled is True else "OFF"
        ),
        "telemetry_session": state.telemetry_session_id,
        "telemetry_started_at": state.telemetry_started_at,
        "policy_version": state.policy_version,
        "router_version": router_version,
        "telemetry_schema_version": TELEMETRY_SCHEMA_VERSION,
        "telemetry_backend": telemetry_backend,
        "state_schema_version": STATE_SCHEMA_VERSION,
        "integration_mode": INTEGRATION_MODE,
        "automatic_model_execution": "OFF",
        "ultra_automatic_execution": "OFF",
        "subagent_execution": "OFF",
        "automatic_policy_learning": "OFF",
        "last_updated_at": state.last_updated_at,
        "last_updated_by": state.last_updated_by,
    }


def render_status(
    snapshot: StateSnapshot,
    *,
    telemetry_backend: str = "NOT_CHECKED",
) -> str:
    payload = status_payload(snapshot, telemetry_backend=telemetry_backend)
    telemetry_session = payload["telemetry_session"] or "NONE"
    return "\n".join(
        (
            f"Smart Router: {payload['smart_router']}",
            f"Research Telemetry: {payload['research_telemetry']}",
            f"Telemetry Session: {telemetry_session}",
            f"Policy Version: {payload['policy_version']}",
            f"Router Version: {payload['router_version']}",
            f"Telemetry Schema: {payload['telemetry_schema_version']}",
            f"Telemetry Backend: {payload['telemetry_backend']}",
            f"State Schema Version: {payload['state_schema_version']}",
            f"Integration Mode: {payload['integration_mode']}",
            f"State Status: {str(payload['state_status']).upper()}",
            "Automatic Model Execution: OFF",
            "Ultra Automatic Execution: OFF",
            "Subagent Execution: OFF",
            "Automatic Policy Learning: OFF",
        )
    )


def _print_snapshot(
    snapshot: StateSnapshot,
    *,
    json_output: bool,
    telemetry_backend: str,
) -> None:
    if json_output:
        print(
            json.dumps(
                status_payload(snapshot, telemetry_backend=telemetry_backend),
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(render_status(snapshot, telemetry_backend=telemetry_backend))


def main(
    argv: Sequence[str] | None = None,
    *,
    store: SessionControlStore | None = None,
    telemetry_status_reader: Callable[[SessionControlStore], str] | None = None,
) -> int:
    args = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    production_store = store is None
    selected = SessionControlStore() if production_store else store
    assert selected is not None
    json_output = bool(getattr(args, "json_output", False))
    try:
        if args.command == "status":
            snapshot = selected.read()
        elif args.command == "reset":
            selected.reset()
            try:
                from .runtime.telemetry.hook_capture import CodexHookTelemetryCapture

                CodexHookTelemetryCapture(selected).discard_pending()
            except Exception as exc:
                raise SessionControlError("TELEMETRY_PENDING_CLEANUP_FAILED") from exc
            snapshot = selected.read()
        elif args.command == "smart-router":
            if args.router_action == "on":
                selected.set_router(True, enable_telemetry=args.telemetry is True)
            elif args.router_action == "off":
                selected.set_router(False)
            snapshot = selected.read()
        elif args.command == "telemetry":
            if args.telemetry_action == "start":
                selected.set_telemetry(True)
            elif args.telemetry_action == "stop":
                selected.set_telemetry(False)
                try:
                    from .runtime.telemetry.hook_capture import CodexHookTelemetryCapture

                    CodexHookTelemetryCapture(selected).discard_pending()
                except Exception as exc:
                    raise SessionControlError("TELEMETRY_PENDING_CLEANUP_FAILED") from exc
            snapshot = selected.read()
        else:  # pragma: no cover - argparse prevents this path
            raise SessionControlError("SESSION_CONTROL_COMMAND_INVALID")
    except SessionControlError as exc:
        error = str(exc) if str(exc) else "SESSION_CONTROL_FAILED"
        if json_output:
            print(json.dumps({"ok": False, "error": error}, sort_keys=True))
        else:
            print(f"Smart Codex session control failed safely: {error}", file=sys.stderr)
        return 2
    if snapshot.state.research_telemetry_enabled is not True:
        telemetry_backend = "OFF"
    elif telemetry_status_reader is not None:
        telemetry_backend = telemetry_status_reader(selected)
    elif production_store:
        try:
            from .runtime.telemetry.hook_capture import telemetry_backend_status

            telemetry_backend = telemetry_backend_status(selected)
        except Exception:
            telemetry_backend = "DEGRADED_TELEMETRY_INITIALIZATION_ERROR"
    else:
        telemetry_backend = "NOT_CHECKED"
    _print_snapshot(
        snapshot,
        json_output=json_output,
        telemetry_backend=telemetry_backend,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
