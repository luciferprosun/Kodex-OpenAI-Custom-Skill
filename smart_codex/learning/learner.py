"""Fixed, dependency-free shadow calibration over comparable telemetry strata."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any

from smart_codex.runtime.telemetry.errors import TelemetryStorageError
from smart_codex.runtime.telemetry.models import canonical_json

from .dataset import _atomic_write, _config, dataset_status, load_rows


ALGORITHM_VERSION = "shadow-pareto-wilson-1.0.0"
MIN_DESCRIPTIVE_RUNS = 5
MIN_CANDIDATE_RUNS = 30
QUALITY_TOLERANCE = 0.05
MIN_EFFICIENCY_IMPROVEMENT = 0.10
STRATUM_FIELDS = (
    "schema_version",
    "workspace_signature",
    "window_id",
    "task_domain",
    "task_subdomain",
    "task_difficulty",
    "task_scope",
    "task_risk",
    "verification_available",
    "codex_protocol_version",
    "product_surface",
    "counter_reconciliation",
    "model_identity_status",
    "sandbox",
    "approval_policy",
)


def _nearest_rank(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def stratum_key(row: dict[str, Any]) -> str:
    payload = {field: row.get(field) for field in STRATUM_FIELDS}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def action_key(row: dict[str, Any]) -> tuple[str, str]:
    model = row.get("backend_model") or row.get("launched_model") or "unknown"
    effort = row.get("reasoning_effort") or "unknown"
    return str(model), str(effort)


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [row for row in rows if row.get("operator_outcome") is not None]
    accepted = [
        row
        for row in labels
        if row.get("operator_outcome") in {"accepted", "accepted-with-edits"}
    ]
    verified = [row for row in accepted if row.get("verifier_result") == "passed"]
    major = [row for row in labels if row.get("edit_magnitude") == "major"]
    rejected = [row for row in labels if row.get("operator_outcome") == "rejected"]
    tokens = [row["total_reported_tokens"] for row in rows if isinstance(row.get("total_reported_tokens"), int)]
    walls = [row["wall_time_ms"] for row in rows if isinstance(row.get("wall_time_ms"), int)]
    retries = [row["retry_count"] for row in rows if isinstance(row.get("retry_count"), int)]
    compactions = [row["compaction_count"] for row in rows if isinstance(row.get("compaction_count"), int)]
    lower, upper = _wilson(len(accepted), len(labels))
    observed_fields = (
        "total_reported_tokens",
        "retry_count",
        "compaction_count",
        "backend_model",
        "verifier_result",
    )
    unknown = sum(row.get(field) is None for row in rows for field in observed_fields)
    total_cells = len(rows) * len(observed_fields)
    return {
        "valid_runs": len(rows),
        "labeled_runs": len(labels),
        "acceptance_rate": len(accepted) / len(labels) if labels else None,
        "acceptance_wilson_lower": lower,
        "acceptance_wilson_upper": upper,
        "verified_success_rate": len(verified) / len(labels) if labels else None,
        "major_edit_rate": len(major) / len(labels) if labels else None,
        "rejection_rate": len(rejected) / len(labels) if labels else None,
        "token_sample_count": len(tokens),
        "median_total_tokens": statistics.median(tokens) if len(tokens) >= MIN_DESCRIPTIVE_RUNS else None,
        "p90_total_tokens": _nearest_rank(tokens, 0.9) if len(tokens) >= MIN_DESCRIPTIVE_RUNS else None,
        "wall_sample_count": len(walls),
        "median_wall_time_ms": statistics.median(walls) if len(walls) >= MIN_DESCRIPTIVE_RUNS else None,
        "p90_wall_time_ms": _nearest_rank(walls, 0.9) if len(walls) >= MIN_DESCRIPTIVE_RUNS else None,
        "retry_rate": sum(value > 0 for value in retries) / len(retries) if retries else None,
        "compaction_rate": sum(value > 0 for value in compactions) / len(compactions) if compactions else None,
        "unknown_field_rate": unknown / total_cells if total_cells else None,
    }


def _drift_detected(rows: list[dict[str, Any]]) -> bool:
    labeled = sorted(
        (row for row in rows if row.get("operator_outcome") is not None),
        key=lambda row: str(row.get("started_at", "")),
    )
    if len(labeled) < 60:
        return False
    earlier = labeled[:-30]
    recent = labeled[-30:]

    def rate(values: list[dict[str, Any]]) -> float:
        return sum(
            row.get("operator_outcome") in {"accepted", "accepted-with-edits"}
            for row in values
        ) / len(values)

    return abs(rate(recent) - rate(earlier)) >= 0.20


def _improvement(candidate: dict[str, Any], incumbent: dict[str, Any]) -> tuple[bool, dict[str, float]]:
    improvements: dict[str, float] = {}
    for field in ("median_total_tokens", "median_wall_time_ms"):
        old = incumbent.get(field)
        new = candidate.get(field)
        if isinstance(old, (int, float)) and old > 0 and isinstance(new, (int, float)):
            improvements[field] = (old - new) / old
    return any(value >= MIN_EFFICIENCY_IMPROVEMENT for value in improvements.values()), improvements


def candidate_report() -> dict[str, Any]:
    manifest, rows = load_rows()
    strata: dict[str, dict[tuple[str, str], list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    descriptors: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = stratum_key(row)
        strata[key][action_key(row)].append(row)
        descriptors[key] = {field: row.get(field) for field in STRATUM_FIELDS}
    affected: list[dict[str, Any]] = []
    abstentions: list[dict[str, Any]] = []
    for key, actions in sorted(strata.items()):
        summaries = {action: _metrics(values) for action, values in actions.items()}
        if any(_drift_detected(values) for values in actions.values()):
            abstentions.append({"stratum_id": key, "status": "DRIFT_DETECTED"})
            continue
        eligible = [
            action for action, metric in summaries.items() if metric["labeled_runs"] >= MIN_CANDIDATE_RUNS
        ]
        if len(eligible) < 2:
            status = "INSUFFICIENT_DATA" if not eligible else "NO_COMPARABLE_ALTERNATIVE"
            abstentions.append(
                {
                    "stratum_id": key,
                    "status": status,
                    "actions": {
                        f"{model}|{effort}": metric for (model, effort), metric in sorted(summaries.items())
                    },
                }
            )
            continue
        incumbent_action = max(eligible, key=lambda action: summaries[action]["labeled_runs"])
        incumbent = summaries[incumbent_action]
        best: tuple[tuple[str, str], dict[str, Any], dict[str, float]] | None = None
        for action in sorted(eligible):
            if action == incumbent_action:
                continue
            metric = summaries[action]
            candidate_lower = metric.get("acceptance_wilson_lower")
            incumbent_lower = incumbent.get("acceptance_wilson_lower")
            quality_ok = (
                isinstance(candidate_lower, float)
                and isinstance(incumbent_lower, float)
                and candidate_lower >= incumbent_lower - QUALITY_TOLERANCE
            )
            improved, improvements = _improvement(metric, incumbent)
            if quality_ok and improved:
                if best is None or max(improvements.values(), default=0.0) > max(best[2].values(), default=0.0):
                    best = (action, metric, improvements)
        if descriptors[key].get("task_risk") in {"high", "critical"} and best is not None:
            abstentions.append({"stratum_id": key, "status": "CANDIDATE_REJECTED_BY_SAFETY"})
        elif best is None:
            abstentions.append({"stratum_id": key, "status": "NO_PARETO_IMPROVEMENT"})
        else:
            action, metric, improvements = best
            affected.append(
                {
                    "stratum_id": key,
                    "stratum": descriptors[key],
                    "incumbent": {
                        "model": incumbent_action[0],
                        "reasoning_effort": incumbent_action[1],
                        "metrics": incumbent,
                    },
                    "shadow_candidate": {
                        "model": action[0],
                        "reasoning_effort": action[1],
                        "metrics": metric,
                    },
                    "improvements": improvements,
                    "status": "CANDIDATE_AVAILABLE",
                }
            )
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "dataset_manifest_hash": manifest.get("manifest_hash"),
        "dataset_hash": manifest.get("dataset_hash"),
        "minimum_descriptive_runs": MIN_DESCRIPTIVE_RUNS,
        "minimum_candidate_runs": MIN_CANDIDATE_RUNS,
        "quality_method": "95% Wilson lower bound must be within 0.05 of incumbent Wilson lower bound",
        "efficiency_method": "at least 10% lower median measured tokens or wall time",
        "affected_strata": affected,
        "abstentions": abstentions,
        "authority": False,
        "live_routing_mutation": False,
    }


def propose_policy() -> dict[str, Any]:
    report = candidate_report()
    content = dict(report)
    candidate_id = hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()
    content["candidate_id"] = candidate_id
    content["promotion_barrier"] = "explicit human approval bound to candidate_id required"
    config = _config()
    target = config.telemetry_root / "policy-candidates" / f"candidate-{candidate_id}.json"
    payload = canonical_json(content).encode("utf-8") + b"\n"
    if target.exists():
        if target.read_bytes() != payload:
            raise TelemetryStorageError("IMMUTABLE_CANDIDATE_COLLISION")
    else:
        _atomic_write(target, payload)
    return content


def validate_candidate(candidate_id: str) -> dict[str, Any]:
    if len(candidate_id) != 64 or any(character not in "0123456789abcdef" for character in candidate_id):
        return {"valid": False, "reason": "INVALID_CANDIDATE_ID"}
    config = _config()
    path = config.telemetry_root / "policy-candidates" / f"candidate-{candidate_id}.json"
    if not path.is_file() or path.is_symlink():
        return {"valid": False, "reason": "CANDIDATE_NOT_FOUND"}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"valid": False, "reason": "CANDIDATE_MALFORMED"}
    if not isinstance(value, dict):
        return {"valid": False, "reason": "CANDIDATE_MALFORMED"}
    claimed = value.pop("candidate_id", None)
    value.pop("promotion_barrier", None)
    actual = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    forbidden = {"sandbox", "approval_policy", "network_access", "tool_permissions", "write_authority"}
    affected = value.get("affected_strata", [])
    unsafe = any(forbidden.intersection(item.get("shadow_candidate", {})) for item in affected if isinstance(item, dict))
    status = dataset_status()
    manifest = status.get("manifest") if isinstance(status, dict) else None
    bound = isinstance(manifest, dict) and value.get("dataset_manifest_hash") == manifest.get("manifest_hash")
    return {
        "valid": claimed == candidate_id == actual and not unsafe and value.get("authority") is False and bound,
        "hash_valid": claimed == candidate_id == actual,
        "safety_fields_absent": not unsafe,
        "manifest_bound": bound,
        "authority": False,
    }


def shadow_status() -> dict[str, Any]:
    status = dataset_status()
    manifest = status.get("manifest") if isinstance(status, dict) else None
    if not isinstance(manifest, dict) or int(manifest.get("labeled_run_count", 0)) < MIN_CANDIDATE_RUNS:
        return {
            "shadow_policy": "ACTIVE",
            "decision": "ABSTAIN — INSUFFICIENT_DATA",
            "minimum_labeled_runs_per_action": MIN_CANDIDATE_RUNS,
            "dataset_state": status.get("state"),
        }
    report = candidate_report()
    if report["affected_strata"]:
        return {
            "shadow_policy": "ACTIVE",
            "decision": "CANDIDATE_AVAILABLE",
            "candidate_strata": len(report["affected_strata"]),
            "dataset_manifest_hash": report["dataset_manifest_hash"],
        }
    return {
        "shadow_policy": "ACTIVE",
        "decision": "ABSTAIN — NO_COMPARABLE_ALTERNATIVE",
        "dataset_manifest_hash": report["dataset_manifest_hash"],
    }
