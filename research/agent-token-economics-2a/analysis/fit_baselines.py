#!/usr/bin/env python3
"""Small interpretable research baselines for token and acceptance economics."""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "normalized"
OUTPUT = ROOT / "data" / "derived" / "baseline_results.json"
ALLOWED_QUALITY = {"A", "B", "C"}
NUMERIC_FEATURES = [
    "task_size",
    "repository_size",
    "agent_count",
    "se_level",
    "math_level",
    "phy_level",
]
CATEGORICAL_FEATURES = [
    "benchmark_version",
    "success_criterion",
    "model_id",
    "model_version",
    "model_provider",
    "product_surface",
    "agent_framework",
    "agent_version",
    "reasoning_effort",
    "task_domain",
    "task_subdomain",
    "interaction_mode",
    "file_scope",
    "repository_scope",
    "mutation_mode",
    "tool_profile",
    "verifier_profile",
    "horizon",
    "requirement_clarity",
    "context_state",
    "risk_level",
    "work_type",
    "prompt_tokens_scope",
    "total_reported_tokens_scope",
    "normalized_cost_scope",
    "cost_currency",
    "price_table_id",
    "price_table_date",
    "cost_reconstruction_basis",
]
MEASUREMENT_PROFILE_FIELDS = [
    "prompt_tokens", "non_cached_input_tokens", "cached_input_tokens",
    "reasoning_tokens", "visible_output_tokens", "total_reported_tokens",
    "number_of_model_requests", "number_of_tool_calls", "retry_count",
    "context_compactions", "wall_time_seconds", "normalized_cost",
]
LOOKUP_FIELDS = [
    "dataset_id", "benchmark_version", "success_criterion", "model_id",
    "model_version", "model_provider", "product_surface", "agent_framework",
    "agent_version", "task_domain", "task_subdomain", "reasoning_effort",
    "agent_count", "tool_profile", "context_state", "context_window",
    "verifier_profile", "verifier_type", "request_breakdown_complete",
    "prompt_tokens_scope", "total_reported_tokens_scope", "measurement_profile",
    "normalized_cost_scope", "cost_currency", "price_table_id",
    "price_table_date", "cost_reconstruction_basis",
]


def load_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def quantile(values, probability):
    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    point = (len(ordered) - 1) * probability
    lo = math.floor(point)
    hi = math.ceil(point)
    return ordered[lo] if lo == hi else ordered[lo] * (hi - point) + ordered[hi] * (point - lo)


def task_enriched_runs():
    tasks = {(row["dataset_id"], row["task_id"]): row for row in load_jsonl(DATA / "tasks.jsonl")}
    registry = {
        row["dataset_id"]: row
        for row in load_jsonl(ROOT / "sources" / "dataset_registry.jsonl")
    }
    enriched = []
    for run in load_jsonl(DATA / "agent_runs.jsonl"):
        if run.get("included_in_numerical_priors") is not True:
            continue
        if run.get("quality_class") not in ALLOWED_QUALITY:
            raise ValueError(f"run {run.get('run_id')} is admitted with disallowed quality")
        dataset = registry.get(run.get("dataset_id"))
        if not dataset or dataset.get("accepted_for_numerical_routing") is not True:
            raise ValueError(
                f"run {run.get('run_id')} is admitted but its dataset registry permission is false"
            )
        item = dict(run)
        task = tasks.get((run.get("dataset_id"), run.get("task_id")), {})
        for key in NUMERIC_FEATURES + CATEGORICAL_FEATURES:
            if key not in item or item.get(key) is None:
                item[key] = task.get(key)
        item["measurement_profile"] = tuple(
            (field, item.get("measurement_method", {}).get(field, "unknown"))
            for field in MEASUREMENT_PROFILE_FIELDS
        )
        enriched.append(item)
    return enriched


def lookup_key(record):
    return tuple(record.get(field) for field in LOOKUP_FIELDS)


def accepted_chain_runs(runs):
    chains = defaultdict(list)
    for run in runs:
        if run.get("attempt_chain_id"):
            chains[(run["dataset_id"], run["attempt_chain_id"])].append(run)
    output = []
    cost_fields = [
        "normalized_cost", "tool_cost", "verification_cost",
        "human_review_cost", "failure_penalty_cost",
    ]
    for records in chains.values():
        records = sorted(records, key=lambda row: row.get("attempt_sequence", -1))
        sequences = [row.get("attempt_sequence") for row in records]
        finals = [record for record in records if record.get("route_final_accepted") is True]
        if len(finals) != 1 or not all(record.get("attempt_chain_complete") is True for record in records):
            continue
        if sequences != list(range(1, len(records) + 1)):
            continue
        if finals[0] is not records[-1] or finals[0].get("task_success") is not True:
            continue
        if len({(record.get("dataset_id"), record.get("task_id")) for record in records}) != 1:
            continue
        if any(record.get(field) is None for record in records for field in cost_fields):
            continue
        if any(record.get("normalized_cost_scope") != "run" for record in records):
            continue
        currencies = {record.get("cost_currency") for record in records}
        price_tables = {record.get("price_table_id") for record in records}
        price_dates = {record.get("price_table_date") for record in records}
        if (
            None in currencies or None in price_tables or None in price_dates
            or len(currencies) != 1 or len(price_tables) != 1 or len(price_dates) != 1
        ):
            continue
        item = dict(finals[0])
        item["accepted_task_cost"] = sum(
            record[field] for record in records for field in cost_fields
        )
        output.append(item)
    return output


def lookup_baselines(runs, accepted_chains):
    chain_groups = defaultdict(list)
    for record in accepted_chains:
        chain_groups[lookup_key(record)].append(record["accepted_task_cost"])
    grouped = defaultdict(list)
    for run in runs:
        grouped[lookup_key(run)].append(run)
    results = []
    for key, records in sorted(grouped.items(), key=lambda item: str(item[0])):
        prompt = [r["prompt_tokens"] for r in records if r.get("prompt_tokens") is not None]
        total = [r["total_reported_tokens"] for r in records if r.get("total_reported_tokens") is not None]
        outcomes = [r["task_success"] for r in records if r.get("task_success") is not None]
        escalations = [r["escalation_count"] > 0 for r in records if r.get("escalation_count") is not None]
        accepted_cost = chain_groups.get(key, [])
        results.append(
            {
                "stratum": dict(zip(LOOKUP_FIELDS, key)),
                "n": len(records),
                "p50_input_tokens": statistics.median(prompt) if prompt else None,
                "p90_total_tokens": quantile(total, 0.9),
                "success_probability_laplace": (sum(outcomes) + 1) / (len(outcomes) + 2) if outcomes else None,
                "escalation_probability_laplace": (sum(escalations) + 1) / (len(escalations) + 2) if escalations else None,
                "expected_accepted_task_cost_median": statistics.median(accepted_cost) if accepted_cost else None,
                "complete_accepted_cost_chains": len(accepted_cost),
                "small_sample": len(records) < 20,
            }
        )
    return results


def lookup_calibration(runs, target, holdout, probability_target=False, quantile_probability=None):
    errors = []
    by_stratum = defaultdict(list)
    for index, record in enumerate(runs):
        actual = record.get(target)
        if actual is None:
            continue
        if holdout == "task":
            held_out = (record.get("dataset_id"), record.get("task_id"))
            different_group = lambda other: (other.get("dataset_id"), other.get("task_id")) != held_out
        elif holdout == "source":
            held_out = record.get("source_id")
            different_group = lambda other: other.get("source_id") != held_out
        else:
            raise ValueError(f"unsupported holdout: {holdout}")
        peers = [
            other for j, other in enumerate(runs)
            if j != index and different_group(other) and lookup_key(other) == lookup_key(record)
            and other.get(target) is not None
        ]
        if not peers:
            continue
        peer_values = [other[target] for other in peers]
        if probability_target:
            prediction = (sum(bool(v) for v in peer_values) + 1) / (len(peer_values) + 2)
            error = (prediction - float(bool(actual))) ** 2
        elif quantile_probability is not None:
            prediction = quantile(peer_values, quantile_probability)
            residual = actual - prediction
            error = max(quantile_probability * residual, (quantile_probability - 1) * residual)
        else:
            prediction = statistics.median(peer_values)
            error = abs(prediction - actual)
        errors.append(error)
        by_stratum[str(lookup_key(record))].append(error)
    return {
        "n": len(errors),
        "error": statistics.mean(errors) if errors else None,
        "holdout_group": holdout,
        "metric": "brier" if probability_target else ("pinball" if quantile_probability is not None else "mean_absolute_error"),
        "by_stratum": {key: {"n": len(values), "error": statistics.mean(values)} for key, values in sorted(by_stratum.items())},
    }


def solve_linear(matrix, vector):
    n = len(vector)
    augmented = [list(matrix[i]) + [vector[i]] for i in range(n)]
    for column in range(n):
        pivot = max(range(column, n), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("singular matrix")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(n):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [a - factor * b for a, b in zip(augmented[row], augmented[column])]
    return [row[-1] for row in augmented]


def build_feature_space(records):
    categories = {
        field: sorted({str(record.get(field)) for record in records if record.get(field) is not None})
        for field in CATEGORICAL_FEATURES
    }
    numeric_stats = {}
    for field in NUMERIC_FEATURES:
        values = [float(r[field]) for r in records if r.get(field) is not None]
        numeric_stats[field] = {
            "median": statistics.median(values) if values else 0.0,
            "mean": statistics.mean(values) if values else 0.0,
            "stdev": statistics.pstdev(values) if len(values) > 1 else 1.0,
        }
        if numeric_stats[field]["stdev"] == 0:
            numeric_stats[field]["stdev"] = 1.0
    names = ["intercept"] + NUMERIC_FEATURES + [f"{field}__missing" for field in NUMERIC_FEATURES]
    for field in CATEGORICAL_FEATURES:
        names.extend(f"{field}={category}" for category in categories[field][1:])

    def encode(record):
        vector = [1.0]
        for field in NUMERIC_FEATURES:
            stats = numeric_stats[field]
            raw = record.get(field)
            value = stats["median"] if raw is None else float(raw)
            vector.append((value - stats["mean"]) / stats["stdev"])
        vector.extend(1.0 if record.get(field) is None else 0.0 for field in NUMERIC_FEATURES)
        for field in CATEGORICAL_FEATURES:
            current = str(record.get(field)) if record.get(field) is not None else None
            vector.extend(1.0 if current == category else 0.0 for category in categories[field][1:])
        return vector

    return names, encode


def fit_ridge(records, target, binary=False, alpha=10.0):
    usable = [r for r in records if r.get(target) is not None]
    names, encode = build_feature_space(usable)
    minimum_n = max(100, 10 * len(names))
    if len(usable) < minimum_n:
        return {
            "trained": False,
            "reason": "insufficient_runs_relative_to_feature_width",
            "n": len(usable),
            "feature_width": len(names),
            "minimum_n": minimum_n,
            "publication_ready": False,
            "grouped_evaluation": None,
        }
    x = [encode(record) for record in usable]
    y = [float(bool(record[target])) if binary else math.log1p(float(record[target])) for record in usable]
    width = len(names)
    xtx = [[0.0] * width for _ in range(width)]
    xty = [0.0] * width
    for row, target_value in zip(x, y):
        for i in range(width):
            xty[i] += row[i] * target_value
            for j in range(width):
                xtx[i][j] += row[i] * row[j]
    for i in range(1, width):
        xtx[i][i] += alpha
    try:
        coefficients = solve_linear(xtx, xty)
    except ValueError:
        return {
            "trained": False, "reason": "singular_design", "n": len(usable),
            "publication_ready": False, "grouped_evaluation": None,
        }
    predictions = []
    for row in x:
        raw = sum(a * b for a, b in zip(row, coefficients))
        predictions.append(min(1.0, max(0.0, raw)) if binary else max(0.0, math.expm1(raw)))
    actual = [float(bool(r[target])) if binary else float(r[target]) for r in usable]
    error = statistics.mean((p - a) ** 2 for p, a in zip(predictions, actual)) if binary else statistics.median(abs(p - a) for p, a in zip(predictions, actual))
    return {
        "trained": True,
        "n": len(usable),
        "alpha": alpha,
        "target": target,
        "model_type": "ridge_linear_probability" if binary else "ridge_log_target_regression",
        "metric": "in_sample_brier_diagnostic_not_generalization" if binary else "in_sample_median_absolute_error_diagnostic_not_generalization",
        "error": error,
        "coefficients": dict(zip(names, coefficients)),
        "publication_ready": False,
        "grouped_evaluation": None,
        "required_evaluation": "nested task-group and source-group held-out evaluation before publication as a routing prior",
        "limitation": "Training diagnostic only; grouped held-out lookup errors, not this in-sample error, are the calibration evidence.",
    }


def fit_stump(records, target="total_reported_tokens"):
    usable = [r for r in records if r.get(target) is not None]
    if len(usable) < 100:
        return {
            "trained": False, "reason": "fewer_than_100_observed_runs", "n": len(usable),
            "publication_ready": False, "grouped_evaluation": None,
        }
    best = None
    for feature in NUMERIC_FEATURES:
        values = sorted({float(r[feature]) for r in usable if r.get(feature) is not None})
        for left, right in zip(values, values[1:]):
            threshold = (left + right) / 2
            low = [float(r[target]) for r in usable if r.get(feature) is not None and float(r[feature]) <= threshold]
            high = [float(r[target]) for r in usable if r.get(feature) is not None and float(r[feature]) > threshold]
            missing = [float(r[target]) for r in usable if r.get(feature) is None]
            if len(low) < 3 or len(high) < 3:
                continue
            low_prediction = statistics.median(low)
            high_prediction = statistics.median(high)
            missing_prediction = statistics.median(missing) if missing else statistics.median([*low, *high])
            loss = (
                sum(abs(v - low_prediction) for v in low)
                + sum(abs(v - high_prediction) for v in high)
                + sum(abs(v - missing_prediction) for v in missing)
            )
            candidate = (loss, feature, threshold, low_prediction, high_prediction, missing_prediction, len(low), len(high), len(missing))
            if best is None or candidate < best:
                best = candidate
    if best is None:
        return {
            "trained": False, "reason": "no_valid_split", "n": len(usable),
            "publication_ready": False, "grouped_evaluation": None,
        }
    return {
        "trained": True,
        "n": len(usable),
        "target": target,
        "feature": best[1],
        "threshold": best[2],
        "left_prediction": best[3],
        "right_prediction": best[4],
        "left_n": best[6],
        "right_n": best[7],
        "missing_prediction": best[5],
        "missing_n": best[8],
        "training_absolute_error": best[0],
        "publication_ready": False,
        "grouped_evaluation": None,
        "required_evaluation": "nested task-group and source-group held-out evaluation before publication as a routing prior",
        "limitation": "One-split descriptive tree; not production calibration evidence.",
    }


def main():
    runs = task_enriched_runs()
    accepted_chains = accepted_chain_runs(runs)
    lookup = lookup_baselines(runs, accepted_chains)
    results = {
        "schema_version": "2a.1",
        "status": "research_only_not_runtime",
        "n_quality_a_to_c": len(runs),
        "lookup_baselines": lookup,
        "lookup_calibration": {
            "task_group_holdout": {
                "p50_input_tokens": lookup_calibration(runs, "prompt_tokens", "task"),
                "p90_total_tokens": lookup_calibration(runs, "total_reported_tokens", "task", quantile_probability=0.9),
                "success_probability": lookup_calibration(runs, "task_success", "task", probability_target=True),
                "escalation_probability": lookup_calibration(runs, "escalation_count", "task", probability_target=True),
                "accepted_task_cost": lookup_calibration(accepted_chains, "accepted_task_cost", "task"),
            },
            "source_group_holdout": {
                "p50_input_tokens": lookup_calibration(runs, "prompt_tokens", "source"),
                "p90_total_tokens": lookup_calibration(runs, "total_reported_tokens", "source", quantile_probability=0.9),
                "success_probability": lookup_calibration(runs, "task_success", "source", probability_target=True),
                "escalation_probability": lookup_calibration(runs, "escalation_count", "source", probability_target=True),
                "accepted_task_cost": lookup_calibration(accepted_chains, "accepted_task_cost", "source"),
            },
        },
        "regularized_baselines": {
            "input_tokens": fit_ridge(runs, "prompt_tokens"),
            "total_tokens": fit_ridge(runs, "total_reported_tokens"),
            "success_probability": fit_ridge(runs, "task_success", binary=True),
            "escalation_probability": fit_ridge(runs, "escalation_count", binary=True),
            "accepted_task_cost": fit_ridge(accepted_chains, "accepted_task_cost"),
        },
        "interpretable_tree": fit_stump(runs),
        "global_limitation": "Public normalized support is sparse and heterogeneous. Accepted-task cost uses complete route chains only. No estimator is activated in SmartRouter runtime.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "runs": len(runs), "lookup_strata": len(lookup)}, indent=2))


if __name__ == "__main__":
    main()
