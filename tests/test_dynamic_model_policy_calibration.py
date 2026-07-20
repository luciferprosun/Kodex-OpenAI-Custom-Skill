from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from smart_codex.app_server_router.policy_mapper import SPARK_TEST_INSTRUCTION
from smart_codex.app_server_router.prompt_features import extract_task_features
from smart_codex.app_server_router.turn_router import RoutingFailure
from smart_codex.router import route_prompt

from app_server_test_helpers import model, turn_message
from model_policy_test_helpers import (
    calibration_model_data,
    calibration_router,
)


ROOT = Path(__file__).resolve().parents[1]


def _tui_message(
    prompt: str,
    *,
    image: bool = False,
    developer_instructions: str | None = None,
) -> dict[str, object]:
    message = turn_message(
        prompt,
        extra_input=(
            [{"type": "image", "url": "https://example.invalid/fixture.png"}]
            if image
            else None
        ),
    )
    message["params"]["collaborationMode"] = {  # type: ignore[index]
        "mode": "default",
        "settings": {
            "model": "gpt-5.6-sol",
            "reasoning_effort": "max",
            "developer_instructions": developer_instructions,
        },
    }
    return message


def _selection_policy_with_threshold(tmp_path: Path, threshold: float) -> Path:
    policy = json.loads(
        (ROOT / "rules" / "model_selection_policy.json").read_text(encoding="utf-8")
    )
    policy["switch_threshold"] = threshold
    target = tmp_path / "selection-policy.json"
    target.write_text(json.dumps(policy), encoding="utf-8")
    return target


def test_selection_exposes_complete_explainable_score_and_fallback_metadata() -> None:
    routed = calibration_router().route_message(
        turn_message("Fix five failing tests across three modules.")
    )

    assert routed.route_class == "terra"
    assert routed.selection_confidence in {"low", "medium", "high"}
    assert routed.switch_confidence in {"low", "medium", "high"}
    assert routed.selection_explanation
    assert routed.fallback_order
    assert routed.rejected_candidates is not None
    components = routed.candidate_scores[0].components
    assert set(components) == {
        "base",
        "capability_fit",
        "task_fit",
        "complexity_fit",
        "context_fit",
        "latency_fit",
        "quality_fit",
        "tool_fit",
        "modality_fit",
        "availability_fit",
        "continuity_cost",
        "preview_model_penalty",
        "migration_penalty",
        "overqualification_penalty",
        "underqualification_penalty",
        "explicit_preference",
        "fallback_fit",
    }


@pytest.mark.parametrize(
    ("fixture", "expected_reason"),
    [
        ("hidden", "hidden_model"),
        ("unavailable", "temporarily_unavailable"),
        ("image", "unsupported_input_modality"),
    ],
)
def test_spark_hard_filters_precede_scoring(
    fixture: str,
    expected_reason: str,
) -> None:
    data = calibration_model_data()
    unavailable: tuple[str, ...] = ()
    image = False
    if fixture == "hidden":
        data = [
            {**item, "hidden": True}
            if item["model"] == "gpt-5.3-codex-spark"
            else item
            for item in data
        ]
    elif fixture == "unavailable":
        unavailable = ("gpt-5.3-codex-spark",)
    elif fixture == "image":
        image = True

    routed = calibration_router(
        data,
        temporarily_unavailable=unavailable,
    ).route_message(_tui_message("Change one button label.", image=image))

    assert routed.route_class != "spark"
    assert routed.rejected_candidates is not None
    assert expected_reason in routed.rejected_candidates["gpt-5.3-codex-spark"]


def test_spark_absence_uses_lightweight_live_fallback() -> None:
    data = [
        item
        for item in calibration_model_data()
        if item["model"] != "gpt-5.3-codex-spark"
    ]
    routed = calibration_router(data).route_message(
        _tui_message("Change one button label.")
    )

    assert routed.route_class in {"luna", "terra"}
    assert routed.selected_model != "gpt-5.3-codex-spark"


def test_spark_context_capacity_is_enforced_before_scoring() -> None:
    routed = calibration_router(
        context_capacity_overrides={"gpt-5.3-codex-spark": "small"}
    ).route_message(
        _tui_message("Change one targeted button label across three files.")
    )

    assert routed.route_class != "spark"
    assert routed.rejected_candidates is not None
    assert "context_requirement_exceeds_verified_capacity" in routed.rejected_candidates[
        "gpt-5.3-codex-spark"
    ]


def test_spark_accepts_verified_small_context() -> None:
    routed = calibration_router(
        context_capacity_overrides={"gpt-5.3-codex-spark": "small"}
    ).route_message(_tui_message("Change one button label."))

    assert routed.route_class == "spark"


def test_spark_recognizes_camel_case_ui_field_as_a_targeted_edit() -> None:
    routed = calibration_router().route_message(
        _tui_message("Change only buttonLabel in this JSON UI fixture.")
    )

    assert routed.route_class == "spark"
    assert routed.effort == "low"


def test_spark_injects_focused_test_requirement_only_when_needed() -> None:
    routed = calibration_router().route_message(
        _tui_message(
            "Fix one isolated function in this file.",
            developer_instructions="Keep the existing project conventions.",
        )
    )

    assert routed.route_class == "spark"
    settings = routed.message["params"]["collaborationMode"]["settings"]
    instructions = settings["developer_instructions"]
    assert instructions.startswith("Keep the existing project conventions.")
    assert SPARK_TEST_INSTRUCTION in instructions


def test_spark_falls_back_when_client_has_no_safe_routed_test_context() -> None:
    message = turn_message("Fix one isolated function in this file.")
    routed = calibration_router().route_message(message)

    assert routed.route_class != "spark"
    assert "collaborationMode" not in routed.message["params"]


@pytest.mark.parametrize(
    "prompt",
    [
        "Prototype one small targeted UI interaction; tests are not required.",
        "Fix one isolated function and run its focused unit test.",
    ],
)
def test_spark_does_not_duplicate_unneeded_test_context(prompt: str) -> None:
    routed = calibration_router().route_message(_tui_message(prompt))

    assert routed.route_class == "spark"
    settings = routed.message["params"]["collaborationMode"]["settings"]
    assert settings["developer_instructions"] is None


def test_materially_simpler_turn_deescalates_from_sol() -> None:
    routed = calibration_router().route_message(
        turn_message("Correct this sentence for grammar."),
        previous_model="gpt-5.6-sol",
    )

    assert routed.selected_model == "gpt-5.6-luna"
    assert routed.switch_reason == "material_score_margin"
    assert routed.score_margin >= 8.0


def test_configurable_hysteresis_retains_a_marginal_previous_model(tmp_path: Path) -> None:
    policy_path = _selection_policy_with_threshold(tmp_path, 1000.0)
    routed = calibration_router(selection_policy_path=policy_path).route_message(
        turn_message("Correct this sentence for grammar."),
        previous_model="gpt-5.6-sol",
    )

    assert routed.selected_model == "gpt-5.6-sol"
    assert routed.switch_reason == "retained_marginal_score_difference"
    assert routed.switch_confidence == "low"


def test_hysteresis_never_blocks_required_capability_escalation(tmp_path: Path) -> None:
    policy_path = _selection_policy_with_threshold(tmp_path, 1000.0)
    routed = calibration_router(selection_policy_path=policy_path).route_message(
        turn_message("Redesign authentication across several services."),
        previous_model="gpt-5.6-luna",
    )

    assert routed.selected_model == "gpt-5.6-sol"
    assert routed.switch_reason == "escalated_for_required_capability_depth"


def test_unknown_model_is_rejected_with_sanitized_drift_signal() -> None:
    data = calibration_model_data()
    data.append(
        model(
            "gpt-6-orbit",
            "GPT-6 Orbit",
            "New model without a verified capability profile.",
        )
    )
    routed = calibration_router(data).route_message(
        turn_message("Fix a routine backend test failure.")
    )

    assert routed.selected_model != "gpt-6-orbit"
    assert routed.rejected_candidates is not None
    assert routed.rejected_candidates["gpt-6-orbit"] == (
        "unknown_capability_profile",
    )
    assert "unknown_model_capabilities:gpt-6-orbit" in routed.drift_warnings


def test_future_family_model_requires_matching_live_capability_shape() -> None:
    data = [
        model(
            "gpt-5.7-terra",
            "GPT-5.7 Terra",
            "Future balanced family model.",
            efforts=("low", "medium", "high", "xhigh", "max", "ultra"),
        )
    ]
    routed = calibration_router(data).route_message(
        turn_message("Fix the failing unit test in this repository.")
    )

    assert routed.selected_model == "gpt-5.7-terra"
    assert "family_model_conservative_profile:gpt-5.7-terra" in routed.drift_warnings


def test_future_family_capability_drift_is_rejected() -> None:
    data = [
        model(
            "gpt-5.7-terra",
            "GPT-5.7 Terra",
            "Future family model with an uncalibrated effort shape.",
            efforts=("low", "medium"),
        ),
        model(
            "gpt-5.6-sol",
            "GPT-5.6 Sol",
            "Known frontier fallback.",
            efforts=("low", "medium", "high", "xhigh", "max", "ultra"),
        ),
    ]
    routed = calibration_router(data).route_message(
        turn_message("Fix the failing unit test in this repository.")
    )

    assert routed.selected_model == "gpt-5.6-sol"
    assert routed.rejected_candidates is not None
    assert "insufficient_future_model_capability_match" in routed.rejected_candidates[
        "gpt-5.7-terra"
    ]
    assert "effort_drift:gpt-5.7-terra" in routed.drift_warnings


def test_future_family_uses_conservative_context_until_verified() -> None:
    data = [
        model(
            "gpt-5.7-terra",
            "GPT-5.7 Terra",
            "Future balanced family model.",
            efforts=("low", "medium", "high", "xhigh", "max", "ultra"),
        ),
        model(
            "gpt-5.6-sol",
            "GPT-5.6 Sol",
            "Known frontier fallback.",
            efforts=("low", "medium", "high", "xhigh", "max", "ultra"),
        ),
    ]
    routed = calibration_router(data).route_message(
        turn_message("Fix five failing tests across three modules.")
    )

    assert routed.selected_model == "gpt-5.6-sol"
    assert routed.rejected_candidates is not None
    assert "context_requirement_exceeds_verified_capacity" in routed.rejected_candidates[
        "gpt-5.7-terra"
    ]


def test_known_model_effort_drift_uses_only_live_supported_effort() -> None:
    data = [
        model(
            "gpt-5.6-sol",
            "GPT-5.6 Sol",
            "Known frontier model with changed efforts.",
            efforts=("low", "medium", "high"),
        )
    ]
    routed = calibration_router(data).route_message(
        turn_message("Redesign this multi-module authorization architecture.")
    )

    assert routed.effort == "high"
    live_efforts = {
        option["reasoningEffort"]
        for option in data[0]["supportedReasoningEfforts"]
    }
    assert routed.effort in live_efforts
    assert "effort_drift:gpt-5.6-sol" in routed.drift_warnings


def test_live_modality_change_rejects_incompatible_candidate() -> None:
    data = [
        {**item, "inputModalities": ["text"]}
        if item["model"] == "gpt-5.6-terra"
        else item
        for item in calibration_model_data()
    ]
    routed = calibration_router(data).route_message(
        _tui_message("Review a medium synthetic patch using this image.", image=True)
    )

    assert routed.selected_model != "gpt-5.6-terra"
    assert routed.rejected_candidates is not None
    assert "unsupported_input_modality" in routed.rejected_candidates["gpt-5.6-terra"]
    assert "modality_drift:gpt-5.6-terra" in routed.drift_warnings


def test_static_legacy_map_does_not_invent_a_live_upgrade() -> None:
    data = [model("gpt-5.4", "GPT-5.4", "Available compatibility model.")]
    routed = calibration_router(data).route_message(
        turn_message("Implement a routine feature in three files with tests.")
    )

    assert routed.selected_model == "gpt-5.4"
    assert routed.migration_warning is None
    assert not any("upgrade_target" in warning for warning in routed.drift_warnings)


def test_explicit_available_legacy_request_emits_live_migration_warning() -> None:
    data = [
        {
            **item,
            "upgrade": "gpt-5.6-terra",
            "upgradeInfo": {"model": "gpt-5.6-terra"},
        }
        if item["model"] == "gpt-5.4"
        else item
        for item in calibration_model_data()
    ]
    routed = calibration_router(data).route_message(
        turn_message("Use gpt-5.4 to implement a routine feature.")
    )

    assert routed.selected_model == "gpt-5.4"
    assert routed.migration_warning == "legacy_model_selected_for_explicit_compatibility"
    assert "upgrade_target_observed:gpt-5.4" in routed.drift_warnings


def test_workspace_model_policy_is_a_hard_filter() -> None:
    routed = calibration_router(
        allowed_models=("gpt-5.6-luna",)
    ).route_message(turn_message("Fix the failing unit test in this repository."))

    assert routed.selected_model == "gpt-5.6-luna"
    assert routed.rejected_candidates is not None
    assert "forbidden_by_workspace_policy" in routed.rejected_candidates[
        "gpt-5.6-terra"
    ]


def test_no_workspace_allowed_model_fails_closed() -> None:
    router = calibration_router(allowed_models=("not-a-live-model",))

    with pytest.raises(RoutingFailure):
        router.route_message(turn_message("Fix the failing unit test."))


def test_model_strength_never_changes_destructive_authority() -> None:
    routed = calibration_router().route_message(
        turn_message(
            "Redesign authentication across several services, then delete the default branch."
        )
    )

    assert routed.route_class == "sol"
    assert routed.sandbox_mode == "read-only"
    assert routed.approval_policy == "on-request"
    assert routed.message["params"]["approvalsReviewer"] == "user"


def test_harmless_security_word_does_not_force_sol() -> None:
    routed = calibration_router().route_message(
        turn_message("Write one documentation sentence containing the word security.")
    )

    assert routed.route_class == "luna"
    assert routed.effort == "low"


def test_ordinary_effort_selection_never_interprets_ultra_as_an_effort() -> None:
    router = calibration_router()
    decision = route_prompt("Correct this sentence for grammar.", dry_run=True)
    features = extract_task_features(
        "Correct this sentence for grammar.",
        decision,
        required_modalities=("text",),
    )
    features = replace(
        features,
        explicit_effort_preference="ultra",
        need_for_delegation=True,
        need_for_parallel_agents=True,
        independent_workstreams="large",
        expected_duration="xlarge",
    )
    live = router.mapper.registry.get("gpt-5.6-luna")
    assert live is not None
    profile = router.mapper.model_policy.catalog.resolve(live)
    assert profile is not None

    effort = router.mapper.effort_policy.select(live, profile, features)

    assert effort.selected != "ultra"
    assert effort.selected in live.ordinary_supported_efforts


def test_descriptive_inflected_delegation_language_never_emits_ultra() -> None:
    routed = calibration_router().route_message(
        _tui_message(
            "Describe without executing a large research-and-implementation "
            "program delegated to four parallel agents, one independent "
            "workstream each."
        )
    )

    assert routed.route_class in {"terra", "sol"}
    assert routed.effort != "ultra"
    assert routed.orchestration_mode == "single_agent"
    assert routed.ultra_recommendation == "not_recommended"


def test_explicit_unavailable_spark_preference_falls_back_safely() -> None:
    data = [
        item
        for item in calibration_model_data()
        if item["model"] != "gpt-5.3-codex-spark"
    ]
    routed = calibration_router(data).route_message(
        _tui_message("Use Spark to change one button label.")
    )

    assert routed.route_class in {"luna", "terra"}
    assert routed.selected_model != "gpt-5.3-codex-spark"
