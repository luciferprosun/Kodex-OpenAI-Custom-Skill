"""Interactive, privacy-safe rating of the latest SmartRouter research run."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import sys
from typing import Any, TextIO

from smart_codex.runtime.telemetry.config import configured_storage
from smart_codex.runtime.telemetry.errors import TelemetryError
from smart_codex.runtime.telemetry.outcome import latest_pending_run, record_outcome


WINDOW_ID = "smart-router"

OUTCOME_CHOICES: dict[str, tuple[str, dict[str, Any]]] = {
    "1": ("accepted without edits", {"outcome": "accepted", "edit_magnitude": "none"}),
    "2": (
        "accepted with minor edits",
        {"outcome": "accepted-with-edits", "edit_magnitude": "minor"},
    ),
    "3": (
        "accepted with major edits",
        {"outcome": "accepted-with-edits", "edit_magnitude": "major"},
    ),
    "4": ("rejected", {"outcome": "rejected"}),
    "5": ("aborted", {"outcome": "aborted"}),
    "6": (
        "accepted but verification unavailable",
        {
            "outcome": "accepted",
            "edit_magnitude": "none",
            "verification_unavailable": True,
        },
    ),
}

FAILURE_CHOICES = {
    "1": "incomplete",
    "2": "incorrect_approach",
    "3": "test_failure",
    "4": "safety_block",
    "5": "environment_failure",
    "6": "other",
}


def foreground_interactive_tty() -> bool:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        return os.getpgrp() == os.tcgetpgrp(sys.stdin.fileno())
    except (OSError, AttributeError):
        return False


def has_codex_ancestor(*, start_pid: int | None = None, proc_root: Path = Path("/proc")) -> bool:
    process_id = os.getppid() if start_pid is None else start_pid
    for _ in range(32):
        if process_id <= 1:
            return False
        process_root = proc_root / str(process_id)
        try:
            command = (process_root / "comm").read_text(encoding="utf-8").strip().casefold()
            stat_value = (process_root / "stat").read_text(encoding="utf-8")
            closing_parenthesis = stat_value.rfind(")")
            if closing_parenthesis < 0:
                return False
            stat_fields = stat_value[closing_parenthesis + 1 :].split()
            process_id = int(stat_fields[1])
        except (OSError, ValueError, IndexError) as exc:
            raise RuntimeError("PROCESS_ANCESTRY_UNVERIFIED") from exc
        if "codex" in command:
            return True
    return False


def _verification_status(run: dict[str, Any]) -> str:
    available = run.get("verification_available")
    result = run.get("verifier_result")
    if available is False:
        return "unavailable"
    if available is True and result in {"passed", "failed"}:
        return str(result)
    if available is True:
        return "available"
    return "unknown"


def _show_metadata(run: dict[str, Any], output: TextIO) -> None:
    print(f"Run ID: {run['run_id']}", file=output)
    print(f"Window ID: {run['window_id']}", file=output)
    print(f"Finished time: {run['finished_at']}", file=output)
    if run.get("backend_model") is not None:
        print(f"Backend model: {run['backend_model']}", file=output)
    if run.get("reasoning_effort") is not None:
        print(f"Reasoning effort: {run['reasoning_effort']}", file=output)
    print(f"Collector status: {run['collector_status']}", file=output)
    print(f"Verification status: {_verification_status(run)}", file=output)


def _ask_listed_choice(
    prompt: str,
    choices: dict[str, Any],
    *,
    input_fn: Callable[[str], str],
    output: TextIO,
) -> str | None:
    while True:
        try:
            choice = input_fn(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("Selection cancelled; no outcome was recorded.", file=output)
            return None
        if choice in choices:
            return choice
        print("Choose exactly one listed number.", file=output)


def main(
    *,
    input_fn: Callable[[str], str] | None = None,
    output: TextIO | None = None,
    error: TextIO | None = None,
) -> int:
    output = sys.stdout if output is None else output
    error = sys.stderr if error is None else error
    input_fn = input if input_fn is None else input_fn

    if not foreground_interactive_tty():
        print("SmartRouter outcome refused safely: INTERACTIVE_FOREGROUND_TTY_REQUIRED.", file=error)
        return 2
    try:
        beneath_codex = has_codex_ancestor()
    except RuntimeError:
        print("SmartRouter outcome refused safely: PROCESS_ANCESTRY_UNVERIFIED.", file=error)
        return 2
    if beneath_codex:
        print("SmartRouter outcome refused safely: CODEX_ANCESTOR_DETECTED.", file=error)
        return 2

    try:
        storage = configured_storage(require_external=True)
        if storage.write_preflight() is not None:
            print("SmartRouter outcome refused safely: TELEMETRY_STORAGE_NOT_READY.", file=error)
            return 2
        run = latest_pending_run(storage, window_id=WINDOW_ID)
    except (OSError, TelemetryError):
        print("SmartRouter outcome refused safely: TELEMETRY_STORAGE_UNAVAILABLE.", file=error)
        return 2

    if run is None:
        print("SmartRouter outcome refused safely: NO_PENDING_SMART_ROUTER_RUN.", file=error)
        return 2
    if run.get("window_id") != WINDOW_ID or run.get("synthetic") is not False:
        print("SmartRouter outcome refused safely: PENDING_RUN_VALIDATION_FAILED.", file=error)
        return 2

    _show_metadata(run, output)
    print("1 — accepted without edits", file=output)
    print("2 — accepted with minor edits", file=output)
    print("3 — accepted with major edits", file=output)
    print("4 — rejected", file=output)
    print("5 — aborted", file=output)
    print("6 — accepted but verification unavailable", file=output)
    choice = _ask_listed_choice(
        "Choose one outcome [1-6]: ",
        OUTCOME_CHOICES,
        input_fn=input_fn,
        output=output,
    )
    if choice is None:
        return 2

    _, outcome_arguments = OUTCOME_CHOICES[choice]
    outcome_arguments = dict(outcome_arguments)
    if choice == "4":
        print("1 — incomplete", file=output)
        print("2 — incorrect approach", file=output)
        print("3 — test failure", file=output)
        print("4 — safety block", file=output)
        print("5 — environment failure", file=output)
        print("6 — other", file=output)
        failure_choice = _ask_listed_choice(
            "Choose one failure category [1-6]: ",
            FAILURE_CHOICES,
            input_fn=input_fn,
            output=output,
        )
        if failure_choice is None:
            return 2
        outcome_arguments["failure_category"] = FAILURE_CHOICES[failure_choice]

    try:
        current = latest_pending_run(storage, window_id=WINDOW_ID)
        if current is None or current.get("run_id") != run.get("run_id"):
            print("SmartRouter outcome refused safely: PENDING_RUN_CHANGED.", file=error)
            return 2
        result = record_outcome(storage, str(run["run_id"]), **outcome_arguments)
    except (OSError, TelemetryError, TypeError, ValueError):
        print("SmartRouter outcome refused safely: OUTCOME_NOT_RECORDED.", file=error)
        return 2
    if not result.appended:
        print("SmartRouter outcome refused safely: OUTCOME_NOT_RECORDED.", file=error)
        return 2

    print("Outcome recorded.", file=output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
