from __future__ import annotations

from datetime import datetime, timezone
import ast
import json
from pathlib import Path

import pytest

from smart_codex.session_cli import main, status_payload
from smart_codex.session_control import SessionControlStore


ROOT = Path(__file__).resolve().parents[1]


def store_at(tmp_path: Path) -> SessionControlStore:
    marker_values = iter(("rm-" + "a" * 32, "rm-" + "b" * 32, "rm-" + "c" * 32))
    return SessionControlStore(
        tmp_path / "state",
        repository_root=ROOT,
        clock=lambda: datetime(2026, 7, 21, 2, 0, tzinfo=timezone.utc),
        session_id_factory=lambda: "rt-" + "d" * 32,
        marker_id_factory=lambda: next(marker_values),
    )


def run_json(
    arguments: list[str],
    store: SessionControlStore,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, object]:
    assert main([*arguments, "--json"], store=store) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    return result


def test_status_is_read_only_and_reports_safe_defaults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = store_at(tmp_path)
    before = list(tmp_path.rglob("*"))

    result = run_json(["status"], store, capsys)

    assert result["smart_router"] == "OFF"
    assert result["research_telemetry"] == "OFF"
    assert result["telemetry_session"] is None
    assert result["automatic_model_execution"] == "OFF"
    assert result["ultra_automatic_execution"] == "OFF"
    assert list(tmp_path.rglob("*")) == before


def test_human_status_contains_the_required_control_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = store_at(tmp_path)
    assert main(["status"], store=store) == 0
    output = capsys.readouterr().out

    for line in (
        "Smart Router: OFF",
        "Research Telemetry: OFF",
        "Telemetry Session: NONE",
        "Policy Version: model-policy-calibration-v0.3",
        "State Schema Version: smart-codex-session-control-v1",
        "Integration Mode: official_codex_wrapper_session_control",
        "Automatic Model Execution: OFF",
        "Ultra Automatic Execution: OFF",
    ):
        assert line in output


def test_router_on_and_off_change_only_router_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = store_at(tmp_path)

    enabled = run_json(["smart-router", "on"], store, capsys)
    disabled = run_json(["smart-router", "off"], store, capsys)

    assert enabled["smart_router"] == "ON"
    assert enabled["research_telemetry"] == "OFF"
    assert disabled["smart_router"] == "OFF"
    assert disabled["research_telemetry"] == "OFF"


def test_router_commands_are_idempotent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = store_at(tmp_path)
    first = run_json(["smart-router", "on"], store, capsys)
    first_bytes = store.state_path.read_bytes()
    second = run_json(["smart-router", "on"], store, capsys)
    assert first == second
    assert store.state_path.read_bytes() == first_bytes

    run_json(["smart-router", "off"], store, capsys)
    off_bytes = store.state_path.read_bytes()
    run_json(["smart-router", "off"], store, capsys)
    assert store.state_path.read_bytes() == off_bytes


def test_telemetry_start_and_stop_preserve_router_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = store_at(tmp_path)
    run_json(["smart-router", "on"], store, capsys)

    started = run_json(["telemetry", "start"], store, capsys)
    stopped = run_json(["telemetry", "stop"], store, capsys)

    assert started["smart_router"] == "ON"
    assert started["research_telemetry"] == "ON"
    assert started["telemetry_session"] == "rt-" + "d" * 32
    assert stopped["smart_router"] == "ON"
    assert stopped["research_telemetry"] == "OFF"
    assert stopped["telemetry_session"] is None


def test_telemetry_activation_does_not_enable_router(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = store_at(tmp_path)
    result = run_json(["telemetry", "start"], store, capsys)
    assert result["smart_router"] == "OFF"
    assert result["research_telemetry"] == "ON"


def test_repeated_telemetry_start_and_stop_are_safe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = store_at(tmp_path)
    first = run_json(["telemetry", "start"], store, capsys)
    marker_count = len(list(store.marker_root.glob("*.json")))
    second = run_json(["telemetry", "start"], store, capsys)
    assert second["telemetry_session"] == first["telemetry_session"]
    assert len(list(store.marker_root.glob("*.json"))) == marker_count

    run_json(["telemetry", "stop"], store, capsys)
    stop_count = len(list(store.marker_root.glob("*.json")))
    run_json(["telemetry", "stop"], store, capsys)
    assert len(list(store.marker_root.glob("*.json"))) == stop_count


def test_combined_activation_is_one_control_transition(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = store_at(tmp_path)
    result = run_json(["smart-router", "on", "--telemetry"], store, capsys)

    assert result["smart_router"] == "ON"
    assert result["research_telemetry"] == "ON"
    assert result["last_updated_by"] == "smart-router-on-with-telemetry"


def test_router_and_telemetry_status_subcommands_are_read_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = store_at(tmp_path)
    run_json(["smart-router", "on", "--telemetry"], store, capsys)
    before = store.state_path.read_bytes()
    before_markers = sorted(path.read_bytes() for path in store.marker_root.glob("*.json"))

    run_json(["smart-router", "status"], store, capsys)
    run_json(["telemetry", "status"], store, capsys)

    assert store.state_path.read_bytes() == before
    assert sorted(path.read_bytes() for path in store.marker_root.glob("*.json")) == before_markers


def test_reset_returns_both_controls_to_safe_defaults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = store_at(tmp_path)
    run_json(["smart-router", "on", "--telemetry"], store, capsys)
    reset = run_json(["reset"], store, capsys)
    assert reset["smart_router"] == "OFF"
    assert reset["research_telemetry"] == "OFF"


@pytest.mark.parametrize(
    "arguments",
    [
        ["smart-router", "enable"],
        ["telemetry", "enable"],
        ["smart-router", "off", "--telemetry"],
        ["unknown"],
    ],
)
def test_unknown_or_conflicting_actions_fail_without_state_change(
    tmp_path: Path, arguments: list[str]
) -> None:
    store = store_at(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(arguments, store=store)
    assert exc.value.code == 2
    assert store.read().status == "missing"


def test_status_payload_contains_no_execution_authority(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    payload = status_payload(store.read())
    assert payload["automatic_model_execution"] == "OFF"
    assert payload["ultra_automatic_execution"] == "OFF"
    assert payload["subagent_execution"] == "OFF"
    assert "approval" not in json.dumps(payload).lower()


def test_control_modules_do_not_import_router_provider_or_app_server() -> None:
    imported: set[str] = set()
    for name in ("session_control.py", "session_cli.py"):
        tree = ast.parse((ROOT / "smart_codex" / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    assert not any(
        forbidden in module
        for forbidden in (
            "router",
            "app_server_router",
            "provider",
            "subprocess",
            "requests",
            "urllib",
            "runtime.telemetry",
        )
        for module in imported
    )
