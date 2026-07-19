from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from smart_codex.app_server_router.model_registry import ModelRegistry
from smart_codex.app_server_router.policy_mapper import PolicyMapper, RuntimeRequirements
from smart_codex.app_server_router.turn_router import TurnRouter

from app_server_test_helpers import live_model_data, model


def calibration_model_data() -> list[dict[str, object]]:
    values = live_model_data()
    values[4:4] = [
        model(
            "gpt-5.5",
            "GPT-5.5",
            "Frontier model for complex coding, research, and real-world work.",
        ),
        model(
            "gpt-5.4",
            "GPT-5.4",
            "Strong compatibility model for everyday coding.",
        ),
        model(
            "gpt-5.4-mini",
            "GPT-5.4-Mini",
            "Small compatibility model for simpler coding tasks.",
        ),
    ]
    return values


def calibration_registry(
    data: list[dict[str, object]] | None = None,
    *,
    temporarily_unavailable: Iterable[str] = (),
) -> ModelRegistry:
    return ModelRegistry.from_model_list(
        data or calibration_model_data(),
        codex_version="codex-cli 0.144.6",
        temporarily_unavailable=temporarily_unavailable,
    )


def calibration_router(
    data: list[dict[str, object]] | None = None,
    *,
    temporarily_unavailable: Iterable[str] = (),
    selection_policy_path: Path | None = None,
    effort_policy_path: Path | None = None,
    fallback_policy_path: Path | None = None,
    context_capacity_overrides: Mapping[str, str] | None = None,
    allowed_models: tuple[str, ...] | None = None,
) -> TurnRouter:
    registry = calibration_registry(
        data,
        temporarily_unavailable=temporarily_unavailable,
    )
    mapper = PolicyMapper(
        registry,
        RuntimeRequirements(None, None),
        selection_policy_path=selection_policy_path,
        effort_policy_path=effort_policy_path,
        fallback_policy_path=fallback_policy_path,
        context_capacity_overrides=context_capacity_overrides,
        allowed_models=allowed_models,
    )
    return TurnRouter(mapper)
