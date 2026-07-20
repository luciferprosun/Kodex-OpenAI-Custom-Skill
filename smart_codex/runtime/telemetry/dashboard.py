"""Read-only, metadata-only terminal view over validated local telemetry."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from .errors import TelemetryError, TelemetryStorageError
from .models import utc_now
from .privacy import scan_record
from .storage import LocalTelemetryStorage
from .validator import validate_outcome_record, validate_run_record


DASHBOARD_VERSION = "1.0.0"
DEFAULT_RUN_LIMIT = 2
MAX_RUN_LIMIT = 20
MAX_SOURCE_RECORDS = 100_000

QUARANTINED_LABELS = (
    "task_subdomain",
    "task_scope",
    "task_risk",
    "negation_sensitive_test_intent",
)

_PRIVATE_PROJECTION_KEYS = {
    "run_id",
    "session_id",
    "router_decision_id",
    "outcome_id",
    "supersedes_outcome_id",
    "record_hash",
    "original_record_hash",
    "task_signature",
    "workspace_signature",
    "tool_calls_by_type",
}
_HEX_64 = re.compile(r"^[a-f0-9]{64}$")
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass
class _Diagnostics:
    source_files: int = 0
    source_records_seen: int = 0
    invalid_records_excluded: int = 0
    duplicate_records_excluded: int = 0
    invalid_outcome_links_excluded: int = 0
    unsafe_source_files_excluded: int = 0
    unstable_source_files_excluded: int = 0

    def reject(self, _category: str) -> None:
        self.invalid_records_excluded += 1


def _safe_source_paths(
    storage: LocalTelemetryStorage,
    diagnostics: _Diagnostics,
) -> list[Path]:
    warning = storage.verify_mount()
    if warning is not None:
        raise TelemetryStorageError(f"DASHBOARD_{warning}")

    locations: list[tuple[Path, str]] = [(storage.paths.root, "codex_runs-*.jsonl")]
    if storage.paths.outcomes_root is not None:
        locations.append((storage.paths.outcomes_root, "codex_outcomes-*.jsonl"))

    paths: list[Path] = []
    for root, pattern in locations:
        if not root.exists():
            continue
        try:
            root_info = root.lstat()
        except OSError as exc:
            raise TelemetryStorageError("DASHBOARD_STORAGE_INSPECTION_FAILED") from exc
        if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
            raise TelemetryStorageError("DASHBOARD_STORAGE_ROOT_UNSAFE")
        try:
            candidates = sorted(root.rglob(pattern))
        except OSError as exc:
            raise TelemetryStorageError("DASHBOARD_STORAGE_SCAN_FAILED") from exc
        for path in candidates:
            try:
                path.relative_to(root)
                info = path.lstat()
            except (OSError, ValueError):
                diagnostics.unsafe_source_files_excluded += 1
                continue
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                diagnostics.unsafe_source_files_excluded += 1
                continue
            if info.st_size > storage.limits.max_file_bytes:
                diagnostics.unsafe_source_files_excluded += 1
                continue
            paths.append(path)
    diagnostics.source_files = len(paths)
    return paths


def _records_from_file(
    path: Path,
    storage: LocalTelemetryStorage,
    diagnostics: _Diagnostics,
) -> list[dict[str, Any]]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError:
        diagnostics.unsafe_source_files_excluded += 1
        return []

    values: list[dict[str, Any]] = []
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > storage.limits.max_file_bytes:
            diagnostics.unsafe_source_files_excluded += 1
            return []
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            for raw_line in handle:
                diagnostics.source_records_seen += 1
                if diagnostics.source_records_seen > MAX_SOURCE_RECORDS:
                    raise TelemetryStorageError("DASHBOARD_RECORD_LIMIT_EXCEEDED")
                if (
                    not raw_line.endswith(b"\n")
                    or len(raw_line) > storage.limits.max_record_bytes
                ):
                    diagnostics.reject("MALFORMED_JSONL_RECORD")
                    continue
                try:
                    value = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    diagnostics.reject("MALFORMED_JSONL_RECORD")
                    continue
                if not isinstance(value, dict):
                    diagnostics.reject("NON_OBJECT_RECORD")
                    continue
                values.append(value)
        after = os.fstat(descriptor)
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ino != after.st_ino
        ):
            diagnostics.unstable_source_files_excluded += 1
            return []
        return values
    finally:
        os.close(descriptor)


def _load_validated_records(
    storage: LocalTelemetryStorage,
    diagnostics: _Diagnostics,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runs_by_id: dict[str, dict[str, Any]] = {}
    outcomes_by_id: dict[str, dict[str, Any]] = {}
    duplicate_run_ids: set[str] = set()
    duplicate_outcome_ids: set[str] = set()

    for path in _safe_source_paths(storage, diagnostics):
        for record in _records_from_file(path, storage, diagnostics):
            record_type = record.get("record_type")
            try:
                if record_type == "run":
                    validate_run_record(record)
                    identifier = str(record["run_id"])
                    if identifier in runs_by_id or identifier in duplicate_run_ids:
                        diagnostics.duplicate_records_excluded += 1
                        duplicate_run_ids.add(identifier)
                        runs_by_id.pop(identifier, None)
                    else:
                        runs_by_id[identifier] = record
                elif record_type == "outcome":
                    validate_outcome_record(record)
                    identifier = str(record["outcome_id"])
                    if identifier in outcomes_by_id or identifier in duplicate_outcome_ids:
                        diagnostics.duplicate_records_excluded += 1
                        duplicate_outcome_ids.add(identifier)
                        outcomes_by_id.pop(identifier, None)
                    else:
                        outcomes_by_id[identifier] = record
                else:
                    diagnostics.reject("UNKNOWN_RECORD_TYPE")
            except TelemetryError as exc:
                diagnostics.reject(exc.category)

    return list(runs_by_id.values()), list(outcomes_by_id.values())


def _measurement(record: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = record.get(field_name)
    sources = record.get("measurement_sources")
    provenance = sources.get(field_name, "unknown") if isinstance(sources, dict) else "unknown"
    return {
        "value": value,
        "availability": "available" if value is not None else "unavailable",
        "provenance": provenance,
    }


def _verification_projection(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "availability": record.get("verification_available"),
        "type": record.get("verifier_type"),
        "result": record.get("verifier_result"),
        "tests_passed": record.get("tests_passed"),
        "tests_failed": record.get("tests_failed"),
        "authority": "advisory",
    }


def _human_outcome_projection(outcome: dict[str, Any] | None) -> dict[str, Any]:
    if outcome is None:
        return {
            "status": "unavailable",
            "outcome": None,
            "recorded_at": None,
            "edit_magnitude": None,
            "followup_turns": None,
            "failure_category": None,
            "authority": "explicit_human_label_only",
        }
    return {
        "status": "recorded",
        "outcome": outcome.get("operator_outcome"),
        "recorded_at": outcome.get("operator_outcome_at"),
        "edit_magnitude": outcome.get("edit_magnitude"),
        "followup_turns": outcome.get("followup_turns"),
        "failure_category": outcome.get("failure_category"),
        "authority": "explicit_human_label_only",
    }


def _run_projection(
    run: dict[str, Any],
    outcome: dict[str, Any] | None,
    *,
    display_index: int,
) -> dict[str, Any]:
    exclusive_fields = (
        "non_cached_input_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "visible_output_tokens",
    )
    exclusive_values = [run.get(field_name) for field_name in exclusive_fields]
    reported_total = run.get("total_reported_tokens")
    if all(isinstance(value, int) for value in exclusive_values):
        exclusive_sum: int | None = sum(exclusive_values)
    else:
        exclusive_sum = None
    total_matches = (
        exclusive_sum == reported_total
        if exclusive_sum is not None and isinstance(reported_total, int)
        else None
    )

    operator_verification = _verification_projection(outcome) if outcome is not None else {
        "availability": None,
        "type": None,
        "result": None,
        "tests_passed": None,
        "tests_failed": None,
        "authority": "advisory",
    }
    return {
        "display_index": display_index,
        "finished_at": run.get("finished_at"),
        "route": {
            "requested_model": _measurement(run, "requested_model"),
            "recommended_model": _measurement(run, "recommended_model"),
            "launched_model": _measurement(run, "launched_model"),
            "backend_model": _measurement(run, "backend_model"),
            "reasoning_effort": _measurement(run, "reasoning_effort"),
            "sandbox": run.get("sandbox"),
            "approval_policy": run.get("approval_policy"),
            "authority": "advisory_route",
        },
        "usage": {
            "input_tokens": _measurement(run, "input_tokens"),
            "non_cached_input_tokens": _measurement(run, "non_cached_input_tokens"),
            "cached_input_tokens": _measurement(run, "cached_input_tokens"),
            "reasoning_tokens": _measurement(run, "reasoning_tokens"),
            "visible_output_tokens": _measurement(run, "visible_output_tokens"),
            "total_reported_tokens": _measurement(run, "total_reported_tokens"),
            "exclusive_bucket_sum": exclusive_sum,
            "exclusive_sum_matches_reported_total": total_matches,
            "cost": None,
            "cost_status": "not_calculated_no_local_price_provenance",
        },
        "performance": {
            "wall_time_ms": _measurement(run, "wall_time_ms"),
            "time_to_first_token_ms": {
                "value": None,
                "availability": "unavailable",
                "provenance": "unknown",
            },
        },
        "operations": {
            "request_count": _measurement(run, "request_count"),
            "retry_count": _measurement(run, "retry_count"),
            "tool_call_count": _measurement(run, "tool_call_count"),
            "invalid_tool_call_count": _measurement(run, "invalid_tool_call_count"),
            "escalation_count": _measurement(run, "escalation_count"),
            "compaction_count": _measurement(run, "compaction_count"),
            "agent_count": _measurement(run, "agent_count"),
            "duplicate_event_count": run.get("duplicate_event_count"),
            "invalid_event_count": run.get("invalid_event_count"),
        },
        "quality": {
            "runtime_verification": _verification_projection(run),
            "operator_recorded_verification": operator_verification,
            "human_outcome": _human_outcome_projection(outcome),
            "verification_is_outcome": False,
        },
        "integrity": {
            "schema_version": run.get("schema_version"),
            "schema_hash_privacy_validation": "passed",
            "outcome_link_validation": "passed" if outcome is not None else "not_applicable",
            "privacy_classification": run.get("privacy_classification"),
            "collector_status": run.get("collector_status"),
            "counter_reconciliation": run.get("counter_reconciliation"),
            "product_surface": run.get("product_surface"),
        },
    }


def _assert_projection_safe(value: Any, *, key: str | None = None) -> None:
    if key in _PRIVATE_PROJECTION_KEYS:
        raise TelemetryStorageError("DASHBOARD_PRIVATE_FIELD")
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            if not isinstance(child_key, str):
                raise TelemetryStorageError("DASHBOARD_NON_STRING_FIELD")
            _assert_projection_safe(child_value, key=child_key)
        return
    if isinstance(value, list):
        for child in value:
            _assert_projection_safe(child)
        return
    if isinstance(value, str) and (_HEX_64.fullmatch(value) or _UUID.fullmatch(value)):
        raise TelemetryStorageError("DASHBOARD_PRIVATE_IDENTIFIER")


def build_dashboard(
    storage: LocalTelemetryStorage,
    *,
    limit: int = DEFAULT_RUN_LIMIT,
) -> dict[str, Any]:
    """Build a strictly allowlisted view without writing source or derived files."""

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RUN_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_RUN_LIMIT}")

    diagnostics = _Diagnostics()
    runs, outcomes = _load_validated_records(storage, diagnostics)
    run_hashes = {str(run["run_id"]): str(run["record_hash"]) for run in runs}
    linked_outcomes: list[dict[str, Any]] = []
    for outcome in outcomes:
        if run_hashes.get(str(outcome["run_id"])) == outcome.get("original_record_hash"):
            linked_outcomes.append(outcome)
        else:
            diagnostics.invalid_outcome_links_excluded += 1

    latest_outcomes: dict[str, dict[str, Any]] = {}
    for outcome in linked_outcomes:
        run_id = str(outcome["run_id"])
        current = latest_outcomes.get(run_id)
        if current is None or str(outcome["operator_outcome_at"]) > str(current["operator_outcome_at"]):
            latest_outcomes[run_id] = outcome

    synthetic_runs_excluded = sum(run.get("synthetic") is True for run in runs)
    eligible_runs = [run for run in runs if run.get("synthetic") is not True]
    eligible_runs.sort(key=lambda run: str(run.get("finished_at", "")), reverse=True)
    displayed = eligible_runs[:limit]
    if limit >= 2 and displayed and latest_outcomes:
        latest_labeled = next(
            (
                run
                for run in eligible_runs
                if str(run["run_id"]) in latest_outcomes
            ),
            None,
        )
        displayed_ids = {str(run["run_id"]) for run in displayed}
        if latest_labeled is not None and str(latest_labeled["run_id"]) not in displayed_ids:
            displayed[-1] = latest_labeled
    projections = [
        _run_projection(
            run,
            latest_outcomes.get(str(run["run_id"])),
            display_index=index,
        )
        for index, run in enumerate(displayed, start=1)
    ]

    snapshot: dict[str, Any] = {
        "dashboard_version": DASHBOARD_VERSION,
        "title": "SmartRouter Local Telemetry Demo View 1A",
        "generated_at": utc_now(),
        "posture": {
            "source_of_truth": "local_jsonl",
            "local_only": True,
            "metadata_only": True,
            "read_only": True,
            "external_export": False,
            "routing_authority": "advisory",
            "telemetry_authority": "descriptive_not_authoritative",
            "verification_authority": "advisory",
            "protected_effects": "explicit_human_approval_required",
        },
        "label_quality": {
            "status": "quarantined",
            "fields": list(QUARANTINED_LABELS),
            "excluded_from": ["display_values", "ranking", "evaluation", "learning", "export"],
            "warning": (
                "Known semantic-classifier defects make these labels unreliable; "
                "they are not used in this view."
            ),
        },
        "coverage": {
            "source_files": diagnostics.source_files,
            "source_records_seen": diagnostics.source_records_seen,
            "valid_runs": len(runs),
            "valid_outcomes": len(outcomes),
            "linked_outcomes": len(linked_outcomes),
            "eligible_non_synthetic_runs": len(eligible_runs),
            "outcome_labeled_runs": sum(
                str(run["run_id"]) in latest_outcomes for run in eligible_runs
            ),
            "displayed_runs": len(projections),
            "synthetic_runs_excluded": synthetic_runs_excluded,
            "invalid_records_excluded": diagnostics.invalid_records_excluded,
            "duplicate_records_excluded": diagnostics.duplicate_records_excluded,
            "invalid_outcome_links_excluded": diagnostics.invalid_outcome_links_excluded,
            "unsafe_source_files_excluded": diagnostics.unsafe_source_files_excluded,
            "unstable_source_files_excluded": diagnostics.unstable_source_files_excluded,
        },
        "runs": projections,
    }
    _assert_projection_safe(snapshot)
    scan_record(snapshot)
    return snapshot


def _format_measurement(
    measurement: dict[str, Any],
    *,
    missing: str = "Unavailable",
) -> str:
    value = measurement.get("value")
    if value is None:
        return missing
    formatted = f"{value:,}" if isinstance(value, int) and not isinstance(value, bool) else str(value)
    provenance = measurement.get("provenance")
    return f"{formatted} [{provenance}]" if provenance and provenance != "unknown" else formatted


def _format_milliseconds(measurement: dict[str, Any]) -> str:
    value = measurement.get("value")
    if not isinstance(value, int):
        return "Unavailable"
    return f"{value / 1000:.2f} s ({value:,} ms) [{measurement.get('provenance')}]"


def render_dashboard(snapshot: dict[str, Any]) -> str:
    """Render the safe projection as a dependency-free terminal dashboard."""

    lines = [
        "=" * 78,
        " SMARTROUTER LOCAL TELEMETRY DEMO VIEW 1A",
        " READ ONLY | LOCAL ONLY | METADATA ONLY | ADVISORY ONLY",
        "=" * 78,
        "",
        "LABEL QUALITY: QUARANTINED",
        "  Known semantic-classifier defects are excluded from display values,",
        "  ranking, evaluation, learning, and export.",
        "  Fields: " + ", ".join(snapshot["label_quality"]["fields"]),
        "",
    ]
    coverage = snapshot["coverage"]
    lines.extend(
        [
            "VALIDATED COVERAGE",
            (
                f"  {coverage['valid_runs']} valid runs | "
                f"{coverage['linked_outcomes']} linked outcomes | "
                f"{coverage['displayed_runs']} displayed"
            ),
            (
                f"  Excluded: {coverage['invalid_records_excluded']} invalid records, "
                f"{coverage['duplicate_records_excluded']} duplicate records, "
                f"{coverage['invalid_outcome_links_excluded']} invalid outcome links, "
                f"{coverage['synthetic_runs_excluded']} synthetic runs"
            ),
        ]
    )

    if not snapshot["runs"]:
        lines.extend(["", "No validated non-synthetic runs are available for display."])

    for run in snapshot["runs"]:
        route = run["route"]
        usage = run["usage"]
        performance = run["performance"]
        operations = run["operations"]
        quality = run["quality"]
        integrity = run["integrity"]
        runtime_verification = quality["runtime_verification"]
        operator_verification = quality["operator_recorded_verification"]
        human = quality["human_outcome"]
        exclusive_check = usage["exclusive_sum_matches_reported_total"]
        if exclusive_check is True:
            exclusive_status = "Matches reported total"
        elif exclusive_check is False:
            exclusive_status = "Mismatch (record should have been excluded)"
        else:
            exclusive_status = "Unavailable because one or more buckets are unknown"

        lines.extend(
            [
                "",
                "-" * 78,
                f"RUN {run['display_index']} | finished {run['finished_at']}",
                "-" * 78,
                "ROUTE IDENTITY (advisory)",
                f"  Requested model   : {_format_measurement(route['requested_model'])}",
                f"  Recommended model : {_format_measurement(route['recommended_model'])}",
                f"  Launched model    : {_format_measurement(route['launched_model'])}",
                f"  Backend model     : {_format_measurement(route['backend_model'])}",
                f"  Reasoning effort  : {_format_measurement(route['reasoning_effort'])}",
                f"  Sandbox / approval: {route['sandbox']} / {route['approval_policy']}",
                "",
                "USAGE (input total is inclusive; exclusive buckets are not double-counted)",
                f"  Input total       : {_format_measurement(usage['input_tokens'], missing='Unavailable (not zero)')}",
                f"  Non-cached input  : {_format_measurement(usage['non_cached_input_tokens'], missing='Unavailable (not zero)')}",
                f"  Cached input      : {_format_measurement(usage['cached_input_tokens'], missing='Unavailable (not zero)')}",
                f"  Reasoning output  : {_format_measurement(usage['reasoning_tokens'], missing='Unavailable (not zero)')}",
                f"  Visible output    : {_format_measurement(usage['visible_output_tokens'], missing='Unavailable (not zero)')}",
                f"  Reported total    : {_format_measurement(usage['total_reported_tokens'], missing='Unavailable (not zero)')}",
                f"  Exclusive check   : {exclusive_status}",
                "  Cost              : Not calculated (no local price provenance)",
                "",
                "PERFORMANCE",
                f"  Wall time         : {_format_milliseconds(performance['wall_time_ms'])}",
                "  Time to first token: Unavailable (not collected)",
                "",
                "OPERATIONS (unknown is never displayed as zero)",
                f"  Requests          : {_format_measurement(operations['request_count'], missing='Unavailable (not zero)')}",
                f"  Retries           : {_format_measurement(operations['retry_count'], missing='Unavailable (not zero)')}",
                f"  Tool calls        : {_format_measurement(operations['tool_call_count'], missing='Unavailable (not zero)')}",
                f"  Escalations       : {_format_measurement(operations['escalation_count'], missing='Unavailable (not zero)')}",
                f"  Duplicate events  : {operations['duplicate_event_count']:,}",
                f"  Invalid events    : {operations['invalid_event_count']:,}",
                "",
                "QUALITY SIGNALS (kept separate)",
                (
                    "  Runtime verification (advisory): "
                    f"{runtime_verification['result'] or 'Unavailable'}"
                ),
                (
                    "  Operator-recorded verification (advisory): "
                    f"{operator_verification['result'] or 'Unavailable'}"
                ),
                (
                    "  Human outcome (explicit label): "
                    f"{human['outcome'] or 'Unavailable'}"
                ),
                "",
                "INTEGRITY AND PRIVACY",
                (
                    "  Schema + hash + metadata privacy validation: "
                    f"{integrity['schema_hash_privacy_validation'].upper()}"
                ),
                f"  Outcome link validation: {integrity['outcome_link_validation'].upper()}",
                f"  Counter reconciliation: {integrity['counter_reconciliation']}",
                "  Stable identifiers, signatures, hashes, paths, and tool details: WITHHELD",
            ]
        )

    lines.extend(
        [
            "",
            "=" * 78,
            "AUTHORITY BOUNDARY",
            "  Routing, telemetry, and verification are advisory. They do not authorize",
            "  protected effects. Explicit human approval remains required.",
            "  Local JSONL remains authoritative and was opened read-only.",
            "=" * 78,
        ]
    )
    return "\n".join(lines)
