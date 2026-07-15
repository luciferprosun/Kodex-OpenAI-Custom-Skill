"""Explainable scoring and hysteresis over hard-filtered live models."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .capability_filter import (
    CapabilityFilter,
    EligibleModel,
    FilterResult,
    ModelProfile,
    ProfileCatalog,
)
from .fallback_resolver import FallbackResolver
from .model_registry import ModelRegistry
from .prompt_features import TaskFeatures
from .routing_explanation import RoutingExplanation, explain_selection


class ModelPolicyError(RuntimeError):
    pass


_SIZE_RANK = {
    "unknown": 0,
    "tiny": 1,
    "small": 2,
    "medium": 3,
    "large": 4,
    "xlarge": 5,
}


@dataclass(frozen=True)
class CandidateScore:
    model: str
    profile: str
    components: dict[str, float]
    total: float
    migration_warning: str | None


@dataclass(frozen=True)
class ModelSelection:
    selected: EligibleModel
    desired_profile: str
    candidate_scores: tuple[CandidateScore, ...]
    rejected_candidates: dict[str, tuple[str, ...]]
    fallback_order: tuple[str, ...]
    selection_confidence: str
    switch_confidence: str
    previous_model: str | None
    score_margin: float
    switch_reason: str
    explanation: RoutingExplanation
    drift_warnings: tuple[str, ...]
    requires_test_instruction: bool


def default_selection_policy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "rules" / "model_selection_policy.json"


def default_fallback_policy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "rules" / "model_fallback_policy.json"


class ModelPolicy:
    def __init__(
        self,
        registry: ModelRegistry,
        *,
        selection_policy: object,
        fallback_policy: object,
        allowed_models: tuple[str, ...] | None = None,
        context_capacity_overrides: Mapping[str, str] | None = None,
    ):
        if not isinstance(selection_policy, dict):
            raise ModelPolicyError("model selection policy must be an object")
        self.registry = registry
        self.catalog = ProfileCatalog.from_policy(selection_policy.get("profiles"))
        self.fallback = FallbackResolver.from_policy(fallback_policy)
        self.fallback.validate_profiles(self.catalog.by_name)
        self.filter = CapabilityFilter(
            registry,
            self.catalog,
            legacy_targets=self.fallback.legacy_targets,
            legacy_profiles=self.fallback.legacy_profiles,
            allowed_models=allowed_models,
            context_capacity_overrides=context_capacity_overrides,
        )
        self.scoring = self._number_map(selection_policy.get("scoring"), "scoring")
        switch_threshold = selection_policy.get("switch_threshold")
        if isinstance(switch_threshold, bool) or not isinstance(switch_threshold, (int, float)) or switch_threshold < 0:
            raise ModelPolicyError("model switch threshold is malformed")
        self.switch_threshold = float(switch_threshold)
        confidence = selection_policy.get("confidence_thresholds")
        if not isinstance(confidence, dict):
            raise ModelPolicyError("selection confidence thresholds are malformed")
        high = confidence.get("high")
        medium = confidence.get("medium")
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (high, medium)):
            raise ModelPolicyError("selection confidence threshold is malformed")
        if float(high) < float(medium) or float(medium) < 0:
            raise ModelPolicyError("selection confidence thresholds are out of order")
        self.confidence_high = float(high)
        self.confidence_medium = float(medium)

    @classmethod
    def from_paths(
        cls,
        registry: ModelRegistry,
        *,
        selection_path: Path | None = None,
        fallback_path: Path | None = None,
        allowed_models: tuple[str, ...] | None = None,
        context_capacity_overrides: Mapping[str, str] | None = None,
    ) -> "ModelPolicy":
        return cls(
            registry,
            selection_policy=_load_json(selection_path or default_selection_policy_path()),
            fallback_policy=_load_json(fallback_path or default_fallback_policy_path()),
            allowed_models=allowed_models,
            context_capacity_overrides=context_capacity_overrides,
        )

    def select(
        self,
        features: TaskFeatures,
        *,
        previous_model: str | None,
        supports_routed_context: bool,
        allow_hidden: bool = False,
    ) -> ModelSelection:
        desired = self._desired_profile(features, supports_routed_context=supports_routed_context)
        filtered = self.filter.apply(features, allow_hidden=allow_hidden)
        eligible = list(filtered.eligible)
        rejected = dict(filtered.rejected)
        if not eligible:
            raise ModelPolicyError("no live model passed hard capability filters")

        scores = [
            self._score_candidate(
                candidate,
                features,
                desired_profile=desired,
                previous_model=previous_model,
            )
            for candidate in eligible
        ]
        scores.sort(key=lambda item: (-item.total, self.registry.get(item.model).ordinal))  # type: ignore[union-attr]
        by_model = {item.model: item for item in scores}
        eligible_by_model = {item.model.model: item for item in eligible}
        top = scores[0]
        selected_score = top
        switch_reason = "highest_explainable_score"
        previous = self.registry.get(previous_model) if previous_model else None
        previous_score = by_model.get(previous.model) if previous is not None else None
        top_eligible = eligible_by_model[top.model]

        explicit_match = self._explicit_matches(top_eligible, features.explicit_model_preference)
        if explicit_match:
            switch_reason = "explicit_live_model_preference"
        elif previous_model is not None and previous_score is None:
            switch_reason = "previous_model_failed_capability_filter"
        elif previous_score is not None and previous_score.model != top.model:
            previous_candidate = eligible_by_model[previous_score.model]
            required_strength = self._required_strength(desired)
            if (
                top_eligible.profile.strength > previous_candidate.profile.strength
                and required_strength > previous_candidate.profile.strength
            ):
                switch_reason = "escalated_for_required_capability_depth"
            else:
                margin_to_previous = round(top.total - previous_score.total, 2)
                if margin_to_previous < self.switch_threshold:
                    selected_score = previous_score
                    switch_reason = "retained_marginal_score_difference"
                else:
                    switch_reason = "material_score_margin"

        selected = eligible_by_model[selected_score.model]
        alternatives = [item for item in scores if item.model != selected_score.model]
        fallback_order = tuple(item.model for item in alternatives)
        runner_up = alternatives[0] if alternatives else None
        if previous_score is not None and previous_score.model != selected_score.model:
            score_margin = round(selected_score.total - previous_score.total, 2)
        elif runner_up is not None:
            score_margin = round(selected_score.total - runner_up.total, 2)
        else:
            score_margin = round(selected_score.total, 2)
        confidence_margin = abs(score_margin)
        selection_confidence = self._confidence(confidence_margin)
        switch_confidence = (
            "low"
            if switch_reason == "retained_marginal_score_difference"
            else self._confidence(confidence_margin)
        )
        fallback_used = selected.profile.name != desired and not self._explicit_matches(
            selected,
            features.explicit_model_preference,
        )
        explanation = explain_selection(
            selected_profile=selected.profile.name,
            features=features,
            switch_reason=switch_reason,
            fallback_used=fallback_used,
            migration_warning=selected.migration_warning,
        )
        requires_test_instruction = bool(
            selected.profile.name == "spark"
            and features.correctness_depends_on_tests
            and not features.explicit_test_requirement
        )
        if requires_test_instruction and not supports_routed_context:
            raise ModelPolicyError("Spark requires supported routed test context")

        return ModelSelection(
            selected=selected,
            desired_profile=desired,
            candidate_scores=tuple(scores),
            rejected_candidates=rejected,
            fallback_order=fallback_order,
            selection_confidence=selection_confidence,
            switch_confidence=switch_confidence,
            previous_model=previous.model if previous is not None else None,
            score_margin=score_margin,
            switch_reason=switch_reason,
            explanation=explanation,
            drift_warnings=filtered.drift_warnings,
            requires_test_instruction=requires_test_instruction,
        )

    def _desired_profile(self, features: TaskFeatures, *, supports_routed_context: bool) -> str:
        preference_profile = self.catalog.preference_profile(features.explicit_model_preference)
        if preference_profile is not None:
            if preference_profile == "legacy_terra":
                return "terra"
            if preference_profile == "legacy_luna":
                return "luna"
            return preference_profile
        if self._spark_eligible(features, supports_routed_context=supports_routed_context):
            return "spark"
        if (
            features.need_for_delegation
            and features.independent_workstreams in {"medium", "large"}
        ):
            if (
                features.architectural_depth == "high"
                or features.broad_refactor
                or features.context_size in {"large", "xlarge"}
                or features.ambiguity == "high"
            ):
                return "sol"
            return "terra"
        if (
            features.final_audit
            or features.deep_security
            or features.architectural_depth == "high"
            or features.mathematical_depth == "high"
            or features.hard_debugging
            or features.broad_refactor
            or features.research_depth == "high"
            or (
                features.task_domain == "incident_response"
                and features.context_size in {"large", "xlarge"}
            )
            or (
                features.ambiguity == "high"
                and (
                    features.quality_sensitivity in {"medium", "high"}
                    or features.context_size in {"large", "xlarge"}
                )
            )
            or (
                features.web_research_requirement
                and features.context_size in {"large", "xlarge"}
                and features.quality_sensitivity == "high"
            )
        ):
            return "sol"
        if (
            features.web_research_requirement
            or features.research_depth == "medium"
            or features.external_tool_workflow
        ):
            return "terra"
        simple_domains = {"email", "simple_text", "literary", "documentation"}
        simple_domain = bool(
            features.task_domain in simple_domains
            and (
                not features.coding
                or features.work_mode != "editing"
                or features.edit_size == "tiny"
            )
        )
        simple_code_analysis = bool(
            features.coding
            and features.work_mode == "analysis"
            and features.context_size in {"tiny", "small", "unknown"}
            and features.architectural_depth == "low"
            and features.ambiguity == "low"
        )
        small_deterministic_code = bool(
            features.coding
            and features.work_mode == "editing"
            and features.edit_size in {"tiny", "small"}
            and features.test_burden == "tiny"
            and features.architectural_depth == "low"
            and not features.web_research_requirement
        )
        if (
            (
                simple_domain
                or features.clear_transformation
                or features.simple_deterministic_task
                or simple_code_analysis
                or small_deterministic_code
            )
            and features.context_size not in {"large", "xlarge"}
            and features.ambiguity == "low"
            and features.quality_sensitivity != "high"
        ):
            return "luna"
        return "terra"

    @staticmethod
    def _spark_eligible(features: TaskFeatures, *, supports_routed_context: bool) -> bool:
        tests_supported = (
            not features.correctness_depends_on_tests
            or features.explicit_test_requirement
            or supports_routed_context
        )
        return bool(
            features.rapid_edit
            and features.coding
            and set(features.required_modalities) <= {"text"}
            and features.context_size in {"tiny", "small", "medium"}
            and features.edit_size in {"tiny", "small"}
            and features.architectural_depth == "low"
            and features.ambiguity == "low"
            and features.risk in {"low", "medium"}
            and not features.broad_refactor
            and features.expected_duration not in {"large", "xlarge"}
            and tests_supported
        )

    def _score_candidate(
        self,
        candidate: EligibleModel,
        features: TaskFeatures,
        *,
        desired_profile: str,
        previous_model: str | None,
    ) -> CandidateScore:
        profile = candidate.profile
        weights = self.scoring
        required_strength = self._required_strength(desired_profile)
        fallback_step = self.fallback.step(desired_profile, profile.name)
        task_fit = (
            weights["exact_task_fit"]
            if profile.name == desired_profile
            else weights["adjacent_task_fit"] if fallback_step == 1 else weights["adjacent_task_fit"] / 2
        )
        strength_delta = profile.strength - required_strength
        complexity_fit = max(-12.0, weights["complexity_exact"] - abs(strength_delta) * 8.0)
        required_context = _SIZE_RANK[features.context_size]
        capacity = _SIZE_RANK[candidate.context_capacity]
        context_fit = weights["context_fit"] - max(0, capacity - required_context) * 0.5
        if features.context_size == "unknown":
            context_fit = weights["context_fit"] / 2

        latency_fit = 0.0
        if features.latency_sensitivity == "high":
            latency_fit = (profile.latency - 1) * weights["latency_unit"]
        elif features.latency_sensitivity == "medium":
            latency_fit = (profile.latency - 1) * weights["latency_unit"] / 2
        quality_fit = 0.0
        if features.quality_sensitivity == "high":
            quality_fit = (profile.quality - 1) * weights["quality_unit"]
        elif features.quality_sensitivity == "medium":
            quality_fit = (profile.quality - 1) * weights["quality_unit"] / 2

        required_tools = {
            "tiny": 1,
            "small": 1,
            "medium": 2,
            "large": 3,
            "xlarge": 3,
            "unknown": 2,
        }[features.expected_tool_calls]
        tool_fit = weights["tool_fit"] if profile.tool_capacity >= required_tools else -weights["tool_fit"]
        continuity = (
            weights["continuity_bonus"]
            if previous_model in {candidate.model.id, candidate.model.model}
            else weights["switch_cost"]
        )
        preview_penalty = (
            weights["preview_penalty"]
            if profile.preview and desired_profile != "spark"
            else 0.0
        )
        migration_penalty = weights["migration_penalty"] if candidate.migration_warning else 0.0
        overqualification = max(0, strength_delta) * weights["overqualification_unit"]
        underqualification = max(0, -strength_delta) * weights["underqualification_unit"]
        preference = features.explicit_model_preference
        explicit_preference = (
            weights["explicit_preference_bonus"]
            if self._explicit_matches(candidate, preference)
            else weights["nonpreferred_explicit_penalty"] if preference is not None else 0.0
        )
        components = {
            "base": weights["base"],
            "capability_fit": weights["capability_fit"],
            "task_fit": task_fit,
            "complexity_fit": complexity_fit,
            "context_fit": context_fit,
            "latency_fit": latency_fit,
            "quality_fit": quality_fit,
            "tool_fit": tool_fit,
            "modality_fit": weights["modality_fit"],
            "availability_fit": weights["availability_fit"],
            "continuity_cost": continuity,
            "preview_model_penalty": preview_penalty,
            "migration_penalty": migration_penalty,
            "overqualification_penalty": overqualification,
            "underqualification_penalty": underqualification,
            "explicit_preference": explicit_preference,
            "fallback_fit": fallback_step * weights["fallback_step_penalty"],
        }
        rounded = {key: round(value, 2) for key, value in components.items()}
        return CandidateScore(
            model=candidate.model.model,
            profile=profile.name,
            components=rounded,
            total=round(sum(rounded.values()), 2),
            migration_warning=candidate.migration_warning,
        )

    def _explicit_matches(self, candidate: EligibleModel, preference: str | None) -> bool:
        if preference is None:
            return False
        preference_profile = self.catalog.preference_profile(preference)
        return preference in {candidate.model.id.lower(), candidate.model.model.lower()} or (
            preference_profile == candidate.profile.name
        )

    def _required_strength(self, desired_profile: str) -> int:
        profile = self.catalog.by_name.get(desired_profile)
        if profile is None:
            raise ModelPolicyError(f"unknown desired profile {desired_profile}")
        return profile.strength

    def _confidence(self, margin: float) -> str:
        if margin >= self.confidence_high:
            return "high"
        if margin >= self.confidence_medium:
            return "medium"
        return "low"

    @staticmethod
    def _number_map(value: object, field: str) -> dict[str, float]:
        if not isinstance(value, Mapping) or not value:
            raise ModelPolicyError(f"model selection {field} is malformed")
        result: dict[str, float] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key or isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ModelPolicyError(f"model selection {field} contains an invalid weight")
            result[key] = float(item)
        required = {
            "base",
            "capability_fit",
            "exact_task_fit",
            "adjacent_task_fit",
            "complexity_exact",
            "context_fit",
            "latency_unit",
            "quality_unit",
            "tool_fit",
            "modality_fit",
            "availability_fit",
            "continuity_bonus",
            "switch_cost",
            "preview_penalty",
            "migration_penalty",
            "overqualification_unit",
            "underqualification_unit",
            "explicit_preference_bonus",
            "nonpreferred_explicit_penalty",
            "fallback_step_penalty",
        }
        if not required.issubset(result):
            raise ModelPolicyError("model selection scoring weights are incomplete")
        return result


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelPolicyError(f"cannot load model policy {path.name}") from exc
