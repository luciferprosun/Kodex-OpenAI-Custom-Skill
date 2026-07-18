#!/usr/bin/env python3
"""Compute stratified robust summaries without silently pooling incompatible runs."""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "normalized"
OUTPUT_DIR = ROOT / "data" / "derived"
BOOTSTRAP_REPLICATES = 2000
SEED = 20260718
METRICS = [
    "prompt_tokens", "non_cached_input_tokens", "cached_input_tokens",
    "reasoning_tokens", "visible_output_tokens", "total_reported_tokens",
    "number_of_model_requests", "number_of_tool_calls", "retry_count",
    "context_compactions", "wall_time_seconds", "normalized_cost",
]
STRATUM_FIELDS = [
    "dataset_id", "benchmark_version", "success_criterion", "model_id",
    "model_version", "model_provider", "product_surface", "agent_framework", "agent_version", "task_domain",
    "task_subdomain", "task_difficulty", "reasoning_effort", "agent_count",
    "tool_profile", "context_state", "context_window", "verifier_profile", "verifier_type",
    "request_breakdown_complete", "prompt_tokens_scope", "total_reported_tokens_scope",
    "measurement_profile", "normalized_cost_scope", "cost_currency",
    "price_table_id", "price_table_date", "cost_reconstruction_basis",
]


def load_jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values, probability):
    ordered = sorted(values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def cluster_bootstrap_interval(pairs, group_key, metric, quantile):
    """Resample tasks, not rows, so repeated trajectories do not fake precision."""
    by_cluster = defaultdict(list)
    for value, cluster in pairs:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            by_cluster[cluster].append(value)
    clusters = sorted(by_cluster, key=str)
    if len(clusters) < 5:
        return None
    seed_material = f"{SEED}|{group_key}|{metric}|{quantile}".encode()
    rng = random.Random(int(hashlib.sha256(seed_material).hexdigest()[:16], 16))
    estimates = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = []
        for _ in clusters:
            sampled_cluster = clusters[rng.randrange(len(clusters))]
            sample.extend(by_cluster[sampled_cluster])
        estimates.append(percentile(sample, quantile))
    return [percentile(estimates, 0.025), percentile(estimates, 0.975)]


def distribution(records, extractor, group_key, metric):
    pairs = []
    for record in records:
        value = extractor(record)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            pairs.append((value, (record["dataset_id"], record["task_id"])))
    values = [value for value, _ in pairs]
    if not values:
        return {
            "n": 0, "task_clusters": 0, "p10": None, "p25": None,
            "p50": None, "p75": None, "p90": None,
            "p50_cluster_bootstrap_95ci": None,
            "p90_cluster_bootstrap_95ci": None,
        }
    return {
        "n": len(values),
        "task_clusters": len({cluster for _, cluster in pairs}),
        "p10": percentile(values, 0.10),
        "p25": percentile(values, 0.25),
        "p50": percentile(values, 0.50),
        "p75": percentile(values, 0.75),
        "p90": percentile(values, 0.90),
        "p50_cluster_bootstrap_95ci": cluster_bootstrap_interval(pairs, group_key, metric, 0.50),
        "p90_cluster_bootstrap_95ci": cluster_bootstrap_interval(pairs, group_key, metric, 0.90),
    }


def task_cluster_success_summary(successes, failures, group_identifier="outcome"):
    """Weight each task equally and bootstrap task clusters, not trajectory rows."""
    by_task = defaultdict(list)
    for record in successes:
        by_task[(record["dataset_id"], record["task_id"])].append(1.0)
    for record in failures:
        by_task[(record["dataset_id"], record["task_id"])].append(0.0)
    task_values = [statistics.mean(by_task[key]) for key in sorted(by_task, key=str)]
    result = {
        "task_clusters": len(task_values),
        "rate": statistics.mean(task_values) if task_values else None,
        "task_cluster_bootstrap_95ci": None,
    }
    if len(task_values) < 5:
        return result
    seed_material = f"{SEED}|{group_identifier}|task_cluster_success".encode()
    rng = random.Random(int(hashlib.sha256(seed_material).hexdigest()[:16], 16))
    estimates = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = [task_values[rng.randrange(len(task_values))] for _ in task_values]
        estimates.append(statistics.mean(sample))
    result["task_cluster_bootstrap_95ci"] = [
        percentile(estimates, 0.025), percentile(estimates, 0.975)
    ]
    return result


def enrich_runs(runs, tasks, requests):
    task_index = {(row["dataset_id"], row["task_id"]): row for row in tasks}
    request_index = defaultdict(list)
    for request in requests:
        request_index[(request["dataset_id"], request["run_id"])].append(request)
    enriched = []
    for run in runs:
        item = dict(run)
        task = task_index.get((run["dataset_id"], run["task_id"]), {})
        for field in [
            "benchmark_id", "benchmark_version", "success_criterion", "tool_profile",
            "context_state", "verifier_profile", "requirement_clarity", "risk_level",
            "repository_scope", "work_type", "se_level", "math_level", "phy_level",
        ]:
            item[field] = task.get(field)
        related = sorted(
            request_index.get((run["dataset_id"], run["run_id"]), []),
            key=lambda row: row["request_sequence"],
        )
        item["_first_request_prompt_tokens"] = related[0].get("prompt_tokens") if related else None
        item["measurement_profile"] = tuple(
            (field, item.get("measurement_method", {}).get(field, "unknown"))
            for field in sorted(set(METRICS) | {
                "tokens_from_tool_output", "tool_cost", "verification_cost",
                "human_review_cost", "failure_penalty_cost",
            })
        )
        enriched.append(item)
    return enriched


def derived_value(record, name):
    if name == "cache_hit_ratio":
        denominator, numerator = record.get("prompt_tokens"), record.get("cached_input_tokens")
    elif name == "reasoning_to_output_ratio":
        denominator, numerator = record.get("visible_output_tokens"), record.get("reasoning_tokens")
    elif name == "tool_output_burden":
        denominator, numerator = record.get("prompt_tokens"), record.get("tokens_from_tool_output")
    elif name == "input_amplification_ratio":
        denominator, numerator = record.get("_first_request_prompt_tokens"), record.get("prompt_tokens")
    else:
        return None
    if not isinstance(denominator, (int, float)) or denominator <= 0:
        return None
    return numerator / denominator if isinstance(numerator, (int, float)) else None


def group_key(record):
    return tuple(record.get(field) for field in STRATUM_FIELDS)


def accepted_chain_records(runs):
    """Return only complete route chains with every cost component observed.

    normalized_cost is the model/API attempt cost. Tool, verification, human-review,
    and failure-penalty components are separate to prevent accidental double counting.
    """
    chains = defaultdict(list)
    for run in runs:
        if run.get("attempt_chain_id"):
            chains[(run["dataset_id"], run["attempt_chain_id"])].append(run)
    accepted = []
    cost_fields = [
        "normalized_cost", "tool_cost", "verification_cost",
        "human_review_cost", "failure_penalty_cost",
    ]
    for chain_id, records in chains.items():
        records = sorted(records, key=lambda row: row.get("attempt_sequence", -1))
        sequences = [row.get("attempt_sequence") for row in records]
        finals = [row for row in records if row.get("route_final_accepted") is True]
        if len(finals) != 1 or not all(row.get("attempt_chain_complete") is True for row in records):
            continue
        if sequences != list(range(1, len(records) + 1)):
            continue
        if finals[0] is not records[-1] or finals[0].get("task_success") is not True:
            continue
        if len({(row.get("dataset_id"), row.get("task_id")) for row in records}) != 1:
            continue
        if any(row.get(field) is None for row in records for field in cost_fields):
            continue
        if any(row.get("normalized_cost_scope") != "run" for row in records):
            continue
        currencies = {row.get("cost_currency") for row in records}
        price_tables = {row.get("price_table_id") for row in records}
        price_dates = {row.get("price_table_date") for row in records}
        if (
            None in currencies or None in price_tables or None in price_dates
            or len(currencies) != 1 or len(price_tables) != 1 or len(price_dates) != 1
        ):
            continue
        final = dict(finals[0])
        final["accepted_task_cost"] = sum(
            row[field] for row in records for field in cost_fields
        )
        final["attempts_in_chain"] = len(records)
        final["_chain_id"] = chain_id
        accepted.append(final)
    return accepted


def admitted_analysis_runs(runs, flag):
    registry = {
        row["dataset_id"]: row
        for row in load_jsonl(ROOT / "sources" / "dataset_registry.jsonl")
    }
    admitted = []
    for run in runs:
        if run.get(flag) is not True:
            continue
        dataset = registry.get(run.get("dataset_id"))
        if not dataset or dataset.get("accepted_for_numerical_routing") is not True:
            raise ValueError(
                f"run {run.get('run_id')} claims {flag} but its dataset is not permitted"
            )
        admitted.append(run)
    return admitted


def main():
    raw_runs = load_jsonl(DATA / "agent_runs.jsonl")
    tasks = load_jsonl(DATA / "tasks.jsonl")
    requests = load_jsonl(DATA / "agent_requests.jsonl")
    runs = enrich_runs(raw_runs, tasks, requests)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    numeric_runs = admitted_analysis_runs(runs, "included_in_numerical_priors")
    censoring_runs = admitted_analysis_runs(runs, "included_in_censoring_analysis")
    groups = defaultdict(list)
    for run in numeric_runs:
        groups[group_key(run)].append(run)

    summaries = []
    for key, records in sorted(groups.items(), key=lambda item: str(item[0])):
        key_string = "|".join("null" if value is None else str(value) for value in key)
        uncensored = [record for record in records if not record.get("censored")]
        successes = [record for record in uncensored if record.get("task_success") is True]
        failures = [record for record in uncensored if record.get("task_success") is False]
        known_outcomes = len(successes) + len(failures)
        metrics = {}
        for metric in METRICS:
            extractor = lambda record, field=metric: record.get(field)
            metrics[metric] = {
                "all_uncensored": distribution(uncensored, extractor, key_string, f"{metric}:all"),
                "success": distribution(successes, extractor, key_string, f"{metric}:success"),
                "failure": distribution(failures, extractor, key_string, f"{metric}:failure"),
            }
        for metric in [
            "cache_hit_ratio", "reasoning_to_output_ratio", "tool_output_burden",
            "input_amplification_ratio",
        ]:
            extractor = lambda record, field=metric: derived_value(record, field)
            metrics[metric] = {
                "all_uncensored": distribution(uncensored, extractor, key_string, f"{metric}:all"),
                "success": distribution(successes, extractor, key_string, f"{metric}:success"),
                "failure": distribution(failures, extractor, key_string, f"{metric}:failure"),
            }
        success_summary = task_cluster_success_summary(successes, failures, key_string)
        summaries.append({
            "stratum": dict(zip(STRATUM_FIELDS, key)),
            "n": len(records),
            "task_clusters": len({(row["dataset_id"], row["task_id"]) for row in records}),
            "quality_class_mix": dict(sorted(Counter(row["quality_class"] for row in records).items())),
            "successes": len(successes),
            "failures": len(failures),
            "unknown_outcomes": len(uncensored) - known_outcomes,
            "censored": len(records) - len(uncensored),
            "outcome_task_clusters": success_summary["task_clusters"],
            "run_success_rate": len(successes) / known_outcomes if known_outcomes else None,
            "task_cluster_success_rate": success_summary["rate"],
            "task_cluster_success_bootstrap_95ci": success_summary["task_cluster_bootstrap_95ci"],
            "small_sample": len(records) < 20,
            "metrics": metrics,
        })

    accepted_chains = accepted_chain_records(numeric_runs)
    accepted_cost = distribution(
        accepted_chains, lambda row: row["accepted_task_cost"],
        "complete_accepted_chains", "accepted_task_cost",
    )
    chain_output = {
        "definition": "sum of model/API, tool, verification, human-review, and failure-penalty costs across every attempt in a complete accepted route chain",
        "n_complete_accepted_chains": len(accepted_chains),
        "distribution": accepted_cost,
        "excluded_incomplete_or_partially_costed_chains": True,
    }
    censoring_summary = {
        "definition": "separate A-C, rights-cleared censored-run cohort; never coded as ordinary success or failure",
        "n": len(censoring_runs),
        "by_reason": dict(sorted(Counter(row.get("censor_reason") for row in censoring_runs).items(), key=lambda item: str(item[0]))),
        "wall_time_seconds": distribution(
            censoring_runs, lambda row: row.get("wall_time_seconds"),
            "censoring_cohort", "wall_time_seconds",
        ),
        "total_reported_tokens": distribution(
            censoring_runs, lambda row: row.get("total_reported_tokens"),
            "censoring_cohort", "total_reported_tokens",
        ),
        "survival_model_fitted": False,
        "survival_model_requirement": "sufficient comparable censoring times/budgets and at least five independent task clusters",
    }

    all_fields = sorted({key for run in raw_runs for key in run})
    missingness = {
        "total_runs": len(raw_runs),
        "fields": {
            field: {
                "missing_count": sum(run.get(field) is None for run in raw_runs),
                "missing_fraction": (sum(run.get(field) is None for run in raw_runs) / len(raw_runs)) if raw_runs else None,
            }
            for field in all_fields
        },
    }
    coverage = {
        "total_runs": len(raw_runs),
        "numeric_prior_runs": len(numeric_runs),
        "quality_classes": dict(sorted(Counter(run.get("quality_class") for run in raw_runs).items(), key=lambda item: str(item[0]))),
        "datasets": dict(sorted(Counter(run.get("dataset_id") for run in raw_runs).items(), key=lambda item: str(item[0]))),
        "models": dict(sorted(Counter(run.get("model_id") for run in raw_runs).items(), key=lambda item: str(item[0]))),
        "frameworks": dict(sorted(Counter(run.get("agent_framework") for run in raw_runs).items(), key=lambda item: str(item[0]))),
        "task_domains": dict(sorted(Counter(run.get("task_domain") for run in raw_runs).items(), key=lambda item: str(item[0]))),
        "successful_runs": sum(run.get("task_success") is True and not run.get("censored") for run in raw_runs),
        "failed_runs": sum(run.get("task_success") is False and not run.get("censored") for run in raw_runs),
        "unknown_outcomes": sum(run.get("task_success") is None and not run.get("censored") for run in raw_runs),
        "censored_runs": sum(bool(run.get("censored")) for run in raw_runs),
        "censoring_analysis_runs": len(censoring_runs),
        "complete_accepted_cost_chains": len(accepted_chains),
    }

    (OUTPUT_DIR / "stratum_statistics.json").write_text(json.dumps({
        "method": {
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "seed": SEED,
            "bootstrap_unit": "dataset_id plus task_id",
            "outcome_policy": "censored runs excluded from ordinary successes and failures",
        },
        "strata": summaries,
    }, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "accepted_task_cost_chains.json").write_text(json.dumps(chain_output, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "censoring_summary.json").write_text(json.dumps(censoring_summary, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "missingness.json").write_text(json.dumps(missingness, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "coverage_map.json").write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Statistical Tables", "",
        f"Runs: {len(raw_runs)}; explicitly admitted A-C numerical-prior runs: {len(numeric_runs)}.", "",
        "No incompatible datasets are averaged together. Censored runs are not coded as failures. Confidence intervals resample task clusters.", "",
        "| Dataset | Model | Framework | Domain | n | Success | p50 total tokens | p90 total tokens |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in summaries:
        total = item["metrics"]["total_reported_tokens"]["all_uncensored"]
        success = (
            "null" if item["task_cluster_success_rate"] is None
            else f"{item['task_cluster_success_rate']:.3f}"
        )
        lines.append(
            f"| {item['stratum']['dataset_id']} | {item['stratum']['model_id']} | "
            f"{item['stratum']['agent_framework']} | {item['stratum']['task_domain']} | {item['n']} | "
            f"{success} | {total['p50'] if total['p50'] is not None else 'null'} | "
            f"{total['p90'] if total['p90'] is not None else 'null'} |"
        )
    lines.extend([
        "", f"Complete accepted route chains with fully observed cost components: {len(accepted_chains)}.",
        "", f"Separate rights-cleared censoring-analysis runs: {len(censoring_runs)}.",
        "", "Intervals are null with fewer than five independent task clusters; n < 20 is flagged in JSON.", "",
    ])
    (OUTPUT_DIR / "STATISTICAL_TABLES.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "status": "PASS", "runs": len(raw_runs), "numeric_runs": len(numeric_runs),
        "censoring_runs": len(censoring_runs), "strata": len(summaries),
        "accepted_cost_chains": len(accepted_chains),
    }, indent=2))


if __name__ == "__main__":
    main()
