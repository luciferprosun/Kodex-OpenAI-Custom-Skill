"""Strict CLI for local Smart Codex session-control state."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

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


def status_payload(snapshot: StateSnapshot) -> dict[str, object]:
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
        "state_schema_version": STATE_SCHEMA_VERSION,
        "integration_mode": INTEGRATION_MODE,
        "automatic_model_execution": "OFF",
        "ultra_automatic_execution": "OFF",
        "subagent_execution": "OFF",
        "last_updated_at": state.last_updated_at,
        "last_updated_by": state.last_updated_by,
    }


def render_status(snapshot: StateSnapshot) -> str:
    payload = status_payload(snapshot)
    telemetry_session = payload["telemetry_session"] or "NONE"
    return "\n".join(
        (
            f"Smart Router: {payload['smart_router']}",
            f"Research Telemetry: {payload['research_telemetry']}",
            f"Telemetry Session: {telemetry_session}",
            f"Policy Version: {payload['policy_version']}",
            f"State Schema Version: {payload['state_schema_version']}",
            f"Integration Mode: {payload['integration_mode']}",
            f"State Status: {str(payload['state_status']).upper()}",
            "Automatic Model Execution: OFF",
            "Ultra Automatic Execution: OFF",
            "Subagent Execution: OFF",
        )
    )


def _print_snapshot(snapshot: StateSnapshot, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(status_payload(snapshot), indent=2, sort_keys=True))
    else:
        print(render_status(snapshot))


def main(
    argv: Sequence[str] | None = None,
    *,
    store: SessionControlStore | None = None,
) -> int:
    args = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    selected = SessionControlStore() if store is None else store
    json_output = bool(getattr(args, "json_output", False))
    try:
        if args.command == "status":
            snapshot = selected.read()
        elif args.command == "reset":
            selected.reset()
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
    _print_snapshot(snapshot, json_output=json_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
