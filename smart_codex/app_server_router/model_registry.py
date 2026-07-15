"""Sanitized, process-local model registry built from App Server model/list."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Iterable


SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class RegistryError(RuntimeError):
    """Raised when live App Server capability metadata is malformed or empty."""


def _safe_token(value: object, field: str) -> str:
    if not isinstance(value, str) or SAFE_TOKEN.fullmatch(value) is None:
        raise RegistryError(f"model/list returned an invalid {field}")
    return value


def _safe_text(value: object, *, limit: int = 300) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


@dataclass(frozen=True)
class LiveModel:
    id: str
    model: str
    display_name: str
    description: str
    hidden: bool
    deprecated: bool
    upgrade_target: str | None
    supported_efforts: tuple[str, ...]
    default_effort: str
    input_modalities: tuple[str, ...]
    is_default: bool
    ordinal: int
    available: bool = True
    supports_personality: bool = False
    service_tiers: tuple[str, ...] = ()
    default_service_tier: str | None = None
    availability_notice: bool = False

    @property
    def routable(self) -> bool:
        return self.available and not self.hidden

    def supports(self, required_modalities: Iterable[str]) -> bool:
        supported = set(self.input_modalities)
        return all(item in supported for item in required_modalities)


@dataclass(frozen=True)
class RegistrySnapshot:
    retrieved_at: str
    codex_version: str
    models: tuple[LiveModel, ...]


class ModelRegistry:
    """Live capability metadata. No prompt or credential data is retained."""

    def __init__(
        self,
        models: Iterable[LiveModel],
        *,
        codex_version: str,
        temporarily_unavailable: Iterable[str] = (),
    ):
        ordered = tuple(models)
        if not ordered:
            raise RegistryError("model/list returned no models")
        lookup: dict[str, LiveModel] = {}
        for item in ordered:
            for key in {item.id, item.model}:
                existing = lookup.get(key)
                if existing is not None and existing is not item:
                    raise RegistryError("model/list returned ambiguous model identifiers")
                lookup[key] = item
        self._models = ordered
        self._lookup = lookup
        unavailable = set(temporarily_unavailable)
        if any(value not in lookup for value in unavailable):
            raise RegistryError("temporary availability overlay names an unknown model")
        self._temporarily_unavailable = unavailable
        self.retrieved_at = datetime.now(timezone.utc).isoformat()
        self.codex_version = _safe_text(codex_version, limit=80)

    @classmethod
    def from_model_list(
        cls,
        data: object,
        *,
        codex_version: str,
        temporarily_unavailable: Iterable[str] = (),
    ) -> "ModelRegistry":
        if not isinstance(data, list):
            raise RegistryError("model/list result.data must be an array")
        models: list[LiveModel] = []
        for ordinal, raw in enumerate(data):
            if not isinstance(raw, dict):
                raise RegistryError("model/list returned a non-object model")
            model_id = _safe_token(raw.get("id"), "model id")
            wire_model = _safe_token(raw.get("model"), "model slug")
            efforts_raw = raw.get("supportedReasoningEfforts")
            if not isinstance(efforts_raw, list) or not efforts_raw:
                raise RegistryError(f"model {model_id} advertises no reasoning efforts")
            efforts: list[str] = []
            for option in efforts_raw:
                if not isinstance(option, dict):
                    raise RegistryError(f"model {model_id} has malformed effort metadata")
                effort = _safe_token(option.get("reasoningEffort"), "reasoning effort")
                if effort not in efforts:
                    efforts.append(effort)
            default_effort = _safe_token(raw.get("defaultReasoningEffort"), "default effort")
            if default_effort not in efforts:
                raise RegistryError(f"model {model_id} default effort is unsupported")
            modalities_raw = raw.get("inputModalities")
            if not isinstance(modalities_raw, list) or not modalities_raw:
                raise RegistryError(f"model {model_id} advertises no input modalities")
            modalities = tuple(
                dict.fromkeys(_safe_token(value, "input modality") for value in modalities_raw)
            )
            upgrade = raw.get("upgrade")
            upgrade_info = raw.get("upgradeInfo")
            upgrade_target: str | None = None
            if isinstance(upgrade_info, dict) and upgrade_info.get("model") is not None:
                upgrade_target = _safe_token(upgrade_info.get("model"), "upgrade target")
            elif upgrade is not None:
                upgrade_target = _safe_token(upgrade, "upgrade target")
            hidden = raw.get("hidden")
            is_default = raw.get("isDefault")
            if not isinstance(hidden, bool) or not isinstance(is_default, bool):
                raise RegistryError(f"model {model_id} has malformed visibility metadata")
            supports_personality = raw.get("supportsPersonality", False)
            if not isinstance(supports_personality, bool):
                raise RegistryError(f"model {model_id} has malformed personality metadata")
            service_tiers_raw = raw.get("serviceTiers", [])
            if not isinstance(service_tiers_raw, list):
                raise RegistryError(f"model {model_id} has malformed service tier metadata")
            service_tiers: list[str] = []
            for tier in service_tiers_raw:
                if not isinstance(tier, dict):
                    raise RegistryError(f"model {model_id} has malformed service tier")
                tier_id = _safe_token(tier.get("id"), "service tier")
                if tier_id not in service_tiers:
                    service_tiers.append(tier_id)
            default_service_tier_raw = raw.get("defaultServiceTier")
            default_service_tier = (
                None
                if default_service_tier_raw is None
                else _safe_token(default_service_tier_raw, "default service tier")
            )
            if default_service_tier is not None and default_service_tier not in service_tiers:
                raise RegistryError(f"model {model_id} default service tier is unsupported")
            availability_notice = raw.get("availabilityNux") is not None
            if raw.get("availabilityNux") is not None and not isinstance(raw.get("availabilityNux"), dict):
                raise RegistryError(f"model {model_id} has malformed availability metadata")
            models.append(
                LiveModel(
                    id=model_id,
                    model=wire_model,
                    display_name=_safe_text(raw.get("displayName"), limit=120) or model_id,
                    description=_safe_text(raw.get("description")),
                    hidden=hidden,
                    deprecated=upgrade_target is not None,
                    upgrade_target=upgrade_target,
                    supported_efforts=tuple(efforts),
                    default_effort=default_effort,
                    input_modalities=modalities,
                    is_default=is_default,
                    ordinal=ordinal,
                    supports_personality=supports_personality,
                    service_tiers=tuple(service_tiers),
                    default_service_tier=default_service_tier,
                    availability_notice=availability_notice,
                )
            )
        return cls(
            models,
            codex_version=codex_version,
            temporarily_unavailable=temporarily_unavailable,
        )

    def get(self, model_id_or_slug: str) -> LiveModel | None:
        return self._lookup.get(model_id_or_slug)

    def all(self) -> tuple[LiveModel, ...]:
        return self._models

    def mark_temporarily_unavailable(self, model_id_or_slug: str) -> None:
        model = self.get(model_id_or_slug)
        if model is None:
            raise RegistryError("cannot mark an unknown model unavailable")
        self._temporarily_unavailable.update({model.id, model.model})

    def clear_temporarily_unavailable(self, model_id_or_slug: str) -> None:
        model = self.get(model_id_or_slug)
        if model is None:
            raise RegistryError("cannot clear availability for an unknown model")
        self._temporarily_unavailable.discard(model.id)
        self._temporarily_unavailable.discard(model.model)

    def is_available(self, model: LiveModel) -> bool:
        return (
            model.available
            and model.id not in self._temporarily_unavailable
            and model.model not in self._temporarily_unavailable
        )

    def is_routable(self, model: LiveModel) -> bool:
        return self.is_available(model) and not model.hidden

    def compatible(self, required_modalities: Iterable[str]) -> list[LiveModel]:
        return [
            item
            for item in self._models
            if self.is_routable(item) and item.supports(required_modalities)
        ]

    def snapshot(self) -> RegistrySnapshot:
        return RegistrySnapshot(
            retrieved_at=self.retrieved_at,
            codex_version=self.codex_version,
            models=self._models,
        )
