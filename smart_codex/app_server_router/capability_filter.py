"""Hard live-capability filtering before any model-quality scoring."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping

from .model_registry import LiveModel, ModelRegistry
from .prompt_features import SIZE_CLASSES, TaskFeatures


class CapabilityPolicyError(RuntimeError):
    """Raised when declarative capability profiles are malformed."""


_CONTEXT_RANK = {
    "unknown": 0,
    "tiny": 1,
    "small": 2,
    "medium": 3,
    "large": 4,
    "xlarge": 5,
}


@dataclass(frozen=True)
class ModelProfile:
    name: str
    exact_models: tuple[str, ...]
    family_patterns: tuple[str, ...]
    strength: int
    context_capacity: str
    latency: int
    quality: int
    tool_capacity: int
    coding_only: bool
    preview: bool
    expected_modalities: tuple[str, ...]
    expected_efforts: tuple[str, ...]


class ProfileCatalog:
    def __init__(self, profiles: Iterable[ModelProfile]):
        values = tuple(profiles)
        if not values:
            raise CapabilityPolicyError("model capability policy has no profiles")
        self.profiles = values
        self.by_name = {profile.name: profile for profile in values}
        if len(self.by_name) != len(values):
            raise CapabilityPolicyError("model capability policy has duplicate profiles")
        exact: dict[str, ModelProfile] = {}
        for profile in values:
            for model in profile.exact_models:
                if model in exact:
                    raise CapabilityPolicyError("model capability policy has duplicate exact models")
                exact[model] = profile
            for pattern in profile.family_patterns:
                try:
                    re.compile(pattern, flags=re.IGNORECASE)
                except re.error as exc:
                    raise CapabilityPolicyError("model capability policy has invalid pattern") from exc
        self._exact = exact

    @classmethod
    def from_policy(cls, value: object) -> "ProfileCatalog":
        if not isinstance(value, dict) or not value:
            raise CapabilityPolicyError("model selection profiles are malformed")
        profiles: list[ModelProfile] = []
        for name, raw in value.items():
            if not isinstance(name, str) or not name or not isinstance(raw, dict):
                raise CapabilityPolicyError("model selection profile is malformed")
            exact = _strings(raw.get("exact_models"), f"profiles.{name}.exact_models")
            patterns = _strings(raw.get("family_patterns"), f"profiles.{name}.family_patterns")
            context = raw.get("context_capacity")
            if context not in SIZE_CLASSES or context == "unknown":
                raise CapabilityPolicyError("model profile has invalid context capacity")
            numeric = {}
            for field in ("strength", "latency", "quality", "tool_capacity"):
                item = raw.get(field)
                if isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 3:
                    raise CapabilityPolicyError(f"model profile has invalid {field}")
                numeric[field] = item
            coding_only = raw.get("coding_only")
            preview = raw.get("preview")
            if not isinstance(coding_only, bool) or not isinstance(preview, bool):
                raise CapabilityPolicyError("model profile flags are malformed")
            profiles.append(
                ModelProfile(
                    name=name,
                    exact_models=exact,
                    family_patterns=patterns,
                    strength=numeric["strength"],
                    context_capacity=str(context),
                    latency=numeric["latency"],
                    quality=numeric["quality"],
                    tool_capacity=numeric["tool_capacity"],
                    coding_only=coding_only,
                    preview=preview,
                    expected_modalities=_strings(
                        raw.get("expected_modalities"),
                        f"profiles.{name}.expected_modalities",
                        allow_empty=False,
                    ),
                    expected_efforts=_strings(
                        raw.get("expected_efforts"),
                        f"profiles.{name}.expected_efforts",
                        allow_empty=False,
                    ),
                )
            )
        return cls(profiles)

    def resolve(self, model: LiveModel) -> ModelProfile | None:
        for key in (model.model, model.id):
            exact = self._exact.get(key)
            if exact is not None:
                return exact
        haystack = f"{model.model} {model.id}"
        matches = [
            profile
            for profile in self.profiles
            if any(
                re.search(pattern, haystack, flags=re.IGNORECASE) is not None
                for pattern in profile.family_patterns
            )
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def is_exact(model: LiveModel, profile: ModelProfile) -> bool:
        return bool({model.model, model.id} & set(profile.exact_models))

    def preference_profile(self, preference: str | None) -> str | None:
        if preference is None:
            return None
        normalized = preference.lower()
        aliases = {
            "sol": "sol",
            "terra": "terra",
            "luna": "luna",
            "spark": "spark",
        }
        if normalized in aliases:
            return aliases[normalized]
        profile = self._exact.get(normalized)
        return profile.name if profile is not None else None


def _strings(value: object, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise CapabilityPolicyError(f"{field} must be a list")
    if not all(isinstance(item, str) and item for item in value):
        raise CapabilityPolicyError(f"{field} contains an invalid value")
    if len(set(value)) != len(value):
        raise CapabilityPolicyError(f"{field} contains duplicates")
    return tuple(value)


@dataclass(frozen=True)
class EligibleModel:
    model: LiveModel
    profile: ModelProfile
    context_capacity: str
    migration_target: str | None
    migration_warning: str | None


@dataclass(frozen=True)
class FilterResult:
    eligible: tuple[EligibleModel, ...]
    rejected: dict[str, tuple[str, ...]]
    drift_warnings: tuple[str, ...]


class CapabilityFilter:
    def __init__(
        self,
        registry: ModelRegistry,
        catalog: ProfileCatalog,
        *,
        legacy_targets: Mapping[str, str],
        legacy_profiles: Iterable[str],
        allowed_models: Iterable[str] | None = None,
        context_capacity_overrides: Mapping[str, str] | None = None,
    ):
        self.registry = registry
        self.catalog = catalog
        self.legacy_targets = dict(legacy_targets)
        self.legacy_profiles = frozenset(legacy_profiles)
        self.allowed_models = None if allowed_models is None else frozenset(allowed_models)
        self.context_capacity_overrides = dict(context_capacity_overrides or {})
        if any(value not in SIZE_CLASSES or value == "unknown" for value in self.context_capacity_overrides.values()):
            raise CapabilityPolicyError("context capacity override is malformed")

    def apply(
        self,
        features: TaskFeatures,
        *,
        allow_hidden: bool = False,
    ) -> FilterResult:
        eligible: list[EligibleModel] = []
        rejected: dict[str, tuple[str, ...]] = {}
        warnings: list[str] = []
        live_identifiers = {value for model in self.registry.all() for value in (model.id, model.model)}
        preference = features.explicit_model_preference
        preference_profile = self.catalog.preference_profile(preference)
        if preference is not None and preference not in live_identifiers and preference_profile is None:
            rejected[preference] = ("absent_from_live_registry",)

        for model in self.registry.all():
            reasons: list[str] = []
            profile = self.catalog.resolve(model)
            exact_profile = profile is not None and self.catalog.is_exact(model, profile)
            if profile is None:
                reasons.append("unknown_capability_profile")
                warnings.append(f"unknown_model_capabilities:{model.model}")
            elif not exact_profile:
                warnings.append(f"family_model_conservative_profile:{model.model}")
                if (
                    set(model.input_modalities) != set(profile.expected_modalities)
                    or set(model.supported_efforts) != set(profile.expected_efforts)
                ):
                    reasons.append("insufficient_future_model_capability_match")
            if not self.registry.is_available(model):
                reasons.append("temporarily_unavailable")
            if model.hidden and not allow_hidden:
                reasons.append("hidden_model")
                warnings.append(f"visibility_drift:{model.model}")
            if self.allowed_models is not None and model.model not in self.allowed_models and model.id not in self.allowed_models:
                reasons.append("forbidden_by_workspace_policy")
            if not model.supports(features.required_modalities):
                reasons.append("unsupported_input_modality")
            if profile is not None and profile.coding_only and not features.coding:
                reasons.append("coding_only_model")
            if profile is not None and profile.name == "spark":
                if features.risk not in {"low", "medium"}:
                    reasons.append("spark_risk_out_of_scope")
                if features.broad_refactor or features.architectural_depth == "high":
                    reasons.append("spark_edit_surface_out_of_scope")
                if features.ambiguity == "high" or features.expected_duration in {"large", "xlarge"}:
                    reasons.append("spark_duration_or_ambiguity_out_of_scope")

            context_capacity = (
                self.context_capacity_overrides.get(model.model)
                or (
                    profile.context_capacity
                    if profile is not None and exact_profile
                    else "small" if profile is not None else "unknown"
                )
            )
            if model.model in self.context_capacity_overrides:
                warnings.append(f"context_capacity_drift:{model.model}")
            if (
                profile is not None
                and features.context_size != "unknown"
                and _CONTEXT_RANK[context_capacity] < _CONTEXT_RANK[features.context_size]
            ):
                reasons.append("context_requirement_exceeds_verified_capacity")

            if features.explicit_effort_preference is not None and (
                features.explicit_effort_preference not in model.supported_efforts
            ):
                reasons.append("explicit_effort_unsupported")

            # Live model/list is authoritative.  The declarative legacy map
            # documents the expected migration relationship, but it must not
            # invent an upgrade for an installed App Server that did not
            # advertise one.
            migration_target = model.upgrade_target
            expected_legacy_target = self.legacy_targets.get(model.model)
            if (
                migration_target is not None
                and expected_legacy_target is not None
                and migration_target != expected_legacy_target
            ):
                warnings.append(f"migration_target_drift:{model.model}")
            explicit_match = self._preference_matches(model, profile, preference, preference_profile)
            verified_gap = self._verified_capability_gap(
                model,
                profile,
                migration_target,
                features,
                context_capacity,
            )
            migration_warning: str | None = None
            if migration_target is not None:
                warnings.append(f"upgrade_target_observed:{model.model}")
            if (
                profile is not None
                and profile.name in self.legacy_profiles
                and migration_target is not None
            ):
                if explicit_match:
                    migration_warning = "legacy_model_selected_for_explicit_compatibility"
                elif not verified_gap:
                    reasons.append("legacy_model_has_migration_target")
            elif model.deprecated and not explicit_match and not verified_gap:
                reasons.append("model_has_live_upgrade_target")

            if profile is not None:
                if set(model.input_modalities) != set(profile.expected_modalities):
                    warnings.append(f"modality_drift:{model.model}")
                if tuple(model.supported_efforts) != tuple(profile.expected_efforts):
                    warnings.append(f"effort_drift:{model.model}")

            if reasons:
                rejected[model.model] = tuple(dict.fromkeys(reasons))
                continue
            assert profile is not None
            eligible.append(
                EligibleModel(
                    model=model,
                    profile=profile,
                    context_capacity=context_capacity,
                    migration_target=migration_target,
                    migration_warning=migration_warning,
                )
            )

        return FilterResult(
            eligible=tuple(eligible),
            rejected=rejected,
            drift_warnings=tuple(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _preference_matches(
        model: LiveModel,
        profile: ModelProfile | None,
        preference: str | None,
        preference_profile: str | None,
    ) -> bool:
        if preference is None:
            return False
        return preference in {model.id.lower(), model.model.lower()} or (
            profile is not None and preference_profile == profile.name
        )

    def _verified_capability_gap(
        self,
        legacy: LiveModel,
        profile: ModelProfile | None,
        target_name: str | None,
        features: TaskFeatures,
        legacy_context: str,
    ) -> bool:
        if target_name is None or profile is None:
            return False
        target = self.registry.get(target_name)
        if target is None or not self.registry.is_routable(target):
            return False
        target_profile = self.catalog.resolve(target)
        if target_profile is None:
            return False
        if not target.supports(features.required_modalities) and legacy.supports(features.required_modalities):
            return True
        target_context = self.context_capacity_overrides.get(target.model, target_profile.context_capacity)
        return (
            features.context_size != "unknown"
            and _CONTEXT_RANK[target_context] < _CONTEXT_RANK[features.context_size]
            <= _CONTEXT_RANK[legacy_context]
        )
