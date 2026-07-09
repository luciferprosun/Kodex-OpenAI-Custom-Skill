import pytest

from smart_codex.router import route_prompt


def test_security_audit_routes_to_security_read_only():
    result = route_prompt("audit repo for secrets and sandbox risks")
    assert result.category == "security_audit"
    assert result.risk == "high"
    assert result.selected_profile == "security"
    assert result.sandbox_mode == "read-only"
    assert result.approval_policy == "on-request"


def test_complex_coding_routes_to_deep():
    result = route_prompt("refactor this multi-file module")
    assert result.category == "complex_coding"
    assert result.selected_profile == "deep"


def test_math_neutrino_routes_to_math():
    result = route_prompt("prove this neutrino equation from LSC notes")
    assert result.category == "math_theory"
    assert result.selected_profile == "math"


def test_repo_commit_routes_to_repo():
    result = route_prompt("commit these changes on a new branch")
    assert result.category == "repo_operations"
    assert result.selected_profile == "repo"


def test_unknown_routes_to_standard_with_warning():
    result = route_prompt("nonsense blorple without known task")
    assert result.category == "unknown"
    assert result.selected_profile == "standard"
    assert result.warning == "low confidence route"


def test_high_risk_mixed_coding_security_routes_to_security():
    result = route_prompt("fix frontend bug and check exposed API keys")
    assert result.category == "security_audit"
    assert result.risk == "high"
    assert result.selected_profile == "security"
    assert result.sandbox_mode == "read-only"


def test_invalid_profile_override_rejected():
    with pytest.raises(ValueError):
        route_prompt("fix frontend bug", profile_override="missing")


def test_danger_full_access_sandbox_override_rejected():
    with pytest.raises(ValueError):
        route_prompt("fix frontend bug", sandbox_override="danger-full-access")

