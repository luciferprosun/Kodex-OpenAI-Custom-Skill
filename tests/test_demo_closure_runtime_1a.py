from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from smart_codex import __version__
from smart_codex.demo_closure import main as demo_main
from smart_codex.policy_version import MODEL_POLICY_VERSION
from smart_codex.runtime.telemetry.collector import TelemetryService
from smart_codex.runtime.telemetry.hook_capture import CodexHookTelemetryCapture
from smart_codex.runtime.telemetry.schema import SCHEMA_VERSION
from smart_codex.runtime.telemetry.storage import (
    LocalTelemetryStorage,
    StorageLimits,
    TelemetryPaths,
)
from smart_codex.runtime.telemetry.validator import validate_run_record
from smart_codex.session_cli import main, status_payload
from smart_codex.session_control import (
    WRAPPER_MODE_ENV,
    WRAPPER_MODE_VALUE,
    SessionControlStore,
)
from smart_codex.session_hook_bridge import (
    route_post_tool_use,
    route_stop,
    route_user_prompt_submit,
)


ROOT = Path(__file__).resolve().parents[1]
WRAPPER_ENV = {WRAPPER_MODE_ENV: WRAPPER_MODE_VALUE}
CANARY = "SYNTHETIC_PRIVATE_PROMPT_7F2B"
RAW_CWD = "/private/synthetic/workspace"


def runtime_at(
    tmp_path: Path,
    *,
    service_factory_error: bool = False,
) -> tuple[
    SessionControlStore,
    LocalTelemetryStorage,
    CodexHookTelemetryCapture,
]:
    marker_ids = iter(("rm-" + "a" * 32, "rm-" + "b" * 32))
    store = SessionControlStore(
        tmp_path / "controls",
        repository_root=ROOT,
        clock=lambda: datetime(2026, 7, 21, 5, 0, tzinfo=timezone.utc),
        session_id_factory=lambda: "rt-" + "c" * 32,
        marker_id_factory=lambda: next(marker_ids),
    )
    storage = LocalTelemetryStorage(
        TelemetryPaths(
            root=tmp_path / "existing-telemetry",
            salt=tmp_path / "telemetry-salt",
        ),
        StorageLimits(min_free_bytes=0),
        activation_reader=lambda: (
            store.read().state.research_telemetry_enabled is True
        ),
    )
    service = TelemetryService(
        storage,
        window_id="smart-router",
        router_policy_version=MODEL_POLICY_VERSION,
        codex_protocol_version="codex-cli-0.144.6",
    )
    def service_factory() -> TelemetryService:
        if service_factory_error:
            raise OSError("synthetic unavailable sink")
        return service

    capture = CodexHookTelemetryCapture(
        store,
        service_factory=service_factory,
    )
    return store, storage, capture


def common_payload(event: str) -> dict[str, object]:
    return {
        "session_id": "synthetic-session-closure",
        "transcript_path": None,
        "cwd": RAW_CWD,
        "hook_event_name": event,
        "model": "gpt-5.6-luna",
        "permission_mode": "default",
        "turn_id": "synthetic-turn-closure",
    }


def user_payload(prompt: str) -> dict[str, object]:
    return {**common_payload("UserPromptSubmit"), "prompt": prompt}


def post_tool_payload(tool_use_id: str, *, tool_name: str = "Bash") -> dict[str, object]:
    return {
        **common_payload("PostToolUse"),
        "tool_name": tool_name,
        "tool_use_id": tool_use_id,
        "tool_input": {"command": f"echo {CANARY}"},
        "tool_response": CANARY,
    }


def stop_payload() -> dict[str, object]:
    return {
        **common_payload("Stop"),
        "last_assistant_message": CANARY,
    }


def run_records(storage: LocalTelemetryStorage) -> list[dict[str, object]]:
    return [record for record in storage.iter_records() if record.get("record_type") == "run"]


def test_telemetry_only_turn_uses_existing_schema_without_influencing_router(
    tmp_path: Path,
) -> None:
    store, storage, capture = runtime_at(tmp_path)
    store.set_telemetry(True)
    prompt = f"Summarize README.md in three bullets. {CANARY}"

    submitted = route_user_prompt_submit(
        user_payload(prompt),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    )
    pending_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in capture.pending_root.glob("*.json")
    )
    completed = route_stop(
        stop_payload(),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    )

    assert submitted == {}
    assert completed == {}
    assert store.read().state.router_enabled is False
    records = run_records(storage)
    assert len(records) == 1
    record = records[0]
    validate_run_record(record)
    assert record["schema_version"] == SCHEMA_VERSION
    assert record["product_surface"] == "codex_cli_hooks"
    assert record["requested_model"] == "gpt-5.6-luna"
    assert record["launched_model"] == "gpt-5.6-luna"
    assert record["recommended_model"] is not None
    assert record["router_policy_version"] == MODEL_POLICY_VERSION
    assert record["input_tokens"] is None
    assert record["request_count"] is None
    assert record["retry_count"] is None
    assert prompt not in pending_text
    assert CANARY not in pending_text
    assert RAW_CWD not in pending_text
    assert CANARY not in json.dumps(record)
    assert RAW_CWD not in json.dumps(record)
    assert not list(capture.pending_root.glob("*.json"))


def test_router_only_turn_is_advisory_and_writes_no_task_telemetry(tmp_path: Path) -> None:
    store, storage, capture = runtime_at(tmp_path)
    store.set_router(True)
    response = route_user_prompt_submit(
        user_payload("Summarize README.md in three bullets."),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    )

    assert response["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "Recommendations are advisory" in response["hookSpecificOutput"]["additionalContext"]
    assert run_records(storage) == []
    assert not capture.pending_root.exists()


def test_combined_turn_routes_and_records_independently(tmp_path: Path) -> None:
    store, storage, capture = runtime_at(tmp_path)
    store.set_router(True, enable_telemetry=True)
    response = route_user_prompt_submit(
        user_payload("Summarize README.md in three bullets."),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    )
    route_stop(
        stop_payload(),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    )

    assert "SMART_ROUTER_DECISION" in response["hookSpecificOutput"]["additionalContext"]
    assert len(run_records(storage)) == 1


def test_post_tool_use_counts_only_bounded_metadata_and_deduplicates_ids(
    tmp_path: Path,
) -> None:
    store, storage, capture = runtime_at(tmp_path)
    store.set_telemetry(True)
    route_user_prompt_submit(
        user_payload("Inspect the synthetic fixture."),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    )
    for payload in (
        post_tool_payload("tool-one"),
        post_tool_payload("tool-one"),
        post_tool_payload("tool-two", tool_name="apply_patch"),
    ):
        assert route_post_tool_use(
            payload,
            store=store,
            environ=WRAPPER_ENV,
            telemetry=capture,
        ) == {}
    route_stop(
        stop_payload(),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    )

    record = run_records(storage)[0]
    assert record["tool_call_count"] == 2
    assert record["tool_calls_by_type"] == {"file_edit": 1, "shell": 1}
    assert record["measurement_sources"]["tool_call_count"] == "measured"
    assert CANARY not in json.dumps(record)


def test_stopping_capture_before_stop_hook_prevents_a_late_record(tmp_path: Path) -> None:
    store, storage, capture = runtime_at(tmp_path)
    store.set_telemetry(True)
    route_user_prompt_submit(
        user_payload("Inspect the synthetic fixture."),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    )
    store.set_telemetry(False)

    assert route_stop(
        stop_payload(),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    ) == {}
    assert run_records(storage) == []


def test_controlled_stop_removes_transient_pending_metadata(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, _, capture = runtime_at(tmp_path)
    store.set_telemetry(True)
    route_user_prompt_submit(
        user_payload("Inspect the synthetic fixture."),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    )
    assert list(capture.pending_root.glob("pending-*.json"))

    assert main(["telemetry", "stop"], store=store) == 0
    capsys.readouterr()
    assert not list(capture.pending_root.glob("pending-*.json"))


def test_telemetry_failure_does_not_corrupt_state_or_router_advice(tmp_path: Path) -> None:
    store, _, capture = runtime_at(tmp_path, service_factory_error=True)
    store.set_router(True, enable_telemetry=True)
    before = store.state_path.read_bytes()

    response = route_user_prompt_submit(
        user_payload("Summarize README.md in three bullets."),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    )

    assert "SMART_ROUTER_DECISION" in response["hookSpecificOutput"]["additionalContext"]
    assert response["systemMessage"].startswith("SMART_CODEX_TELEMETRY_DEGRADED:")
    assert store.state_path.read_bytes() == before


def test_telemetry_only_classification_failure_is_reported_without_state_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, storage, capture = runtime_at(tmp_path)
    store.set_telemetry(True)
    before = store.state_path.read_bytes()

    def fail_classification(payload: object) -> tuple[str, object, object]:
        del payload
        raise RuntimeError("synthetic classifier failure")

    monkeypatch.setattr(
        "smart_codex.session_hook_bridge.classify_user_prompt",
        fail_classification,
    )
    response = route_user_prompt_submit(
        user_payload("Synthetic classification failure fixture."),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    )

    assert response == {
        "systemMessage": (
            "SMART_CODEX_TELEMETRY_DEGRADED:TELEMETRY_CLASSIFICATION_FAILED"
        )
    }
    assert store.state_path.read_bytes() == before
    assert run_records(storage) == []


def test_session_gated_storage_accepts_only_exact_boolean_activation(
    tmp_path: Path,
) -> None:
    for value, expected in ((True, True), (False, False), ("true", False), (1, False)):
        storage = LocalTelemetryStorage(
            TelemetryPaths(tmp_path / f"root-{value!s}", tmp_path / f"salt-{value!s}"),
            activation_reader=lambda selected=value: selected,  # type: ignore[return-value]
        )
        assert storage.enabled() is expected
        with pytest.raises(Exception, match="SESSION_GATED_STORAGE_STATE"):
            storage.set_enabled(True)


def test_status_reports_actual_versions_and_independent_safety_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, _, capture = runtime_at(tmp_path)
    store.set_router(True, enable_telemetry=True)
    assert main(
        ["status", "--json"],
        store=store,
        telemetry_status_reader=lambda _: capture.backend_status(),
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["smart_router"] == "ON"
    assert payload["research_telemetry"] == "ON"
    assert payload["router_version"] == __version__
    assert payload["telemetry_schema_version"] == SCHEMA_VERSION
    assert payload["telemetry_backend"] == "READY"
    assert payload["automatic_model_execution"] == "OFF"
    assert payload["automatic_policy_learning"] == "OFF"
    assert status_payload(store.read())["telemetry_backend"] == "NOT_CHECKED"


@pytest.mark.parametrize(
    ("router_enabled", "telemetry_enabled", "expected_router", "expected_telemetry"),
    [
        (False, False, "OFF", "OFF"),
        (True, False, "ON", "OFF"),
        (False, True, "OFF", "ON"),
        (True, True, "ON", "ON"),
    ],
)
def test_status_reports_every_independent_state_combination(
    tmp_path: Path,
    router_enabled: bool,
    telemetry_enabled: bool,
    expected_router: str,
    expected_telemetry: str,
) -> None:
    store, _, _ = runtime_at(tmp_path)
    if router_enabled:
        store.set_router(True)
    if telemetry_enabled:
        store.set_telemetry(True)
    payload = status_payload(store.read())
    assert payload["smart_router"] == expected_router
    assert payload["research_telemetry"] == expected_telemetry


def test_telemetry_never_mutates_router_policy_or_control_state(tmp_path: Path) -> None:
    store, _, capture = runtime_at(tmp_path)
    store.set_telemetry(True)
    before_policy = MODEL_POLICY_VERSION
    before_router = store.read().state.router_enabled
    route_user_prompt_submit(
        user_payload("Summarize README.md in three bullets."),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    )
    route_stop(
        stop_payload(),
        store=store,
        environ=WRAPPER_ENV,
        telemetry=capture,
    )

    assert MODEL_POLICY_VERSION == before_policy
    assert store.read().state.router_enabled == before_router is False


def test_provider_free_demo_smoke_flow_completes_with_one_synthetic_record(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert demo_main() == 0
    output = capsys.readouterr().out
    assert "LOCAL MOCKED HOOK FLOW — NO MODEL OR PROVIDER CALL" in output
    assert "SMART_ROUTER_DECISION" in output
    assert '"record_count": 1' in output
    assert '"synthetic": true' in output
    assert output.count("Smart Router: OFF") >= 2
    assert "Smart Router: ON" in output
    assert "Research Telemetry: ON" in output
