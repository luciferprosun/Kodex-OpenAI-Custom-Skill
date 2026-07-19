"""Versioned local telemetry contract constants."""

from __future__ import annotations


SCHEMA_VERSION = "2.0.0"
LEGACY_SCHEMA_VERSION = "1.0.0"
SUPPORTED_SCHEMA_VERSIONS = {LEGACY_SCHEMA_VERSION, SCHEMA_VERSION}
MAX_RECORD_BYTES = 64 * 1024

MODEL_IDENTITY_STATUSES = {
    "provider_reported",
    "service_reported",
    "client_requested_only",
    "inferred_alias",
    "unknown",
}
MEASUREMENT_STATUSES = {
    "measured",
    "provider_reported",
    "client_reported",
    "reconstructed",
    "unknown",
}
TASK_DIFFICULTIES = {"low", "medium", "high", "unknown"}
TASK_RISKS = {"low", "medium", "high", "critical", "unknown"}
TASK_SCOPES = {
    "none",
    "local",
    "remote",
    "network",
    "system",
    "repo",
    "module",
    "single_file",
    "unknown",
}
OPERATOR_OUTCOMES = {
    "accepted",
    "accepted-with-edits",
    "rejected",
    "aborted",
}
WINDOW_IDS = {"aoia", "smart-router"}
EDIT_MAGNITUDES = {"none", "minor", "major", "unknown"}
FAILURE_CATEGORIES = {
    "none",
    "incomplete",
    "incorrect_approach",
    "test_failure",
    "safety_block",
    "environment_failure",
    "operator_abort",
    "other_categorical",
}
COLLECTOR_STATUSES = {
    "completed",
    "completed_with_invalid_events",
    "process_error",
    "aborted",
    "collector_interrupted",
    "partial_unreconciled",
}
RECONCILIATION_METHODS = {
    "per_request_sum",
    "final_cumulative_snapshot",
    "mixed_reconciled",
    "unknown",
}

LEGACY_RUN_RECORD_FIELDS = {
    "schema_version",
    "record_type",
    "run_id",
    "session_id",
    "started_at",
    "finished_at",
    "wall_time_ms",
    "router_version",
    "router_decision_id",
    "task_signature",
    "task_domain",
    "task_subdomain",
    "task_difficulty",
    "task_scope",
    "task_risk",
    "verification_available",
    "requested_model",
    "recommended_model",
    "launched_model",
    "backend_model",
    "model_identity_status",
    "reasoning_effort",
    "agent_count",
    "sandbox",
    "approval_policy",
    "input_tokens",
    "non_cached_input_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "visible_output_tokens",
    "total_reported_tokens",
    "request_count",
    "tool_call_count",
    "tool_calls_by_type",
    "invalid_tool_call_count",
    "retry_count",
    "escalation_count",
    "compaction_count",
    "verifier_type",
    "verifier_result",
    "tests_passed",
    "tests_failed",
    "operator_outcome",
    "operator_outcome_at",
    "measurement_sources",
    "missing_fields",
    "privacy_classification",
    "product_surface",
    "counter_reconciliation",
    "duplicate_event_count",
    "invalid_event_count",
    "collector_status",
    "process_exit_code",
    "record_hash",
}

RUN_RECORD_FIELDS = LEGACY_RUN_RECORD_FIELDS | {
    "window_id",
    "workspace_signature",
    "router_policy_version",
    "codex_protocol_version",
    "synthetic",
}

LEGACY_OUTCOME_RECORD_FIELDS = {
    "schema_version",
    "record_type",
    "outcome_id",
    "run_id",
    "original_record_hash",
    "operator_outcome",
    "operator_outcome_at",
    "tests_passed",
    "tests_failed",
    "verification_available",
    "verifier_type",
    "verifier_result",
    "escalated_to",
    "privacy_classification",
    "record_hash",
}

OUTCOME_RECORD_FIELDS = LEGACY_OUTCOME_RECORD_FIELDS | {
    "edit_magnitude",
    "followup_turns",
    "failure_category",
    "supersedes_outcome_id",
}

SOURCED_FIELDS = {
    "wall_time_ms",
    "requested_model",
    "recommended_model",
    "launched_model",
    "backend_model",
    "reasoning_effort",
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
    "verifier_result",
    "tests_passed",
    "tests_failed",
}

MISSINGNESS_FIELDS = {
    "session_id",
    "task_subdomain",
    "verification_available",
    "requested_model",
    "recommended_model",
    "launched_model",
    "backend_model",
    "reasoning_effort",
    "agent_count",
    "input_tokens",
    "non_cached_input_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "visible_output_tokens",
    "total_reported_tokens",
    "request_count",
    "tool_call_count",
    "tool_calls_by_type",
    "invalid_tool_call_count",
    "retry_count",
    "escalation_count",
    "compaction_count",
    "verifier_type",
    "verifier_result",
    "tests_passed",
    "tests_failed",
    "operator_outcome",
    "operator_outcome_at",
    "process_exit_code",
    "window_id",
    "workspace_signature",
    "router_policy_version",
    "codex_protocol_version",
}

LEGACY_MISSINGNESS_FIELDS = MISSINGNESS_FIELDS - {
    "window_id",
    "workspace_signature",
    "router_policy_version",
    "codex_protocol_version",
}


def unknown_measurement_sources() -> dict[str, str]:
    return {field: "unknown" for field in sorted(SOURCED_FIELDS)}


def expected_missing_fields(record: dict[str, object]) -> list[str]:
    fields = (
        LEGACY_MISSINGNESS_FIELDS
        if record.get("schema_version") == LEGACY_SCHEMA_VERSION
        else MISSINGNESS_FIELDS
    )
    return sorted(field for field in fields if record.get(field) is None)
