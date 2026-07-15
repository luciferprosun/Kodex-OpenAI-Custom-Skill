from __future__ import annotations

import json
from pathlib import Path

import pytest

from smart_codex.app_server_router.launcher import build_tui_command
from smart_codex.app_server_router.protocol import JsonlEventSink, sanitize_event
from smart_codex.app_server_router.proxy import AppServerProxy
from smart_codex.app_server_router.websocket import WebSocketError, WebSocketServer

from app_server_test_helpers import turn_router


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "smart_codex" / "app_server_router"


def test_routing_log_never_contains_raw_prompt_or_untrusted_ids(tmp_path: Path) -> None:
    prompt = "private prompt containing passwords tokens cookies and credentials"
    path = tmp_path / "routes.jsonl"
    sink = JsonlEventSink(path)
    sink.emit(
        {
            "event": "route",
            "status": "forwarded",
            "request_id": prompt,
            "thread_id": prompt,
            "prompt_hash": "a" * 64,
            "category": "email",
            "selected_model": "gpt-5.6-luna",
            "unsafe": prompt,
        }
    )

    raw = path.read_text(encoding="utf-8")
    record = json.loads(raw)
    assert prompt not in raw
    assert record["prompt_hash"] == "a" * 64
    assert record["request_id"] != prompt
    assert record["thread_id"] != prompt
    assert "unsafe" not in record
    assert path.stat().st_mode & 0o777 == 0o600


def test_sanitize_event_emits_only_whitelisted_capability_data() -> None:
    record = sanitize_event(
        {
            "event": "route",
            "status": "accepted",
            "prompt_hash": "b" * 64,
            "selected_model": "gpt-5.6-terra",
            "raw_prompt": "do not persist me",
            "token": "do not persist me",
            "cookie": "do not persist me",
        }
    )
    assert record["selected_model"] == "gpt-5.6-terra"
    assert "raw_prompt" not in record
    assert "token" not in record
    assert "cookie" not in record


def test_original_tui_command_contains_no_prompt_or_shell_wrapper(tmp_path: Path) -> None:
    fake_codex = tmp_path / "codex"
    fake_codex.write_text("#!/bin/sh\n", encoding="utf-8")
    command = build_tui_command(str(fake_codex), "ws://127.0.0.1:4500", ROOT)

    assert command == [
        str(fake_codex),
        "--remote",
        "ws://127.0.0.1:4500",
        "-C",
        str(ROOT),
    ]
    assert all("prompt" not in argument.lower() for argument in command)


def test_proxy_and_websocket_server_reject_non_loopback_binding() -> None:
    with pytest.raises(WebSocketError):
        WebSocketServer("0.0.0.0", 4500, lambda connection: None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        AppServerProxy(
            backend_url="ws://127.0.0.1:4501",
            turn_router=turn_router(),
            host="0.0.0.0",
        )


def test_router_package_has_no_shell_global_config_or_binary_mutation() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PACKAGE.rglob("*.py")
    )
    forbidden = [
        "shell=True",
        "dangerFullAccess\" }",
        "config/value/write",
        "config/batchWrite",
        "os.symlink",
        "Path.unlink",
        "shutil.copy",
        "auth.json",
    ]
    for value in forbidden:
        assert value not in source


def test_opt_in_launchers_leave_normal_codex_untouched() -> None:
    script = (ROOT / "scripts" / "start-routed-codex").read_text(encoding="utf-8")
    desktop = (ROOT / "desktop" / "Kodex OpenAI Custom Skill.desktop").read_text(
        encoding="utf-8"
    )

    assert "smart_codex.app_server_router.launcher" in script
    assert '"$@"' in script
    assert "alias codex" not in script
    assert ".local/bin/codex" not in script
    assert "Name=Kodex OpenAI Custom Skill" in desktop
    assert "Terminal=true" in desktop
    assert "scripts/start-routed-codex" in desktop
