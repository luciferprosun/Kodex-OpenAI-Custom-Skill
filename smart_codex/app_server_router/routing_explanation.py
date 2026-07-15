"""Prompt-free, deterministic explanations for model-selection outcomes."""
from __future__ import annotations

from dataclasses import dataclass

from .prompt_features import TaskFeatures


@dataclass(frozen=True)
class RoutingExplanation:
    code: str
    summary: str


def explain_selection(
    *,
    selected_profile: str,
    features: TaskFeatures,
    switch_reason: str,
    fallback_used: bool,
    migration_warning: str | None,
) -> RoutingExplanation:
    if migration_warning is not None:
        return RoutingExplanation(
            "legacy_explicit_compatibility",
            "The explicitly requested live legacy model was retained with a migration warning.",
        )
    if fallback_used:
        return RoutingExplanation(
            f"{selected_profile}_live_capability_fallback",
            "The preferred capability class was unavailable or incompatible, so a scored live fallback was selected.",
        )
    if switch_reason == "retained_marginal_score_difference":
        return RoutingExplanation(
            "hysteresis_retained_previous_model",
            "The score difference was below the configured switch threshold, so the compatible active model was retained.",
        )
    if selected_profile == "spark":
        return RoutingExplanation(
            "spark_rapid_targeted_code_edit",
            "A text-only, low-ambiguity, small-surface coding edit favors the live latency-first model.",
        )
    if selected_profile == "luna":
        return RoutingExplanation(
            "luna_clear_repeatable_task",
            "A clear, repeatable, low-depth task favors the lightweight general model.",
        )
    if selected_profile == "terra":
        return RoutingExplanation(
            "terra_professional_default",
            "Everyday professional work with normal tools and judgment favors the balanced model.",
        )
    if selected_profile == "sol":
        if features.final_audit:
            code = "sol_final_audit"
        elif features.deep_security:
            code = "sol_deep_security_reasoning"
        elif features.architectural_depth == "high":
            code = "sol_architectural_depth"
        elif features.hard_debugging:
            code = "sol_hard_ambiguous_debugging"
        else:
            code = "sol_frontier_depth"
        return RoutingExplanation(
            code,
            "High architectural, analytical, ambiguity, or audit depth favors the frontier model.",
        )
    if selected_profile == "compatibility":
        return RoutingExplanation(
            "gpt55_compatibility_fallback",
            "GPT-5.5 was selected only as a live compatibility fallback for substantial work.",
        )
    return RoutingExplanation(
        "capability_aware_live_selection",
        "The selected live model passed all hard capability filters and had the strongest explainable score.",
    )
