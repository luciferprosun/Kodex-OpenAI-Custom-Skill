from __future__ import annotations

import pytest

from smart_codex.preprocessor import analyze_prompt_semantics
from smart_codex.router import route_prompt


NEGATED_SECRET_CONSTRAINTS = [
    "Do not access credentials.",
    "Do not read auth.json.",
    "Without reading passwords or tokens, use the connected Gmail tool.",
    "Use the existing Gmail connection; never inspect login data.",
    "Send the approved draft, but do not access cookies or credentials.",
    "Check the repository without opening .env.",
]

DIRECT_SECRET_ACCESS = [
    "Read ~/.codex/auth.json.",
    "Print my Gmail password.",
    "Export the access token.",
    "Open .env and show the API key.",
    "Copy ~/.ssh/id_rsa.",
    "Retrieve saved browser cookies.",
]

DOCUMENTATION_OR_ANALYSIS = [
    "Write documentation explaining why credentials must not be logged.",
    "Add the sentence ‘Do not expose tokens’ to README.",
    "Review this policy: never read private keys.",
]


@pytest.mark.parametrize("prompt", NEGATED_SECRET_CONSTRAINTS)
def test_negated_secret_access_is_a_constraint_not_execution(prompt: str) -> None:
    decision = route_prompt(prompt)

    assert decision.safety_constraints
    assert "sensitive_data_access_prohibited" in decision.safety_constraints
    assert decision.category != "secret_handling"
    assert decision.risk_level != "critical"
    assert decision.action_danger != "secret_touching_operation"
    assert decision.approval_policy == "on-request"


def test_connected_gmail_send_retains_normal_external_action_approval() -> None:
    prompt = (
        "Use an already connected Gmail account to send an existing approved draft. "
        "Do not access passwords, tokens, auth files, cookies, or credential stores."
    )

    decision = route_prompt(prompt)

    assert decision.category == "email"
    assert decision.selected_profile == "fast"
    assert decision.risk_level == "medium"
    assert decision.action_danger == "external_service_action"
    assert decision.approval_policy == "on-request"
    assert "external service action requires human approval" in (decision.warning or "")
    assert decision.safety_constraints == [
        "sensitive_data_access_prohibited",
        "credential_access_prohibited",
        "password_access_prohibited",
        "token_access_prohibited",
        "auth_data_access_prohibited",
        "cookie_access_prohibited",
    ]


@pytest.mark.parametrize("prompt", DIRECT_SECRET_ACCESS)
def test_direct_secret_access_remains_critical_and_read_only(prompt: str) -> None:
    decision = route_prompt(prompt)

    assert decision.safety_constraints == []
    assert decision.category == "secret_handling"
    assert decision.risk_level == "critical"
    assert decision.action_danger == "secret_touching_operation"
    assert decision.selected_profile == "security"
    assert decision.sandbox_mode == "read-only"
    assert decision.approval_policy == "on-request"
    assert "REQUIRES_CONFIRMATION" in (decision.warning or "")


@pytest.mark.parametrize("prompt", DOCUMENTATION_OR_ANALYSIS)
def test_secret_prohibition_text_remains_documentation_or_analysis(prompt: str) -> None:
    decision = route_prompt(prompt)

    assert decision.safety_constraints
    assert decision.category == "documentation"
    assert decision.risk_level != "critical"
    assert decision.action_danger != "secret_touching_operation"
    assert decision.selected_profile == "fast"


def test_semantic_view_preserves_only_sanitized_constraint_labels() -> None:
    prompt = "Send the approved draft, but do not access cookies or credentials."

    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)

    assert semantics.normalized_text == prompt.lower()
    assert semantics.actionable_text == "send the approved draft"
    assert "cookies" not in semantics.actionable_text
    assert "credentials" not in semantics.actionable_text
    assert prompt not in decision.decision_reasons
    assert all(prompt not in reason for reason in decision.decision_reasons)
