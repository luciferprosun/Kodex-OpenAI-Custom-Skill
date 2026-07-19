"""Strict validation for telemetry run and outcome records."""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any
import uuid

from .errors import TelemetryValidationError
from .models import canonical_json, verify_record_hash
from .privacy import scan_record
from .schema import (
    COLLECTOR_STATUSES,
    EDIT_MAGNITUDES,
    FAILURE_CATEGORIES,
    LEGACY_OUTCOME_RECORD_FIELDS,
    LEGACY_RUN_RECORD_FIELDS,
    LEGACY_SCHEMA_VERSION,
    MAX_RECORD_BYTES,
    MEASUREMENT_STATUSES,
    MODEL_IDENTITY_STATUSES,
    OPERATOR_OUTCOMES,
    OUTCOME_RECORD_FIELDS,
    RECONCILIATION_METHODS,
    RUN_RECORD_FIELDS,
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    SOURCED_FIELDS,
    TASK_DIFFICULTIES,
    TASK_RISKS,
    TASK_SCOPES,
    WINDOW_IDS,
    expected_missing_fields,
)


SAFE_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,159}$")
HEX_64 = re.compile(r"^[a-f0-9]{64}$")


def _fail(category: str) -> None:
    raise TelemetryValidationError(category)


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        _fail(f"INVALID_{field.upper()}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _fail(f"INVALID_{field.upper()}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(f"INVALID_{field.upper()}")
    return parsed


def _uuid(value: object, field: str) -> None:
    if not isinstance(value, str):
        _fail(f"INVALID_{field.upper()}")
    try:
        uuid.UUID(value)
    except ValueError:
        _fail(f"INVALID_{field.upper()}")


def _safe_optional(value: object, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or SAFE_VALUE.fullmatch(value) is None:
        _fail(f"INVALID_{field.upper()}")


def _nonnegative_optional(value: object, field: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(f"INVALID_{field.upper()}")


def _validate_hash(value: object, field: str) -> None:
    if not isinstance(value, str) or HEX_64.fullmatch(value) is None:
        _fail(f"INVALID_{field.upper()}")


def _validate_size(record: dict[str, Any]) -> None:
    try:
        size = len(canonical_json(record).encode("utf-8"))
    except (TypeError, ValueError, OverflowError):
        _fail("NON_JSON_VALUE")
    if size > MAX_RECORD_BYTES:
        _fail("RECORD_TOO_LARGE")


def validate_run_record(record: dict[str, Any]) -> None:
    if not isinstance(record, dict):
        _fail("RUN_NOT_OBJECT")
    version = record.get("schema_version")
    expected_fields = LEGACY_RUN_RECORD_FIELDS if version == LEGACY_SCHEMA_VERSION else RUN_RECORD_FIELDS
    if set(record) != expected_fields:
        _fail("RUN_FIELD_SET_MISMATCH")
    if version not in SUPPORTED_SCHEMA_VERSIONS or record.get("record_type") != "run":
        _fail("SCHEMA_VERSION_MISMATCH")

    _uuid(record.get("run_id"), "run_id")
    _uuid(record.get("router_decision_id"), "router_decision_id")
    _validate_hash(record.get("task_signature"), "task_signature")
    _validate_hash(record.get("record_hash"), "record_hash")
    if version == SCHEMA_VERSION:
        workspace_signature = record.get("workspace_signature")
        if workspace_signature is not None:
            _validate_hash(workspace_signature, "workspace_signature")
        if record.get("window_id") not in WINDOW_IDS | {None}:
            _fail("INVALID_WINDOW_ID")
        if not isinstance(record.get("synthetic"), bool):
            _fail("INVALID_SYNTHETIC_FLAG")

    started = _timestamp(record.get("started_at"), "started_at")
    finished = _timestamp(record.get("finished_at"), "finished_at")
    if finished < started:
        _fail("NON_MONOTONIC_TIME")

    for field in (
        "wall_time_ms",
        "agent_count",
        "input_tokens",
        "non_cached_input_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "visible_output_tokens",
        "total_reported_tokens",
        "request_count",
        "tool_call_count",
        "invalid_tool_call_count",
        "retry_count",
        "escalation_count",
        "compaction_count",
        "tests_passed",
        "tests_failed",
    ):
        _nonnegative_optional(record.get(field), field)
    if record["wall_time_ms"] is None:
        _fail("MISSING_WALL_TIME")
    process_exit = record.get("process_exit_code")
    if process_exit is not None and (isinstance(process_exit, bool) or not isinstance(process_exit, int)):
        _fail("INVALID_PROCESS_EXIT_CODE")

    for field in (
        "session_id",
        "router_version",
        "task_domain",
        "task_subdomain",
        "requested_model",
        "recommended_model",
        "launched_model",
        "backend_model",
        "reasoning_effort",
        "sandbox",
        "approval_policy",
        "verifier_type",
        "verifier_result",
        "operator_outcome",
        "operator_outcome_at",
        "privacy_classification",
        "product_surface",
    ):
        _safe_optional(record.get(field), field)
    if version == SCHEMA_VERSION:
        for field in ("window_id", "router_policy_version", "codex_protocol_version"):
            _safe_optional(record.get(field), field)
        if record.get("product_surface") == "codex_app_server_research":
            if record.get("window_id") not in WINDOW_IDS:
                _fail("MISSING_RESEARCH_WINDOW_ID")
            if record.get("workspace_signature") is None:
                _fail("MISSING_WORKSPACE_SIGNATURE")
            if record.get("codex_protocol_version") is None:
                _fail("MISSING_CODEX_PROTOCOL_VERSION")
    if not isinstance(record.get("task_domain"), str):
        _fail("MISSING_TASK_DOMAIN")
    if record.get("task_difficulty") not in TASK_DIFFICULTIES:
        _fail("INVALID_TASK_DIFFICULTY")
    if record.get("task_scope") not in TASK_SCOPES:
        _fail("INVALID_TASK_SCOPE")
    if record.get("task_risk") not in TASK_RISKS:
        _fail("INVALID_TASK_RISK")
    if record.get("model_identity_status") not in MODEL_IDENTITY_STATUSES:
        _fail("INVALID_MODEL_IDENTITY_STATUS")
    if record.get("counter_reconciliation") not in RECONCILIATION_METHODS:
        _fail("INVALID_RECONCILIATION")
    if record.get("collector_status") not in COLLECTOR_STATUSES:
        _fail("INVALID_COLLECTOR_STATUS")
    if record.get("privacy_classification") != "metadata_only_hmac":
        _fail("INVALID_PRIVACY_CLASSIFICATION")
    if record.get("verification_available") not in {True, False, None}:
        _fail("INVALID_VERIFICATION_AVAILABLE")
    if record.get("operator_outcome") is not None or record.get("operator_outcome_at") is not None:
        _fail("SELF_ACCEPTANCE_FORBIDDEN")

    for field in ("duplicate_event_count", "invalid_event_count"):
        value = record.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            _fail(f"INVALID_{field.upper()}")

    tools = record.get("tool_calls_by_type")
    if tools is not None:
        if not isinstance(tools, dict) or not tools:
            _fail("INVALID_TOOL_CALLS_BY_TYPE")
        for tool, count in tools.items():
            if not isinstance(tool, str) or SAFE_VALUE.fullmatch(tool) is None:
                _fail("INVALID_TOOL_TYPE")
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                _fail("INVALID_TOOL_COUNT")
        if record.get("tool_call_count") != sum(tools.values()):
            _fail("TOOL_COUNT_MISMATCH")

    input_tokens = record.get("input_tokens")
    cached = record.get("cached_input_tokens")
    non_cached = record.get("non_cached_input_tokens")
    if input_tokens is not None and cached is not None:
        if cached > input_tokens:
            _fail("CACHED_INPUT_EXCEEDS_INPUT")
        if non_cached is not None and non_cached + cached != input_tokens:
            _fail("INPUT_TOKEN_MISMATCH")
    total = record.get("total_reported_tokens")
    visible = record.get("visible_output_tokens")
    reasoning = record.get("reasoning_tokens")
    if None not in (total, input_tokens, visible, reasoning):
        if total != input_tokens + visible + reasoning:
            _fail("TOTAL_TOKEN_MISMATCH")

    sources = record.get("measurement_sources")
    if not isinstance(sources, dict) or set(sources) != SOURCED_FIELDS:
        _fail("MEASUREMENT_SOURCE_SET_MISMATCH")
    for field, status in sources.items():
        if status not in MEASUREMENT_STATUSES:
            _fail("INVALID_MEASUREMENT_SOURCE")
        if record.get(field) is None and status != "unknown":
            _fail("SOURCE_FOR_MISSING_VALUE")
        if record.get(field) is not None and status == "unknown":
            _fail("MISSING_MEASUREMENT_SOURCE")

    missing = record.get("missing_fields")
    if not isinstance(missing, list) or missing != expected_missing_fields(record):
        _fail("MISSINGNESS_MISMATCH")
    if not all(isinstance(value, str) for value in missing):
        _fail("INVALID_MISSING_FIELDS")
    if not verify_record_hash(record):
        _fail("RECORD_HASH_MISMATCH")
    scan_record(record)
    _validate_size(record)


def validate_outcome_record(record: dict[str, Any]) -> None:
    if not isinstance(record, dict):
        _fail("OUTCOME_NOT_OBJECT")
    version = record.get("schema_version")
    expected_fields = LEGACY_OUTCOME_RECORD_FIELDS if version == LEGACY_SCHEMA_VERSION else OUTCOME_RECORD_FIELDS
    if set(record) != expected_fields:
        _fail("OUTCOME_FIELD_SET_MISMATCH")
    if version not in SUPPORTED_SCHEMA_VERSIONS or record.get("record_type") != "outcome":
        _fail("SCHEMA_VERSION_MISMATCH")
    _uuid(record.get("outcome_id"), "outcome_id")
    _uuid(record.get("run_id"), "run_id")
    _validate_hash(record.get("original_record_hash"), "original_record_hash")
    _validate_hash(record.get("record_hash"), "record_hash")
    _timestamp(record.get("operator_outcome_at"), "operator_outcome_at")
    if record.get("operator_outcome") not in OPERATOR_OUTCOMES:
        _fail("INVALID_OPERATOR_OUTCOME")
    if version == SCHEMA_VERSION:
        if record.get("edit_magnitude") not in EDIT_MAGNITUDES:
            _fail("INVALID_EDIT_MAGNITUDE")
        if record.get("failure_category") not in FAILURE_CATEGORIES:
            _fail("INVALID_FAILURE_CATEGORY")
        _nonnegative_optional(record.get("followup_turns"), "followup_turns")
        supersedes = record.get("supersedes_outcome_id")
        if supersedes is not None:
            _uuid(supersedes, "supersedes_outcome_id")
        outcome = record.get("operator_outcome")
        edit = record.get("edit_magnitude")
        failure = record.get("failure_category")
        if outcome == "accepted" and (edit != "none" or failure != "none"):
            _fail("INCONSISTENT_ACCEPTED_OUTCOME")
        if outcome == "accepted-with-edits" and (
            edit not in {"minor", "major", "unknown"} or failure != "none"
        ):
            _fail("INCONSISTENT_EDITED_OUTCOME")
        if outcome == "rejected" and failure == "none":
            _fail("REJECTED_OUTCOME_REQUIRES_FAILURE")
        if outcome == "aborted" and failure not in {
            "operator_abort",
            "environment_failure",
            "safety_block",
            "other_categorical",
        }:
            _fail("INCONSISTENT_ABORTED_OUTCOME")
    for field in ("tests_passed", "tests_failed"):
        _nonnegative_optional(record.get(field), field)
    if record.get("verification_available") not in {True, False, None}:
        _fail("INVALID_VERIFICATION_AVAILABLE")
    for field in ("verifier_type", "verifier_result", "escalated_to"):
        _safe_optional(record.get(field), field)
    if record.get("privacy_classification") != "metadata_only_hmac":
        _fail("INVALID_PRIVACY_CLASSIFICATION")
    verification_available = record.get("verification_available")
    tests_passed = record.get("tests_passed")
    tests_failed = record.get("tests_failed")
    verifier_type = record.get("verifier_type")
    verifier_result = record.get("verifier_result")
    if verification_available is True:
        if tests_passed is None or tests_failed is None:
            _fail("INCOMPLETE_TEST_COUNTS")
        if verifier_type != "tests":
            _fail("INVALID_VERIFIER_TYPE")
        expected_result = "failed" if tests_failed > 0 else "passed"
        if verifier_result != expected_result:
            _fail("VERIFIER_RESULT_MISMATCH")
    elif verification_available is False:
        if tests_passed is not None or tests_failed is not None:
            _fail("CONFLICTING_VERIFICATION_EVIDENCE")
        if verifier_type != "unavailable" or verifier_result != "unavailable":
            _fail("INVALID_UNAVAILABLE_VERIFICATION")
    elif any(value is not None for value in (tests_passed, tests_failed, verifier_type, verifier_result)):
        _fail("UNLINKED_VERIFICATION_EVIDENCE")
    if not verify_record_hash(record):
        _fail("RECORD_HASH_MISMATCH")
    scan_record(record)
    _validate_size(record)


def validate_json_schema_document(value: object) -> None:
    if not isinstance(value, dict):
        _fail("SCHEMA_NOT_OBJECT")
    if value.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        _fail("SCHEMA_DRAFT_MISMATCH")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        _fail("SCHEMA_NOT_JSON")
