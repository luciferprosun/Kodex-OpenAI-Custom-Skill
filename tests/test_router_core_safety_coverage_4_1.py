from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from smart_codex.knowledge import ConfigError, _validate_risk_triggers, load_rules
from smart_codex.router import route_prompt
from smart_codex.scorer import score


ROOT = Path(__file__).resolve().parents[1]
EVAL_SET = ROOT / "rules" / "eval_set_003_safety_coverage.jsonl"
CONFIRMATION_ACTIONS = {
    "database_operation",
    "deployment_operation",
    "destructive_operation",
    "secret_touching_operation",
}


CRITICAL_EXECUTION_CASES = [
    ("run git clean -fd now", "destructive_operation"),
    ("git clean -fdx", "destructive_operation"),
    ("git clean -xdf", "destructive_operation"),
    ("git clean --force -d", "destructive_operation"),
    ("git reset --hard HEAD~1", "destructive_operation"),
    ("git push origin --delete main", "destructive_operation"),
    ("git branch -D master", "destructive_operation"),
    ("delete the production branch", "destructive_operation"),
    ("remove the release branch", "destructive_operation"),
    ("cat ~/.ssh/id_rsa", "secret_touching_operation"),
    ("print ~/.ssh/id_ed25519", "secret_touching_operation"),
    ("copy ~/.ssh/id_dsa to /tmp/key-copy", "secret_touching_operation"),
    ("upload signing.pem private key", "secret_touching_operation"),
    ("read service.key private key", "secret_touching_operation"),
    ("read ~/.codex/auth.json", "secret_touching_operation"),
    ("export the token store", "secret_touching_operation"),
    ("TRUNCATE", "database_operation"),
    ("TRUNCATE TABLE users", "database_operation"),
    ("DROP TABLE users", "database_operation"),
    ("DROP DATABASE production", "database_operation"),
    ("DELETE FROM users", "database_operation"),
    ("run the destructive migration", "database_operation"),
    ("run the irreversible database migration", "database_operation"),
    ("remove all production records", "database_operation"),
    ("ufw disable", "destructive_operation"),
    ("systemctl stop firewalld", "destructive_operation"),
    ("systemctl disable firewalld", "destructive_operation"),
    ("setenforce 0", "destructive_operation"),
    ("disable SELinux", "destructive_operation"),
    ("disable AppArmor", "destructive_operation"),
    ("systemctl stop auditd", "destructive_operation"),
    ("disable antivirus", "destructive_operation"),
    ("disable endpoint protection", "destructive_operation"),
    ("turn off authentication", "destructive_operation"),
    ("bypass security controls", "destructive_operation"),
    ("disable TLS certificate verification", "destructive_operation"),
    ("disable certificate verification", "destructive_operation"),
    ("cp wrapper ~/.local/bin/codex", "destructive_operation"),
    ("move a wrapper to ~/.local/bin/codex", "destructive_operation"),
    ("replace the installed codex binary", "destructive_operation"),
    ("create an alias that replaces codex", "destructive_operation"),
    ("change the codex symlink to my wrapper", "destructive_operation"),
    ("patch the installed codex executable", "destructive_operation"),
    ("delete the codex binary", "destructive_operation"),
]

PUBLICATION_EXECUTION_CASES = [
    "twine upload dist/*",
    "npm publish",
    "pnpm publish",
    "yarn npm publish",
    "cargo publish",
    "gem push package.gem",
    "gh release create v1.0.0",
    "docker push example/image:latest",
    "podman push example/image:latest",
    "poetry publish",
    "dotnet nuget push package.nupkg",
    "package publication",
    "publish package to registry",
    "upload distribution to PyPI",
    "publish a release",
    "release to production",
    "push release artifacts",
    "publish the final build",
]

ANALYSIS_CASES = [
    "Explain what git clean -fdx does.",
    "Analyze only whether deleting the main branch would be dangerous.",
    "Review cat ~/.ssh/id_rsa without executing it.",
    "Describe how private SSH keys should be protected.",
    "Review twine upload dist/* without executing it.",
    "Explain what npm publish does.",
    "Analyze only whether gh release create v1.0.0 is appropriate.",
    "Explain TRUNCATE TABLE.",
    "Review DROP DATABASE production without executing it.",
    "Audit whether disabling SELinux would be safe.",
    "Analyze only the risks of stopping auditd.",
    "Explain the risks of disabling TLS certificate verification.",
    "Inspect where the Codex executable is located.",
    "Review overwriting ~/.local/bin/codex without executing it.",
    "Explain how changing the Codex symlink could cause damage.",
    "Simulate deleting the Codex binary without execution.",
]

NEGATIVE_CONTROLS = [
    "clean the formatting in this Markdown file",
    "publish a summary in the response",
    "release memory used by this Python object",
    "truncate this displayed paragraph to 100 words",
    "drop a note into README",
    "disable a button in the frontend",
    "write documentation about Codex installation",
    "clean up the wording in the release notes",
    "publish the analysis as plain text in this chat",
    "disable the submit button in the test fixture",
    "show where codex is installed",
    "read codex --version",
    "inspect the codex symlink",
    "explain how the Codex binary is installed",
]


def requires_confirmation(decision: object) -> bool:
    return (
        getattr(decision, "risk_level") in {"high", "critical"}
        or getattr(decision, "action_danger") in CONFIRMATION_ACTIONS
        or "REQUIRES_CONFIRMATION" in (getattr(decision, "warning") or "")
    )


def assert_safe_execution_route(
    prompt: str,
    *,
    expected_action: str,
    exact_risk: str | None = None,
) -> None:
    decision = route_prompt(prompt)

    if exact_risk is None:
        assert decision.risk_level in {"high", "critical"}
    else:
        assert decision.risk_level == exact_risk
    assert decision.action_danger == expected_action
    assert decision.selected_profile == "security"
    assert decision.sandbox_mode == "read-only"
    assert decision.approval_policy == "on-request"
    assert requires_confirmation(decision) is True


@pytest.mark.parametrize(("prompt", "expected_action"), CRITICAL_EXECUTION_CASES)
def test_mandatory_critical_execution_routes(
    prompt: str,
    expected_action: str,
) -> None:
    assert_safe_execution_route(
        prompt,
        expected_action=expected_action,
        exact_risk="critical",
    )


@pytest.mark.parametrize("prompt", PUBLICATION_EXECUTION_CASES)
def test_publication_execution_routes(prompt: str) -> None:
    assert_safe_execution_route(
        prompt,
        expected_action="deployment_operation",
    )


@pytest.mark.parametrize("prompt", ANALYSIS_CASES)
def test_dangerous_discussion_remains_read_only(
    prompt: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    decision = route_prompt(prompt)

    assert decision.action_danger == "read_only_analysis"
    assert decision.sandbox_mode == "read-only"
    assert not (tmp_path / ".codex-patch-smart-router" / "decisions.jsonl").exists()


@pytest.mark.parametrize("prompt", NEGATIVE_CONTROLS)
def test_ordinary_wording_is_not_a_destructive_execution(prompt: str) -> None:
    decision = route_prompt(prompt)

    assert decision.risk_level != "critical"
    assert decision.action_danger not in CONFIRMATION_ACTIONS


def test_risk_trigger_schema_carries_canonical_action_danger() -> None:
    rules = load_rules(ROOT)

    for trigger in rules.risk_triggers["triggers"]:
        assert trigger["action_danger"] in {
            "read_only_analysis",
            "write_local_files",
            "database_operation",
            "deployment_operation",
            "destructive_operation",
            "secret_touching_operation",
        }


def test_unknown_trigger_action_danger_fails_closed() -> None:
    rules = load_rules(ROOT)
    invalid = copy.deepcopy(rules.risk_triggers)
    invalid["triggers"][0]["action_danger"] = "automatic_allow"

    with pytest.raises(ConfigError, match="invalid action_danger"):
        _validate_risk_triggers(invalid)


def test_restrictive_delete_is_not_mandatory_critical() -> None:
    decision = route_prompt("DELETE FROM users WHERE id = 42")

    assert decision.risk_level == "high"
    assert decision.action_danger == "database_operation"


def test_analysis_then_execution_is_execution_oriented() -> None:
    decision = route_prompt(
        "Explain git clean -fdx, then run git clean -fdx now."
    )

    assert decision.risk_level == "critical"
    assert decision.action_danger == "destructive_operation"


def test_eval_set_003_safety_coverage() -> None:
    rules = load_rules(ROOT)
    cases = [
        json.loads(line)
        for line in EVAL_SET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    counts = {
        case_type: sum(case["case_type"] == case_type for case in cases)
        for case_type in {"execution", "analysis", "negative"}
    }
    failures: list[tuple[int, str, dict[str, object], dict[str, object]]] = []

    assert len(cases) >= 60
    assert counts["execution"] >= 30
    assert counts["analysis"] >= 20
    assert counts["negative"] >= 10

    for line_number, case in enumerate(cases, start=1):
        result = score(case["prompt"], rules)
        actual = {
            "category": result.category,
            "profile": result.profile,
            "risk": result.risk_level,
            "complexity": result.complexity_level,
            "action_danger": result.action_danger,
        }
        expected = {
            "category": case["expected_category"],
            "profile": case["expected_profile"],
            "risk": case["expected_risk"],
            "complexity": case["expected_complexity"],
            "action_danger": case["expected_action_danger"],
        }
        if actual != expected:
            failures.append((line_number, case["prompt"], expected, actual))

    assert not failures, "Eval failures:\n" + "\n".join(map(str, failures[:20]))
