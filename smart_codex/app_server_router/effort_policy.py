"""Independent, live-supported reasoning-effort selection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .capability_filter import ModelProfile
from .model_registry import LiveModel
from .prompt_features import TaskFeatures


class EffortPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class EffortSelection:
    desired: str
    selected: str
    reason_code: str


class EffortPolicy:
    def __init__(self, policy: object):
        if not isinstance(policy, dict):
            raise EffortPolicyError("reasoning effort policy must be an object")
        self.ladder = _string_tuple(policy.get("ladder"), "ladder")
        if not {"low", "medium", "high", "xhigh", "max"}.issubset(self.ladder):
            raise EffortPolicyError("reasoning effort ladder is incomplete")
        if "ultra" in self.ladder:
            raise EffortPolicyError("Ultra must not be an ordinary reasoning-effort rung")
        self.profile_default = _string_map(policy.get("profile_default"), "profile_default")
        self.profile_ceiling = _string_map(
            policy.get("profile_default_ceiling"),
            "profile_default_ceiling",
        )
        self.category_baseline = _string_map(
            policy.get("category_baseline"),
            "category_baseline",
        )
        for value in (
            *self.profile_default.values(),
            *self.profile_ceiling.values(),
            *self.category_baseline.values(),
        ):
            if value not in self.ladder:
                raise EffortPolicyError("reasoning effort policy references an unknown effort")

    def select(
        self,
        model: LiveModel,
        profile: ModelProfile,
        features: TaskFeatures,
        *,
        force_max: bool = False,
        force_max_reason: str | None = None,
    ) -> EffortSelection:
        explicit = features.explicit_effort_preference
        if force_max:
            desired = "max"
            reason = force_max_reason or "orchestration_max_single_agent_fallback"
        elif explicit is not None and explicit in model.ordinary_supported_efforts:
            return EffortSelection(explicit, explicit, "explicit_supported_effort")
        else:
            desired, reason = self._recommended(features)
        ceiling = self.profile_ceiling.get(profile.name)
        if ceiling is None:
            raise EffortPolicyError(f"no effort ceiling for profile {profile.name}")
        if self._index(desired) > self._index(ceiling):
            desired = ceiling
            reason = "profile_default_ceiling"
        selected = self._nearest_supported(model, desired)
        if selected != desired:
            reason = "nearest_live_supported_effort"
        return EffortSelection(desired, selected, reason)

    def _recommended(self, features: TaskFeatures) -> tuple[str, str]:
        if features.final_audit:
            return "max", "final_audit"
        if features.research_depth == "high":
            return "xhigh", "broad_strategic_research"
        if features.mathematical_depth == "high":
            if features.quality_sensitivity == "high" or features.context_size in {"large", "xlarge"}:
                return "max", "difficult_mathematical_reasoning"
            return "xhigh", "deep_mathematical_reasoning"
        if features.hard_debugging and features.ambiguity == "high" and features.context_size in {"large", "xlarge"}:
            return "max", "hardest_bounded_debugging"
        if (
            features.architectural_depth == "high"
            or features.broad_refactor
            or features.hard_debugging
            or features.deep_security
            or (
                features.task_domain == "incident_response"
                and features.context_size in {"large", "xlarge"}
            )
            or (
                features.ambiguity == "high"
                and features.context_size in {"large", "xlarge"}
            )
            or (features.ambiguity == "high" and features.quality_sensitivity == "high")
        ):
            return "xhigh", "deep_multi_step_reasoning"
        if (
            features.likely_files in {"medium", "large", "xlarge"}
            or features.test_burden in {"medium", "large"}
            or features.research_depth == "medium"
            or (features.web_research_requirement and features.source_verification_requirement)
            or features.expected_tool_calls == "large"
            or features.task_domain == "complex_coding"
            or features.quality_sensitivity == "high"
        ):
            return "high", "substantial_judgment"
        if features.external_tool_workflow:
            return "medium", "ordinary_external_tool_workflow"
        if features.clear_transformation:
            return "low", "direct_transformation"
        if features.rapid_edit and features.test_burden == "tiny":
            return "low", "rapid_low_ambiguity_edit"
        if (
            features.coding
            or features.web_research_requirement
            or features.test_burden == "small"
            or features.expected_tool_calls in {"small", "medium"}
            or features.quality_sensitivity == "medium"
        ):
            return "medium", "everyday_professional_work"
        baseline = self.category_baseline.get(features.task_domain, "low")
        if baseline in {"high", "xhigh", "max"}:
            baseline = "medium"
        return baseline, "direct_low_ambiguity_work"

    def _nearest_supported(self, model: LiveModel, desired: str) -> str:
        if desired in model.ordinary_supported_efforts:
            return desired
        desired_index = self._index(desired)
        ranked = [
            (abs(self._index(value) - desired_index), self._index(value), value)
            for value in model.ordinary_supported_efforts
            if value in self.ladder
        ]
        if not ranked:
            if model.default_effort not in model.ordinary_supported_efforts:
                raise EffortPolicyError("live model default effort is unsupported")
            return model.default_effort
        return min(ranked)[2]

    def _index(self, effort: str) -> int:
        try:
            return self.ladder.index(effort)
        except ValueError as exc:
            raise EffortPolicyError(f"unknown reasoning effort {effort}") from exc


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise EffortPolicyError(f"reasoning effort {field} is malformed")
    if len(set(value)) != len(value):
        raise EffortPolicyError(f"reasoning effort {field} has duplicates")
    return tuple(value)


def _string_map(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) and key and isinstance(item, str) and item
        for key, item in value.items()
    ):
        raise EffortPolicyError(f"reasoning effort {field} is malformed")
    return dict(value)
