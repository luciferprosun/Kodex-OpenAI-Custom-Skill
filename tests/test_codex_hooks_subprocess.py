from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from smart_codex.session_control import (
    WRAPPER_MODE_ENV,
    WRAPPER_MODE_VALUE,
    SessionControlStore,
)


ROOT = Path(__file__).resolve().parents[1]
HOOK_DIR = ROOT / ".codex" / "hooks"
CANARY = "FAKE_CODEX_HOOK_SECRET_91E73A"


def common_payload(event: str) -> dict[str, object]:
    return {
        "session_id": "subprocess-session-001",
        "transcript_path": None,
        "cwd": str(ROOT),
        "hook_event_name": event,
        "model": "synthetic-model",
        "permission_mode": "default",
        "turn_id": "subprocess-turn-001",
    }


def run_hook(
    script: str,
    payload: object,
    home: Path,
    *,
    raw_input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    state_base = home.parent / f"{home.name}-xdg-state"
    SessionControlStore(
        state_base / "smart-codex" / "session-control",
        repository_root=ROOT,
    ).set_router(True)
    environment["XDG_STATE_HOME"] = str(state_base)
    environment[WRAPPER_MODE_ENV] = WRAPPER_MODE_VALUE
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    encoded = raw_input if raw_input is not None else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(HOOK_DIR / script)],
        input=encoded,
        text=True,
        capture_output=True,
        shell=False,
        cwd=home,
        env=environment,
        check=False,
    )


def assert_private_result(
    completed: subprocess.CompletedProcess[str],
    raw_value: str,
) -> dict[str, object]:
    assert completed.returncode == 0
    assert completed.stderr == ""
    assert completed.stdout.count("\n") == 1
    result = json.loads(completed.stdout)
    assert isinstance(result, dict)
    assert raw_value not in completed.stdout
    assert raw_value not in completed.stderr
    assert CANARY not in completed.stdout
    assert CANARY not in completed.stderr
    return result


def test_user_prompt_submit_subprocess_is_json_only_and_private(tmp_path: Path) -> None:
    prompt = f"fix frontend bug {CANARY}"
    payload = {**common_payload("UserPromptSubmit"), "prompt": prompt}

    completed = run_hook("user_prompt_submit.py", payload, tmp_path)
    result = assert_private_result(completed, prompt)

    assert result["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert list(tmp_path.iterdir()) == []


def test_pre_tool_use_subprocess_denies_without_command_leak(tmp_path: Path) -> None:
    command = f"cat ~/.codex/auth.json {CANARY}"
    payload = {
        **common_payload("PreToolUse"),
        "tool_name": "Bash",
        "tool_use_id": "subprocess-tool-001",
        "tool_input": {"command": command},
    }

    completed = run_hook("pre_tool_use.py", payload, tmp_path)
    result = assert_private_result(completed, command)

    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert list(tmp_path.iterdir()) == []


def test_permission_request_subprocess_denies_without_input_leak(
    tmp_path: Path,
) -> None:
    command = f"git clean -fdx {CANARY}"
    payload = {
        **common_payload("PermissionRequest"),
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }

    completed = run_hook("permission_request.py", payload, tmp_path)
    result = assert_private_result(completed, command)

    assert result["hookSpecificOutput"]["decision"]["behavior"] == "deny"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("script", "event", "expected_event"),
    [
        ("user_prompt_submit.py", "UserPromptSubmit", None),
        ("pre_tool_use.py", "PreToolUse", "PreToolUse"),
        ("permission_request.py", "PermissionRequest", "PermissionRequest"),
    ],
)
def test_malformed_json_fails_closed_without_canary_leak(
    script: str,
    event: str,
    expected_event: str | None,
    tmp_path: Path,
) -> None:
    raw = f'{{"hook_event_name":"{event}","fixture":"{CANARY}"'
    completed = run_hook(script, {}, tmp_path, raw_input=raw)
    result = assert_private_result(completed, raw)

    if expected_event is None:
        assert result["decision"] == "block"
    else:
        assert result["hookSpecificOutput"]["hookEventName"] == expected_event
    assert list(tmp_path.iterdir()) == []


def test_entrypoints_read_stdin_once_and_launch_no_external_processes() -> None:
    sources = [
        (HOOK_DIR / name).read_text(encoding="utf-8")
        for name in (
            "user_prompt_submit.py",
            "pre_tool_use.py",
            "permission_request.py",
        )
    ]
    adapter_source = (ROOT / "smart_codex" / "codex_hook_adapter.py").read_text(
        encoding="utf-8"
    )
    production_source = "\n".join([adapter_source, *sources])

    for source in sources:
        assert source.count("sys.stdin.read()") == 1
    assert "subprocess" not in production_source
    assert "smart_codex.launcher" not in production_source
    assert "launch_codex" not in production_source
    assert "shell=True" not in production_source
    assert "shlex.split" not in production_source
    assert "tempfile" not in production_source
    assert "NamedTemporaryFile" not in production_source
    assert "provider" not in production_source.lower()
    assert "auth.json" not in production_source
    assert "BEGIN PRIVATE KEY" not in production_source
    assert "eval(" not in production_source
    assert "exec(" not in production_source
