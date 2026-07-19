from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import sys

from .knowledge import ConfigError
from .launcher import build_codex_command, run_codex_command
from .logging_safe import write_decision_log
from .model_audit import audit_models
from .router import route_prompt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smart-codex",
        description="Safe local Codex prompt router.",
    )
    parser.add_argument("--execute", action="store_true", help="execute Codex instead of dry-run")
    parser.add_argument("--dry-run", action="store_true", help="force dry-run behavior")
    parser.add_argument("--profile", help="manual profile override")
    parser.add_argument("--model", help="manual model override")
    parser.add_argument("--sandbox", help="manual sandbox override")
    parser.add_argument("--cd", help="working directory for Codex")
    parser.add_argument("--config", action="append", default=[], help="Codex config override key=value")
    parser.add_argument("--ask-for-approval", help="Codex approval policy override")
    parser.add_argument("--explain", action="store_true", help="print routing explanation")
    parser.add_argument("--no-log", action="store_true", help="disable privacy-safe decision log")
    parser.add_argument("prompt", nargs="+", help="prompt text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == "audit-models":
        return audit_models_command()
    if args_list and args_list[0] == "telemetry":
        return telemetry_command(args_list[1:])
    if args_list and args_list[0] == "outcome":
        return outcome_command(args_list[1:])
    parser = build_parser()
    args = parser.parse_args(args_list)
    prompt = " ".join(args.prompt)
    dry_run = args.dry_run or not args.execute

    try:
        decision = route_prompt(
            prompt,
            dry_run=dry_run,
            profile_override=args.profile,
            model_override=args.model,
            sandbox_override=args.sandbox,
            approval_override=args.ask_for_approval,
        )
    except ConfigError as exc:
        print(json.dumps({"ok": False, "error": "CONFIG_ERROR", "detail": str(exc)}, indent=2))
        return 2
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2

    command = build_codex_command(
        prompt,
        profile=decision.selected_profile,
        model=args.model,
        sandbox=decision.sandbox_mode,
        cd=args.cd,
        configs=args.config,
        approval_policy=decision.approval_policy,
        execute=args.execute and not args.dry_run,
    )

    if not args.no_log:
        write_decision_log(decision, enabled=True)

    print_decision(decision, command.argv, explain=args.explain)

    if command.execute:
        telemetry_run = None
        try:
            from .runtime.telemetry.collector import TelemetryService

            start = TelemetryService.from_default().start_from_decision(
                task=prompt,
                decision=decision,
                requested_model=args.model,
                launched_model=args.model,
                product_surface="smart_codex_cli",
            )
            telemetry_run = start.run
            if start.warning:
                print(start.warning, file=sys.stderr)
        except (OSError, RuntimeError, ValueError):
            print("TELEMETRY_DISABLED_INITIALIZATION_ERROR", file=sys.stderr)
        try:
            completed = run_codex_command(command)
        except BaseException:
            if telemetry_run is not None:
                result = telemetry_run.finish(status="process_error")
                if result.warning:
                    print(result.warning, file=sys.stderr)
            raise
        if telemetry_run is not None:
            result = telemetry_run.finish(
                status="completed" if completed.returncode == 0 else "process_error",
                process_exit_code=completed.returncode,
            )
            if result.warning:
                print(result.warning, file=sys.stderr)
            elif result.appended:
                print(f"telemetry_run_id: {result.run_id}", file=sys.stderr)
        return completed.returncode
    return 0


def audit_models_command() -> int:
    result = audit_models()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


def telemetry_command(argv: list[str]) -> int:
    from .runtime.telemetry.errors import TelemetryError
    from .runtime.telemetry.privacy import ensure_installation_salt
    from .runtime.telemetry.config import (
        configure_external_storage,
        configured_storage,
        load_external_config,
        reset_external_config,
    )
    from .runtime.telemetry.mounts import discover_storage_candidates
    from .runtime.telemetry.outcome import pending_runs
    from .runtime.telemetry.summary import inspect_run, storage_status, summarize

    parser = argparse.ArgumentParser(prog="smart-codex telemetry")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("status")
    subparsers.add_parser("enable")
    subparsers.add_parser("disable")
    subparsers.add_parser("preflight")
    pending_parser = subparsers.add_parser("pending")
    pending_parser.add_argument("--window-id", choices=["aoia", "smart-router"])
    storage_parser = subparsers.add_parser("storage")
    storage_subparsers = storage_parser.add_subparsers(dest="storage_action", required=True)
    storage_subparsers.add_parser("discover")
    storage_configure = storage_subparsers.add_parser("configure")
    storage_configure.add_argument("--root", required=True)
    storage_configure.add_argument("--device-uuid", required=True)
    storage_subparsers.add_parser("status")
    storage_subparsers.add_parser("reset")
    summary_parser = subparsers.add_parser("summary")
    group = summary_parser.add_mutually_exclusive_group()
    group.add_argument("--by-model", action="store_true")
    group.add_argument("--by-task-level", action="store_true")
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("run_id")
    inspect_parser.add_argument("--show-task-signature", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "storage":
        try:
            if args.storage_action == "discover":
                candidates, selected = discover_storage_candidates()
                print(
                    json.dumps(
                        {
                            "candidates": [value.public_dict() for value in candidates],
                            "selected": selected.public_dict() if selected is not None else None,
                            "selection_status": (
                                "UNIQUE_SAFE_REMOVABLE_STORAGE"
                                if selected is not None
                                else "HUMAN_SELECTION_REQUIRED"
                            ),
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0 if selected is not None else 2
            if args.storage_action == "configure":
                from pathlib import Path

                config = configure_external_storage(Path(args.root), args.device_uuid)
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "storage_mode": "external",
                            "mount_point": config.mount_point.as_posix(),
                            "telemetry_root": config.telemetry_root.as_posix(),
                            "device_uuid": config.device_uuid,
                            "filesystem_type": config.filesystem_type,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
            if args.storage_action == "reset":
                removed = reset_external_config()
                print(json.dumps({"ok": True, "configuration_removed": removed, "telemetry_data_deleted": False}, indent=2))
                return 0
            config = load_external_config()
            if config is None:
                print(json.dumps({"configured": False, "storage_mode": "internal"}, indent=2))
                return 0
            storage = configured_storage(require_external=True)
            result = storage_status(storage)
            result.update(
                {
                    "configured": True,
                    "device_uuid": config.device_uuid,
                    "mount_point": config.mount_point.as_posix(),
                }
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["mount_verification"] == "VERIFIED" else 2
        except (OSError, TelemetryError) as exc:
            category = getattr(exc, "category", "STORAGE_COMMAND_FAILED")
            print(json.dumps({"ok": False, "error": category}, indent=2))
            return 2
    try:
        storage = configured_storage()
    except (OSError, TelemetryError) as exc:
        category = getattr(exc, "category", "TELEMETRY_CONFIGURATION_FAILED")
        print(json.dumps({"ok": False, "error": category}, indent=2))
        return 2

    if args.action == "enable":
        try:
            ensure_installation_salt(storage.paths.salt)
            storage.set_enabled(True)
        except (OSError, TelemetryError):
            print(json.dumps({"ok": False, "error": "TELEMETRY_ENABLE_FAILED"}, indent=2))
            return 2
        print(json.dumps({"ok": True, **storage_status(storage)}, indent=2, sort_keys=True))
        return 0
    if args.action == "disable":
        try:
            storage.set_enabled(False)
        except (OSError, TelemetryError):
            print(json.dumps({"ok": False, "error": "TELEMETRY_DISABLE_FAILED"}, indent=2))
            return 2
        print(json.dumps({"ok": True, **storage_status(storage)}, indent=2, sort_keys=True))
        return 0
    if args.action == "status":
        print(json.dumps(storage_status(storage), indent=2, sort_keys=True))
        return 0
    if args.action == "preflight":
        warning = storage.write_preflight()
        result = storage_status(storage)
        result.update({"ok": warning is None, "preflight": warning or "READY"})
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if warning is None else 2
    if args.action == "pending":
        values = pending_runs(storage, window_id=args.window_id)
        print(
            json.dumps(
                {
                    "pending_count": len(values),
                    "runs": [
                        {
                            "run_id": value["run_id"],
                            "window_id": value.get("window_id"),
                            "finished_at": value.get("finished_at"),
                        }
                        for value in values
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.action == "summary":
        grouping = "model" if args.by_model else "task_level" if args.by_task_level else None
        print(json.dumps(summarize(storage, group_by=grouping), indent=2, sort_keys=True))
        return 0
    record = inspect_run(storage, args.run_id, show_signature=args.show_task_signature)
    if record is None:
        print(json.dumps({"ok": False, "error": "RUN_NOT_FOUND_OR_INVALID"}, indent=2))
        return 2
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


def outcome_command(argv: list[str]) -> int:
    from .runtime.telemetry.errors import TelemetryError
    from .runtime.telemetry.config import configured_storage
    from .runtime.telemetry.outcome import latest_pending_run, record_outcome
    from .runtime.telemetry.schema import EDIT_MAGNITUDES, FAILURE_CATEGORIES, OPERATOR_OUTCOMES

    if not _interactive_operator_terminal():
        print(json.dumps({"ok": False, "warning": "OUTCOME_REQUIRES_INTERACTIVE_OPERATOR_TTY"}, indent=2))
        return 2

    parser = argparse.ArgumentParser(prog="smart-codex outcome")
    latest_mode = bool(argv and argv[0] == "latest")
    if latest_mode:
        parser.add_argument("latest", choices=["latest"])
        parser.add_argument("--window-id", required=True, choices=["aoia", "smart-router"])
        parser.add_argument("outcome", choices=sorted(OPERATOR_OUTCOMES))
    else:
        parser.add_argument("run_id")
        parser.add_argument("outcome", choices=sorted(OPERATOR_OUTCOMES))
    parser.add_argument("--tests-passed", type=int)
    parser.add_argument("--tests-failed", type=int)
    parser.add_argument("--verification-unavailable", action="store_true")
    parser.add_argument("--escalated-to")
    parser.add_argument("--edit-magnitude", choices=sorted(EDIT_MAGNITUDES))
    parser.add_argument("--followup-turns", type=int)
    parser.add_argument("--failure-category", choices=sorted(FAILURE_CATEGORIES))
    args = parser.parse_args(argv)
    if args.verification_unavailable and (args.tests_passed is not None or args.tests_failed is not None):
        parser.error("test counts cannot be combined with --verification-unavailable")
    if args.outcome == "rejected" and args.failure_category in {None, "none"}:
        parser.error("a rejected outcome requires --failure-category")
    if args.outcome == "accepted" and args.edit_magnitude not in {None, "none"}:
        parser.error("accepted requires --edit-magnitude none")
    try:
        storage = configured_storage()
        if latest_mode:
            latest = latest_pending_run(storage, window_id=args.window_id)
            if latest is None:
                print(json.dumps({"ok": False, "warning": "NO_PENDING_RUN_FOR_WINDOW"}, indent=2))
                return 2
            run_id = str(latest["run_id"])
        else:
            run_id = args.run_id
        result = record_outcome(
            storage,
            run_id,
            args.outcome,
            tests_passed=args.tests_passed,
            tests_failed=args.tests_failed,
            verification_unavailable=args.verification_unavailable,
            escalated_to=args.escalated_to,
            edit_magnitude=args.edit_magnitude,
            followup_turns=args.followup_turns,
            failure_category=args.failure_category,
        )
    except (OSError, TelemetryError):
        print(json.dumps({"ok": False, "run_id": locals().get("run_id"), "warning": "OUTCOME_REJECTED"}, indent=2))
        return 2
    print(
        json.dumps(
            {
                "ok": result.appended,
                "run_id": run_id,
                "warning": result.warning,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result.appended else 2


def _interactive_operator_terminal() -> bool:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        if os.getpgrp() != os.tcgetpgrp(sys.stdin.fileno()):
            return False
    except (OSError, AttributeError):
        return False
    process_id = os.getppid()
    for _ in range(12):
        if process_id <= 1:
            break
        try:
            command = (Path("/proc") / str(process_id) / "comm").read_text(
                encoding="utf-8"
            ).strip().casefold()
            stat_fields = (Path("/proc") / str(process_id) / "stat").read_text(
                encoding="utf-8"
            ).split()
            process_id = int(stat_fields[3])
        except (OSError, ValueError, IndexError):
            break
        if "codex" in command:
            return False
    return True


def print_decision(decision, argv: list[str], *, explain: bool) -> None:
    print(f"category: {decision.category}")
    print(f"risk: {decision.risk}")
    print(f"complexity: {decision.complexity}")
    print(f"action_danger: {decision.action_danger}")
    print(f"selected_profile: {decision.selected_profile}")
    print(f"selected_model: {decision.selected_model}")
    print(f"sandbox_mode: {decision.sandbox_mode}")
    print(f"approval_policy: {decision.approval_policy}")
    print(f"confidence: {decision.confidence:.2f}")
    print(f"dry_run: {decision.dry_run}")
    if decision.warning:
        print(f"warning: {decision.warning}")
    print(f"planned_command: {shlex.join(argv)}")
    if explain:
        print("decision_reasons:")
        for reason in decision.decision_reasons:
            print(f"- {reason}")


if __name__ == "__main__":
    raise SystemExit(main())
