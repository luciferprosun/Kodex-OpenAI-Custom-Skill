from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from smart_codex.session_control import (
    WRAPPER_MODE_ENV,
    WRAPPER_MODE_VALUE,
    SessionControlStore,
)
from smart_codex.session_hook_bridge import (
    route_permission_request,
    route_pre_tool_use,
    route_user_prompt_submit,
)


ROOT = Path(__file__).resolve().parents[1]
WRAPPER_ENV = {WRAPPER_MODE_ENV: WRAPPER_MODE_VALUE}


def store_at(tmp_path: Path) -> SessionControlStore:
    return SessionControlStore(
        tmp_path / "state",
        repository_root=ROOT,
        clock=lambda: datetime(2026, 7, 21, 2, 30, tzinfo=timezone.utc),
    )


def common_payload(event: str) -> dict[str, object]:
    return {
        "session_id": "synthetic-session-001",
        "transcript_path": None,
        "cwd": str(ROOT),
        "hook_event_name": event,
        "model": "synthetic-model",
        "permission_mode": "default",
        "turn_id": "synthetic-turn-001",
    }


def user_payload(prompt: str) -> dict[str, object]:
    return {**common_payload("UserPromptSubmit"), "prompt": prompt}


def tool_payload(event: str, command: str) -> dict[str, object]:
    payload = {
        **common_payload(event),
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    if event == "PreToolUse":
        payload["tool_use_id"] = "synthetic-tool-001"
    return payload


def test_router_off_does_not_block_or_classify_normal_prompt(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    assert route_user_prompt_submit({}, store=store, environ=WRAPPER_ENV) == {}


def test_router_on_exposes_only_existing_bounded_advisory_context(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    store.set_router(True)
    prompt = "Summarize the synthetic fixture without modifying files."

    result = route_user_prompt_submit(user_payload(prompt), store=store, environ=WRAPPER_ENV)
    encoded = json.dumps(result)

    assert result["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "advisory" in result["hookSpecificOutput"]["additionalContext"]
    assert prompt not in encoded
    assert "model-policy-calibration-v0.3" not in encoded or "advisory" in encoded


def test_normal_codex_without_wrapper_marker_remains_unmodified(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    store.set_router(True)
    assert route_user_prompt_submit(user_payload("synthetic task"), store=store, environ={}) == {}
    assert route_pre_tool_use(tool_payload("PreToolUse", "git clean -fdx"), store=store, environ={}) == {}


def test_telemetry_switch_alone_does_not_enable_router_hooks(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    store.set_telemetry(True)
    assert route_user_prompt_submit(user_payload("synthetic task"), store=store, environ=WRAPPER_ENV) == {}


def test_router_on_preserves_existing_pre_tool_and_permission_denials(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    store.set_router(True)

    pre_tool = route_pre_tool_use(
        tool_payload("PreToolUse", "git clean -fdx"),
        store=store,
        environ=WRAPPER_ENV,
    )
    permission = route_permission_request(
        tool_payload("PermissionRequest", "git clean -fdx"),
        store=store,
        environ=WRAPPER_ENV,
    )

    assert pre_tool["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert permission["hookSpecificOutput"]["decision"]["behavior"] == "deny"


def test_router_on_does_not_block_allowlisted_local_control_entrypoints(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    store.set_router(True)
    for command in (
        "python .agents/skills/smart-router/scripts/control.py off",
        "python .agents/skills/telemetry/scripts/control.py start",
    ):
        assert route_pre_tool_use(
            tool_payload("PreToolUse", command),
            store=store,
            environ=WRAPPER_ENV,
        ) == {}


def test_malformed_state_fails_closed_to_integration_off(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    store.root.mkdir(mode=0o700, parents=True)
    store.state_path.write_text('{"router_enabled":"true"}', encoding="utf-8")
    os.chmod(store.state_path, 0o600)

    assert route_user_prompt_submit(user_payload("synthetic task"), store=store, environ=WRAPPER_ENV) == {}
    assert route_pre_tool_use(tool_payload("PreToolUse", "git clean -fdx"), store=store, environ=WRAPPER_ENV) == {}


def test_hook_routing_does_not_write_prompt_or_task_records(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    store.set_router(True)
    prompt = "SYNTHETIC_PRIVATE_PROMPT_CANARY"
    route_user_prompt_submit(user_payload(prompt), store=store, environ=WRAPPER_ENV)

    persisted = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in store.root.rglob("*")
        if path.is_file()
    )
    assert prompt not in persisted
    assert not list(store.root.rglob("*.jsonl"))


def test_hook_bridge_adds_no_model_ultra_or_provider_execution_path() -> None:
    source = (ROOT / "smart_codex" / "session_hook_bridge.py").read_text(encoding="utf-8")
    for forbidden in (
        "reasoningEffort",
        "ultra_subagents",
        "approval_evidence",
        "subprocess",
        "provider",
        "TelemetryService",
    ):
        assert forbidden not in source
