#!/usr/bin/env python3
"""Build the research-only SmartRouter token-economics knowledge pack."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "knowledge" / "token-economics"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    datasets = load_jsonl(ROOT / "sources" / "dataset_registry.jsonl")
    sources = load_jsonl(ROOT / "sources" / "source_registry.jsonl")
    taxonomy = load(ROOT / "taxonomy" / "token_task_taxonomy.json")
    coverage = load(ROOT / "data" / "derived" / "coverage_map.json")
    statistics = load(ROOT / "data" / "derived" / "stratum_statistics.json")
    censoring = load(ROOT / "data" / "derived" / "censoring_summary.json")
    baselines = load(ROOT / "data" / "derived" / "baseline_results.json")

    dump(OUT / "dataset_registry.json", {
        "record_version": "2a.1",
        "evidence_cutoff": "2026-07-18",
        "universal_coverage_claimed": False,
        "datasets": datasets,
    })
    dump(OUT / "telemetry_schema.json", {
        "record_version": "2a.1",
        "status": "research_proposal_not_runtime",
        "agent_run_record": load(ROOT / "schemas" / "agent_run_record.schema.json"),
        "agent_request_record": load(ROOT / "schemas" / "agent_request_record.schema.json"),
        "task_record": load(ROOT / "schemas" / "task_record.schema.json"),
        "source_provenance": load(ROOT / "schemas" / "source_provenance.schema.json"),
    })
    dump(OUT / "task_features.json", {
        "record_version": "2a.1",
        "status": "research_proposal_not_runtime",
        "taxonomy": taxonomy,
        "prediction_feature_groups": {
            "capability": ["se_level", "math_level", "phy_level"],
            "scope": ["interaction_mode", "file_scope", "repository_scope", "mutation_mode"],
            "execution": ["tool_profile", "horizon", "agent_count", "context_state"],
            "evidence": ["verifier_profile", "success_criterion", "benchmark_version"],
            "risk": ["requirement_clarity", "risk_level", "work_type"],
        },
    })
    dump(OUT / "empirical_priors.json", {
        "record_version": "2a.1",
        "status": "withheld_insufficient_compatible_public_evidence",
        "admitted_run_count": coverage.get("numeric_prior_runs", 0),
        "priors": [],
        "stratified_statistics": statistics,
        "censoring_analysis": censoring,
        "activation_condition": "At least one compatible A-C stratum with explicit numerical admission, rights clearance, outcome evidence, and held-out calibration.",
        "non_claim": "No public aggregate, demonstration, or model-name heuristic is converted into a SmartRouter numerical prior.",
    })
    dump(OUT / "token_prediction_baselines.json", baselines)
    dump(OUT / "escalation_priors.json", {
        "record_version": "2a.1",
        "status": "withheld_pending_complete_attempt_chains",
        "priors": [],
        "required_chain_fields": [
            "attempt_chain_id", "attempt_sequence", "attempt_chain_complete",
            "route_final_accepted", "retry_count", "escalation_count",
            "normalized_cost", "tool_cost", "verification_cost",
            "human_review_cost", "failure_penalty_cost",
        ],
        "decision_constraints": [
            "minimum calibrated success probability", "capability ceiling",
            "risk and human-approval constraints", "available verifier",
            "token and time budgets", "current model availability",
        ],
        "runtime_enabled": False,
    })
    dump(OUT / "missingness_policy.json", {
        "record_version": "2a.1",
        "null_is_zero": False,
        "allowed_measurement_methods": [
            "measured", "provider_reported", "framework_reported",
            "reconstructed", "estimated", "unknown",
        ],
        "rules": [
            "Every null quantitative telemetry field is listed in missing_fields and uses measurement method unknown.",
            "Estimated and reconstructed measurements retain their method and never become provider-reported.",
            "Censored runs have null task_success, never enter ordinary failure rates, and require a separate explicit censoring-analysis flag.",
            "D/E, rights-blocked, privacy-pending, and confidence-unknown records cannot enter numerical priors.",
            "Cumulative session usage is not current context occupancy.",
            "API pricing is not subscription quota consumption.",
            "Current prices applied to historical usage are labeled counterfactual.",
            "Accepted-task cost requires a complete accepted attempt chain and all cost components.",
        ],
    })
    (OUT / "source_evidence.jsonl").write_text("".join(json.dumps({
        "record_version": "2a.1",
        "source_id": source["source_id"],
        "title": source["title"],
        "publisher": source["publisher"],
        "canonical_url": source["canonical_url"],
        "tier": source["tier"],
        "claims_supported": source["claims_supported"],
        "limitations": source["limitations"],
        "last_inspected": source["last_inspected"],
    }, sort_keys=True) + "\n" for source in sources), encoding="utf-8")
    (OUT / "README.md").write_text(
        "# SmartRouter Token-Economics Research Pack\n\n"
        "This directory is a non-executing research proposal. No production SmartRouter module imports it in mission 2A.\n\n"
        "The pack preserves missingness and provenance. Because no compatible public run sample passed the A–C numerical, rights, outcome, and reproducibility gates, empirical and escalation priors are intentionally empty. The schemas, task features, source registry, baseline code, and collection requirements are ready for a separately authorized local telemetry mission 2B.\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "PASS", "files": 9, "datasets": len(datasets),
        "sources": len(sources), "numerical_priors": 0, "runtime_enabled": False,
    }, indent=2))


if __name__ == "__main__":
    main()
