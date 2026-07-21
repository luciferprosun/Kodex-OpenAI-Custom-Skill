from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from smart_codex.codex_smart import (
    CodexSmartLaunchError,
    main,
    resolve_official_codex,
)
from smart_codex.session_control import WRAPPER_MODE_ENV, WRAPPER_MODE_VALUE


ROOT = Path(__file__).resolve().parents[1]


def make_fake_codex(tmp_path: Path, *, exit_code: int = 37) -> Path:
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    binary = binary_dir / "codex"
    binary.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

payload = {
    "argv": sys.argv[1:],
    "stdin": sys.stdin.read(),
    "integration_mode": os.environ.get("SMART_CODEX_INTEGRATION_MODE"),
}
print(json.dumps(payload, sort_keys=True))
print("FAKE_CODEX_STDERR", file=sys.stderr)
raise SystemExit(%d)
"""
        % exit_code,
        encoding="utf-8",
    )
    binary.chmod(0o755)
    return binary


def wrapper_environment(tmp_path: Path, binary: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PATH"] = f"{binary.parent}{os.pathsep}{environment.get('PATH', '')}"
    environment["XDG_STATE_HOME"] = str(tmp_path / "xdg-state")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.pop(WRAPPER_MODE_ENV, None)
    return environment


def run_wrapper(
    tmp_path: Path,
    binary: Path,
    arguments: list[str],
    *,
    stdin: str = "",
    environment_updates: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = wrapper_environment(tmp_path, binary)
    if environment_updates:
        environment.update(environment_updates)
    return subprocess.run(
        [sys.executable, "-m", "smart_codex.codex_smart", *arguments],
        input=stdin,
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=environment,
        shell=False,
        check=False,
    )


def test_wrapper_forwards_all_arguments_stdin_stdout_stderr_and_exit_status(
    tmp_path: Path,
) -> None:
    binary = make_fake_codex(tmp_path)
    before = binary.read_bytes()
    arguments = ["--model", "synthetic-model", "value with spaces", ";not-shell"]

    completed = run_wrapper(tmp_path, binary, arguments, stdin="exact stdin\n")

    assert completed.returncode == 37
    payload = json.loads(completed.stdout)
    assert payload["argv"] == arguments
    assert payload["stdin"] == "exact stdin\n"
    assert payload["integration_mode"] == WRAPPER_MODE_VALUE
    assert completed.stderr == "FAKE_CODEX_STDERR\n"
    assert binary.read_bytes() == before


def test_wrapper_preserves_zero_exit_status(tmp_path: Path) -> None:
    binary = make_fake_codex(tmp_path, exit_code=0)
    completed = run_wrapper(tmp_path, binary, ["--version"])
    assert completed.returncode == 0


def test_missing_official_codex_fails_with_clear_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    environment = {
        "PATH": str(tmp_path / "empty"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }
    assert main([], environ=environment) == 2
    assert "OFFICIAL_CODEX_NOT_FOUND" in capsys.readouterr().err


def test_active_wrapper_marker_rejects_recursive_invocation(tmp_path: Path) -> None:
    binary = make_fake_codex(tmp_path)
    completed = run_wrapper(
        tmp_path,
        binary,
        [],
        environment_updates={WRAPPER_MODE_ENV: WRAPPER_MODE_VALUE},
    )
    assert completed.returncode == 2
    assert "RECURSIVE_CODEX_WRAPPER_INVOCATION" in completed.stderr
    assert "FAKE_CODEX_STDERR" not in completed.stderr


def test_recursive_executable_resolution_is_rejected(tmp_path: Path) -> None:
    wrapper = tmp_path / "codex-smart"
    wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    wrapper.chmod(0o755)
    (tmp_path / "codex").symlink_to(wrapper)

    with pytest.raises(CodexSmartLaunchError, match="RECURSIVE"):
        resolve_official_codex(search_path=str(tmp_path), wrapper_executable=wrapper)


def test_wrapper_exec_contract_uses_one_resolved_executable_and_preserved_environment(
    tmp_path: Path,
) -> None:
    binary = make_fake_codex(tmp_path)
    environment = wrapper_environment(tmp_path, binary)
    seen: list[tuple[str, list[str], dict[str, str]]] = []

    def fake_execve(path: str, argv: list[str], env: dict[str, str]) -> object:
        seen.append((path, argv, env))
        return object()

    assert main(["--no-alt-screen", "prompt"], environ=environment, execve=fake_execve) == 0
    assert len(seen) == 1
    path, argv, forwarded_environment = seen[0]
    assert Path(path).samefile(binary)
    assert argv == [str(binary.resolve()), "--no-alt-screen", "prompt"]
    assert forwarded_environment[WRAPPER_MODE_ENV] == WRAPPER_MODE_VALUE
    for key, value in environment.items():
        assert forwarded_environment[key] == value


def test_wrapper_module_contains_no_shell_provider_or_codex_mutation() -> None:
    source = (ROOT / "smart_codex" / "codex_smart.py").read_text(encoding="utf-8")
    for forbidden in (
        "subprocess",
        "shell=True",
        "os.system",
        "provider",
        "OPENAI_API_KEY",
        "unlink(",
        "replace(official",
        ".local/bin/codex",
    ):
        assert forbidden not in source
    assert "execve" in source
