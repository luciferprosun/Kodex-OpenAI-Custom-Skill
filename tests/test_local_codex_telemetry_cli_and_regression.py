from __future__ import annotations

import json
from pathlib import Path
import subprocess

from smart_codex import cli
from smart_codex.launcher import build_codex_command
from smart_codex.router import route_prompt
from smart_codex.runtime.telemetry.storage import LocalTelemetryStorage

from app_server_test_helpers import turn_message
from model_policy_test_helpers import calibration_router


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "tests" / "fixtures" / "router_behavior_snapshot_2b1.json"


def test_telemetry_enable_status_disable_commands(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cli.main(["telemetry", "status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["enabled"] is False

    assert cli.main(["telemetry", "enable"]) == 0
    enabled = json.loads(capsys.readouterr().out)
    assert enabled["enabled"] is True
    salt = tmp_path / ".local" / "state" / "smart-codex" / "telemetry_salt"
    assert salt.exists()
    assert salt.stat().st_mode & 0o777 == 0o600

    assert cli.main(["telemetry", "disable"]) == 0
    disabled = json.loads(capsys.readouterr().out)
    assert disabled["enabled"] is False


def test_disabled_execution_passes_identical_command_to_launcher(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    observed = {}

    def fake_run(command):
        observed["argv"] = command.argv
        return subprocess.CompletedProcess(command.argv, 0)

    monkeypatch.setattr(cli, "run_codex_command", fake_run)
    prompt = "Fix one typo in README.md."
    decision = route_prompt(prompt, dry_run=False)
    expected = build_codex_command(
        prompt,
        profile=decision.selected_profile,
        sandbox=decision.sandbox_mode,
        approval_policy=decision.approval_policy,
        execute=True,
    ).argv
    assert cli.main(["--execute", "--no-log", prompt]) == 0
    captured = capsys.readouterr()
    assert observed["argv"] == expected
    assert "telemetry_run_id" not in captured.err
    assert not (tmp_path / ".local" / "state" / "smart-codex" / "telemetry").exists()


def test_enabled_execution_writes_metadata_but_does_not_change_command(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cli.main(["telemetry", "enable"]) == 0
    capsys.readouterr()
    observed = {}

    def fake_run(command):
        observed["argv"] = command.argv
        return subprocess.CompletedProcess(command.argv, 0)

    monkeypatch.setattr(cli, "run_codex_command", fake_run)
    prompt = "Fix the off-by-one bug in one Python file."
    decision = route_prompt(prompt, dry_run=False)
    expected = build_codex_command(
        prompt,
        profile=decision.selected_profile,
        sandbox=decision.sandbox_mode,
        approval_policy=decision.approval_policy,
        execute=True,
    ).argv
    assert cli.main(["--execute", "--no-log", prompt]) == 0
    captured = capsys.readouterr()
    assert observed["argv"] == expected
    assert "telemetry_run_id:" in captured.err
    storage = LocalTelemetryStorage()
    stored = [record for record in storage.iter_records() if record.get("record_type") == "run"]
    assert len(stored) == 1
    assert stored[0]["input_tokens"] is None
    assert stored[0]["operator_outcome"] is None
    assert stored[0]["recommended_model"] == decision.selected_model
    assert stored[0]["launched_model"] is None
    assert stored[0]["backend_model"] is None


def test_low_disk_telemetry_warning_does_not_block_codex_task(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cli.main(["telemetry", "enable"]) == 0
    capsys.readouterr()
    called = {"value": False}

    def fake_run(command):
        called["value"] = True
        return subprocess.CompletedProcess(command.argv, 0)

    monkeypatch.setattr(cli, "run_codex_command", fake_run)
    monkeypatch.setattr(LocalTelemetryStorage, "free_bytes", lambda self: 0)
    assert cli.main(["--execute", "--no-log", "Fix one typo in README.md."]) == 0
    captured = capsys.readouterr()
    assert called["value"] is True
    assert "TELEMETRY_DISABLED_LOW_DISK" in captured.err


def test_outcome_and_inspect_cli_keep_original_immutable(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli, "_interactive_operator_terminal", lambda: True)
    assert cli.main(["telemetry", "enable"]) == 0
    capsys.readouterr()
    monkeypatch.setattr(
        cli,
        "run_codex_command",
        lambda command: subprocess.CompletedProcess(command.argv, 0),
    )
    assert cli.main(["--execute", "--no-log", "Fix one typo in README.md."]) == 0
    run_line = next(line for line in capsys.readouterr().err.splitlines() if line.startswith("telemetry_run_id:"))
    run_id = run_line.split(":", 1)[1].strip()

    assert cli.main(["outcome", run_id, "accepted-with-edits", "--tests-passed", "2", "--tests-failed", "0"]) == 0
    outcome = json.loads(capsys.readouterr().out)
    assert outcome["ok"] is True
    assert cli.main(["telemetry", "inspect", run_id]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["operator_outcome"] is None
    assert inspected["task_signature"] == "<hidden>"
    assert inspected["outcome_events"][0]["operator_outcome"] == "accepted-with-edits"


def test_summary_cli_supports_model_and_task_level_groups(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cli.main(["telemetry", "enable"]) == 0
    capsys.readouterr()
    assert cli.main(["telemetry", "summary", "--by-model"]) == 0
    by_model = json.loads(capsys.readouterr().out)
    assert by_model == {"group_by": "model", "strata": {}}
    assert cli.main(["telemetry", "summary", "--by-task-level"]) == 0
    by_level = json.loads(capsys.readouterr().out)
    assert by_level == {"group_by": "task_level", "strata": {}}


def test_behavioral_snapshot_matches_pre_implementation_router() -> None:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    router = calibration_router()
    actual = {}
    for name, expected in snapshot["cases"].items():
        prompt = expected["prompt"]
        decision = route_prompt(prompt, dry_run=True)
        message = turn_message(prompt)
        message["params"].pop("model", None)
        live = router.route_message(message)
        command = build_codex_command(
            prompt,
            profile=decision.selected_profile,
            sandbox=decision.sandbox_mode,
            approval_policy=decision.approval_policy,
        ).argv
        command[0] = "<codex>"
        command[-1] = "<task>"
        actual[name] = {
            "prompt": prompt,
            "category": decision.category,
            "complexity": decision.complexity,
            "risk": decision.risk,
            "profile": decision.selected_profile,
            "classic_model": decision.selected_model,
            "live_model": live.selected_model,
            "fallback_model": live.fallback_order[0] if live.fallback_order else None,
            "reasoning_effort": live.effort,
            "sandbox": decision.sandbox_mode,
            "approval": decision.approval_policy,
            "command": command,
        }
    assert actual == snapshot["cases"]
