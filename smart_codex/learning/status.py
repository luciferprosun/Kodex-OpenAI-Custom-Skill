"""Sanitized research-loop collection status."""

from __future__ import annotations

from collections import Counter
from typing import Any

from smart_codex.runtime.telemetry.config import configured_storage, load_external_config
from smart_codex.runtime.telemetry.outcome import pending_runs
from smart_codex.runtime.telemetry.summary import load_valid_records, storage_status

from .dataset import dataset_status
from .learner import MIN_CANDIDATE_RUNS, action_key, shadow_status, stratum_key


def research_status() -> dict[str, Any]:
    storage = configured_storage(require_external=True)
    status = storage_status(storage)
    runs, outcomes = load_valid_records(storage)
    latest_outcome_runs = {str(value.get("run_id")) for value in outcomes}
    known = [
        run
        for run in runs
        if isinstance(run.get("total_reported_tokens"), int)
        and run.get("measurement_sources", {}).get("total_reported_tokens") != "unknown"
    ]
    by_window = Counter(str(run.get("window_id") or "unknown") for run in runs)
    by_stratum = Counter(stratum_key(run) for run in runs)
    by_action = Counter(f"{model}|{effort}" for model, effort in (action_key(run) for run in runs))
    labeled_by_stratum_action = Counter(
        (stratum_key(run), action_key(run))
        for run in runs
        if str(run.get("run_id")) in latest_outcome_runs
    )
    ready_actions = sum(count >= MIN_CANDIDATE_RUNS for count in labeled_by_stratum_action.values())
    max_comparable_labels = max(labeled_by_stratum_action.values(), default=0)
    config = load_external_config()
    candidates = (
        len(list((config.telemetry_root / "policy-candidates").glob("candidate-*.json")))
        if config is not None
        else 0
    )
    dataset = dataset_status()
    manifest = dataset.get("manifest") if isinstance(dataset, dict) else None
    labeled = len(latest_outcome_runs)
    return {
        "telemetry_enabled": status["enabled"],
        "external_storage_verification": status["mount_verification"],
        "microsd_uuid_match": status["mount_verification"] == "VERIFIED",
        "raw_run_count": len(runs),
        "outcome_labeled_count": labeled,
        "pending_outcomes": len(pending_runs(storage)),
        "known_token_run_count": len(known),
        "unknown_token_ratio": (len(runs) - len(known)) / len(runs) if runs else None,
        "records_by_window": dict(sorted(by_window.items())),
        "records_by_task_stratum": dict(sorted(by_stratum.items())),
        "records_by_model_and_effort": dict(sorted(by_action.items())),
        "current_dataset_manifest": manifest.get("manifest_hash") if isinstance(manifest, dict) else None,
        "dataset_state": dataset.get("state"),
        "shadow_learner_state": shadow_status(),
        "candidate_policy_count": candidates,
        "dropped_or_rejected_telemetry_writes": "not_persisted_when_storage_is_unsafe",
        "last_successful_append": max(
            (
                str(value.get("finished_at") or value.get("operator_outcome_at"))
                for value in [*runs, *outcomes]
            ),
            default=None,
        ),
        "last_learning_refresh": manifest.get("evidence_cutoff") if isinstance(manifest, dict) else None,
        "calibration_readiness": (
            "READY_FOR_CANDIDATE_REVIEW"
            if ready_actions >= 2
            else (
                f"INSUFFICIENT_COMPARABLE_ACTIONS_{ready_actions}_OF_2;"
                f"MAX_LABELS_IN_ONE_STRATUM_ACTION_{max_comparable_labels}_OF_{MIN_CANDIDATE_RUNS}"
            )
        ),
    }
