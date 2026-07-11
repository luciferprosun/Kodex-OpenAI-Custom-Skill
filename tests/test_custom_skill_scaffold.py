from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / ".agents" / "skills" / "codex-patch-smart-router"
SKILL_FILE = SKILL_DIR / "SKILL.md"
REFERENCE_FILE = SKILL_DIR / "references" / "routing-policy.md"


def read_skill() -> str:
    return SKILL_FILE.read_text(encoding="utf-8")


def frontmatter(text: str) -> str:
    lines = text.splitlines()
    assert lines and lines[0] == "---"
    closing_index = lines.index("---", 1)
    assert closing_index > 1
    return "\n".join(lines[1:closing_index])


def test_skill_scaffold_has_exact_phase_2_structure():
    assert SKILL_DIR.is_dir()
    assert SKILL_FILE.is_file()
    assert REFERENCE_FILE.is_file()
    assert {path.name for path in SKILL_DIR.iterdir()} == {"SKILL.md", "references"}
    assert {path.name for path in (SKILL_DIR / "references").iterdir()} == {
        "routing-policy.md"
    }


def test_skill_frontmatter_is_minimal_and_trigger_focused():
    metadata = frontmatter(read_skill())
    lines = metadata.splitlines()

    assert lines[0] == "name: codex-patch-smart-router"
    assert lines[1].startswith("description: ")
    assert len(lines) == 2

    description = lines[1].removeprefix("description: ").lower()
    for concept in ("risk", "complexity", "security", "repository"):
        assert concept in description


def test_skill_rejects_unsupported_capability_claims():
    text = read_skill().lower()
    unsupported_claims = (
        "automatically switches the model",
        "automatically changes the model",
        "automatically changes the sandbox",
        "intercepts every prompt",
        "intercepts all tools",
        "guarantees complete enforcement",
    )

    for claim in unsupported_claims:
        assert claim not in text

    assert "does not replace codex, modify codex internals, or automatically change the active model, profile, sandbox, or approval policy" in text
    assert "do not imply complete interception of codex tool paths" in text
    assert "do not call tools, run commands, or read files" in text
    assert "do not perform the underlying task" in text


def test_skill_contains_no_forbidden_runtime_or_secret_material():
    text = read_skill()
    lowered = text.lower()

    for forbidden in (
        "danger-full-access",
        "approval_policy = \"never\"",
        "shell=true",
        "-----begin private key-----",
        "-----begin openssh private key-----",
        "ghp_",
        "sk-proj-",
    ):
        assert forbidden not in lowered

    assert re.search(r"\bgpt-\d[\w.-]*\b", lowered) is None
    assert re.search(r"\bo[1-9](?:-[\w.-]+)?\b", lowered) is None


def test_phase_3_through_6_artifacts_are_absent():
    forbidden_paths = (
        SKILL_DIR / "scripts",
        SKILL_DIR / "hooks",
        SKILL_DIR / "assets",
        SKILL_DIR / "agents",
        REPO_ROOT / "hooks",
        REPO_ROOT / ".codex-plugin",
    )

    for path in forbidden_paths:
        assert not path.exists(), path
