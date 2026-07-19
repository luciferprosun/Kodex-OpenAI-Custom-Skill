"""Deterministic raw-to-derived telemetry dataset construction."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Iterator
import uuid

from smart_codex.runtime.telemetry.config import ExternalTelemetryConfig, load_external_config
from smart_codex.runtime.telemetry.errors import TelemetryStorageError, TelemetryValidationError
from smart_codex.runtime.telemetry.models import canonical_json, verify_record_hash
from smart_codex.runtime.telemetry.mounts import verify_mount
from smart_codex.runtime.telemetry.schema import MAX_RECORD_BYTES
from smart_codex.runtime.telemetry.validator import validate_outcome_record, validate_run_record


DATASET_VERSION = "1.0.0"
DATASET_FILE = "telemetry_dataset.jsonl"
MANIFEST_FILE = "dataset_manifest.json"
EXCLUSIONS_FILE = "dataset_exclusions.json"
STATE_FILE = "dataset_state.json"


def _config() -> ExternalTelemetryConfig:
    config = load_external_config()
    if config is None:
        raise TelemetryStorageError("EXTERNAL_STORAGE_NOT_CONFIGURED")
    verification = verify_mount(
        config.telemetry_root,
        config.device_uuid,
        minimum_free_bytes=config.limits.min_free_bytes,
    )
    if not verification.ok:
        raise TelemetryStorageError(verification.reason)
    return config


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise TelemetryStorageError("DERIVED_TARGET_UNSAFE")
    temporary = path.parent / f".{path.name}-{uuid.uuid4()}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        try:
            position = 0
            while position < len(payload):
                written = os.write(descriptor, payload[position:])
                if written <= 0:
                    raise TelemetryStorageError("DERIVED_PARTIAL_WRITE")
                position += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, path)


def _raw_records(root: Path) -> Iterator[tuple[dict[str, Any] | None, str, str]]:
    raw = root / "raw"
    if not raw.exists():
        return
    for path in sorted(raw.rglob("codex_runs-*.jsonl")):
        try:
            info = path.lstat()
        except OSError:
            yield None, "RAW_FILE_INSPECTION_FAILED", path.name
            continue
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            yield None, "RAW_FILE_UNSAFE", path.name
            continue
        try:
            with path.open("rb") as handle:
                for number, line in enumerate(handle, 1):
                    if not line.endswith(b"\n"):
                        yield None, "TRAILING_FRAGMENT", f"{path.name}:{number}"
                        continue
                    if len(line) > MAX_RECORD_BYTES + 1:
                        yield None, "RECORD_TOO_LARGE", f"{path.name}:{number}"
                        continue
                    try:
                        value = json.loads(line)
                    except (UnicodeDecodeError, ValueError):
                        yield None, "INVALID_JSON", f"{path.name}:{number}"
                        continue
                    if not isinstance(value, dict):
                        yield None, "RECORD_NOT_OBJECT", f"{path.name}:{number}"
                        continue
                    yield value, "VALID", f"{path.name}:{number}"
        except OSError:
            yield None, "RAW_FILE_READ_FAILED", path.name


def _row(run: dict[str, Any], outcome: dict[str, Any] | None) -> dict[str, Any]:
    total_source = run.get("measurement_sources", {}).get("total_reported_tokens")
    total_tokens = run.get("total_reported_tokens") if total_source != "unknown" else None
    input_tokens = run.get("input_tokens")
    cached_tokens = run.get("cached_input_tokens")
    cache_ratio = (
        cached_tokens / input_tokens
        if isinstance(input_tokens, int) and input_tokens > 0 and isinstance(cached_tokens, int)
        else None
    )
    return {
        "dataset_version": DATASET_VERSION,
        "schema_version": run.get("schema_version"),
        "run_id": run.get("run_id"),
        "run_record_hash": run.get("record_hash"),
        "outcome_record_hash": outcome.get("record_hash") if outcome else None,
        "started_at": run.get("started_at"),
        "task_domain": run.get("task_domain"),
        "task_subdomain": run.get("task_subdomain"),
        "task_difficulty": run.get("task_difficulty"),
        "task_scope": run.get("task_scope"),
        "task_risk": run.get("task_risk"),
        "verification_available": run.get("verification_available"),
        "workspace_signature": run.get("workspace_signature"),
        "window_id": run.get("window_id"),
        "router_policy_version": run.get("router_policy_version"),
        "codex_protocol_version": run.get("codex_protocol_version"),
        "recommended_model": run.get("recommended_model"),
        "launched_model": run.get("launched_model"),
        "backend_model": run.get("backend_model"),
        "model_identity_status": run.get("model_identity_status"),
        "reasoning_effort": run.get("reasoning_effort"),
        "agent_count": run.get("agent_count"),
        "sandbox": run.get("sandbox"),
        "approval_policy": run.get("approval_policy"),
        "product_surface": run.get("product_surface"),
        "counter_reconciliation": run.get("counter_reconciliation"),
        "input_tokens": run.get("input_tokens"),
        "non_cached_input_tokens": run.get("non_cached_input_tokens"),
        "cached_input_tokens": run.get("cached_input_tokens"),
        "reasoning_tokens": run.get("reasoning_tokens"),
        "visible_output_tokens": run.get("visible_output_tokens"),
        "total_reported_tokens": total_tokens,
        "cache_ratio": cache_ratio,
        "wall_time_ms": run.get("wall_time_ms"),
        "request_count": run.get("request_count"),
        "tool_call_count": run.get("tool_call_count"),
        "retry_count": run.get("retry_count"),
        "compaction_count": run.get("compaction_count"),
        "collector_status": run.get("collector_status"),
        "operator_outcome": outcome.get("operator_outcome") if outcome else None,
        "edit_magnitude": outcome.get("edit_magnitude", "unknown") if outcome else None,
        "followup_turns": outcome.get("followup_turns") if outcome else None,
        "failure_category": outcome.get("failure_category", "none") if outcome else None,
        "verifier_type": outcome.get("verifier_type") if outcome else run.get("verifier_type"),
        "verifier_result": outcome.get("verifier_result") if outcome else run.get("verifier_result"),
        "tests_passed": outcome.get("tests_passed") if outcome else run.get("tests_passed"),
        "tests_failed": outcome.get("tests_failed") if outcome else run.get("tests_failed"),
        "token_comparison_usable": isinstance(total_tokens, int),
    }


def build_dataset() -> dict[str, Any]:
    config = _config()
    exclusions: Counter[str] = Counter()
    unique: dict[str, dict[str, Any]] = {}
    for record, status, location in _raw_records(config.telemetry_root):
        if record is None:
            exclusions[status] += 1
            continue
        record_hash = record.get("record_hash")
        if not isinstance(record_hash, str) or not verify_record_hash(record):
            exclusions["RECORD_HASH_INVALID"] += 1
            continue
        try:
            if record.get("record_type") == "run":
                validate_run_record(record)
            elif record.get("record_type") == "outcome":
                validate_outcome_record(record)
            else:
                exclusions["UNKNOWN_RECORD_TYPE"] += 1
                continue
        except TelemetryValidationError as exc:
            exclusions[f"INVALID_{exc.category}"] += 1
            continue
        if record_hash in unique:
            exclusions["DUPLICATE_RECORD"] += 1
            continue
        unique[record_hash] = record

    runs = [value for value in unique.values() if value.get("record_type") == "run"]
    run_hashes = {str(run["run_id"]): str(run["record_hash"]) for run in runs}
    outcomes = [value for value in unique.values() if value.get("record_type") == "outcome"]
    valid_outcomes: list[dict[str, Any]] = []
    seen_outcomes: dict[str, set[str]] = {}
    for outcome in sorted(outcomes, key=lambda item: (str(item.get("operator_outcome_at")), str(item.get("outcome_id")))):
        run_id = str(outcome.get("run_id"))
        if run_hashes.get(run_id) != outcome.get("original_record_hash"):
            exclusions["ORPHANED_OUTCOME"] += 1
            continue
        supersedes = outcome.get("supersedes_outcome_id")
        if supersedes is not None and supersedes not in seen_outcomes.get(run_id, set()):
            exclusions["ORPHANED_OUTCOME_CORRECTION"] += 1
            continue
        valid_outcomes.append(outcome)
        seen_outcomes.setdefault(run_id, set()).add(str(outcome.get("outcome_id")))
    latest: dict[str, dict[str, Any]] = {}
    for outcome in valid_outcomes:
        latest[str(outcome["run_id"])] = outcome

    rows: list[dict[str, Any]] = []
    schema_protocol_groups: Counter[str] = Counter()
    group_rows: dict[str, list[dict[str, Any]]] = {}
    for run in sorted(runs, key=lambda item: str(item.get("run_id"))):
        if run.get("synthetic") is True:
            exclusions["SYNTHETIC_VALIDATION_RECORD"] += 1
            continue
        row = _row(run, latest.get(str(run["run_id"])))
        group = f"{row['schema_version']}|{row['codex_protocol_version'] or 'unknown'}"
        schema_protocol_groups[group] += 1
        group_rows.setdefault(group, []).append(row)
        rows.append(row)

    dataset_payload = b"".join(
        canonical_json(row).encode("utf-8") + b"\n" for row in rows
    )
    dataset_hash = hashlib.sha256(dataset_payload).hexdigest()
    input_hash = hashlib.sha256(
        canonical_json({"record_hashes": sorted(unique)}).encode("utf-8")
    ).hexdigest()
    evidence_cutoff = max(
        (
            str(record.get("finished_at") or record.get("operator_outcome_at") or "")
            for record in unique.values()
        ),
        default=None,
    )
    group_files: dict[str, str] = {}
    derived = config.telemetry_root / "derived"
    for group, values in sorted(group_rows.items()):
        group_id = hashlib.sha256(group.encode("utf-8")).hexdigest()[:16]
        relative = f"by-contract/telemetry_dataset-{group_id}.jsonl"
        payload = b"".join(canonical_json(row).encode("utf-8") + b"\n" for row in values)
        _atomic_write(derived / relative, payload)
        group_files[group] = relative
    manifest: dict[str, Any] = {
        "dataset_version": DATASET_VERSION,
        "input_set_hash": input_hash,
        "dataset_hash": dataset_hash,
        "record_count": len(rows),
        "valid_raw_record_count": len(unique),
        "labeled_run_count": sum(row["operator_outcome"] is not None for row in rows),
        "known_token_run_count": sum(row["token_comparison_usable"] is True for row in rows),
        "schema_protocol_groups": dict(sorted(schema_protocol_groups.items())),
        "contract_group_files": group_files,
        "exclusions": dict(sorted(exclusions.items())),
        "evidence_cutoff": evidence_cutoff,
        "deterministic_order": "run_id",
        "raw_is_source_of_truth": True,
    }
    manifest["manifest_hash"] = hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
    _atomic_write(derived / DATASET_FILE, dataset_payload)
    _atomic_write(derived / MANIFEST_FILE, canonical_json(manifest).encode("utf-8") + b"\n")
    _atomic_write(
        derived / EXCLUSIONS_FILE,
        canonical_json({"exclusions": dict(sorted(exclusions.items()))}).encode("utf-8") + b"\n",
    )
    _atomic_write(
        derived / STATE_FILE,
        canonical_json({"state": "CURRENT", "manifest_hash": manifest["manifest_hash"]}).encode("utf-8") + b"\n",
    )
    return manifest


def mark_dataset_stale(reason: str = "NEW_OUTCOME") -> None:
    config = _config()
    _atomic_write(
        config.telemetry_root / "derived" / STATE_FILE,
        canonical_json({"state": "STALE", "reason": reason}).encode("utf-8") + b"\n",
    )


def dataset_status() -> dict[str, Any]:
    config = _config()
    state_path = config.telemetry_root / "derived" / STATE_FILE
    state: dict[str, Any] | None = None
    if state_path.is_file() and not state_path.is_symlink():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"state": "INVALID", "manifest": None}
        if isinstance(state, dict) and state.get("state") == "STALE":
            return {"state": "STALE", "manifest": None, "reason": state.get("reason")}
    manifest = config.telemetry_root / "derived" / MANIFEST_FILE
    if not manifest.is_file() or manifest.is_symlink():
        return {"state": "STALE_OR_MISSING", "manifest": None}
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "INVALID", "manifest": None}
    if not isinstance(value, dict):
        return {"state": "INVALID", "manifest": None}
    claimed_hash = value.get("manifest_hash")
    unsigned = {key: item for key, item in value.items() if key != "manifest_hash"}
    actual_hash = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()
    if claimed_hash != actual_hash:
        return {"state": "INVALID", "manifest": None, "reason": "MANIFEST_HASH_MISMATCH"}
    if isinstance(state, dict) and state.get("state") == "CURRENT":
        if state.get("manifest_hash") != claimed_hash:
            return {"state": "INVALID", "manifest": None, "reason": "STATE_MANIFEST_MISMATCH"}
    return {"state": "CURRENT", "manifest": value}


def load_rows() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = _config()
    status = dataset_status()
    manifest = status.get("manifest")
    if status.get("state") != "CURRENT" or not isinstance(manifest, dict):
        raise TelemetryStorageError("DERIVED_DATASET_NOT_READY")
    path = config.telemetry_root / "derived" / DATASET_FILE
    rows: list[dict[str, Any]] = []
    try:
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != manifest.get("dataset_hash"):
            raise TelemetryStorageError("DERIVED_DATASET_HASH_MISMATCH")
        for line in payload.splitlines():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TelemetryStorageError("DERIVED_DATASET_MALFORMED")
            rows.append(value)
    except (OSError, ValueError) as exc:
        raise TelemetryStorageError("DERIVED_DATASET_READ_FAILED") from exc
    return manifest, rows
