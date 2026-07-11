from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER = (
    REPO_ROOT
    / ".agents"
    / "skills"
    / "codex-patch-smart-router"
    / "scripts"
    / "route_prompt.py"
)
SUCCESS_KEYS = {
    "schema_version",
    "status",
    "source",
    "prompt_hash",
    "category",
    "risk_level",
    "complexity_level",
    "action_danger",
    "recommended_profile",
    "recommended_sandbox",
    "recommended_approval",
    "evidence_requirement",
    "context_requirement",
    "confidence",
    "mixed_categories",
    "requires_confirmation",
    "warnings",
}


def run_adapter(
    prompt: str,
    *options: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(ADAPTER), "--stdin", *options]
    assert prompt not in command
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        input=prompt,
        text=True,
        capture_output=True,
        shell=False,
        env=env,
        check=False,
    )


def result_json(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert isinstance(payload, dict)
    return payload


def load_adapter_module():
    spec = importlib.util.spec_from_file_location("skill_route_prompt_test", ADAPTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_success_schema_is_stable_and_prompt_is_not_returned():
    prompt = "fix frontend bug"
    completed = run_adapter(prompt)
    payload = result_json(completed)

    assert completed.returncode == 0
    assert set(payload) == SUCCESS_KEYS
    assert payload["schema_version"] == "0.1.0"
    assert payload["status"] == "ok"
    assert payload["source"] == "codex-patch-smart-router-core"
    assert payload["prompt_hash"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert payload["category"] == "normal_coding"
    assert payload["recommended_profile"] == "standard"
    assert isinstance(payload["confidence"], float)
    assert prompt not in completed.stdout


def test_secret_sensitive_prompt_fails_closed_for_confirmation():
    prompt = "fix frontend bug and check exposed API keys"
    completed = run_adapter(prompt)
    payload = result_json(completed)

    assert completed.returncode == 0
    assert payload["status"] == "ok"
    assert payload["category"] in {"security_audit", "secret_handling"}
    assert payload["risk_level"] in {"high", "critical"}
    assert payload["recommended_profile"] == "security"
    assert payload["recommended_sandbox"] == "read-only"
    assert payload["recommended_approval"] == "on-request"
    assert payload["requires_confirmation"] is True


def test_destructive_prompt_requires_confirmation():
    completed = run_adapter("run rm -rf on the build directory")
    payload = result_json(completed)

    assert completed.returncode == 0
    assert payload["risk_level"] == "critical"
    assert payload["action_danger"] == "destructive_operation"
    assert payload["recommended_profile"] == "security"
    assert payload["recommended_sandbox"] == "read-only"
    assert payload["requires_confirmation"] is True


def test_normal_repository_operation_uses_repo_profile():
    completed = run_adapter("open a pull request for this branch")
    payload = result_json(completed)

    assert completed.returncode == 0
    assert payload["category"] == "repo_operations"
    assert payload["risk_level"] == "medium"
    assert payload["action_danger"] == "git_operations"
    assert payload["recommended_profile"] == "repo"
    assert payload["recommended_sandbox"] == "workspace-write"
    assert payload["recommended_approval"] == "on-request"
    assert payload["requires_confirmation"] is False


def test_mathematical_prompt_uses_math_profile_read_only():
    completed = run_adapter("prove this neutrino equation from LSC notes")
    payload = result_json(completed)

    assert completed.returncode == 0
    assert payload["category"] == "math_theory"
    assert payload["recommended_profile"] == "math"
    assert payload["recommended_sandbox"] == "read-only"


def test_empty_input_returns_exact_input_error():
    completed = run_adapter("")
    payload = result_json(completed)

    assert completed.returncode == 2
    assert payload == {
        "schema_version": "0.1.0",
        "status": "input_error",
        "error_code": "EMPTY_PROMPT",
        "message": "No prompt was provided.",
        "requires_confirmation": False,
    }


def test_missing_rules_return_sanitized_config_error(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    import smart_codex.knowledge as knowledge

    adapter = load_adapter_module()
    monkeypatch.setattr(knowledge, "repo_root_from_here", lambda: tmp_path / "missing")
    monkeypatch.setattr(sys, "stdin", io.StringIO("fix frontend bug"))

    exit_code = adapter.main(["--stdin"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "schema_version": "0.1.0",
        "status": "config_error",
        "error_code": "KNOWLEDGE_LIBRARY_ERROR",
        "message": "The Smart Router Knowledge Library could not be loaded.",
        "requires_confirmation": True,
    }
    assert "command" not in captured.out.lower()


def test_unexpected_error_is_sanitized(monkeypatch, capsys):
    adapter = load_adapter_module()
    fake_secret = "FAKE_SECRET_INTERNAL_ERROR_8D4C"

    class FakeConfigError(Exception):
        pass

    def broken_router(prompt: str, *, dry_run: bool):
        assert dry_run is True
        raise RuntimeError(f"failure while handling {prompt}")

    monkeypatch.setattr(adapter, "_load_router", lambda: (broken_router, FakeConfigError))
    monkeypatch.setattr(sys, "stdin", io.StringIO(fake_secret))

    exit_code = adapter.main(["--stdin"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 3
    assert captured.err == ""
    assert payload == {
        "schema_version": "0.1.0",
        "status": "internal_error",
        "error_code": "ROUTER_INTERNAL_ERROR",
        "message": "The Smart Router could not produce a decision.",
        "requires_confirmation": True,
    }
    assert fake_secret not in captured.out


def test_prompt_privacy_leaves_no_raw_output_or_router_log(tmp_path: Path):
    fake_secret = "FAKE_SECRET_ROUTER_TEST_76AB21"
    prompt = f"check exposed API keys containing {fake_secret}"
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["TMPDIR"] = str(tmp_path)

    completed = run_adapter(prompt, env=env)
    payload = result_json(completed)

    assert completed.returncode == 0
    assert payload["prompt_hash"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert fake_secret not in completed.stdout
    assert fake_secret not in completed.stderr
    assert not (tmp_path / ".codex-patch-smart-router" / "decisions.jsonl").exists()
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert fake_secret.encode("utf-8") not in path.read_bytes()


def test_shell_metacharacters_remain_one_string_and_do_not_execute(tmp_path: Path):
    canary = tmp_path / "adapter-command-ran"
    prompt = f"fix bug; rm -rf / && echo owned $(whoami) && touch {canary}"

    completed = run_adapter(prompt)
    payload = result_json(completed)

    assert completed.returncode == 0
    assert payload["prompt_hash"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert payload["risk_level"] == "critical"
    assert payload["action_danger"] == "destructive_operation"
    assert payload["requires_confirmation"] is True
    assert not canary.exists()


def test_adapter_has_no_launcher_logging_or_command_execution_imports():
    source = ADAPTER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert "smart_codex.launcher" not in source
    assert "smart_codex.logging_safe" not in source
    assert "subprocess" not in imported_modules
    assert "shlex" not in imported_modules
    assert "tempfile" not in imported_modules
    assert "shell=True" not in source
    assert "__dict__" not in source
