#!/usr/bin/env python3
"""Build historical coverage and missing-data maps from the canonical registry."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "sources" / "dataset_registry.jsonl"
OUT_JSON = ROOT / "sources" / "coverage_map.json"
OUT_MD = ROOT / "sources" / "COVERAGE_AND_MISSING_DATA.md"

ERAS = [
    {
        "era": "early_tool_using_and_react",
        "period": "2022-10 through 2023-02",
        "examples": ["ReAct"],
        "public_evidence": "papers, prompts, demonstrations, benchmark outcomes",
        "run_level_token_telemetry": "not located",
        "routing_use": "task taxonomy and historical context only",
    },
    {
        "era": "autonomous_general_agents",
        "period": "2023-03 onward",
        "examples": ["AutoGPT", "BabyAGI"],
        "public_evidence": "framework code, examples, benchmark infrastructure",
        "run_level_token_telemetry": "no standardized historical corpus located",
        "routing_use": "framework history only",
    },
    {
        "era": "web_and_computer_use_agents",
        "period": "2023-06 onward",
        "examples": ["Mind2Web", "WebArena", "VisualWebArena", "WebLINX", "BrowserGym"],
        "public_evidence": "actions, screenshots, page state, tool traces, verifier outcomes",
        "run_level_token_telemetry": "usually absent; one very large archive remains license/schema blocked",
        "routing_use": "structural and tool-intensity features, not token priors",
    },
    {
        "era": "software_engineering_agents",
        "period": "2023 onward",
        "examples": ["SWE-agent", "OpenHands", "SWE-bench", "SWE-smith", "Multi-SWE-bench"],
        "public_evidence": "tasks, patches, trajectories, objective verifier outcomes",
        "run_level_token_telemetry": "heterogeneous, often aggregate/cost-only, and frequently license-ambiguous",
        "routing_use": "future bounded adapters after source-specific audit",
    },
    {
        "era": "multi_agent_systems",
        "period": "2023-07 onward",
        "examples": ["ChatDev", "MetaGPT", "MegaAgent", "Magentic-One", "AgencyBench"],
        "public_evidence": "frameworks, outcomes, a few aggregate token/cost examples",
        "run_level_token_telemetry": "mostly absent or aggregate and non-comparable",
        "routing_use": "qualitative amplification evidence only",
    },
    {
        "era": "long_horizon_terminal_agents",
        "period": "2024 onward",
        "examples": ["Terminal-Bench", "Harbor", "STATE-Bench", "AgentRE-Bench"],
        "public_evidence": "tasks, tools, deterministic verifiers, some aggregate usage",
        "run_level_token_telemetry": "adapter- and release-dependent",
        "routing_use": "future locally measured strata",
    },
    {
        "era": "current_codex_and_agents_sdk",
        "period": "2025 through evidence cutoff 2026-07-18",
        "examples": ["OpenAI Responses", "OpenAI Agents SDK", "Codex JSONL", "Codex app-server"],
        "public_evidence": "documented usage/tracing interfaces and versioned schemas",
        "run_level_token_telemetry": "interfaces exist; no universal public task/outcome corpus",
        "routing_use": "preferred collection surfaces for local telemetry 2B",
    },
]

FIELD_GROUPS = {
    "input_tokens": ["input", "prompt", "sent"],
    "cached_tokens": ["cache", "cached"],
    "reasoning_tokens": ["reasoning"],
    "output_tokens": ["output", "completion", "received"],
    "request_count": ["request", "api_calls"],
}


def load_rows():
    return [json.loads(line) for line in REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]


def has_term(values, terms):
    text = " ".join(str(value).lower() for value in values)
    return any(term in text for term in terms)


def main():
    rows = load_rows()
    coverage = {}
    for field, terms in FIELD_GROUPS.items():
        matching = [row["dataset_id"] for row in rows if has_term(row["token_fields_available"], terms)]
        coverage[field] = {"candidate_records": len(matching), "dataset_ids": matching}
    for field, registry_field in [
        ("cost", "cost_fields_available"),
        ("timing", "timing_fields_available"),
        ("tool_calls", "tool_call_fields_available"),
    ]:
        matching = [row["dataset_id"] for row in rows if row.get(registry_field)]
        coverage[field] = {"candidate_records": len(matching), "dataset_ids": matching}
    for field, predicate in [
        ("verifier_result", lambda row: row.get("verifiers_status") in {"present", "present_untyped"}),
        ("raw_trajectory", lambda row: row.get("raw_trajectory_status") in {"present", "present_untyped"}),
        ("complete_failure_coverage", lambda row: str(row.get("failure_trajectory_coverage", "")).lower() in {"complete", "yes", "true"}),
    ]:
        matching = [row["dataset_id"] for row in rows if predicate(row)]
        coverage[field] = {"candidate_records": len(matching), "dataset_ids": matching}

    output = {
        "evidence_cutoff": "2026-07-18",
        "universal_coverage_claimed": False,
        "candidate_dataset_records": len(rows),
        "accepted_for_numerical_routing": sum(bool(row["accepted_for_numerical_routing"]) for row in rows),
        "historical_eras": ERAS,
        "field_coverage_candidates": coverage,
        "critical_missing_measurements": [
            "comparable provider-reported per-request token breakdowns joined to objective outcomes",
            "complete failed, censored, retry, and escalation attempt chains",
            "current context occupancy distinct from cumulative usage",
            "tool-output and repeated-history token attribution",
            "compaction input/output and post-compaction context",
            "subscription quota consumption with documented semantics",
            "price-date-correct accepted-task cost including verification and human review",
            "representative multi-agent runs with per-agent attribution",
            "SmartRouter-specific tasks and route decisions",
        ],
    }
    OUT_JSON.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Historical Coverage and Missing-Data Map", "",
        "Evidence cutoff: 2026-07-18. This is a discovery map, not a claim of exhaustive historical telemetry.", "",
        "| Era | Period | Public evidence | Token telemetry | Routing use |",
        "| --- | --- | --- | --- | --- |",
    ]
    for era in ERAS:
        lines.append(
            f"| {era['era']} | {era['period']} | {era['public_evidence']} | "
            f"{era['run_level_token_telemetry']} | {era['routing_use']} |"
        )
    lines.extend([
        "", "## Registry field coverage", "",
        "Counts below indicate candidates whose registry metadata mentions a field. They do not establish comparable, complete, or provider-reported measurements.", "",
        "| Field | Candidate records |", "| --- | ---: |",
    ])
    for field, item in coverage.items():
        lines.append(f"| {field} | {item['candidate_records']} |")
    lines.extend(["", "## Critical gaps", ""])
    lines.extend(f"- {gap}" for gap in output["critical_missing_measurements"])
    lines.extend([
        "", "A missing public measurement is stored as `null` with provenance; it is never replaced by zero or guessed from an era, model name, text length, or current price table.", "",
    ])
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "PASS", "datasets": len(rows), "eras": len(ERAS)}, indent=2))


if __name__ == "__main__":
    main()
