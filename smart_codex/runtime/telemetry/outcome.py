"""Operator-authored, append-only outcome amendments."""

from __future__ import annotations

from typing import Any

from .errors import TelemetryValidationError
from .models import compute_record_hash, new_id, utc_now, verify_record_hash
from .schema import OPERATOR_OUTCOMES, SCHEMA_VERSION
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


def build_outcome_record(
    run: dict[str, Any],
    outcome: str,
    *,
    tests_passed: int | None = None,
    tests_failed: int | None = None,
    verification_unavailable: bool = False,
    escalated_to: str | None = None,
) -> dict[str, Any]:
    if outcome not in OPERATOR_OUTCOMES:
        raise TelemetryValidationError("INVALID_OPERATOR_OUTCOME")
    if not verify_record_hash(run):
        raise TelemetryValidationError("ORIGINAL_RECORD_HASH_MISMATCH")
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
) -> AppendResult:
    if not storage.enabled():
        return AppendResult(False, "TELEMETRY_DISABLED")
    run = find_run(storage, run_id)
    if run is None:
        return AppendResult(False, "RUN_NOT_FOUND_OR_INVALID")
    record = build_outcome_record(
        run,
        outcome,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        verification_unavailable=verification_unavailable,
        escalated_to=escalated_to,
    )
    return storage.append(record)
