#!/usr/bin/env python3
"""Build stable, conservative source and dataset registries from research packets."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKETS = ROOT / "research_packets"
SOURCES_DIR = ROOT / "sources"

OFFICIAL_SOURCE_MAP = {
    "OA-TELEM-RESPONSES-RUN": ["OA-OFFICIAL-001", "OA-OFFICIAL-002", "OA-OFFICIAL-003", "OA-OFFICIAL-004"],
    "OA-TELEM-ORG-USAGE": ["OA-OFFICIAL-007"],
    "OA-TELEM-ORG-COSTS": ["OA-OFFICIAL-008"],
    "OA-TELEM-AGENTS-SDK": ["OA-OFFICIAL-009", "OA-OFFICIAL-010", "OA-OFFICIAL-011", "OA-OFFICIAL-012"],
    "OA-TELEM-CODEX-EXEC": ["OA-OFFICIAL-013", "OA-OFFICIAL-014"],
    "OA-TELEM-CODEX-APP-SERVER": ["OA-OFFICIAL-015"],
    "OA-TELEM-CODEX-ROLLOUT": ["OA-OFFICIAL-013"],
}

SOURCE_URL_OVERRIDES = {
    "OA-OFFICIAL-001": "https://github.com/openai/openai-openapi",
    "OA-OFFICIAL-007": "https://github.com/openai/openai-openapi",
    "OA-OFFICIAL-008": "https://github.com/openai/openai-openapi",
    "SE-SRC-002": "https://github.com/SWE-bench/experiments/blob/2f15350cd32becc4569e0d826361048555b605c0/README.md",
    "SE-SRC-003": "https://github.com/SWE-bench/experiments/blob/2f15350cd32becc4569e0d826361048555b605c0/checklist.md",
    "SE-SRC-005": "https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/docs/usage/trajectories.md",
    "SE-SRC-006": "https://github.com/SWE-agent/SWE-agent/blob/3ea751c087f32b16e039a2233dd6eefecef325d5/sweagent/agent/models.py",
}

OPERATOR_SURFACES = set(OFFICIAL_SOURCE_MAP)
BLOCKED_RAW = {
    "ds_swebench_experiments", "ds_nebius_sweagent_trajectories",
    "ds_nebius_openhands_swerebench", "hwm_webarena_human_trajectories",
    "hwm_visualwebarena_human_trajectories", "hwm_webarena_execution_traces_v1_v2",
    "hwm_visualwebarena_agent_trajectories", "hwm_agentlab_tmlr_traces",
    "hwm_openhands_token_consumption_independent_2026",
    "hwm_trace_commons_agent_traces_2026_07_18", "hwm_gaia_submissions_public",
}
DATE_SEMANTIC_OVERRIDES = {
    "hwm_react_public_artifacts_v1": None,
    "ds_openhands_benchmark_outputs": None,
}
REPOSITORY_DISK_USAGE_KIB = {
    "ds_swebench_experiments": 344242,
    "ds_terminalbench2_tasks": 46843,
    "ds_statebench": 4019,
    "ds_agentrebench": 3197,
    "ds_multiswebench": 5205,
}
DISPLAY_SIZE_CLAIMS = {
    "hwm_gaia_core_2023": "110 MB",
    "hwm_gaia_results_public": "148 kB observed in repository listing",
    "hwm_gaia_submissions_public": "2.64 MB",
    "hwm_agentboard_dataset": "1.4 GB",
    "hwm_weblinx_1_0_1_1": "526 MB processed",
    "hwm_weblinx_browsergym_1_1": "140 GB",
    "hwm_agentlab_tmlr_traces": "207 GB in archive parts",
    "hwm_trace_commons_agent_traces_2026_07_18": "127 MB",
    "hwm_openhands_token_consumption_independent_2026": "41.9 GB",
}


class RegistryError(Exception):
    pass


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def first(record, *keys, default=None):
    for key in keys:
        if key in record:
            return record[key]
    return default


def as_string_list(value):
    if value is None:
        return [], None
    if isinstance(value, list):
        if not all(isinstance(item, str) for item in value):
            raise RegistryError(f"list contains non-string availability value: {value!r}")
        return sorted(set(value)), None
    if isinstance(value, str):
        return [], value
    return [], str(value)


def normalize_field_availability(value):
    if value is None:
        return [], "unknown", None
    if value is False:
        return [], "absent", None
    if value is True:
        return [], "present_untyped", None
    if isinstance(value, list):
        if not all(isinstance(item, str) for item in value):
            raise RegistryError(f"field list contains non-string item: {value!r}")
        return sorted(set(value)), "present" if value else "absent", None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"none", "no", "absent", "false"}:
            return [], "absent", value
        if any(term in lowered for term in ["unknown", "unverified", "not uniformly", "dependent", "may ", "potential"]):
            return [], "unknown", value
        return [], "present_untyped", value
    raise RegistryError(f"unsupported field availability type: {type(value).__name__}")


def normalize_presence(value):
    if value is True:
        return "present", None
    if value is False:
        return "absent", None
    if value is None:
        return "unknown", None
    return "present_untyped", str(value)


def normalize_count(value):
    if isinstance(value, bool):
        return None, str(value)
    if isinstance(value, int) and value >= 0:
        return value, None
    if value is None:
        return None, None
    return None, str(value)


def infer_record_type(dataset_id, name):
    lowered = name.lower()
    if dataset_id == "OA-TELEM-CODEX-ROLLOUT":
        return "private_local_surface"
    if dataset_id in OPERATOR_SURFACES:
        return "operator_telemetry_surface"
    if any(term in lowered for term in ["aggregate", "comparison", "appendix"]):
        return "aggregate_paper_results"
    if any(term in lowered for term in ["tasks", "benchmark core", "task instances"]):
        return "benchmark_tasks"
    if any(term in lowered for term in ["schema", "harness"]):
        return "framework_schema"
    if any(term in lowered for term in ["trajector", "run outputs", "trace", "demonstration"]):
        return "public_trajectory_dataset"
    return "discovery_index"


def rights_decision(dataset_id, raw, record_type):
    rejected = raw.get("accepted") is False or raw.get("rejected") is True
    if dataset_id in OPERATOR_SURFACES:
        return {
            "raw_acquisition_status": "local_private_only",
            "raw_redistribution_status": "private_by_default",
            "allowed_derived_statistics_status": "sanitized_consent_only",
            "accepted_for_qualitative_use": dataset_id != "OA-TELEM-CODEX-ROLLOUT",
            "accepted_for_numerical_routing": False,
            "human_review_required": True,
        }
    if rejected:
        return {
            "raw_acquisition_status": "rejected_no_download",
            "raw_redistribution_status": "blocked",
            "allowed_derived_statistics_status": "blocked",
            "accepted_for_qualitative_use": False,
            "accepted_for_numerical_routing": False,
            "human_review_required": False,
        }
    if dataset_id in BLOCKED_RAW:
        return {
            "raw_acquisition_status": "blocked",
            "raw_redistribution_status": "blocked",
            "allowed_derived_statistics_status": "blocked",
            "accepted_for_qualitative_use": True,
            "accepted_for_numerical_routing": False,
            "human_review_required": True,
        }
    if dataset_id == "ds_sweagent_demonstrations":
        return {
            "raw_acquisition_status": "bounded_after_audit",
            "raw_redistribution_status": "derived_only",
            "allowed_derived_statistics_status": "allowed_after_content_scan",
            "accepted_for_qualitative_use": True,
            "accepted_for_numerical_routing": False,
            "human_review_required": False,
        }
    raw_available = first(raw, "raw_trajectory_availability", "raw_trajectory_available")
    raw_status, _ = normalize_presence(raw_available)
    acquisition = "bounded_after_audit" if raw_status.startswith("present") else "metadata_only"
    explicit_numeric = (
        raw.get("accepted_for_numerical_routing") is True
        or raw.get("accepted_for_quantitative_priors") is True
    )
    return {
        "raw_acquisition_status": acquisition,
        "raw_redistribution_status": "reference_only",
        "allowed_derived_statistics_status": "allowed_after_audit" if raw.get("license") else "unknown",
        "accepted_for_qualitative_use": True,
        "accepted_for_numerical_routing": explicit_numeric and raw.get("license") is not None,
        "human_review_required": raw.get("license") is None and acquisition != "metadata_only",
    }


def decision_label(rights, rejected):
    if rights["accepted_for_numerical_routing"]:
        return "accepted_numerical"
    if rejected:
        return "rejected"
    if rights["raw_acquisition_status"] == "blocked" or rights["allowed_derived_statistics_status"] in {"blocked", "unknown"}:
        return "blocked_pending_review"
    if rights["raw_acquisition_status"] in {"metadata_only", "local_private_only"}:
        return "metadata_only"
    return "accepted_qualitative"


def build_sources():
    raw_rows = []
    seen = set()
    for path in sorted(PACKETS.glob("**/SOURCES.jsonl")):
        packet = path.parent.name
        for raw in load_jsonl(path):
            source_id = first(raw, "source_id", "id")
            if not source_id:
                raise RegistryError(f"{path}: source has no stable ID")
            if source_id in seen:
                raise RegistryError(f"duplicate source ID {source_id}")
            seen.add(source_id)
            raw_url = first(raw, "url", "canonical_url", "canonical_source")
            canonical_url = SOURCE_URL_OVERRIDES.get(source_id, raw_url)
            raw_rows.append({
                "source_id": source_id,
                "title": first(raw, "title", "name"),
                "publisher": first(raw, "publisher", default="unknown"),
                "canonical_url": canonical_url,
                "api_endpoint": raw_url if isinstance(raw_url, str) and raw_url.startswith("https://api.openai.com/") else None,
                "tier": first(raw, "tier", default=1 if str(source_id).startswith("OA-") else 2),
                "source_type": first(raw, "source_type", "type"),
                "publication_date": first(raw, "publication_date", "date", "first_release_date"),
                "date_precision": first(raw, "date_precision"),
                "last_inspected": first(raw, "last_inspected", "accessed_date", default="2026-07-18"),
                "license": None if source_id == "SE-SRC-007" else first(raw, "license_scope", "license"),
                "redistribution_status": first(raw, "redistribution", "redistribution_status"),
                "claims_supported": first(raw, "claims_supported", "decisive_claims", "claims", default=[]),
                "limitations": first(raw, "limitations", default=[]),
                "original_refs": [f"{packet}:{source_id}"],
            })
    groups = {}
    for row in raw_rows:
        identity = (row["canonical_url"], row["api_endpoint"])
        groups.setdefault(identity, []).append(row)
    rows = []
    alias_map = {}
    for entries in groups.values():
        entries = sorted(entries, key=lambda row: row["source_id"])
        canonical = dict(entries[0])
        aliases = [row["source_id"] for row in entries[1:]]
        for alias in aliases:
            alias_map[alias] = canonical["source_id"]
        canonical["aliases"] = aliases
        canonical["original_refs"] = sorted({ref for row in entries for ref in row["original_refs"]})
        canonical["claims_supported"] = sorted({claim for row in entries for claim in row.get("claims_supported", [])})
        canonical["limitations"] = sorted({item for row in entries for item in row.get("limitations", [])})
        licenses = {row.get("license") for row in entries}
        if len(licenses) > 1:
            canonical["license"] = None
            canonical["limitations"].append("duplicate source records reported conflicting or incomplete license signals")
        redistributions = {row.get("redistribution_status") for row in entries}
        if len(redistributions) > 1:
            canonical["redistribution_status"] = "conflict_requires_review"
        canonical["tier"] = min(row["tier"] for row in entries)
        rows.append(canonical)
    return sorted(rows, key=lambda row: row["source_id"]), alias_map


def structured_size(dataset_id, raw):
    return {
        "compressed_bytes": None,
        "extracted_bytes": None,
        "repository_disk_usage_kib": REPOSITORY_DISK_USAGE_KIB.get(dataset_id),
        "container_bytes": None,
        "external_payload_bytes": None,
        "content_bytes": 1503861 if dataset_id == "ds_sweagent_demonstrations" else None,
        "file_count": 19 if dataset_id == "ds_sweagent_demonstrations" else None,
        "display_size_claim": DISPLAY_SIZE_CLAIMS.get(dataset_id),
        "size_kind": "sum_of_git_blob_content_bytes" if dataset_id == "ds_sweagent_demonstrations" else None,
        "size_source": "source packet and registry/license audit",
        "size_inspected_at": "2026-07-18",
    }


def build_datasets(source_ids, alias_map=None):
    alias_map = alias_map or {}
    rows = []
    seen = set()
    for path in sorted(PACKETS.glob("**/DATASETS.jsonl")):
        packet = path.parent.name
        for raw in load_jsonl(path):
            dataset_id = first(raw, "dataset_id", "id")
            if not dataset_id or dataset_id in seen:
                raise RegistryError(f"missing or duplicate dataset ID {dataset_id!r}")
            seen.add(dataset_id)
            raw_sources = raw.get("source_ids") or OFFICIAL_SOURCE_MAP.get(dataset_id, [])
            raw_sources = [alias_map.get(source_id, source_id) for source_id in raw_sources]
            missing_sources = sorted(set(raw_sources) - source_ids)
            if missing_sources:
                raise RegistryError(f"{dataset_id}: unresolved source IDs {missing_sources}")
            if not raw_sources:
                raise RegistryError(f"{dataset_id}: no source provenance")

            task_count, task_count_notes = normalize_count(first(raw, "number_of_tasks", "number_tasks", "tasks"))
            trajectory_count, trajectory_count_notes = normalize_count(first(raw, "number_of_trajectories", "number_trajectories", "trajectories"))
            model_list, model_notes = as_string_list(first(raw, "models_represented", "models"))
            framework_list, framework_notes = as_string_list(first(raw, "agent_frameworks_represented", "agent_frameworks", "frameworks"))
            field_data = {}
            for canonical, raw_names in {
                "token": ("token_fields_available", "token_fields"),
                "cost": ("cost_fields_available", "cost_fields"),
                "timing": ("timing_fields_available", "timing_fields"),
                "tool_call": ("tool_call_fields_available", "tool_call_fields"),
            }.items():
                values, status, notes = normalize_field_availability(first(raw, *raw_names))
                field_data[f"{canonical}_fields_available"] = values
                field_data[f"{canonical}_fields_status"] = status
                field_data[f"{canonical}_fields_notes"] = notes
            success_status, success_notes = normalize_presence(first(raw, "success_labels_available", "success_labels"))
            verifier_status, verifier_notes = normalize_presence(first(raw, "verifiers_available", "verifiers"))
            trajectory_status, trajectory_notes = normalize_presence(first(raw, "raw_trajectory_availability", "raw_trajectory_available"))
            name = first(raw, "name", "dataset_name")
            record_type = infer_record_type(dataset_id, name)
            rights = rights_decision(dataset_id, raw, record_type)
            rejected = raw.get("accepted") is False or raw.get("rejected") is True

            if dataset_id in OPERATOR_SURFACES:
                software_license = "MIT/Apache source or schema where identified"
                telemetry_rights = "operator-controlled; private by default"
            else:
                software_license = raw.get("license")
                telemetry_rights = first(raw, "redistribution_status")

            first_release = first(raw, "first_release_date", "release_date")
            if dataset_id in DATE_SEMANTIC_OVERRIDES:
                first_release = DATE_SEMANTIC_OVERRIDES[dataset_id]
            row = {
                "dataset_id": dataset_id,
                "name": name,
                "publisher": first(raw, "publisher", default="unknown"),
                "record_type": record_type,
                "repository_or_canonical_source": first(raw, "canonical_source", "repository_or_canonical_source", "repository"),
                "source_ids": sorted(set(raw_sources)),
                "first_release_date": first_release,
                "first_public_evidence_date": first(raw, "first_release_date", "release_date"),
                "date_precision": first(raw, "date_precision"),
                "latest_inspected_version": first(raw, "latest_inspected_version", "version"),
                "license": raw.get("license"),
                "software_or_schema_license": software_license,
                "dataset_or_telemetry_rights": telemetry_rights,
                "redistribution_status": first(raw, "redistribution_status"),
                "commercial_use_status": first(raw, "commercial_use_status"),
                "attribution_requirement": first(raw, "attribution_requirement"),
                "trajectory_content_status": first(raw, "trajectory_content_status"),
                "personal_data_risk": first(raw, "personal_data_risk", default="unknown"),
                "secret_risk": first(raw, "secret_risk", default="unknown"),
                "chain_of_thought_or_hidden_reasoning_risk": first(raw, "hidden_reasoning_risk", "chain_of_thought_risk", default="unknown"),
                "task_domains": first(raw, "task_domains", "domains", default=[]),
                "number_of_tasks": task_count,
                "number_of_tasks_notes": task_count_notes,
                "number_of_trajectories": trajectory_count,
                "number_of_trajectories_notes": trajectory_count_notes,
                "models_represented": model_list,
                "models_represented_notes": model_notes,
                "agent_frameworks_represented": framework_list,
                "agent_frameworks_represented_notes": framework_notes,
                "success_labels_status": success_status,
                "success_labels_notes": success_notes,
                "verifiers_status": verifier_status,
                "verifiers_notes": verifier_notes,
                **field_data,
                "raw_trajectory_status": trajectory_status,
                "raw_trajectory_notes": trajectory_notes,
                "download_method": first(raw, "download_method", "acquisition_method"),
                "estimated_download_size": first(raw, "estimated_download_size", "estimated_size", "download_size"),
                "estimated_extracted_size": first(raw, "estimated_extracted_size", "extracted_size"),
                "structured_size": structured_size(dataset_id, raw),
                "quality_class": first(raw, "quality_class", "preliminary_quality"),
                "quality_risks": first(raw, "quality_risks", "risks", default=[]),
                "comparability_risks": first(raw, "comparability_risks", default=[]),
                "failure_trajectory_coverage": first(raw, "failure_trajectory_coverage"),
                "accepted_for_registry": first(raw, "accepted_for_discovery_registry", default=not rejected) is not False,
                **rights,
                "decision": decision_label(rights, rejected),
                "rejection_reason": first(raw, "rejection_reason", "exclusion_reason"),
                "accepted_use": first(raw, "accepted_use"),
                "original_refs": [f"{packet}:{dataset_id}"],
            }
            rows.append(row)
    return sorted(rows, key=lambda row: row["dataset_id"])


def validate_output(sources, datasets):
    source_ids = {row["source_id"] for row in sources}
    if len(source_ids) != len(sources):
        raise RegistryError("duplicate source IDs in output")
    dataset_ids = {row["dataset_id"] for row in datasets}
    if len(dataset_ids) != len(datasets):
        raise RegistryError("duplicate dataset IDs in output")
    for row in datasets:
        if not row["source_ids"] or not set(row["source_ids"]) <= source_ids:
            raise RegistryError(f"{row['dataset_id']}: invalid source references")
        for field in ["token_fields_available", "cost_fields_available", "timing_fields_available", "tool_call_fields_available"]:
            if not all(isinstance(item, str) for item in row[field]):
                raise RegistryError(f"{row['dataset_id']}: non-string item in {field}")
        for field in ["number_of_tasks", "number_of_trajectories"]:
            if row[field] is not None and not isinstance(row[field], int):
                raise RegistryError(f"{row['dataset_id']}: non-integer {field}")
        if row["accepted_for_numerical_routing"] and row["allowed_derived_statistics_status"] not in {"allowed", "allowed_after_audit"}:
            raise RegistryError(f"{row['dataset_id']}: numerical use conflicts with rights")


def write_markdown(sources, datasets):
    source_lines = [
        "# Source Registry", "",
        f"Canonical sources: {len(sources)}. Evidence cutoff: 2026-07-18.", "",
        "IDs are stable packet/publisher identifiers. Source and telemetry-content rights are separate.", "",
        "| ID | Tier | Source | Publisher | Date | License signal |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for row in sources:
        label = row["title"] or row["canonical_url"] or row["source_id"]
        linked = f"[{label}]({row['canonical_url']})" if row["canonical_url"] else label
        source_lines.append(
            f"| {row['source_id']} | {row['tier']} | {linked} | {row['publisher']} | "
            f"{row['publication_date'] or 'unknown'} | {row['license'] or 'unknown'} |"
        )
    source_lines.append("")
    (SOURCES_DIR / "SOURCE_REGISTRY.md").write_text("\n".join(source_lines), encoding="utf-8")

    dataset_lines = [
        "# Dataset Registry", "",
        f"Discovered records: {len(datasets)}. Discovery inclusion is distinct from acquisition, redistribution, derived-statistics, and numerical-routing permission.", "",
        "| ID | Record | Type | Token fields | Raw acquisition | Derived use | Decision | Size signal |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in datasets:
        label = row["name"] or row["dataset_id"]
        linked = f"[{label}]({row['repository_or_canonical_source']})" if row["repository_or_canonical_source"] else label
        token_fields = ", ".join(row["token_fields_available"]) or row["token_fields_status"]
        size = row["structured_size"]["display_size_claim"] or row["structured_size"]["content_bytes"] or row["estimated_download_size"] or "unknown"
        dataset_lines.append(
            f"| {row['dataset_id']} | {linked} | {row['record_type']} | {token_fields} | "
            f"{row['raw_acquisition_status']} | {row['allowed_derived_statistics_status']} | "
            f"{row['decision']} | {size} |"
        )
    dataset_lines.extend([
        "", "Unknown fields, sizes, licenses, and counts remain `null`; booleans are never converted into fictitious field names.",
        "", "A code or schema license does not license captured prompts, responses, traces, web pages, or operator telemetry.", "",
    ])
    (SOURCES_DIR / "DATASET_REGISTRY.md").write_text("\n".join(dataset_lines), encoding="utf-8")


def main():
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    sources, alias_map = build_sources()
    datasets = build_datasets({row["source_id"] for row in sources}, alias_map)
    validate_output(sources, datasets)
    write_jsonl(SOURCES_DIR / "source_registry.jsonl", sources)
    write_jsonl(SOURCES_DIR / "dataset_registry.jsonl", datasets)
    write_markdown(sources, datasets)
    print(json.dumps({
        "status": "PASS",
        "sources": len(sources),
        "datasets": len(datasets),
        "accepted_numerical": sum(row["accepted_for_numerical_routing"] for row in datasets),
        "blocked": sum(row["decision"] == "blocked_pending_review" for row in datasets),
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except RegistryError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2))
        raise SystemExit(1)
