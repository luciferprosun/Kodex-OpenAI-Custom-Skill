#!/usr/bin/env python3
"""Dependency-free structural and corpus validation for research 2A."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
MEASUREMENT_VALUES = {
    "measured",
    "provider_reported",
    "framework_reported",
    "reconstructed",
    "estimated",
    "unknown",
}
QUALITY_SCORE_RANGES = {
    "A": (90, 100),
    "B": (75, 89),
    "C": (55, 74),
    "D": (30, 54),
    "E": (0, 29),
}
QUALITY_COMPONENT_FIELDS = {
    "exact_model_identity",
    "exact_agent_identity",
    "exact_task_identity",
    "provider_reported_tokens",
    "complete_request_breakdown",
    "complete_public_safe_trajectory",
    "objective_verifier",
    "timestamped_price_table",
    "repeatable_acquisition",
    "license_clarity",
}
NUMERICAL_ADMISSION_REQUIRED_FIELDS = {
    "timestamp",
    "model_id",
    "model_version",
    "model_provider",
    "product_surface",
    "agent_framework",
    "agent_version",
    "task_id",
    "prompt_tokens",
    "total_reported_tokens",
    "task_success",
    "verifier_type",
    "verifier_result",
}
ACCOUNTING_FIELDS = {
    "prompt_tokens",
    "non_cached_input_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
    "visible_output_tokens",
    "total_reported_tokens",
    "cumulative_session_tokens",
    "current_context_occupancy",
    "tokens_resent_from_history",
    "tokens_from_tool_output",
    "tokens_from_compaction",
    "api_billed_tokens",
    "subscription_quota_units",
    "number_of_model_requests",
    "number_of_tool_calls",
    "invalid_tool_calls",
    "repeated_tool_calls",
    "context_window",
    "peak_context_used",
    "context_compactions",
    "retry_count",
    "escalation_count",
    "wall_time_seconds",
    "human_review_minutes",
    "reported_cost",
    "normalized_cost",
    "tool_cost",
    "verification_cost",
    "human_review_cost",
    "failure_penalty_cost",
    "tool_output_tokens",
    "context_before_tokens",
    "context_after_tokens",
    "latency_seconds",
}


class ValidationError(Exception):
    pass


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path):
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValidationError(f"{path}:{line_number}: {exc}") from exc
    return records


def resolve_pointer(document, pointer: str):
    value = document
    if pointer in {"", "#"}:
        return value
    if not pointer.startswith("#/"):
        raise ValidationError(f"unsupported JSON pointer: {pointer}")
    for raw_part in pointer[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        value = value[part]
    return value


def resolve_ref(ref: str, schema_path: Path, schema):
    if ref.startswith("#"):
        return schema_path, schema, resolve_pointer(schema, ref)
    file_part, _, pointer = ref.partition("#")
    target_path = (schema_path.parent / file_part).resolve()
    if not target_path.exists():
        raise ValidationError(f"unresolved schema reference {ref} in {schema_path}")
    target_schema = load_json(target_path)
    target = resolve_pointer(target_schema, f"#{pointer}" if pointer else "#")
    return target_path, target_schema, target


def type_matches(value, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


def validate_instance(value, rule, schema_path: Path, root_schema, location="$"):
    if "$ref" in rule:
        target_path, target_schema, target = resolve_ref(rule["$ref"], schema_path, root_schema)
        validate_instance(value, target, target_path, target_schema, location)
        return

    if "const" in rule and value != rule["const"]:
        raise ValidationError(f"{location}: expected constant {rule['const']!r}")
    if "enum" in rule and value not in rule["enum"]:
        raise ValidationError(f"{location}: {value!r} not in enum")

    expected = rule.get("type")
    if expected:
        choices = expected if isinstance(expected, list) else [expected]
        if not any(type_matches(value, choice) for choice in choices):
            raise ValidationError(f"{location}: type mismatch, expected {choices}")

    if value is None:
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in rule and value < rule["minimum"]:
            raise ValidationError(f"{location}: below minimum")
        if "maximum" in rule and value > rule["maximum"]:
            raise ValidationError(f"{location}: above maximum")
    if isinstance(value, str):
        if "minLength" in rule and len(value) < rule["minLength"]:
            raise ValidationError(f"{location}: shorter than minLength")
        if "pattern" in rule and not re.fullmatch(rule["pattern"], value):
            raise ValidationError(f"{location}: pattern mismatch")
        if rule.get("format") == "date-time":
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        elif rule.get("format") == "date":
            date.fromisoformat(value)
        elif rule.get("format") == "uri" and not urlparse(value).scheme:
            raise ValidationError(f"{location}: URI has no scheme")
    if isinstance(value, list):
        if rule.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            raise ValidationError(f"{location}: duplicate array items")
        if "items" in rule:
            for index, item in enumerate(value):
                validate_instance(item, rule["items"], schema_path, root_schema, f"{location}[{index}]")
    if isinstance(value, dict):
        required = set(rule.get("required", []))
        missing = required - value.keys()
        if missing:
            raise ValidationError(f"{location}: missing required keys {sorted(missing)}")
        properties = rule.get("properties", {})
        if rule.get("additionalProperties") is False:
            extra = value.keys() - properties.keys()
            if extra:
                raise ValidationError(f"{location}: unexpected keys {sorted(extra)}")
        for key, item in value.items():
            if key in properties:
                validate_instance(item, properties[key], schema_path, root_schema, f"{location}.{key}")
            elif isinstance(rule.get("additionalProperties"), dict):
                validate_instance(
                    item,
                    rule["additionalProperties"],
                    schema_path,
                    root_schema,
                    f"{location}.{key}",
                )


def validate_schema_document(path: Path):
    schema = load_json(path)
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValidationError(f"{path}: unexpected schema dialect")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise ValidationError(f"{path}: top-level object must be strict")
    properties = set(schema.get("properties", {}))
    required = set(schema.get("required", []))
    if not required <= properties:
        raise ValidationError(f"{path}: required keys absent from properties")

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                resolve_ref(node["$ref"], path, schema)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(schema)


def validate_missingness(record, path: Path, index: int):
    missing = set(record.get("missing_fields", []))
    for field in missing:
        if field not in record:
            raise ValidationError(f"{path}:{index}: missing_fields names absent field {field}")
        if record[field] is not None:
            raise ValidationError(f"{path}:{index}: {field} listed missing but is not null")
    for field in ACCOUNTING_FIELDS & record.keys():
        method = record.get("measurement_method", {}).get(field)
        if record[field] is None:
            if field not in missing:
                raise ValidationError(f"{path}:{index}: null {field} not listed in missing_fields")
            if method != "unknown":
                raise ValidationError(f"{path}:{index}: null {field} must use unknown method")
        elif method not in MEASUREMENT_VALUES - {"unknown"}:
            raise ValidationError(f"{path}:{index}: observed {field} lacks measurement method")
    any_cost = any(
        record.get(field) is not None
        for field in [
            "reported_cost", "normalized_cost", "tool_cost", "verification_cost",
            "human_review_cost", "failure_penalty_cost",
        ]
        if field in record
    )
    if any_cost and record.get("cost_currency") is None:
        raise ValidationError(f"{path}:{index}: monetary value has no ISO currency")
    if record.get("reported_cost") is not None and record.get("reported_cost_scope") in {None, "unknown"}:
        raise ValidationError(f"{path}:{index}: reported cost has no usable scope")
    if record.get("normalized_cost") is not None:
        for field in ["price_table_date", "price_table_id", "cost_reconstruction_basis"]:
            if record.get(field) is None:
                raise ValidationError(f"{path}:{index}: normalized cost has no {field}")
        if record.get("normalized_cost_scope") in {None, "unknown"}:
            raise ValidationError(f"{path}:{index}: normalized cost has no usable scope")

    quality_class = record.get("quality_class")
    quality_score = record.get("quality_score")
    if quality_class in QUALITY_SCORE_RANGES:
        components = record.get("quality_components")
        if not isinstance(components, dict) or set(components) != QUALITY_COMPONENT_FIELDS:
            raise ValidationError(
                f"{path}:{index}: quality components are absent or incomplete"
            )
        if any(type(value) is not bool for value in components.values()):
            raise ValidationError(f"{path}:{index}: quality components must be boolean")
        recomputed_score = 10 * sum(components.values())
        if quality_score != recomputed_score:
            raise ValidationError(
                f"{path}:{index}: quality score {quality_score!r} does not equal "
                f"component score {recomputed_score}"
            )
        minimum, maximum = QUALITY_SCORE_RANGES[quality_class]
        if not isinstance(quality_score, int) or isinstance(quality_score, bool) or not minimum <= quality_score <= maximum:
            raise ValidationError(
                f"{path}:{index}: quality class {quality_class} disagrees with score {quality_score!r}"
            )

    if "included_in_numerical_priors" in record:
        included = record["included_in_numerical_priors"]
        if included and record.get("quality_class") not in {"A", "B", "C"}:
            raise ValidationError(f"{path}:{index}: only A-C records may enter numerical priors")
        if included and record.get("censored"):
            raise ValidationError(f"{path}:{index}: censored record included in numerical priors")
        provenance = record.get("provenance", {})
        if included and provenance.get("derived_statistics_status") != "allowed":
            raise ValidationError(f"{path}:{index}: numerical prior lacks derived-statistics permission")
        if included and provenance.get("privacy_review") not in {"passed", "sanitized"}:
            raise ValidationError(f"{path}:{index}: numerical prior lacks completed privacy review")
        if included and record.get("measurement_confidence") == "unknown":
            raise ValidationError(f"{path}:{index}: numerical prior has unknown measurement confidence")
        if included:
            absent = sorted(
                field for field in NUMERICAL_ADMISSION_REQUIRED_FIELDS
                if record.get(field) is None or record.get(field) == ""
            )
            if absent:
                raise ValidationError(
                    f"{path}:{index}: numerical prior lacks required evidence fields {absent}"
                )
            if record.get("prompt_tokens_scope") in {None, "unknown"}:
                raise ValidationError(f"{path}:{index}: numerical prior has unknown prompt-token scope")
            if record.get("total_reported_tokens_scope") in {None, "unknown"}:
                raise ValidationError(f"{path}:{index}: numerical prior has unknown total-token scope")
            if record.get("license") in {None, "", "unknown"}:
                raise ValidationError(f"{path}:{index}: numerical prior has no run-level license signal")
            if provenance.get("license") in {None, "", "unknown"}:
                raise ValidationError(f"{path}:{index}: numerical prior provenance has no license")
            if record.get("normalized_cost") is not None and record.get("normalized_cost_scope") != "run":
                raise ValidationError(
                    f"{path}:{index}: accepted-cost analysis requires run-scoped normalized cost"
                )

    if record.get("included_in_censoring_analysis") is True:
        if record.get("censored") is not True:
            raise ValidationError(f"{path}:{index}: censoring cohort contains an uncensored run")
        if record.get("quality_class") not in {"A", "B", "C"}:
            raise ValidationError(f"{path}:{index}: only A-C records may enter censoring analysis")
        provenance = record.get("provenance", {})
        if provenance.get("derived_statistics_status") != "allowed":
            raise ValidationError(f"{path}:{index}: censoring analysis lacks derived-statistics permission")
        if provenance.get("privacy_review") not in {"passed", "sanitized"}:
            raise ValidationError(f"{path}:{index}: censoring analysis lacks completed privacy review")
        if record.get("measurement_confidence") == "unknown":
            raise ValidationError(f"{path}:{index}: censoring analysis has unknown measurement confidence")
        identity_fields = {
            "timestamp", "model_id", "model_version", "model_provider", "product_surface",
            "agent_framework", "agent_version", "task_id", "censor_reason",
        }
        absent = sorted(field for field in identity_fields if record.get(field) in {None, ""})
        if absent:
            raise ValidationError(
                f"{path}:{index}: censoring analysis lacks required fields {absent}"
            )
        if record.get("wall_time_seconds") is None and record.get("total_reported_tokens") is None:
            raise ValidationError(
                f"{path}:{index}: censoring analysis needs observed time or token exposure"
            )

    if record.get("censored"):
        if not record.get("censor_reason"):
            raise ValidationError(f"{path}:{index}: censored run lacks censor_reason")
        if record.get("task_success") is not None:
            raise ValidationError(f"{path}:{index}: censored run must not be coded as ordinary success/failure")
    elif "censor_reason" in record and record.get("censor_reason") is not None:
        raise ValidationError(f"{path}:{index}: uncensored run has censor_reason")

    if record.get("attempt_sequence") is not None and not record.get("attempt_chain_id"):
        raise ValidationError(f"{path}:{index}: attempt sequence has no chain ID")
    if record.get("attempt_chain_complete") is True and not record.get("attempt_chain_id"):
        raise ValidationError(f"{path}:{index}: completed chain has no chain ID")
    if record.get("route_final_accepted") is True:
        if record.get("attempt_chain_complete") is not True or record.get("task_success") is not True:
            raise ValidationError(f"{path}:{index}: accepted route is not a complete successful chain")


def _unique(records, key_fn, label):
    seen = set()
    for index, record in enumerate(records, 1):
        key = key_fn(record)
        if key in seen:
            raise ValidationError(f"{label}:{index}: duplicate identity {key!r}")
        seen.add(key)


def validate_relations(corpora):
    runs = corpora.get("agent_runs.jsonl", [])
    requests = corpora.get("agent_requests.jsonl", [])
    tasks = corpora.get("tasks.jsonl", [])
    provenance_rows = corpora.get("provenance.jsonl", [])

    _unique(runs, lambda row: (row["dataset_id"], row["run_id"]), "agent_runs")
    _unique(requests, lambda row: (row["dataset_id"], row["run_id"], row["request_id"]), "agent_requests")
    _unique(tasks, lambda row: (row["dataset_id"], row["task_id"]), "tasks")
    _unique(provenance_rows, lambda row: row["source_id"], "provenance")

    registry_dataset_rows = load_jsonl(ROOT / "sources" / "dataset_registry.jsonl") \
        if (ROOT / "sources" / "dataset_registry.jsonl").exists() else []
    registry_datasets = {row["dataset_id"] for row in registry_dataset_rows}
    numerical_dataset_permission = {
        row["dataset_id"]: row.get("accepted_for_numerical_routing") is True
        for row in registry_dataset_rows
    }
    registry_sources = {
        row["source_id"] for row in load_jsonl(ROOT / "sources" / "source_registry.jsonl")
    } if (ROOT / "sources" / "source_registry.jsonl").exists() else set()
    task_index = {(row["dataset_id"], row["task_id"]): row for row in tasks}
    run_index = {(row["dataset_id"], row["run_id"]): row for row in runs}

    for collection_name, records in corpora.items():
        for index, row in enumerate(records, 1):
            if registry_datasets and row.get("dataset_id") is not None and row["dataset_id"] not in registry_datasets:
                raise ValidationError(f"{collection_name}:{index}: unknown dataset_id {row['dataset_id']}")
            if registry_sources and row["source_id"] not in registry_sources:
                raise ValidationError(f"{collection_name}:{index}: unknown source_id {row['source_id']}")
            embedded = row.get("provenance")
            if embedded:
                if embedded.get("source_id") != row.get("source_id"):
                    raise ValidationError(f"{collection_name}:{index}: embedded provenance source mismatch")
                if embedded.get("dataset_id") != row.get("dataset_id"):
                    raise ValidationError(f"{collection_name}:{index}: embedded provenance dataset mismatch")

    for index, run in enumerate(runs, 1):
        task = task_index.get((run["dataset_id"], run["task_id"]))
        if task is None:
            raise ValidationError(f"agent_runs:{index}: task reference not found")
        if run["task_domain"] != task["task_domain"]:
            raise ValidationError(f"agent_runs:{index}: task domain disagrees with task record")
        if run.get("included_in_numerical_priors") is True or run.get("included_in_censoring_analysis") is True:
            if numerical_dataset_permission.get(run["dataset_id"]) is not True:
                raise ValidationError(
                    f"agent_runs:{index}: dataset registry does not permit numerical analysis"
                )
            if task.get("success_criterion") in {None, "", "unknown"}:
                raise ValidationError(
                    f"agent_runs:{index}: numerical prior task has no success criterion"
                )
            if task.get("verifier_profile") in {None, "", "none", "unknown"}:
                raise ValidationError(
                    f"agent_runs:{index}: numerical prior task has no objective verifier profile"
                )

    requests_by_run = {}
    for index, request in enumerate(requests, 1):
        key = (request["dataset_id"], request["run_id"])
        if key not in run_index:
            raise ValidationError(f"agent_requests:{index}: run reference not found")
        requests_by_run.setdefault(key, []).append(request)

    sum_fields = [
        "prompt_tokens", "non_cached_input_tokens", "cached_input_tokens",
        "cache_write_tokens", "reasoning_tokens", "visible_output_tokens",
        "total_reported_tokens",
    ]
    for key, run in run_index.items():
        if not run.get("request_breakdown_complete"):
            continue
        related = requests_by_run.get(key, [])
        if run.get("number_of_model_requests") != len(related):
            raise ValidationError(f"agent_runs:{key}: complete request count disagrees with request records")
        sequences = [row["request_sequence"] for row in related]
        if len(sequences) != len(set(sequences)):
            raise ValidationError(f"agent_runs:{key}: duplicate request sequence")
        for field in sum_fields:
            if run.get(field) is None or any(row.get(field) is None for row in related):
                continue
            if field in {"prompt_tokens", "total_reported_tokens"} and run.get(f"{field}_scope") != "per_run_cumulative":
                continue
            if run[field] != sum(row[field] for row in related):
                raise ValidationError(f"agent_runs:{key}: {field} disagrees with complete request sum")
        if run.get("number_of_tool_calls") is not None:
            tool_count = sum(len(row.get("tool_calls", [])) for row in related)
            if run["number_of_tool_calls"] != tool_count:
                raise ValidationError(f"agent_runs:{key}: tool-call count disagrees with requests")

    chains = {}
    for run in runs:
        if run.get("attempt_chain_id"):
            chains.setdefault((run["dataset_id"], run["attempt_chain_id"]), []).append(run)
    for chain_id, chain_runs in chains.items():
        sequences = [row.get("attempt_sequence") for row in chain_runs]
        if None in sequences or len(sequences) != len(set(sequences)):
            raise ValidationError(f"attempt_chain:{chain_id}: missing or duplicate attempt sequence")
        if sorted(sequences) != list(range(1, len(sequences) + 1)):
            raise ValidationError(f"attempt_chain:{chain_id}: attempt sequence must be contiguous from one")
        task_keys = {(row["dataset_id"], row["task_id"]) for row in chain_runs}
        if len(task_keys) != 1:
            raise ValidationError(f"attempt_chain:{chain_id}: attempts refer to different tasks")
        accepted = [row for row in chain_runs if row.get("route_final_accepted") is True]
        if len(accepted) > 1:
            raise ValidationError(f"attempt_chain:{chain_id}: multiple final accepted runs")
        if accepted and accepted[0].get("attempt_sequence") != max(sequences):
            raise ValidationError(f"attempt_chain:{chain_id}: accepted attempt is not last")


def validate_corpus():
    schema_paths = sorted(SCHEMA_DIR.glob("*.schema.json"))
    for path in schema_paths:
        validate_schema_document(path)

    corpus_specs = [
        (ROOT / "data/normalized/agent_runs.jsonl", SCHEMA_DIR / "agent_run_record.schema.json"),
        (ROOT / "data/normalized/agent_requests.jsonl", SCHEMA_DIR / "agent_request_record.schema.json"),
        (ROOT / "data/normalized/tasks.jsonl", SCHEMA_DIR / "task_record.schema.json"),
        (ROOT / "data/normalized/provenance.jsonl", SCHEMA_DIR / "source_provenance.schema.json"),
    ]
    counts = {}
    corpora = {}
    for path, schema_path in corpus_specs:
        if not path.exists():
            counts[path.name] = 0
            corpora[path.name] = []
            continue
        schema = load_json(schema_path)
        records = load_jsonl(path)
        for index, record in enumerate(records, 1):
            validate_instance(record, schema, schema_path, schema)
            if path.name in {"agent_runs.jsonl", "agent_requests.jsonl"}:
                validate_missingness(record, path, index)
        counts[path.name] = len(records)
        corpora[path.name] = records
    validate_relations(corpora)
    return {"status": "PASS", "schemas": len(schema_paths), "records": counts}


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()
    try:
        result = validate_corpus()
    except (ValidationError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
