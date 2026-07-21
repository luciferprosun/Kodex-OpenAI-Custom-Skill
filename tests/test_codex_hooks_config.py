from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".codex" / "hooks.json"
REQUIRED_EVENTS = {
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PermissionRequest",
    "Stop",
}
EXPECTED_SCRIPTS = {
    "UserPromptSubmit": "user_prompt_submit.py",
    "PreToolUse": "pre_tool_use.py",
    "PostToolUse": "post_tool_use.py",
    "PermissionRequest": "permission_request.py",
    "Stop": "stop.py",
}
EXPECTED_STATUS = {
    "UserPromptSubmit": "Checking Smart Router session gate",
    "PreToolUse": "Checking proposed tool action",
    "PostToolUse": "Recording bounded tool metadata",
    "PermissionRequest": "Reviewing permission request",
    "Stop": "Finalizing bounded Smart Router telemetry",
}


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def test_project_hooks_config_has_only_reviewed_router_and_capture_events() -> None:
    config = load_config()

    assert set(config) == {"hooks"}
    assert set(config["hooks"]) == REQUIRED_EVENTS


def test_every_hook_is_a_short_command_resolved_from_git_root() -> None:
    hooks = load_config()["hooks"]

    for event, groups in hooks.items():
        assert len(groups) == 1
        handlers = groups[0]["hooks"]
        assert len(handlers) == 1
        handler = handlers[0]
        command = handler["command"]

        assert handler["type"] == "command"
        assert isinstance(handler["timeout"], int)
        assert 0 < handler["timeout"] <= 30
        assert handler["statusMessage"] == EXPECTED_STATUS[event]
        assert command.startswith("/usr/bin/python3 ")
        assert "$(git rev-parse --show-toplevel)/.codex/hooks/" in command
        assert command.endswith(f'/{EXPECTED_SCRIPTS[event]}"')
        for interpolation in ("$prompt", "${prompt}", "{prompt}", "%prompt%"):
            assert interpolation not in command.lower()
        assert "tool_input" not in command
        assert "/home/" not in command
        assert "~/.codex" not in command


def test_matchers_follow_the_installed_release_aliases() -> None:
    hooks = load_config()["hooks"]

    assert "matcher" not in hooks["UserPromptSubmit"][0]
    assert "matcher" not in hooks["Stop"][0]
    expected = "^(Bash|apply_patch|Edit|Write|mcp__.*)$"
    assert hooks["PreToolUse"][0]["matcher"] == expected
    assert hooks["PostToolUse"][0]["matcher"] == expected
    assert hooks["PermissionRequest"][0]["matcher"] == expected


def test_entrypoints_exist_and_no_plugin_or_marketplace_was_created() -> None:
    hook_dir = ROOT / ".codex" / "hooks"
    for script in EXPECTED_SCRIPTS.values():
        assert (hook_dir / script).is_file()

    assert not (ROOT / ".codex-plugin").exists()
    assert not (ROOT / "plugin.json").exists()
    assert not (ROOT / "marketplace.json").exists()
    assert not (ROOT / ".agents" / "plugins" / "marketplace.json").exists()


def test_hook_policy_is_not_duplicated_in_adapter_or_entrypoints() -> None:
    paths = [
        ROOT / "smart_codex" / "codex_hook_adapter.py",
        *(ROOT / ".codex" / "hooks" / name for name in EXPECTED_SCRIPTS.values()),
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths).lower()

    for forbidden_pattern in (
        "git clean",
        "git push --force",
        "id_rsa",
        "twine upload",
        "truncate table",
        "ufw disable",
        ".local/bin/codex",
        "curl https://",
    ):
        assert forbidden_pattern not in source
