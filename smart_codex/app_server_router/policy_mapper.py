"""Map Router Core output onto live App Server model and policy capabilities."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from smart_codex.policy_version import MODEL_POLICY_VERSION

from .model_registry import LiveModel, ModelRegistry
from .effort_policy import EffortPolicy, EffortPolicyError, EffortSelection
from .model_policy import (
    CandidateScore,
    ModelPolicy,
    ModelPolicyError,
    ModelSelection,
    default_fallback_policy_path,
    default_selection_policy_path,
)
from .orchestration_policy import (
    OrchestrationDecision,
    OrchestrationPolicy,
    OrchestrationPolicyError,
    UltraApprovalEvidence,
    UltraProposal,
    analyze_orchestration_structure,
)
from .prompt_features import TaskFeatures, extract_task_features


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
    candidate_scores: tuple[CandidateScore, ...] = ()
    rejected_candidates: dict[str, tuple[str, ...]] | None = None
    fallback_order: tuple[str, ...] = ()
    selection_confidence: str = "unknown"
    switch_confidence: str = "unknown"
    previous_model: str | None = None
    score_margin: float = 0.0
    switch_reason: str = "unknown"
    selection_explanation: str = "capability_aware_live_selection"
    selection_summary: str = ""
    drift_warnings: tuple[str, ...] = ()
    migration_warning: str | None = None
    test_instruction: str | None = None
    ordinary_reasoning_effort: str = "low"
    orchestration_mode: str = "single_agent"
    ultra_recommendation: str = "not_recommended"
    ultra_approval: str = "not_requested"
    planned_worker_count: int = 0
    workstream_count: str = "0"
    controlled_workstream_categories: tuple[str, ...] = ()
    dependency_shape: str = "unknown"
    parallel_benefit: str = "none"
    shared_state_risk: str = "unknown"
    orchestration_work_mode: str = "read_heavy"
    write_isolation: str = "not_applicable"
    orchestration_resource_class: str = "ordinary"
    ultra_human_approval_required: bool = False
    maximum_delegation_depth: int = 1
    recursive_delegation_allowed: bool = False
    orchestration_reason_codes: tuple[str, ...] = ()
    orchestration_fallback_reason_code: str | None = None
    ultra_proposal: UltraProposal | None = None


SPARK_TEST_INSTRUCTION = (
    "Smart Router requirement: run the smallest relevant test and report its "
    "result before treating this targeted code edit as complete."
)


def _default_policy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "rules" / "app_server_model_policy.json"


def _default_effort_policy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "rules" / "reasoning_effort_policy.json"


def _default_orchestration_policy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "rules" / "orchestration_policy.json"


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


def _load_json_policy(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolicyError(f"cannot load dynamic policy {path.name}") from exc


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
        selection_policy_path: Path | None = None,
        effort_policy_path: Path | None = None,
        orchestration_policy_path: Path | None = None,
        fallback_policy_path: Path | None = None,
        allowed_models: tuple[str, ...] | None = None,
        context_capacity_overrides: Mapping[str, str] | None = None,
    ):
        self.registry = registry
        self.requirements = requirements
        self.policy = _load_policy(policy_path)
        self.model_policy = ModelPolicy.from_paths(
            registry,
            selection_path=selection_policy_path or default_selection_policy_path(),
            fallback_path=fallback_policy_path or default_fallback_policy_path(),
            allowed_models=allowed_models,
            context_capacity_overrides=context_capacity_overrides,
        )
        self.effort_policy = EffortPolicy(
            _load_json_policy(effort_policy_path or _default_effort_policy_path())
        )
        self.orchestration_policy = OrchestrationPolicy(
            _load_json_policy(
                orchestration_policy_path or _default_orchestration_policy_path()
            )
        )
        if self.orchestration_policy.policy_version != MODEL_POLICY_VERSION:
            raise PolicyError("orchestration policy provenance does not match current policy")

    def apply(
        self,
        decision: object,
        prompt: str,
        *,
        required_modalities: Iterable[str],
        previous_model: str | None = None,
        supports_routed_context: bool = False,
        task_signature: str | None = None,
        effective_turn_context_schema_version: str | None = None,
        effective_turn_context_hash: str | None = None,
        policy_version: str = "unknown",
        ultra_approval: UltraApprovalEvidence | None = None,
        now_epoch_seconds: int | None = None,
    ) -> AppliedPolicy:
        category = str(getattr(decision, "category", "unknown"))
        features: TaskFeatures = extract_task_features(
            prompt,
            decision,
            required_modalities=required_modalities,
        )
        try:
            selection: ModelSelection = self.model_policy.select(
                features,
                previous_model=previous_model,
                supports_routed_context=supports_routed_context,
            )
            orchestration_analysis = analyze_orchestration_structure(prompt, features)
            orchestration_assessment = self.orchestration_policy.assess(
                selection.selected.model,
                selection.selected.profile,
                features,
                orchestration_analysis,
            )
            effort_selection: EffortSelection = self.effort_policy.select(
                selection.selected.model,
                selection.selected.profile,
                features,
                force_max=orchestration_assessment.force_max_single_agent,
                force_max_reason=(
                    orchestration_assessment.fallback_reason_code
                    or "ultra_candidate_max_single_agent"
                ),
            )
        except (ModelPolicyError, EffortPolicyError, OrchestrationPolicyError) as exc:
            raise PolicyError("dynamic model policy could not produce a safe live route") from exc

        route_class = selection.selected.profile.name
        model = selection.selected.model
        sandbox_mode = self._resolve_sandbox(str(getattr(decision, "sandbox_mode", "read-only")))
        approval = self._resolve_approval(getattr(decision, "approval_policy", "on-request"))
        try:
            orchestration: OrchestrationDecision = self.orchestration_policy.decide(
                analysis=orchestration_analysis,
                assessment=orchestration_assessment,
                ordinary_reasoning_effort=effort_selection.selected,
                selected_model=model.model,
                task_signature=task_signature,
                effective_turn_context_schema_version=(
                    effective_turn_context_schema_version
                ),
                effective_turn_context_hash=effective_turn_context_hash,
                policy_version=policy_version,
                sandbox_mode=sandbox_mode,
                approval_policy=approval,
                approval_evidence=ultra_approval,
                now_epoch_seconds=now_epoch_seconds,
            )
        except OrchestrationPolicyError as exc:
            raise PolicyError("orchestration policy could not produce a safe route") from exc
        effort = orchestration.wire_reasoning_effort
        reasons = [
            f"Router Core category {category} is evaluated independently from authority",
            selection.explanation.summary,
            f"model switch reason {selection.switch_reason}",
            f"reasoning effort reason {effort_selection.reason_code}",
        ]
        if effort_selection.selected != effort_selection.desired:
            reasons.append(
                f"unsupported effort {effort_selection.desired} resolved to nearest live effort {effort_selection.selected}"
            )
        reasons.append(f"orchestration mode {orchestration.orchestration_mode}")
        reasons.extend(
            f"orchestration reason {reason}"
            for reason in orchestration.reason_codes
        )
        if orchestration.fallback_reason_code is not None:
            reasons.append(
                f"orchestration fallback {orchestration.fallback_reason_code}"
            )
        if selection.selected.migration_warning is not None:
            reasons.append(selection.selected.migration_warning)
        if any(
            "upgrade_target" in reason
            for values in selection.rejected_candidates.values()
            for reason in values
        ):
            reasons.append("live upgrade target replaces a deprecated candidate")
        reasons.extend(f"capability drift {warning}" for warning in selection.drift_warnings)

        sandbox_policy = self._wire_sandbox(sandbox_mode)
        return AppliedPolicy(
            route_class=route_class,
            model=model,
            effort=effort,
            sandbox_mode=sandbox_mode,
            sandbox_policy=sandbox_policy,
            approval_policy=approval,
            reasons=tuple(reasons),
            candidate_scores=selection.candidate_scores,
            rejected_candidates=selection.rejected_candidates,
            fallback_order=selection.fallback_order,
            selection_confidence=selection.selection_confidence,
            switch_confidence=selection.switch_confidence,
            previous_model=selection.previous_model,
            score_margin=selection.score_margin,
            switch_reason=selection.switch_reason,
            selection_explanation=selection.explanation.code,
            selection_summary=selection.explanation.summary,
            drift_warnings=selection.drift_warnings,
            migration_warning=selection.selected.migration_warning,
            test_instruction=(
                SPARK_TEST_INSTRUCTION if selection.requires_test_instruction else None
            ),
            ordinary_reasoning_effort=orchestration.ordinary_reasoning_effort,
            orchestration_mode=orchestration.orchestration_mode,
            ultra_recommendation=orchestration.ultra_recommendation,
            ultra_approval=orchestration.ultra_approval,
            planned_worker_count=orchestration.planned_worker_count,
            workstream_count=orchestration.workstream_count,
            controlled_workstream_categories=(
                orchestration.controlled_workstream_categories
            ),
            dependency_shape=orchestration.dependency_shape,
            parallel_benefit=orchestration.parallel_benefit,
            shared_state_risk=orchestration.shared_state_risk,
            orchestration_work_mode=orchestration.work_mode,
            write_isolation=orchestration.write_isolation,
            orchestration_resource_class=orchestration.resource_class,
            ultra_human_approval_required=orchestration.human_approval_required,
            maximum_delegation_depth=orchestration.max_delegation_depth,
            recursive_delegation_allowed=orchestration.recursive_delegation_allowed,
            orchestration_reason_codes=orchestration.reason_codes,
            orchestration_fallback_reason_code=orchestration.fallback_reason_code,
            ultra_proposal=orchestration.proposal,
        )

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
