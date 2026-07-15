from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from smart_codex.app_server_router.policy_mapper import (
    PolicyError,
    PolicyMapper,
    RuntimeRequirements,
)
from smart_codex.app_server_router.turn_router import RoutingFailure

from app_server_test_helpers import (
    live_model_data,
    model,
    registry,
    turn_message,
    turn_router,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("prompt", "expected_model", "expected_effort", "expected_class"),
    [
        ("Write a two-sentence email.", "gpt-5.6-luna", "low", "luna"),
        ("Fix the failing unit test in this repository.", "gpt-5.6-terra", "medium", "terra"),
        ("Redesign this multi-module authorization architecture.", "gpt-5.6-sol", "xhigh", "sol"),
        ("Research suitable funding programs for the AIOA project.", "gpt-5.6-terra", "high", "terra"),
        ("Change one button label.", "gpt-5.3-codex-spark", "low", "spark"),
    ],
)
def test_dynamic_model_routes(
    prompt: str,
    expected_model: str,
    expected_effort: str,
    expected_class: str,
) -> None:
    routed = turn_router().route_message(turn_message(prompt))

    assert routed.selected_model == expected_model
    assert routed.effort == expected_effort
    assert routed.route_class == expected_class
    assert routed.message["params"]["model"] == expected_model
    assert routed.message["params"]["effort"] == expected_effort


def test_turn_rewrite_preserves_all_input_items_and_unrelated_fields() -> None:
    original = turn_message(
        "Explain this screenshot and fix one typo.",
        extra_input=[{"type": "image", "url": "https://example.invalid/image.png"}],
    )
    before = copy.deepcopy(original)

    routed = turn_router().route_message(original)

    params = routed.message["params"]
    assert original == before
    assert params["input"] == before["params"]["input"]
    assert params["threadId"] == before["params"]["threadId"]
    assert params["cwd"] == before["params"]["cwd"]
    assert params["outputSchema"] == before["params"]["outputSchema"]
    assert routed.selected_model != "gpt-5.3-codex-spark"
    assert set(params) == set(before["params"]) | {
        "sandboxPolicy",
        "approvalPolicy",
        "approvalsReviewer",
    }
    assert params["approvalsReviewer"] == "user"


def test_tui_collaboration_mode_effective_model_and_effort_are_rewritten() -> None:
    original = turn_message("Write a two-sentence email.")
    original["params"]["collaborationMode"] = {
        "mode": "default",
        "settings": {
            "model": "gpt-5.6-sol",
            "reasoning_effort": "max",
            "developer_instructions": "keep this instruction",
        },
    }
    before = copy.deepcopy(original)

    routed = turn_router().route_message(original)

    assert original == before
    collaboration = routed.message["params"]["collaborationMode"]
    assert collaboration["mode"] == "default"
    assert collaboration["settings"] == {
        "model": "gpt-5.6-luna",
        "reasoning_effort": "low",
        "developer_instructions": "keep this instruction",
    }
    assert routed.message["params"]["model"] == "gpt-5.6-luna"
    assert routed.message["params"]["effort"] == "low"


@pytest.mark.parametrize(
    "collaboration_mode",
    ["default", {}, {"mode": "default", "settings": "invalid"}],
)
def test_malformed_tui_collaboration_mode_fails_closed(
    collaboration_mode: object,
) -> None:
    message = turn_message("Write a two-sentence email.")
    message["params"]["collaborationMode"] = collaboration_mode

    with pytest.raises(RoutingFailure):
        turn_router().route_message(message)


def test_high_risk_execution_keeps_safety_separate_from_model_strength() -> None:
    routed = turn_router().route_message(turn_message("Delete the default branch."))

    assert routed.selected_model == "gpt-5.6-terra"
    assert routed.category == "repo_operations"
    assert routed.sandbox_mode == "read-only"
    assert routed.message["params"]["sandboxPolicy"] == {
        "type": "readOnly",
        "networkAccess": False,
    }
    assert routed.approval_policy == "on-request"
    assert routed.message["params"]["approvalsReviewer"] == "user"


def test_false_positive_gmail_case_uses_luna_with_external_approval() -> None:
    prompt = (
        "Use the already connected Gmail account to send an existing approved draft. "
        "Do not access credentials."
    )
    routed = turn_router().route_message(turn_message(prompt))

    assert routed.category == "email"
    assert routed.selected_model == "gpt-5.6-luna"
    assert routed.sandbox_mode == "read-only"
    assert routed.approval_policy == "on-request"


def test_ultra_requires_supported_model_concrete_delegation_and_non_eval() -> None:
    prompt = "Redesign this architecture and delegate analysis to multiple agents in parallel."
    routed = turn_router().route_message(turn_message(prompt))
    assert routed.selected_model == "gpt-5.6-sol"
    assert routed.effort == "ultra"
    assert any("explicit delegation" in reason for reason in routed.reasons)

    deterministic = turn_router().route_message(
        turn_message(prompt + " This is a deterministic eval case requiring reproducibility.")
    )
    assert deterministic.effort != "ultra"
    assert any("suppressed" in reason for reason in deterministic.reasons)


def test_unsupported_effort_resolves_to_nearest_live_effort() -> None:
    data = [
        model(
            "gpt-5.6-sol",
            "GPT-5.6-Sol",
            "Latest frontier model.",
            efforts=("low", "medium", "high"),
            is_default=True,
        )
    ]
    routed = turn_router(data).route_message(
        turn_message("Redesign this multi-module authorization architecture.")
    )

    assert routed.effort == "high"
    assert any("nearest live effort" in reason for reason in routed.reasons)


@pytest.mark.parametrize(
    ("removed", "prompt", "expected"),
    [
        ({"gpt-5.6-sol"}, "Redesign this authorization architecture.", "gpt-5.6-terra"),
        ({"gpt-5.6-terra"}, "Fix the failing unit test.", "gpt-5.6-sol"),
        ({"gpt-5.6-luna"}, "Write a two-sentence email.", "gpt-5.6-terra"),
        ({"gpt-5.3-codex-spark"}, "Change one button label.", "gpt-5.6-luna"),
    ],
)
def test_live_availability_fallbacks(
    removed: set[str],
    prompt: str,
    expected: str,
) -> None:
    data = [item for item in live_model_data() if item["model"] not in removed]
    routed = turn_router(data).route_message(turn_message(prompt))
    assert routed.selected_model == expected


def test_hidden_model_is_never_selected() -> None:
    data = live_model_data()
    for index, item in enumerate(data):
        if item["model"] == "gpt-5.6-sol":
            data[index] = {**item, "hidden": True}
    routed = turn_router(data).route_message(
        turn_message("Redesign this authorization architecture.")
    )
    assert routed.selected_model == "gpt-5.6-terra"


def test_deprecated_candidate_uses_live_upgrade_target() -> None:
    data = [
        model(
            "gpt-5.6-luna",
            "GPT-5.6-Luna",
            "Fast and affordable model.",
            upgrade="gpt-5.6-terra",
        ),
        model(
            "gpt-5.6-terra",
            "GPT-5.6-Terra",
            "Balanced model for everyday work.",
        ),
    ]
    routed = turn_router(data).route_message(turn_message("Write a short email."))
    assert routed.selected_model == "gpt-5.6-terra"
    assert any("upgrade target" in reason for reason in routed.reasons)


def test_managed_requirements_can_only_tighten_sandbox_and_approval() -> None:
    requirements = RuntimeRequirements(("read-only",), ("untrusted",))
    routed = turn_router(requirements=requirements).route_message(
        turn_message("Fix the failing unit test in this repository.")
    )

    assert routed.sandbox_mode == "read-only"
    assert routed.approval_policy == "untrusted"


def test_existing_stricter_turn_policy_is_not_loosened() -> None:
    message = turn_message("Fix the failing unit test in this repository.")
    message["params"]["sandboxPolicy"] = {"type": "readOnly", "networkAccess": False}
    message["params"]["approvalPolicy"] = "untrusted"

    routed = turn_router().route_message(message)

    assert routed.sandbox_mode == "read-only"
    assert routed.message["params"]["sandboxPolicy"]["type"] == "readOnly"
    assert routed.approval_policy == "untrusted"
    assert routed.message["params"]["approvalsReviewer"] == "user"


def test_named_permission_profile_fails_closed_instead_of_conflicting_with_sandbox() -> None:
    message = turn_message("Fix the failing unit test in this repository.")
    message["params"]["permissions"] = ":workspace"

    with pytest.raises(RoutingFailure):
        turn_router().route_message(message)


def test_unsafe_managed_requirements_fail_without_forward_route() -> None:
    requirements = RuntimeRequirements(("danger-full-access",), ("never",))
    with pytest.raises(RoutingFailure):
        turn_router(requirements=requirements).route_message(
            turn_message("Fix the failing unit test.")
        )


def test_malformed_declarative_model_policy_fails_closed(tmp_path: Path) -> None:
    policy = json.loads(
        (ROOT / "rules" / "app_server_model_policy.json").read_text(encoding="utf-8")
    )
    policy["category_classes"] = []
    policy_path = tmp_path / "invalid-policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(PolicyError):
        PolicyMapper(
            registry(),
            RuntimeRequirements(None, None),
            policy_path=policy_path,
        )
