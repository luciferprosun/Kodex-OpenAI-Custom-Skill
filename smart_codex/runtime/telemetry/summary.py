"""Small local summaries over comparable telemetry strata."""

from __future__ import annotations

from collections import defaultdict
import math
import statistics
from typing import Any, Iterable

from .models import verify_record_hash
from .schema import SCHEMA_VERSION
from .storage import LocalTelemetryStorage
from .validator import validate_outcome_record, validate_run_record
from .errors import TelemetryValidationError


MIN_MEDIAN_SAMPLES = 5
MIN_CALIBRATION_SAMPLES = 30


def load_valid_records(storage: LocalTelemetryStorage) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runs: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    for record in storage.iter_records():
        try:
            if record.get("record_type") == "run":
                validate_run_record(record)
                runs.append(record)
            elif record.get("record_type") == "outcome":
                validate_outcome_record(record)
                outcomes.append(record)
        except TelemetryValidationError:
            continue
    run_hashes = {run["run_id"]: run["record_hash"] for run in runs}
    outcomes = [
        outcome
        for outcome in outcomes
        if run_hashes.get(outcome["run_id"]) == outcome["original_record_hash"]
    ]
    return runs, outcomes


def latest_outcomes(outcomes: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for outcome in outcomes:
        run_id = outcome["run_id"]
        current = latest.get(run_id)
        if current is None or outcome["operator_outcome_at"] > current["operator_outcome_at"]:
            latest[run_id] = outcome
    return latest


def _nearest_rank(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _stratum_summary(runs: list[dict[str, Any]], outcomes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    token_fields = (
        "input_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "visible_output_tokens",
        "total_reported_tokens",
    )
    known_token_runs = [run for run in runs if any(isinstance(run.get(field), int) for field in token_fields)]
    token_values = [
        value
        for run in runs
        if isinstance((value := run.get("total_reported_tokens")), int)
        and run["measurement_sources"].get("total_reported_tokens") != "unknown"
    ]
    wall_values = [run["wall_time_ms"] for run in runs if isinstance(run.get("wall_time_ms"), int)]
    labels = [outcomes[run["run_id"]] for run in runs if run["run_id"] in outcomes]
    accepted = sum(label["operator_outcome"] in {"accepted", "accepted-with-edits"} for label in labels)
    rejected = sum(label["operator_outcome"] == "rejected" for label in labels)
    known_retry = [run["retry_count"] for run in runs if isinstance(run.get("retry_count"), int)]
    known_escalation = [run["escalation_count"] for run in runs if isinstance(run.get("escalation_count"), int)]
    enough_tokens = len(token_values) >= MIN_MEDIAN_SAMPLES
    enough_wall = len(wall_values) >= MIN_MEDIAN_SAMPLES
    return {
        "run_count": len(runs),
        "known_token_run_count": len(known_token_runs),
        "unknown_token_run_count": len(runs) - len(known_token_runs),
        "total_token_sample_count": len(token_values),
        "accepted_count": accepted,
        "rejected_count": rejected,
        "median_total_tokens": statistics.median(token_values) if enough_tokens else "INSUFFICIENT_DATA",
        "p90_total_tokens": _nearest_rank(token_values, 0.90) if enough_tokens else "INSUFFICIENT_DATA",
        "median_wall_time_ms": statistics.median(wall_values) if enough_wall else "INSUFFICIENT_DATA",
        "known_retry_total": sum(known_retry) if known_retry else None,
        "known_escalation_total": sum(known_escalation) if known_escalation else None,
        "outcome_labeled_count": len(labels),
        "success_rate": (accepted / len(labels)) if labels else "INSUFFICIENT_DATA",
        "calibration_ready": len(labels) >= MIN_CALIBRATION_SAMPLES,
    }


def summarize(storage: LocalTelemetryStorage, *, group_by: str | None = None) -> dict[str, Any]:
    runs, outcome_records = load_valid_records(storage)
    outcomes = latest_outcomes(outcome_records)
    if group_by is None:
        return {"schema_version": runs[0]["schema_version"] if runs else None, "summary": _stratum_summary(runs, outcomes)}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        if group_by == "model":
            model = run.get("backend_model") or run.get("launched_model") or run.get("recommended_model") or "unknown"
            key = (
                f"{model}|{run.get('model_identity_status')}|"
                f"{run.get('product_surface')}|{run.get('counter_reconciliation')}"
            )
        elif group_by == "task_level":
            key = (
                f"{run.get('task_difficulty')}|{run.get('product_surface')}|"
                f"{run.get('counter_reconciliation')}"
            )
        else:
            raise ValueError("unsupported summary group")
        groups[key].append(run)
    return {
        "group_by": group_by,
        "strata": {key: _stratum_summary(values, outcomes) for key, values in sorted(groups.items())},
    }


def inspect_run(storage: LocalTelemetryStorage, run_id: str, *, show_signature: bool = False) -> dict[str, Any] | None:
    runs, outcomes = load_valid_records(storage)
    run = next((value for value in runs if value.get("run_id") == run_id), None)
    if run is None or not verify_record_hash(run):
        return None
    result = dict(run)
    if not show_signature:
        result["task_signature"] = "<hidden>"
    linked = [value for value in outcomes if value.get("run_id") == run_id and value.get("original_record_hash") == run["record_hash"]]
    result["outcome_events"] = linked
    return result


def storage_status(storage: LocalTelemetryStorage) -> dict[str, Any]:
    runs, _ = load_valid_records(storage)
    return {
        "enabled": storage.enabled(),
        "storage_directory": "~/.local/state/smart-codex/telemetry",
        "current_storage_bytes": storage.storage_size(),
        "free_disk_bytes": storage.free_bytes(),
        "schema_version": SCHEMA_VERSION,
        "recorded_runs": len(runs),
        "last_record_timestamp": max((run["finished_at"] for run in runs), default=None),
    }
