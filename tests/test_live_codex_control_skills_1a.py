from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib

import pytest


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".agents" / "skills"
ROUTER_SKILL = SKILLS / "smart-router"
TELEMETRY_SKILL = SKILLS / "telemetry"


def run_skill_script(
    tmp_path: Path,
    skill: Path,
    arguments: list[str],
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["XDG_STATE_HOME"] = str(tmp_path / "xdg-state")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, str(skill / "scripts" / "control.py"), *arguments],
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=environment,
        shell=False,
        check=False,
    )


@pytest.mark.parametrize(
    ("skill", "name", "actions"),
    [
        (ROUTER_SKILL, "smart-router", ("on", "off", "status")),
        (TELEMETRY_SKILL, "telemetry", ("start", "stop", "status")),
    ],
)
def test_repo_native_control_skills_have_minimal_supported_structure(
    skill: Path, name: str, actions: tuple[str, ...]
) -> None:
    assert {path.name for path in skill.iterdir()} == {"SKILL.md", "scripts"}
    assert {path.name for path in (skill / "scripts").iterdir()} == {"control.py"}
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith(f"---\nname: {name}\n")
    assert f"${name}" in text
    for action in actions:
        assert action in text


def test_smart_router_skill_maps_to_the_central_controller(tmp_path: Path) -> None:
    status = run_skill_script(tmp_path, ROUTER_SKILL, ["status"])
    enabled = run_skill_script(tmp_path, ROUTER_SKILL, ["on"])
    final_status = run_skill_script(tmp_path, ROUTER_SKILL, ["status"])

    assert status.returncode == enabled.returncode == final_status.returncode == 0
    assert "Smart Router: OFF" in status.stdout
    assert "Smart Router: ON" in enabled.stdout
    assert "Smart Router: ON" in final_status.stdout
    assert "Automatic Model Execution: OFF" in enabled.stdout


def test_telemetry_skill_maps_to_the_same_independent_controller(tmp_path: Path) -> None:
    started = run_skill_script(tmp_path, TELEMETRY_SKILL, ["start"])
    status = run_skill_script(tmp_path, TELEMETRY_SKILL, ["status"])
    stopped = run_skill_script(tmp_path, TELEMETRY_SKILL, ["stop"])

    assert started.returncode == status.returncode == stopped.returncode == 0
    assert "Research Telemetry: ON" in started.stdout
    assert "Smart Router: OFF" in started.stdout
    assert "Research Telemetry: ON" in status.stdout
    assert "Research Telemetry: OFF" in stopped.stdout


@pytest.mark.parametrize(
    ("skill", "arguments"),
    [
        (ROUTER_SKILL, ["enable"]),
        (ROUTER_SKILL, ["on;touch", "INJECTED"]),
        (ROUTER_SKILL, ["off", "--telemetry"]),
        (TELEMETRY_SKILL, ["enable"]),
        (TELEMETRY_SKILL, ["start;touch", "INJECTED"]),
    ],
)
def test_skill_control_arguments_cannot_inject_or_infer_actions(
    tmp_path: Path, skill: Path, arguments: list[str]
) -> None:
    completed = run_skill_script(tmp_path, skill, arguments)
    assert completed.returncode == 2
    assert not (ROOT / "INJECTED").exists()
    assert not (tmp_path / "xdg-state").exists()


def test_skill_entrypoints_have_no_shell_execution_or_policy_copy() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROUTER_SKILL / "SKILL.md",
            ROUTER_SKILL / "scripts" / "control.py",
            TELEMETRY_SKILL / "SKILL.md",
            TELEMETRY_SKILL / "scripts" / "control.py",
        )
    )
    for forbidden in (
        "shell=True",
        "subprocess",
        "os.system",
        "route_prompt",
        "reasoningEffort",
        "approval_evidence",
        "OPENAI_API_KEY",
    ):
        assert forbidden not in source
    assert source.count("smart_codex.session_cli") == 2


def test_installable_console_entrypoints_are_separate_from_official_codex() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        scripts = tomllib.load(handle)["project"]["scripts"]

    assert scripts["codex-smart"] == "smart_codex.codex_smart:main"
    assert scripts["smart-routerctl"] == "smart_codex.session_cli:main"
    assert scripts["smart-codex"] == "smart_codex.cli:main"
    assert "codex" not in scripts


def test_skills_do_not_claim_unsupported_bare_slash_commands() -> None:
    text = "\n".join(
        (skill / "SKILL.md").read_text(encoding="utf-8")
        for skill in (ROUTER_SKILL, TELEMETRY_SKILL)
    )
    assert re.search(r"(?m)^\s*/smart-router(?:\s|$)", text) is None
    assert re.search(r"(?m)^\s*/telemetry(?:\s|$)", text) is None
    assert "$smart-router" in text
    assert "$telemetry" in text


def test_documentation_states_the_exact_native_and_execution_boundaries() -> None:
    documentation = (
        ROOT / "docs" / "app-server" / "LIVE_CODEX_SESSION_CONTROL_1A.md"
    ).read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    required = (
        "The router control plane is live and demo-ready. Automatic per-turn model",
        "$smart-router on",
        "$telemetry start",
        "smart-routerctl smart-router on --telemetry",
        "smart-codex-session-control-v1",
        "does not register or claim",
    )
    for phrase in required:
        assert phrase in documentation or phrase in readme
    assert "these commands are **not** claimed or\nregistered" in documentation
    assert "/smart-router\n/telemetry" in documentation
