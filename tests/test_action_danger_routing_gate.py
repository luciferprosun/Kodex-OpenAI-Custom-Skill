import smart_codex.router as router
from smart_codex.scorer import ScoreCard


def fake_score(action_danger: str, *, risk: str = "low", profile: str = "standard") -> ScoreCard:
    return ScoreCard(
        category="normal_coding",
        profile=profile,
        risk_level=risk,
        complexity_level="low",
        evidence_requirement="none",
        context_requirement="small",
        action_danger=action_danger,
        confidence=1.0,
        confidence_level="high",
        reasons=["test score"],
    )


def assert_security_read_only(decision, *, risk: str | None = None) -> None:
    assert decision.selected_profile == "security"
    assert decision.sandbox_mode == "read-only"
    assert decision.approval_policy == "on-request"
    assert "REQUIRES_CONFIRMATION" in (decision.warning or "")
    if risk:
        assert decision.risk == risk


def test_action_danger_destructive_operation_forces_security_read_only(monkeypatch):
    monkeypatch.setattr(router, "score", lambda prompt: fake_score("destructive_operation"))

    decision = router.route_prompt("synthetic destructive action")

    assert_security_read_only(decision, risk="critical")


def test_action_danger_deployment_operation_forces_security_read_only(monkeypatch):
    monkeypatch.setattr(router, "score", lambda prompt: fake_score("deployment_operation"))

    decision = router.route_prompt("synthetic deployment action")

    assert_security_read_only(decision, risk="high")


def test_action_danger_database_operation_forces_security_read_only(monkeypatch):
    monkeypatch.setattr(router, "score", lambda prompt: fake_score("database_operation"))

    decision = router.route_prompt("synthetic database action")

    assert_security_read_only(decision, risk="high")


def test_action_danger_secret_touching_operation_forces_security_read_only(monkeypatch):
    monkeypatch.setattr(router, "score", lambda prompt: fake_score("secret_touching_operation"))

    decision = router.route_prompt("synthetic secret action")

    assert_security_read_only(decision, risk="high")


def test_force_push_routes_security_read_only_critical():
    decision = router.route_prompt("force push to main")

    assert decision.category == "repo_operations"
    assert decision.action_danger == "destructive_operation"
    assert_security_read_only(decision, risk="critical")


def test_normal_git_operation_routes_repo_workspace_write():
    decision = router.route_prompt("create a new branch for the router refactor")

    assert decision.category == "repo_operations"
    assert decision.action_danger == "git_operations"
    assert decision.selected_profile == "repo"
    assert decision.sandbox_mode == "workspace-write"
    assert decision.approval_policy == "on-request"
    assert decision.risk in {"low", "medium"}


def test_normal_prompt_action_danger_does_not_force_security():
    decision = router.route_prompt("fix frontend bug")

    assert decision.category == "normal_coding"
    assert decision.action_danger == "write_local_files"
    assert decision.selected_profile == "standard"
    assert decision.sandbox_mode == "workspace-write"
    assert decision.risk == "low"


def test_dependency_install_routes_repo_with_warning(monkeypatch):
    monkeypatch.setattr(router, "score", lambda prompt: fake_score("dependency_install", profile="deep"))

    decision = router.route_prompt("synthetic dependency action")

    assert decision.selected_profile == "repo"
    assert decision.sandbox_mode == "workspace-write"
    assert decision.approval_policy == "on-request"
    assert "dependency install requires confirmation" in (decision.warning or "")


def test_network_access_routes_repo_with_warning(monkeypatch):
    monkeypatch.setattr(router, "score", lambda prompt: fake_score("network_access"))

    decision = router.route_prompt("synthetic network action")

    assert decision.selected_profile == "repo"
    assert decision.sandbox_mode == "workspace-write"
    assert decision.approval_policy == "on-request"
    assert "network access requires confirmation" in (decision.warning or "")
