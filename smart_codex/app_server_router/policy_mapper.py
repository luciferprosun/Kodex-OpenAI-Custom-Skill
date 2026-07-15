"""Map Router Core output onto live App Server model and policy capabilities."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable

from .model_registry import LiveModel, ModelRegistry


class PolicyError(RuntimeError):
    """Raised when declarative routing policy cannot produce a safe route."""


@dataclass(frozen=True)
class RuntimeRequirements:
    allowed_sandbox_modes: tuple[str, ...] | None
    allowed_approval_policies: tuple[object, ...] | None

    @classmethod
    def from_response(cls, response: object) -> "RuntimeRequirements":
        if not isinstance(response, dict):
            raise PolicyError("configRequirements/read returned a malformed result")
        requirements = response.get("requirements")
        if requirements is None:
            return cls(None, None)
        if not isinstance(requirements, dict):
            raise PolicyError("configRequirements/read requirements must be an object or null")
        sandboxes = requirements.get("allowedSandboxModes")
        approvals = requirements.get("allowedApprovalPolicies")
        if sandboxes is not None and not isinstance(sandboxes, list):
            raise PolicyError("managed sandbox requirements are malformed")
        if approvals is not None and not isinstance(approvals, list):
            raise PolicyError("managed approval requirements are malformed")
        return cls(
            None if sandboxes is None else tuple(sandboxes),
            None if approvals is None else tuple(approvals),
        )

    def allows_sandbox(self, value: str) -> bool:
        return self.allowed_sandbox_modes is None or value in self.allowed_sandbox_modes

    def allows_approval(self, value: object) -> bool:
        return self.allowed_approval_policies is None or value in self.allowed_approval_policies


@dataclass(frozen=True)
class AppliedPolicy:
    route_class: str
    model: LiveModel
    effort: str
    sandbox_mode: str
    sandbox_policy: dict[str, object]
    approval_policy: object
    reasons: tuple[str, ...]


def _default_policy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "rules" / "app_server_model_policy.json"


def _string_list(
    value: object,
    field: str,
    *,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise PolicyError(f"App Server policy {field} must be a non-empty list")
    if not all(isinstance(item, str) and item for item in value):
        raise PolicyError(f"App Server policy {field} contains an invalid value")
    if len(set(value)) != len(value):
        raise PolicyError(f"App Server policy {field} contains duplicates")
    return value


def _load_policy(path: Path | None = None) -> dict[str, Any]:
    target = path or _default_policy_path()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolicyError(f"cannot load App Server model policy: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyError("App Server model policy must be an object")
    required = {
        "effort_ladder",
        "model_classes",
        "fallback_classes",
        "category_classes",
        "effort_by_category",
        "rapid_edit_signals",
        "deep_research_signals",
        "delegation_signals",
        "deterministic_eval_signals",
        "local_policy",
    }
    if not required.issubset(value):
        raise PolicyError("App Server model policy is missing required fields")

    efforts = _string_list(value["effort_ladder"], "effort_ladder")
    if not {"low", "medium"}.issubset(efforts):
        raise PolicyError("App Server policy effort_ladder is missing safe defaults")

    model_classes = value["model_classes"]
    if not isinstance(model_classes, dict) or not model_classes:
        raise PolicyError("App Server policy model_classes is malformed")
    for name, config in model_classes.items():
        if not isinstance(name, str) or not name or not isinstance(config, dict):
            raise PolicyError("App Server policy model class is malformed")
        _string_list(
            config.get("preferred_ids"),
            f"model_classes.{name}.preferred_ids",
            allow_empty=True,
        )
        _string_list(
            config.get("patterns"),
            f"model_classes.{name}.patterns",
            allow_empty=True,
        )
    if not {"spark", "luna", "terra", "sol"}.issubset(model_classes):
        raise PolicyError("App Server policy is missing a required capability class")

    fallback_classes = value["fallback_classes"]
    if not isinstance(fallback_classes, dict):
        raise PolicyError("App Server policy fallback_classes is malformed")
    for name, class_order in fallback_classes.items():
        if name not in model_classes:
            raise PolicyError("App Server policy has an unknown fallback source class")
        classes = _string_list(class_order, f"fallback_classes.{name}")
        if any(item not in model_classes for item in classes):
            raise PolicyError("App Server policy has an unknown fallback target class")
    if any(name not in fallback_classes for name in model_classes):
        raise PolicyError("App Server policy is missing a capability fallback")

    category_classes = value["category_classes"]
    if not isinstance(category_classes, dict) or any(
        not isinstance(category, str)
        or not isinstance(capability_class, str)
        or capability_class not in model_classes
        for category, capability_class in category_classes.items()
    ):
        raise PolicyError("App Server policy category_classes is malformed")

    category_efforts = value["effort_by_category"]
    if not isinstance(category_efforts, dict) or any(
        not isinstance(category, str)
        or not isinstance(effort, str)
        or effort not in efforts
        for category, effort in category_efforts.items()
    ):
        raise PolicyError("App Server policy effort_by_category is malformed")

    for signal_field in (
        "rapid_edit_signals",
        "deep_research_signals",
        "delegation_signals",
        "deterministic_eval_signals",
    ):
        for pattern in _string_list(value[signal_field], signal_field, allow_empty=True):
            try:
                re.compile(pattern, flags=re.IGNORECASE)
            except re.error as exc:
                raise PolicyError(f"invalid policy signal: {exc}") from exc

    local = value.get("local_policy")
    if not isinstance(local, dict):
        raise PolicyError("App Server local policy is malformed")
    sandboxes = _string_list(
        local.get("allowed_sandbox_modes"),
        "local_policy.allowed_sandbox_modes",
    )
    approvals = _string_list(
        local.get("allowed_approval_policies"),
        "local_policy.allowed_approval_policies",
    )
    if not set(sandboxes) <= {"read-only", "workspace-write"}:
        raise PolicyError("App Server local policy contains a forbidden sandbox mode")
    if not set(approvals) <= {"on-request", "untrusted"}:
        raise PolicyError("App Server local policy contains a forbidden approval policy")
    if "on-request" not in approvals:
        raise PolicyError("App Server local policy must retain human approval")
    return value


def _matches_any(prompt: str, patterns: object) -> bool:
    if not isinstance(patterns, list):
        raise PolicyError("policy signal list is malformed")
    for pattern in patterns:
        if not isinstance(pattern, str):
            raise PolicyError("policy signal must be a string")
        try:
            if re.search(pattern, prompt, flags=re.IGNORECASE):
                return True
        except re.error as exc:
            raise PolicyError(f"invalid policy signal: {exc}") from exc
    return False


class PolicyMapper:
    def __init__(
        self,
        registry: ModelRegistry,
        requirements: RuntimeRequirements,
        *,
        policy_path: Path | None = None,
    ):
        self.registry = registry
        self.requirements = requirements
        self.policy = _load_policy(policy_path)

    def apply(
        self,
        decision: object,
        prompt: str,
        *,
        required_modalities: Iterable[str],
    ) -> AppliedPolicy:
        category = str(getattr(decision, "category", "unknown"))
        complexity = str(getattr(decision, "complexity_level", "medium"))
        risk = str(getattr(decision, "risk_level", "low"))
        action_danger = str(getattr(decision, "action_danger", "read_only_analysis"))
        context = str(getattr(decision, "context_requirement", "unknown"))

        route_class = self.policy["category_classes"].get(category, "terra")
        reasons = [f"Router Core category {category} maps to {route_class}"]

        rapid = _matches_any(prompt, self.policy["rapid_edit_signals"])
        spark_safe = (
            rapid
            and complexity in {"low", "medium"}
            and risk in {"low", "medium"}
            and context in {"small", "medium"}
            and action_danger
            not in {
                "secret_touching_operation",
                "destructive_operation",
                "database_operation",
                "deployment_operation",
            }
            and set(required_modalities) <= {"text"}
        )
        if spark_safe:
            route_class = "spark"
            reasons.append("small targeted rapid edit is eligible for Spark")
        elif category in {"research", "grant_work"} and (
            complexity == "high"
            or _matches_any(prompt, self.policy["deep_research_signals"])
        ):
            route_class = "sol"
            reasons.append("research depth requires the frontier capability class")

        model, selection_reason = self._select_model(
            route_class,
            tuple(required_modalities),
        )
        reasons.append(selection_reason)

        desired_effort = self.policy["effort_by_category"].get(category, "medium")
        if route_class == "spark":
            desired_effort = "low"
        delegation = _matches_any(prompt, self.policy["delegation_signals"])
        deterministic_eval = _matches_any(
            prompt,
            self.policy["deterministic_eval_signals"],
        )
        if (
            delegation
            and not deterministic_eval
            and category
            in {
                "architecture",
                "complex_coding",
                "security_audit",
                "research",
                "incident_response",
            }
            and "ultra" in model.supported_efforts
        ):
            desired_effort = "ultra"
            reasons.append("explicit delegation benefits this complex task")
        elif delegation and deterministic_eval:
            reasons.append("delegation suppressed for deterministic evaluation")

        effort = self._nearest_effort(model, desired_effort)
        if effort != desired_effort:
            reasons.append(
                f"unsupported effort {desired_effort} resolved to nearest live effort {effort}"
            )

        sandbox_mode = self._resolve_sandbox(str(getattr(decision, "sandbox_mode", "read-only")))
        approval = self._resolve_approval(getattr(decision, "approval_policy", "on-request"))
        sandbox_policy = self._wire_sandbox(sandbox_mode)
        return AppliedPolicy(
            route_class=route_class,
            model=model,
            effort=effort,
            sandbox_mode=sandbox_mode,
            sandbox_policy=sandbox_policy,
            approval_policy=approval,
            reasons=tuple(reasons),
        )

    def _select_model(
        self,
        desired_class: str,
        required_modalities: tuple[str, ...],
    ) -> tuple[LiveModel, str]:
        compatible = self.registry.compatible(required_modalities)
        if not compatible:
            raise PolicyError("no visible live model supports the turn input modalities")
        class_order = self.policy["fallback_classes"].get(desired_class)
        if not isinstance(class_order, list) or not class_order:
            raise PolicyError(f"no fallback classes configured for {desired_class}")
        for capability_class in class_order:
            candidates = [
                item
                for item in compatible
                if self._matches_class(item, str(capability_class))
            ]
            if not candidates:
                continue
            candidates.sort(key=lambda item: self._candidate_key(item, str(capability_class)))
            selected = candidates[0]
            if selected.deprecated and selected.upgrade_target:
                replacement = self.registry.get(selected.upgrade_target)
                if (
                    replacement is not None
                    and replacement.routable
                    and replacement.supports(required_modalities)
                ):
                    return replacement, (
                        f"live upgrade target {replacement.model} replaces deprecated "
                        f"candidate {selected.model}"
                    )
            fallback = "" if capability_class == desired_class else f" fallback class {capability_class}"
            return selected, f"selected live{fallback} model {selected.model}"

        compatible.sort(key=lambda item: (item.deprecated, not item.is_default, item.ordinal))
        selected = compatible[0]
        return selected, f"selected generic live fallback model {selected.model}"

    def _matches_class(self, model: LiveModel, capability_class: str) -> bool:
        if "spark" in model.model.lower() and capability_class != "spark":
            return False
        config = self.policy["model_classes"].get(capability_class)
        if not isinstance(config, dict):
            raise PolicyError(f"unknown capability class {capability_class}")
        preferred = config.get("preferred_ids", [])
        if model.model in preferred or model.id in preferred:
            return True
        haystack = " ".join(
            [model.id, model.model, model.display_name, model.description]
        ).lower()
        patterns = config.get("patterns", [])
        return any(
            isinstance(pattern, str) and pattern.lower() in haystack
            for pattern in patterns
        )

    def _candidate_key(self, model: LiveModel, capability_class: str) -> tuple[object, ...]:
        config = self.policy["model_classes"][capability_class]
        preferred = config.get("preferred_ids", [])
        try:
            preference = preferred.index(model.model)
        except ValueError:
            preference = len(preferred) + model.ordinal
        return (model.deprecated, preference, not model.is_default, model.ordinal)

    def _nearest_effort(self, model: LiveModel, desired: str) -> str:
        ladder = self.policy["effort_ladder"]
        if desired in model.supported_efforts:
            return desired
        if desired not in ladder:
            return model.default_effort
        desired_index = ladder.index(desired)
        ranked = [
            (abs(ladder.index(item) - desired_index), ladder.index(item), item)
            for item in model.supported_efforts
            if item in ladder
        ]
        if not ranked:
            return model.default_effort
        return min(ranked)[2]

    def _resolve_sandbox(self, requested: str) -> str:
        allowed_local = self.policy["local_policy"]["allowed_sandbox_modes"]
        if requested not in allowed_local:
            raise PolicyError("Router Core requested a locally forbidden sandbox mode")
        if self.requirements.allows_sandbox(requested):
            return requested
        if requested == "workspace-write" and self.requirements.allows_sandbox("read-only"):
            return "read-only"
        raise PolicyError("managed requirements do not allow a safe sandbox policy")

    def _resolve_approval(self, requested: object) -> object:
        allowed_local = self.policy["local_policy"]["allowed_approval_policies"]
        if requested not in allowed_local:
            raise PolicyError("Router Core requested a locally forbidden approval policy")
        if self.requirements.allows_approval(requested):
            return requested
        if self.requirements.allows_approval("untrusted") and "untrusted" in allowed_local:
            return "untrusted"
        raise PolicyError("managed requirements do not allow a safe approval policy")

    @staticmethod
    def _wire_sandbox(mode: str) -> dict[str, object]:
        if mode == "read-only":
            return {"type": "readOnly", "networkAccess": False}
        if mode == "workspace-write":
            return {
                "type": "workspaceWrite",
                "writableRoots": [],
                "networkAccess": False,
                "excludeTmpdirEnvVar": False,
                "excludeSlashTmp": False,
            }
        raise PolicyError("unsupported safe sandbox mode")
