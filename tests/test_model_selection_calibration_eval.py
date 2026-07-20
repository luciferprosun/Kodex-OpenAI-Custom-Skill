from __future__ import annotations

from collections import Counter
from pathlib import Path

from smart_codex.app_server_router.evaluation import (
    EvalOutcome,
    load_eval_cases,
    summarize_evaluation,
)

from app_server_test_helpers import model, turn_message
from model_policy_test_helpers import calibration_model_data, calibration_router


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "rules" / "model_selection_eval_001.jsonl"


def _fixture(name: str) -> tuple[list[dict[str, object]], tuple[str, ...], bool]:
    data = calibration_model_data()
    unavailable: tuple[str, ...] = ()
    image = False
    if name == "spark_missing":
        data = [item for item in data if item["model"] != "gpt-5.3-codex-spark"]
    elif name == "spark_hidden":
        data = [
            {**item, "hidden": True}
            if item["model"] == "gpt-5.3-codex-spark"
            else item
            for item in data
        ]
    elif name == "spark_rate_limited":
        unavailable = ("gpt-5.3-codex-spark",)
    elif name == "sol_missing":
        data = [item for item in data if item["model"] != "gpt-5.6-sol"]
    elif name == "terra_missing":
        data = [item for item in data if item["model"] != "gpt-5.6-terra"]
    elif name == "luna_missing":
        data = [item for item in data if item["model"] != "gpt-5.6-luna"]
    elif name == "effort_changed":
        data = [
            {
                **item,
                "supportedReasoningEfforts": [
                    option
                    for option in item["supportedReasoningEfforts"]  # type: ignore[index]
                    if option["reasoningEffort"] in {"low", "medium", "high"}  # type: ignore[index]
                ],
            }
            if item["model"] == "gpt-5.6-sol"
            else item
            for item in data
        ]
    elif name == "unknown_model_added":
        data.append(
            model(
                "gpt-6-orbit",
                "GPT-6 Orbit",
                "New model without a verified capability profile.",
            )
        )
    elif name == "spark_image":
        image = True
    elif name == "legacy_upgrade":
        data = [
            {
                **item,
                "upgrade": "gpt-5.6-terra",
                "upgradeInfo": {"model": "gpt-5.6-terra"},
            }
            if item["model"] == "gpt-5.4"
            else item
            for item in data
        ]
    elif name != "default":
        raise AssertionError(f"unknown evaluation fixture {name}")
    return data, unavailable, image


def test_curated_model_selection_eval_meets_phase_5_3_targets() -> None:
    cases = load_eval_cases(DATASET)
    groups = Counter(case.group for case in cases)
    assert len(cases) == 180
    assert groups == {
        "trivial_writing": 30,
        "luna_simple": 25,
        "spark_targeted": 25,
        "terra_coding": 35,
        "terra_research": 20,
        "sol_frontier": 25,
        "ultra_admission_pending": 10,
        "fallback_migration": 10,
    }

    outcomes: list[EvalOutcome] = []
    for case in cases:
        data, unavailable, image = _fixture(case.fixture)
        router = calibration_router(data, temporarily_unavailable=unavailable)
        message = turn_message(
            case.prompt,
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
                "developer_instructions": None,
            },
        }
        routed = router.route_message(message)
        selected = router.mapper.registry.get(routed.selected_model)
        assert selected is not None
        outcomes.append(
            EvalOutcome(
                case_id=case.id,
                profile=routed.route_class,
                effort=routed.effort,
                model=routed.selected_model,
                effort_supported=routed.effort in selected.supported_efforts,
                model_available=router.mapper.registry.is_routable(selected),
                orchestration_mode=routed.orchestration_mode,
            )
        )

    metrics = summarize_evaluation(cases, outcomes)
    assert metrics.overall_accuracy >= 95.0
    assert metrics.trivial_deescalation >= 95.0
    assert metrics.spark_eligible_accuracy >= 85.0
    assert metrics.terra_professional_accuracy >= 90.0
    assert metrics.sol_architecture_accuracy >= 95.0
    assert metrics.critical_under_routing == 0
    assert metrics.unsupported_efforts == 0
    assert metrics.unavailable_selections == 0
    assert metrics.ultra_without_approved_orchestration == 0
