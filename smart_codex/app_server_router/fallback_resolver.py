"""Declarative capability-class fallback ordering."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class FallbackPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class FallbackResolver:
    class_order: dict[str, tuple[str, ...]]
    legacy_targets: dict[str, str]
    legacy_profiles: tuple[str, ...]
    hidden_use_default: bool

    @classmethod
    def from_policy(cls, value: object) -> "FallbackResolver":
        if not isinstance(value, dict):
            raise FallbackPolicyError("model fallback policy must be an object")
        order_raw = value.get("class_order")
        legacy_raw = value.get("legacy_models")
        legacy_profiles_raw = value.get("legacy_profiles")
        hidden = value.get("hidden_use_default")
        if not isinstance(order_raw, dict) or not order_raw:
            raise FallbackPolicyError("model fallback class order is malformed")
        order: dict[str, tuple[str, ...]] = {}
        for name, sequence in order_raw.items():
            if not isinstance(name, str) or not isinstance(sequence, list) or not sequence:
                raise FallbackPolicyError("model fallback class is malformed")
            if not all(isinstance(item, str) and item for item in sequence):
                raise FallbackPolicyError("model fallback sequence is malformed")
            if len(set(sequence)) != len(sequence):
                raise FallbackPolicyError("model fallback sequence has duplicates")
            order[name] = tuple(sequence)
        if not isinstance(legacy_raw, dict) or not all(
            isinstance(source, str)
            and source
            and isinstance(target, str)
            and target
            for source, target in legacy_raw.items()
        ):
            raise FallbackPolicyError("legacy model migration map is malformed")
        if not isinstance(legacy_profiles_raw, list) or not all(
            isinstance(item, str) and item for item in legacy_profiles_raw
        ):
            raise FallbackPolicyError("legacy profile list is malformed")
        if not isinstance(hidden, bool):
            raise FallbackPolicyError("hidden model default is malformed")
        return cls(
            class_order=order,
            legacy_targets=dict(legacy_raw),
            legacy_profiles=tuple(legacy_profiles_raw),
            hidden_use_default=hidden,
        )

    def order_for(self, desired_profile: str) -> tuple[str, ...]:
        order = self.class_order.get(desired_profile)
        if order is None:
            raise FallbackPolicyError(f"no fallback order for profile {desired_profile}")
        return order

    def step(self, desired_profile: str, candidate_profile: str) -> int:
        order = self.order_for(desired_profile)
        try:
            return order.index(candidate_profile)
        except ValueError:
            return len(order) + 1

    def validate_profiles(self, profiles: Mapping[str, object]) -> None:
        known = set(profiles)
        for source, sequence in self.class_order.items():
            if source not in known:
                raise FallbackPolicyError("fallback source references an unknown profile")
            if any(item not in known for item in sequence):
                raise FallbackPolicyError("fallback sequence references an unknown profile")
        if any(item not in known for item in self.legacy_profiles):
            raise FallbackPolicyError("legacy profile references an unknown profile")
