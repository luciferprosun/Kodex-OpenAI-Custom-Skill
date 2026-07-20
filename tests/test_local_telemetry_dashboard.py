from __future__ import annotations

import json
from pathlib import Path

from smart_codex import cli
from smart_codex.runtime.telemetry.collector import TelemetryService
from smart_codex.runtime.telemetry.dashboard import build_dashboard, render_dashboard
from smart_codex.runtime.telemetry.models import compute_record_hash
from smart_codex.runtime.telemetry.mounts import MountedFilesystem, verify_mount
from smart_codex.runtime.telemetry.outcome import record_outcome
from smart_codex.runtime.telemetry.storage import LocalTelemetryStorage

from telemetry_test_helpers import (
    enabled_service,
    exec_usage_event,
    records,
    start_basic,
    telemetry_storage,
)


def _recorded_demo_run(tmp_path: Path):
    service, storage = enabled_service(tmp_path)
    run = start_basic(
        service,
        requested_model="gpt-5.6-sol",
        recommended_model="gpt-5.6-terra",
        launched_model="gpt-5.6-terra",
        backend_model="gpt-5.6-terra",
        model_identity_status="provider_reported",
        task_subdomain="known_bad_fixture_label",
        task_scope="module",
        task_risk="critical",
    )
    assert run.consume_event(exec_usage_event(total_tokens=130)) is True
    tool_event = {
        "type": "item.started",
        "item": {"id": "tool-1", "type": "command_execution"},
    }
    assert run.consume_event(tool_event) is True
    assert run.consume_event(tool_event) is False
    assert run.finish(status="completed", process_exit_code=0).appended is True
    stored_run = records(storage, "run")[0]
    assert record_outcome(
        storage,
        stored_run["run_id"],
        "accepted-with-edits",
        tests_passed=2,
        tests_failed=0,
        edit_magnitude="minor",
    ).appended is True
    return storage, stored_run


def _source_bytes(storage: LocalTelemetryStorage) -> dict[Path, bytes]:
    roots = [storage.paths.root]
    if storage.paths.outcomes_root is not None:
        roots.append(storage.paths.outcomes_root)
    return {
        path: path.read_bytes()
        for root in roots
        if root.exists()
        for path in root.rglob("*.jsonl")
    }


def test_dashboard_projects_valid_run_and_human_outcome_without_private_linkage(tmp_path) -> None:
    storage, stored_run = _recorded_demo_run(tmp_path)
    before = _source_bytes(storage)

    dashboard = build_dashboard(storage, limit=1)
    rendered = render_dashboard(dashboard)
    serialized = json.dumps(dashboard, sort_keys=True)

    assert dashboard["coverage"]["displayed_runs"] == 1
    view = dashboard["runs"][0]
    assert view["route"]["requested_model"]["value"] == "gpt-5.6-sol"
    assert view["route"]["recommended_model"]["value"] == "gpt-5.6-terra"
    assert view["route"]["launched_model"]["value"] == "gpt-5.6-terra"
    assert view["route"]["backend_model"]["value"] == "gpt-5.6-terra"
    assert view["usage"]["exclusive_bucket_sum"] == 130
    assert view["usage"]["exclusive_sum_matches_reported_total"] is True
    assert view["quality"]["runtime_verification"]["result"] is None
    assert view["quality"]["operator_recorded_verification"]["result"] == "passed"
    assert view["quality"]["human_outcome"]["outcome"] == "accepted-with-edits"
    assert "Unavailable (not zero)" in rendered
    assert "LABEL QUALITY: QUARANTINED" in rendered
    assert dashboard["posture"]["max_semantics"] == "maximum_single_agent_reasoning"
    assert dashboard["posture"]["orchestration_observability"] == "unavailable_in_schema_2_0_0"
    assert "Max means maximum single-agent reasoning" in rendered
    assert "Routing, telemetry, and verification are advisory" in rendered

    for private_field in (
        "run_id",
        "session_id",
        "router_decision_id",
        "record_hash",
        "task_signature",
        "workspace_signature",
    ):
        private_value = stored_run.get(private_field)
        if private_value is not None:
            assert str(private_value) not in serialized
            assert str(private_value) not in rendered
    assert "known_bad_fixture_label" not in serialized
    assert "normal_coding" not in serialized
    assert '"module"' not in serialized
    assert '"critical"' not in serialized
    assert "command_execution" not in serialized
    assert _source_bytes(storage) == before


def test_dashboard_empty_input_is_explicit_and_does_not_create_storage(tmp_path) -> None:
    storage = telemetry_storage(tmp_path)
    dashboard = build_dashboard(storage)
    rendered = render_dashboard(dashboard)

    assert dashboard["coverage"]["source_records_seen"] == 0
    assert dashboard["runs"] == []
    assert "No validated non-synthetic runs are available" in rendered
    assert not storage.paths.root.exists()


def test_dashboard_excludes_malformed_schema_hash_and_privacy_invalid_records(tmp_path) -> None:
    storage, _ = _recorded_demo_run(tmp_path)
    target = next(storage.paths.root.rglob("codex_runs-*.jsonl"))
    valid_records = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    run = next(value for value in valid_records if value.get("record_type") == "run")

    schema_invalid = dict(run)
    schema_invalid["schema_version"] = "999.0.0"
    hash_invalid = dict(run)
    hash_invalid["backend_model"] = "gpt-5.6-sol"
    privacy_invalid = dict(run)
    privacy_invalid["prompt"] = "synthetic forbidden fixture"
    malformed = "{not-json}"
    target.write_text(
        "\n".join(
            [
                malformed,
                json.dumps(schema_invalid, sort_keys=True),
                json.dumps(hash_invalid, sort_keys=True),
                json.dumps(privacy_invalid, sort_keys=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    before = target.read_bytes()

    dashboard = build_dashboard(storage)
    rendered = render_dashboard(dashboard)

    assert dashboard["runs"] == []
    assert dashboard["coverage"]["invalid_records_excluded"] == 4
    assert "synthetic forbidden fixture" not in rendered
    assert target.read_bytes() == before


def test_dashboard_duplicate_event_is_visible_but_not_double_counted(tmp_path) -> None:
    storage, _ = _recorded_demo_run(tmp_path)
    view = build_dashboard(storage, limit=1)["runs"][0]

    assert view["operations"]["tool_call_count"]["value"] == 1
    assert view["operations"]["duplicate_event_count"] == 1
    assert view["usage"]["total_reported_tokens"]["value"] == 130


def test_dashboard_preserves_null_request_and_retry_counts(tmp_path) -> None:
    storage, _ = _recorded_demo_run(tmp_path)
    dashboard = build_dashboard(storage, limit=1)
    view = dashboard["runs"][0]
    rendered = render_dashboard(dashboard)

    assert view["operations"]["request_count"]["value"] is None
    assert view["operations"]["retry_count"]["value"] is None
    assert "Requests          : Unavailable (not zero)" in rendered
    assert "Retries           : Unavailable (not zero)" in rendered


def test_default_two_run_demo_includes_latest_human_labeled_run(tmp_path) -> None:
    storage, _ = _recorded_demo_run(tmp_path)
    service = TelemetryService(storage)
    assert start_basic(service, task="Synthetic newer fixture one").finish(status="completed").appended
    assert start_basic(service, task="Synthetic newer fixture two").finish(status="completed").appended

    dashboard = build_dashboard(storage, limit=2)
    outcomes = [run["quality"]["human_outcome"]["outcome"] for run in dashboard["runs"]]

    assert dashboard["coverage"]["eligible_non_synthetic_runs"] == 3
    assert "accepted-with-edits" in outcomes


def test_dashboard_excludes_duplicate_run_identity_instead_of_double_counting(tmp_path) -> None:
    storage, _ = _recorded_demo_run(tmp_path)
    target = next(storage.paths.root.rglob("codex_runs-*.jsonl"))
    lines = target.read_text(encoding="utf-8").splitlines()
    run_line = next(line for line in lines if json.loads(line).get("record_type") == "run")
    with target.open("a", encoding="utf-8") as handle:
        handle.write(run_line + "\n")
    before = target.read_bytes()

    dashboard = build_dashboard(storage)

    assert dashboard["coverage"]["duplicate_records_excluded"] == 1
    assert dashboard["coverage"]["displayed_runs"] == 0
    assert target.read_bytes() == before


def test_dashboard_excludes_hash_unlinked_outcome(tmp_path) -> None:
    storage, _ = _recorded_demo_run(tmp_path)
    target = next(storage.paths.root.rglob("codex_runs-*.jsonl"))
    values = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    outcome = next(value for value in values if value.get("record_type") == "outcome")
    outcome["original_record_hash"] = "0" * 64
    outcome["record_hash"] = compute_record_hash(outcome)
    target.write_text(
        "\n".join(json.dumps(value, sort_keys=True) for value in [values[0], outcome]) + "\n",
        encoding="utf-8",
    )

    dashboard = build_dashboard(storage, limit=1)

    assert dashboard["coverage"]["invalid_outcome_links_excluded"] == 1
    assert dashboard["runs"][0]["quality"]["human_outcome"]["outcome"] is None


def test_dashboard_read_verification_accepts_read_only_exact_external_mount(tmp_path) -> None:
    root = tmp_path / "SmartRouterTelemetry"
    root.mkdir()
    filesystem = MountedFilesystem(
        device="/dev/test",
        filesystem="ext4",
        label=None,
        uuid="TEST-1234",
        mount_point=str(tmp_path),
        read_only=True,
        available_bytes=0,
        writable=False,
    )

    write_check = verify_mount(
        root,
        "TEST-1234",
        minimum_free_bytes=1,
        filesystems=[filesystem],
    )
    read_check = verify_mount(
        root,
        "TEST-1234",
        minimum_free_bytes=1,
        filesystems=[filesystem],
        require_writable=False,
    )

    assert write_check.reason == "FILESYSTEM_NOT_WRITABLE"
    assert read_check.ok is True


def test_dashboard_cli_uses_one_local_command_and_safe_json_projection(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    storage = LocalTelemetryStorage()
    storage.set_enabled(True)
    service = TelemetryService(storage)
    run = start_basic(service, task_subdomain="cli_bad_label")
    assert run.finish(status="completed").appended
    raw = records(storage, "run")[0]

    assert cli.main(["telemetry", "dashboard", "--limit", "1", "--json"]) == 0
    output = capsys.readouterr().out
    dashboard = json.loads(output)

    assert dashboard["title"] == "SmartRouter Local Telemetry Demo View 1A"
    assert dashboard["coverage"]["displayed_runs"] == 1
    assert raw["run_id"] not in output
    assert raw["record_hash"] not in output
    assert "cli_bad_label" not in output


def test_dashboard_module_has_no_network_or_output_file_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "smart_codex"
        / "runtime"
        / "telemetry"
        / "dashboard.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "import socket",
        "import requests",
        "import urllib",
        "import http.client",
        "http.server",
        "urlopen(",
        "write_text(",
        "write_bytes(",
        "open(\"w\"",
        "open('w'",
    )

    assert not any(marker in source for marker in forbidden)
    assert "os.O_RDONLY" in source
    wrapper = (root / "scripts" / "smart-codex").read_text(encoding="utf-8")
    assert "PYTHONDONTWRITEBYTECODE=1" in wrapper
