"""Record construction and integrity helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
import uuid

from smart_codex import __version__ as router_version

from .schema import SCHEMA_VERSION, expected_missing_fields, unknown_measurement_sources


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def canonical_json(record: dict[str, Any], *, include_hash: bool = True) -> str:
    payload = record if include_hash else {key: value for key, value in record.items() if key != "record_hash"}
    return json.dumps(payload, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))


def compute_record_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(record, include_hash=False).encode("utf-8")).hexdigest()


def seal_record(record: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(record)
    sealed["missing_fields"] = expected_missing_fields(sealed)
    sealed["record_hash"] = compute_record_hash(sealed)
    return sealed


def verify_record_hash(record: dict[str, Any]) -> bool:
    value = record.get("record_hash")
    return isinstance(value, str) and value == compute_record_hash(record)


@dataclass(frozen=True)
class RunMetadata:
    task_signature: str
    task_domain: str
    task_subdomain: str | None
    task_difficulty: str
    task_scope: str
    task_risk: str
    verification_available: bool | None
    requested_model: str | None
    recommended_model: str | None
    launched_model: str | None
    backend_model: str | None
    model_identity_status: str
    reasoning_effort: str | None
    agent_count: int | None
    sandbox: str
    approval_policy: str
    product_surface: str
    session_id: str | None = None


def new_run_record(metadata: RunMetadata, *, started_at: str, run_id: str | None = None) -> dict[str, Any]:
    sources = unknown_measurement_sources()
    for field in (
        "requested_model",
        "recommended_model",
        "launched_model",
        "reasoning_effort",
        "agent_count",
    ):
        if getattr(metadata, field) is not None:
            sources[field] = "client_reported"
    if metadata.backend_model is not None:
        sources["backend_model"] = "provider_reported"
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "run",
        "run_id": run_id or new_id(),
        "session_id": metadata.session_id,
        "started_at": started_at,
        "finished_at": None,
        "wall_time_ms": None,
        "router_version": router_version,
        "router_decision_id": new_id(),
        "task_signature": metadata.task_signature,
        "task_domain": metadata.task_domain,
        "task_subdomain": metadata.task_subdomain,
        "task_difficulty": metadata.task_difficulty,
        "task_scope": metadata.task_scope,
        "task_risk": metadata.task_risk,
        "verification_available": metadata.verification_available,
        "requested_model": metadata.requested_model,
        "recommended_model": metadata.recommended_model,
        "launched_model": metadata.launched_model,
        "backend_model": metadata.backend_model,
        "model_identity_status": metadata.model_identity_status,
        "reasoning_effort": metadata.reasoning_effort,
        "agent_count": metadata.agent_count,
        "sandbox": metadata.sandbox,
        "approval_policy": metadata.approval_policy,
        "input_tokens": None,
        "non_cached_input_tokens": None,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "visible_output_tokens": None,
        "total_reported_tokens": None,
        "request_count": None,
        "tool_call_count": None,
        "tool_calls_by_type": None,
        "invalid_tool_call_count": None,
        "retry_count": None,
        "escalation_count": None,
        "compaction_count": None,
        "verifier_type": None,
        "verifier_result": None,
        "tests_passed": None,
        "tests_failed": None,
        "operator_outcome": None,
        "operator_outcome_at": None,
        "measurement_sources": sources,
        "missing_fields": [],
        "privacy_classification": "metadata_only_hmac",
        "product_surface": metadata.product_surface,
        "counter_reconciliation": "unknown",
        "duplicate_event_count": 0,
        "invalid_event_count": 0,
        "collector_status": "completed",
        "process_exit_code": None,
        "record_hash": "",
    }
