#!/usr/bin/env python3
"""Promote the audited metadata-only SWE-agent fixture into canonical records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "research_packets" / "wave2_agent_05_sample_acquisition" / "FIELD_INVENTORY.jsonl"
REVISION = "3ea751c087f32b16e039a2233dd6eefecef325d5"
RETRIEVED_AT = "2026-07-18T15:18:41+02:00"
SOURCE_ID = "SE-SRC-004"
DATASET_ID = "ds_sweagent_demonstrations"
CANONICAL_URL = f"https://github.com/SWE-agent/SWE-agent/tree/{REVISION}/trajectories/demonstrations"

ACCOUNTING_FIELDS = [
    "prompt_tokens", "non_cached_input_tokens", "cached_input_tokens", "cache_write_tokens",
    "reasoning_tokens", "visible_output_tokens", "total_reported_tokens",
    "cumulative_session_tokens", "current_context_occupancy", "tokens_resent_from_history",
    "tokens_from_tool_output", "tokens_from_compaction", "api_billed_tokens",
    "subscription_quota_units", "number_of_model_requests", "number_of_tool_calls",
    "invalid_tool_calls", "repeated_tool_calls", "context_window", "peak_context_used",
    "context_compactions", "retry_count", "escalation_count", "wall_time_seconds",
    "human_review_minutes", "reported_cost", "normalized_cost", "tool_cost",
    "verification_cost", "human_review_cost", "failure_penalty_cost",
]


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def task_identity(path):
    if "marshmallow-code__marshmallow-1867" in path:
        return "sweagent_demo:marshmallow-1867", "SE", "repository_issue_resolution"
    if "/ctf/" in f"/{path}":
        return f"sweagent_demo:ctf:{Path(path).stem}", "OTHER", "capture_the_flag"
    if "humanevalfix-python-0" in path:
        return "sweagent_demo:humanevalfix-python-0", "SE", "program_repair"
    return "sweagent_demo:function_calling_simple", "OTHER", "synthetic_tool_calling"


def provenance(sha256=None, locator=None):
    return {
        "record_version": "2a.1",
        "source_id": SOURCE_ID,
        "dataset_id": DATASET_ID,
        "canonical_url": CANONICAL_URL,
        "artifact_locator": locator,
        "publisher": "SWE-agent",
        "retrieved_at": RETRIEVED_AT,
        "license": "MIT",
        "redistribution_status": "derived_only",
        "commercial_use_status": "allowed",
        "derived_statistics_status": "allowed",
        "sha256": sha256,
        "transformation": ["raw content inspected in memory", "text/reasoning discarded", "allowlisted structural metadata retained"],
        "raw_content_committed": False,
        "hidden_reasoning_removed": True,
        "privacy_review": "passed",
        "notes": "Parser fixture only; placeholder zeros are normalized to null and excluded from numerical priors.",
    }


def task_record(task_id, domain, subdomain, locator):
    row = {
        "record_version": "2a.1", "source_id": SOURCE_ID, "dataset_id": DATASET_ID,
        "benchmark_id": "sweagent_repository_demonstrations", "benchmark_version": REVISION,
        "task_id": task_id, "task_domain": domain, "task_subdomain": subdomain,
        "task_difficulty": None, "se_level": None, "math_level": None, "phy_level": None,
        "interaction_mode": "agentic", "file_scope": "unknown", "repository_scope": "unknown",
        "mutation_mode": "unknown", "tool_profile": "tool_heavy", "verifier_profile": "none",
        "horizon": "unknown", "requirement_clarity": "unknown", "context_state": "fresh",
        "risk_level": "unknown", "work_type": "implementation" if domain == "SE" else "mixed",
        "task_size": None, "repository_size": None, "success_criterion": None,
        "missing_fields": [
            "task_difficulty", "se_level", "math_level", "phy_level", "task_size",
            "repository_size", "success_criterion",
        ],
        "provenance": provenance(locator=locator),
    }
    return row


def run_record(item):
    task_id, domain, subdomain = task_identity(item["path"])
    model_alias = item.get("model_config")
    row = {
        "record_version": "2a.1", "source_id": SOURCE_ID, "dataset_id": DATASET_ID,
        "run_id": f"sweagent_demo:{item['sha256'][:16]}", "task_id": task_id,
        "timestamp": None, "model_id": None, "model_alias": model_alias, "model_version": None,
        "model_provider": None, "product_surface": None, "agent_framework": "SWE-agent",
        "agent_version": REVISION, "agent_count": None, "reasoning_effort": None,
        "task_domain": domain, "task_subdomain": subdomain, "task_difficulty": None,
        "task_size": None, "repository_size": None, "files_touched": None,
        "prompt_tokens": None, "non_cached_input_tokens": None, "cached_input_tokens": None,
        "cache_write_tokens": None, "reasoning_tokens": None, "visible_output_tokens": None,
        "total_reported_tokens": None, "prompt_tokens_scope": "unknown",
        "total_reported_tokens_scope": "unknown", "cumulative_session_tokens": None,
        "current_context_occupancy": None, "tokens_resent_from_history": None,
        "tokens_from_tool_output": None, "tokens_from_compaction": None,
        "api_billed_tokens": None, "subscription_quota_units": None,
        "number_of_model_requests": None, "number_of_tool_calls": None,
        "tool_calls_by_type": {}, "invalid_tool_calls": None, "repeated_tool_calls": None,
        "context_window": None, "peak_context_used": None, "context_compactions": None,
        "retry_count": None, "escalation_count": None, "wall_time_seconds": None,
        "verifier_type": None, "verifier_result": None, "task_success": None,
        "partial_score": None, "human_review_minutes": None, "reported_cost": None,
        "normalized_cost": None, "cost_currency": None, "reported_cost_scope": None,
        "normalized_cost_scope": None, "price_table_date": None, "price_table_id": None,
        "cost_reconstruction_basis": None, "tool_cost": None, "verification_cost": None,
        "human_review_cost": None, "failure_penalty_cost": None, "attempt_chain_id": None,
        "attempt_sequence": None, "attempt_chain_complete": None, "route_final_accepted": None,
        "request_breakdown_complete": False, "trajectory_available": True,
        "measurement_method": {field: "unknown" for field in ACCOUNTING_FIELDS},
        "measurement_confidence": "low",
        "quality_components": {
            "exact_model_identity": False,
            "exact_agent_identity": True,
            "exact_task_identity": False,
            "provider_reported_tokens": False,
            "complete_request_breakdown": False,
            "complete_public_safe_trajectory": False,
            "objective_verifier": False,
            "timestamped_price_table": False,
            "repeatable_acquisition": True,
            "license_clarity": False,
        },
        "quality_score": 20, "quality_class": "E",
        "included_in_numerical_priors": False, "included_in_censoring_analysis": False,
        "censored": False, "censor_reason": None,
        "license": "MIT", "provenance": provenance(item["sha256"], item["path"]),
    }
    row["missing_fields"] = sorted(key for key, value in row.items() if value is None)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    inventory = load_jsonl(args.input)
    if len(inventory) != 19 or sum(row["size_bytes"] for row in inventory) != 1_503_861:
        raise SystemExit("inventory count/size differs from audited fixture")
    if len({row["sha256"] for row in inventory}) != 19:
        raise SystemExit("inventory SHA-256 values are not unique")

    raw_index = []
    sample = []
    tasks = {}
    runs = []
    for item in inventory:
        raw_index.append({
            **item, "source_revision": REVISION, "retrieved_at": RETRIEVED_AT,
            "downloaded": True, "downloaded_bytes": item["size_bytes"],
            "acquisition_mode": "bounded_in_memory", "raw_retained": False,
        })
        sample.append({
            **item, "record_version": "2a.1", "dataset_id": DATASET_ID,
            "quality_class": "E", "included_in_numerical_priors": False,
            "token_value_interpretation": "placeholder_zero_normalized_to_unknown",
            "task_success_interpretation": "unknown_submitted_is_not_success",
            "raw_content_committed": False,
        })
        task_id, domain, subdomain = task_identity(item["path"])
        tasks.setdefault(task_id, task_record(task_id, domain, subdomain, item["path"]))
        runs.append(run_record(item))

    write_jsonl(ROOT / "data" / "raw-index" / "swe_agent_demonstration_index.jsonl", raw_index)
    write_jsonl(ROOT / "data" / "samples" / "swe_agent_demonstration_field_sample.jsonl", sample)
    write_jsonl(ROOT / "data" / "normalized" / "tasks.jsonl", sorted(tasks.values(), key=lambda row: row["task_id"]))
    write_jsonl(ROOT / "data" / "normalized" / "agent_runs.jsonl", sorted(runs, key=lambda row: row["run_id"]))
    write_jsonl(ROOT / "data" / "normalized" / "agent_requests.jsonl", [])
    write_jsonl(ROOT / "data" / "normalized" / "provenance.jsonl", [provenance(locator="pinned demonstration tree")])
    print(json.dumps({
        "status": "PASS", "source_files": len(inventory), "source_bytes": 1_503_861,
        "tasks": len(tasks), "normalized_runs": len(runs), "normalized_requests": 0,
        "numerical_prior_runs": 0, "raw_content_committed": False,
    }, indent=2))


if __name__ == "__main__":
    main()
