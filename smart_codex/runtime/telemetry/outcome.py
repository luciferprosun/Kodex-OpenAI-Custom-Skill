"""Operator-authored, append-only outcome amendments."""

from __future__ import annotations

from typing import Any

from .errors import TelemetryValidationError
from .models import compute_record_hash, new_id, utc_now, verify_record_hash
from .schema import EDIT_MAGNITUDES, FAILURE_CATEGORIES, OPERATOR_OUTCOMES, SCHEMA_VERSION
from .storage import AppendResult, LocalTelemetryStorage
from .validator import validate_outcome_record, validate_run_record


def find_run(storage: LocalTelemetryStorage, run_id: str) -> dict[str, Any] | None:
    for record in storage.iter_records():
        if record.get("record_type") == "run" and record.get("run_id") == run_id:
            try:
                validate_run_record(record)
            except TelemetryValidationError:
                return None
            return record
    return None


def pending_runs(
    storage: LocalTelemetryStorage,
    *,
    window_id: str | None = None,
) -> list[dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    outcome_links: list[tuple[str, str]] = []
    for record in storage.iter_records():
        try:
            if record.get("record_type") == "run":
                validate_run_record(record)
                if record.get("synthetic") is True:
                    continue
                if window_id is None or record.get("window_id") == window_id:
                    runs[str(record["run_id"])] = record
            elif record.get("record_type") == "outcome":
                validate_outcome_record(record)
                outcome_links.append((str(record["run_id"]), str(record["original_record_hash"])))
        except TelemetryValidationError:
            continue
    labeled = {
        run_id
        for run_id, original_hash in outcome_links
        if run_id in runs and runs[run_id].get("record_hash") == original_hash
    }
    values = [record for run_id, record in runs.items() if run_id not in labeled]
    values.sort(key=lambda item: str(item.get("finished_at", "")), reverse=True)
    return values


def latest_pending_run(
    storage: LocalTelemetryStorage,
    *,
    window_id: str,
) -> dict[str, Any] | None:
    values = pending_runs(storage, window_id=window_id)
    return values[0] if values else None


def build_outcome_record(
    run: dict[str, Any],
    outcome: str,
    *,
    tests_passed: int | None = None,
    tests_failed: int | None = None,
    verification_unavailable: bool = False,
    escalated_to: str | None = None,
    edit_magnitude: str | None = None,
    followup_turns: int | None = None,
    failure_category: str | None = None,
    supersedes_outcome_id: str | None = None,
) -> dict[str, Any]:
    if outcome not in OPERATOR_OUTCOMES:
        raise TelemetryValidationError("INVALID_OPERATOR_OUTCOME")
    if not verify_record_hash(run):
        raise TelemetryValidationError("ORIGINAL_RECORD_HASH_MISMATCH")
    if edit_magnitude is None:
        edit_magnitude = {
            "accepted": "none",
            "accepted-with-edits": "unknown",
            "rejected": "unknown",
            "aborted": "unknown",
        }[outcome]
    if failure_category is None:
        if outcome == "rejected":
            raise TelemetryValidationError("REJECTED_OUTCOME_REQUIRES_FAILURE")
        failure_category = {
            "accepted": "none",
            "accepted-with-edits": "none",
            "aborted": "operator_abort",
        }[outcome]
    if edit_magnitude not in EDIT_MAGNITUDES:
        raise TelemetryValidationError("INVALID_EDIT_MAGNITUDE")
    if failure_category not in FAILURE_CATEGORIES:
        raise TelemetryValidationError("INVALID_FAILURE_CATEGORY")
    has_passed = tests_passed is not None
    has_failed = tests_failed is not None
    if verification_unavailable and (has_passed or has_failed):
        raise TelemetryValidationError("CONFLICTING_VERIFICATION_EVIDENCE")
    if has_passed != has_failed:
        raise TelemetryValidationError("INCOMPLETE_TEST_COUNTS")
    if verification_unavailable:
        verification_available: bool | None = False
        verifier_type = "unavailable"
        verifier_result = "unavailable"
    elif has_passed and has_failed:
        verification_available = True
        verifier_type = "tests"
        verifier_result = "failed" if tests_failed > 0 else "passed"
    else:
        verification_available = None
        verifier_type = None
        verifier_result = None
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "outcome",
        "outcome_id": new_id(),
        "run_id": run["run_id"],
        "original_record_hash": run["record_hash"],
        "operator_outcome": outcome,
        "operator_outcome_at": utc_now(),
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "verification_available": verification_available,
        "verifier_type": verifier_type,
        "verifier_result": verifier_result,
        "escalated_to": escalated_to,
        "edit_magnitude": edit_magnitude,
        "followup_turns": followup_turns,
        "failure_category": failure_category,
        "supersedes_outcome_id": supersedes_outcome_id,
        "privacy_classification": "metadata_only_hmac",
        "record_hash": "",
    }
    record["record_hash"] = compute_record_hash(record)
    validate_outcome_record(record)
    return record


def record_outcome(
    storage: LocalTelemetryStorage,
    run_id: str,
    outcome: str,
    *,
    tests_passed: int | None = None,
    tests_failed: int | None = None,
    verification_unavailable: bool = False,
    escalated_to: str | None = None,
    edit_magnitude: str | None = None,
    followup_turns: int | None = None,
    failure_category: str | None = None,
) -> AppendResult:
    if not storage.enabled():
        return AppendResult(False, "TELEMETRY_DISABLED")
    run = find_run(storage, run_id)
    if run is None:
        return AppendResult(False, "RUN_NOT_FOUND_OR_INVALID")
    prior: list[dict[str, Any]] = []
    for record in storage.iter_records():
        if record.get("record_type") != "outcome" or record.get("run_id") != run_id:
            continue
        try:
            validate_outcome_record(record)
        except TelemetryValidationError:
            continue
        if record.get("original_record_hash") == run.get("record_hash"):
            prior.append(record)
    prior.sort(key=lambda value: str(value.get("operator_outcome_at", "")))
    supersedes = prior[-1].get("outcome_id") if prior else None
    record = build_outcome_record(
        run,
        outcome,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        verification_unavailable=verification_unavailable,
        escalated_to=escalated_to,
        edit_magnitude=edit_magnitude,
        followup_turns=followup_turns,
        failure_category=failure_category,
        supersedes_outcome_id=supersedes if isinstance(supersedes, str) else None,
    )
    return storage.append(record)
