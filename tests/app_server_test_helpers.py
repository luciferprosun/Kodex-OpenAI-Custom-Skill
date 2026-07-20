from __future__ import annotations

from typing import Iterable

from smart_codex.app_server_router.model_registry import ModelRegistry
from smart_codex.app_server_router.policy_mapper import PolicyMapper, RuntimeRequirements
from smart_codex.app_server_router.turn_router import TurnRouter


EFFORTS = {
    "low": "Fast responses with lighter reasoning",
    "medium": "Balances speed and reasoning depth",
    "high": "Greater reasoning depth",
    "xhigh": "Extra high reasoning depth",
    "max": "Maximum reasoning depth",
    "ultra": "Maximum reasoning with automatic task delegation",
}


def model(
    model_id: str,
    display_name: str,
    description: str,
    *,
    efforts: Iterable[str] = ("low", "medium", "high", "xhigh"),
    modalities: Iterable[str] = ("text", "image"),
    hidden: bool = False,
    upgrade: str | None = None,
    is_default: bool = False,
    default_effort: str | None = None,
    service_tiers: Iterable[str] = (),
    default_service_tier: str | None = None,
    supports_personality: bool = False,
) -> dict[str, object]:
    effort_values = tuple(efforts)
    tier_values = tuple(service_tiers)
    selected_default = default_effort or (
        "medium" if "medium" in effort_values else effort_values[0]
    )
    if selected_default not in effort_values:
        raise ValueError("test fixture default effort must be supported")
    if default_service_tier is not None and default_service_tier not in tier_values:
        raise ValueError("test fixture default service tier must be supported")
    return {
        "id": model_id,
        "model": model_id,
        "upgrade": upgrade,
        "upgradeInfo": None,
        "availabilityNux": None,
        "displayName": display_name,
        "description": description,
        "hidden": hidden,
        "supportedReasoningEfforts": [
            {"reasoningEffort": item, "description": EFFORTS[item]}
            for item in effort_values
        ],
        "defaultReasoningEffort": selected_default,
        "inputModalities": list(modalities),
        "supportsPersonality": supports_personality,
        "additionalSpeedTiers": [],
        "serviceTiers": [
            {"id": item, "description": f"{item} service tier"}
            for item in tier_values
        ],
        "defaultServiceTier": default_service_tier,
        "isDefault": is_default,
    }


def live_model_data() -> list[dict[str, object]]:
    return [
        model(
            "gpt-5.6-sol",
            "GPT-5.6-Sol",
            "Latest frontier agentic coding model.",
            efforts=("low", "medium", "high", "xhigh", "max", "ultra"),
            default_effort="low",
            service_tiers=("priority",),
            is_default=True,
        ),
        model(
            "gpt-5.6-terra",
            "GPT-5.6-Terra",
            "Balanced agentic coding model for everyday work.",
            efforts=("low", "medium", "high", "xhigh", "max", "ultra"),
            default_effort="medium",
            service_tiers=("priority",),
        ),
        model(
            "gpt-5.6-luna",
            "GPT-5.6-Luna",
            "Fast and affordable agentic coding model.",
            efforts=("low", "medium", "high", "xhigh", "max"),
            default_effort="medium",
            service_tiers=("priority",),
        ),
        model(
            "gpt-5.3-codex-spark",
            "GPT-5.3-Codex-Spark",
            "Ultra-fast coding model.",
            modalities=("text",),
        ),
        model(
            "codex-auto-review",
            "Codex Auto Review",
            "Automatic approval review model for Codex.",
            hidden=True,
        ),
    ]


def registry(data: list[dict[str, object]] | None = None) -> ModelRegistry:
    return ModelRegistry.from_model_list(
        data or live_model_data(),
        codex_version="codex-cli 0.144.6",
    )


def turn_router(
    data: list[dict[str, object]] | None = None,
    requirements: RuntimeRequirements | None = None,
) -> TurnRouter:
    mapper = PolicyMapper(
        registry(data),
        requirements or RuntimeRequirements(None, None),
    )
    return TurnRouter(mapper)


def turn_message(
    prompt: str,
    *,
    request_id: object = 7,
    thread_id: str = "thread-test",
    extra_input: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    inputs: list[dict[str, object]] = [
        {"type": "text", "text": prompt, "text_elements": []}
    ]
    if extra_input:
        inputs.extend(extra_input)
    return {
        "method": "turn/start",
        "id": request_id,
        "params": {
            "threadId": thread_id,
            "input": inputs,
            "cwd": "/home/l/codex-patch-smart-router",
            "model": "gpt-5.6-sol",
            "effort": "max",
            "outputSchema": {"type": "string"},
        },
    }
