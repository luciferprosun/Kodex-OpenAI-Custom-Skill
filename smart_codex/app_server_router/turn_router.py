"""Safe turn/start extraction, Router Core classification, and field rewriting."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

from smart_codex.router import RoutingDecision, route_prompt

from .model_policy import CandidateScore
from .orchestration_policy import (
    EFFECTIVE_TURN_CONTEXT_SCHEMA_VERSION,
    UltraApprovalEvidence,
    UltraProposal,
)
from .policy_mapper import AppliedPolicy, PolicyError, PolicyMapper


class RoutingFailure(RuntimeError):
    """Sanitized failure raised instead of forwarding an unclassified turn."""


@dataclass(frozen=True)
class EffectiveTurnContext:
    """Immutable, privacy-preserving approval binding for one routed turn."""

    schema_version: str
    canonical_bytes: bytes
    context_hash: str


@dataclass(frozen=True)
class RoutedTurn:
    message: dict[str, Any]
    prompt_hash: str
    category: str
    route_class: str
    original_model: str | None
    selected_model: str
    effort: str
    sandbox_mode: str
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
    drift_warnings: tuple[str, ...] = ()
    migration_warning: str | None = None
    task_difficulty: str = "unknown"
    task_scope: str = "unknown"
    task_risk: str = "unknown"
    action_danger: str = "unknown"
    verification_available: bool | None = None
    task_subdomain: str | None = None
    semantic_reason_codes: tuple[str, ...] = ()
    policy_version: str | None = None
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


def _safe_original_model(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 128:
        return None
    if not all(character.isalnum() or character in "._-" for character in value):
        return None
    return value


def _validate_effective_turn_value(value: object, active: set[int]) -> None:
    """Accept only deterministic JSON values and reject cycles fail closed."""

    if value is None or type(value) in {bool, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise RoutingFailure("effective turn context contains a non-finite number")
        return
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise RoutingFailure("effective turn context contains invalid text") from exc
        return
    if type(value) not in {dict, list}:
        raise RoutingFailure("effective turn context contains an unsupported value")

    identity = id(value)
    if identity in active:
        raise RoutingFailure("effective turn context contains a cycle")
    active.add(identity)
    try:
        if type(value) is dict:
            for key, item in value.items():
                if type(key) is not str:
                    raise RoutingFailure(
                        "effective turn context contains a non-string mapping key"
                    )
                _validate_effective_turn_value(key, active)
                _validate_effective_turn_value(item, active)
        else:
            for item in value:
                _validate_effective_turn_value(item, active)
    finally:
        active.remove(identity)


def canonical_effective_turn_context(
    message: object,
    *,
    previous_model: str | None = None,
) -> bytes:
    """Serialize every incoming execution-relevant turn value canonically.

    The complete original ``turn/start`` message is bound, including ordered
    inputs and every field the transparent proxy forwards. Session model state
    is included separately because it can affect model selection without being
    present in the request. Router-derived output fields are bound separately
    by the Ultra proposal decision signature.
    """

    if type(message) is not dict:
        raise RoutingFailure("effective turn context request is malformed")
    if previous_model is not None and type(previous_model) is not str:
        raise RoutingFailure("effective turn context previous model is malformed")
    payload = {
        "schema_version": EFFECTIVE_TURN_CONTEXT_SCHEMA_VERSION,
        "turn_start_request": message,
        "session_state": {"previous_model": previous_model},
    }
    _validate_effective_turn_value(payload, set())
    try:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return canonical.encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise RoutingFailure("effective turn context cannot be canonicalized") from exc


def effective_turn_context_hash(
    message: object,
    *,
    previous_model: str | None = None,
) -> str:
    """Return the SHA-256 binding without exposing turn contents."""

    canonical = canonical_effective_turn_context(
        message,
        previous_model=previous_model,
    )
    return hashlib.sha256(canonical).hexdigest()


def _effective_turn_context(
    message: object,
    *,
    previous_model: str | None = None,
) -> EffectiveTurnContext:
    canonical = canonical_effective_turn_context(
        message,
        previous_model=previous_model,
    )
    return EffectiveTurnContext(
        schema_version=EFFECTIVE_TURN_CONTEXT_SCHEMA_VERSION,
        canonical_bytes=canonical,
        context_hash=hashlib.sha256(canonical).hexdigest(),
    )


def _apply_collaboration_mode_overrides(
    params: dict[str, Any],
    *,
    model: str,
    effort: str,
    test_instruction: str | None,
) -> None:
    """Align precedence-bearing TUI settings with top-level overrides.

    The installed experimental schema says ``collaborationMode`` takes
    precedence over the top-level model and effort fields. The stock remote
    TUI supplies this object, so leaving its nested settings untouched would
    make an otherwise valid turn/start rewrite inert. Do not add the
    experimental field to clients that omitted it and do not alter the mode or
    developer instructions.
    """

    if "collaborationMode" not in params or params["collaborationMode"] is None:
        return
    collaboration_mode = params["collaborationMode"]
    if not isinstance(collaboration_mode, dict):
        raise RoutingFailure("turn/start collaboration mode is malformed")
    settings = collaboration_mode.get("settings")
    if not isinstance(settings, dict):
        raise RoutingFailure("turn/start collaboration settings are malformed")
    settings["model"] = model
    settings["reasoning_effort"] = effort
    if test_instruction is not None:
        existing = settings.get("developer_instructions")
        if existing is not None and not isinstance(existing, str):
            raise RoutingFailure("turn/start developer instructions are malformed")
        if not existing:
            settings["developer_instructions"] = test_instruction
        elif test_instruction not in existing:
            settings["developer_instructions"] = f"{existing.rstrip()}\n\n{test_instruction}"


def _has_supported_routed_context(params: object) -> bool:
    if not isinstance(params, dict):
        return False
    if "collaborationMode" not in params or params.get("collaborationMode") is None:
        return False
    collaboration_mode = params.get("collaborationMode")
    if not isinstance(collaboration_mode, dict) or not isinstance(
        collaboration_mode.get("settings"),
        dict,
    ):
        raise RoutingFailure("turn/start collaboration mode is malformed")
    return True


def extract_turn_input(params: object) -> tuple[str, tuple[str, ...]]:
    if not isinstance(params, dict):
        raise RoutingFailure("turn/start params are malformed")
    thread_id = params.get("threadId")
    inputs = params.get("input")
    if not isinstance(thread_id, str) or not thread_id:
        raise RoutingFailure("turn/start thread id is missing")
    if not isinstance(inputs, list) or not inputs:
        raise RoutingFailure("turn/start input is missing")

    texts: list[str] = []
    modalities: list[str] = []
    for item in inputs:
        if not isinstance(item, dict):
            raise RoutingFailure("turn/start contains a malformed input item")
        item_type = item.get("type")
        if item_type == "text":
            text = item.get("text")
            if not isinstance(text, str):
                raise RoutingFailure("turn/start contains malformed text input")
            if text.strip():
                texts.append(text)
            if "text" not in modalities:
                modalities.append("text")
        elif item_type in {"image", "localImage"}:
            if "image" not in modalities:
                modalities.append("image")
        elif item_type in {"skill", "mention"}:
            continue
        else:
            raise RoutingFailure("turn/start contains an unsupported input type")
    if not texts:
        raise RoutingFailure("turn/start contains no routable user text")
    if "text" not in modalities:
        modalities.insert(0, "text")
    return "\n\n".join(texts), tuple(modalities)


class TurnRouter:
    def __init__(self, mapper: PolicyMapper):
        self.mapper = mapper

    def route_message(
        self,
        message: object,
        *,
        previous_model: str | None = None,
        ultra_approval: UltraApprovalEvidence | None = None,
        now_epoch_seconds: int | None = None,
    ) -> RoutedTurn:
        if not isinstance(message, dict) or message.get("method") != "turn/start":
            raise RoutingFailure("only turn/start can be routed")
        request_id = message.get("id")
        if isinstance(request_id, bool) or not isinstance(request_id, (str, int)):
            raise RoutingFailure("turn/start request id is malformed")
        raw_params = message.get("params")
        prompt, modalities = extract_turn_input(raw_params)
        if not isinstance(raw_params, dict):
            raise RoutingFailure("turn/start params are malformed")
        supports_routed_context = _has_supported_routed_context(raw_params)
        params_for_previous = raw_params if isinstance(raw_params, dict) else {}
        original_for_policy = _safe_original_model(params_for_previous.get("model"))
        if original_for_policy is not None and self.mapper.registry.get(original_for_policy) is None:
            original_for_policy = None
        effective_previous = previous_model or original_for_policy
        effective_context = _effective_turn_context(
            message,
            previous_model=previous_model,
        )
        try:
            decision: RoutingDecision = route_prompt(prompt, dry_run=True)
            applied: AppliedPolicy = self.mapper.apply(
                decision,
                prompt,
                required_modalities=modalities,
                previous_model=effective_previous,
                supports_routed_context=supports_routed_context,
                task_signature=decision.prompt_hash,
                effective_turn_context_schema_version=effective_context.schema_version,
                effective_turn_context_hash=effective_context.context_hash,
                policy_version=decision.policy_version or "unknown",
                ultra_approval=ultra_approval,
                now_epoch_seconds=now_epoch_seconds,
            )
        except (PolicyError, ValueError, RuntimeError) as exc:
            raise RoutingFailure("turn/start could not be classified safely") from exc

        routed = deepcopy(message)
        params = routed["params"]
        if params.get("permissions") is not None:
            raise RoutingFailure(
                "turn/start named permissions cannot be combined with routed sandbox policy"
            )
        original_model = _safe_original_model(params.get("model"))
        if original_model is not None and self.mapper.registry.get(original_model) is None:
            original_model = None
        sandbox_mode = applied.sandbox_mode
        sandbox_policy = deepcopy(applied.sandbox_policy)
        original_sandbox = params.get("sandboxPolicy")
        if (
            applied.sandbox_mode == "workspace-write"
            and isinstance(original_sandbox, dict)
            and original_sandbox.get("type") == "readOnly"
            and self.mapper.requirements.allows_sandbox("read-only")
        ):
            sandbox_mode = "read-only"
            sandbox_policy = {"type": "readOnly", "networkAccess": False}

        approval_policy = deepcopy(applied.approval_policy)
        original_approval = params.get("approvalPolicy")
        if (
            applied.approval_policy == "on-request"
            and original_approval == "untrusted"
            and self.mapper.requirements.allows_approval("untrusted")
        ):
            approval_policy = "untrusted"

        params["model"] = applied.model.model
        params["effort"] = applied.effort
        params["sandboxPolicy"] = sandbox_policy
        params["approvalPolicy"] = approval_policy
        params["approvalsReviewer"] = "user"
        _apply_collaboration_mode_overrides(
            params,
            model=applied.model.model,
            effort=applied.effort,
            test_instruction=applied.test_instruction,
        )

        return RoutedTurn(
            message=routed,
            prompt_hash=decision.prompt_hash,
            category=decision.category,
            route_class=applied.route_class,
            original_model=original_model,
            selected_model=applied.model.model,
            effort=applied.effort,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            reasons=applied.reasons,
            candidate_scores=applied.candidate_scores,
            rejected_candidates=applied.rejected_candidates,
            fallback_order=applied.fallback_order,
            selection_confidence=applied.selection_confidence,
            switch_confidence=applied.switch_confidence,
            previous_model=applied.previous_model,
            score_margin=applied.score_margin,
            switch_reason=applied.switch_reason,
            selection_explanation=applied.selection_explanation,
            drift_warnings=applied.drift_warnings,
            migration_warning=applied.migration_warning,
            task_difficulty=decision.complexity_level,
            task_scope=decision.execution_scope,
            task_risk=decision.risk_level,
            action_danger=decision.action_danger,
            task_subdomain=decision.task_subdomain,
            semantic_reason_codes=tuple(decision.semantic_reason_codes),
            policy_version=decision.policy_version,
            verification_available=None,
            ordinary_reasoning_effort=applied.ordinary_reasoning_effort,
            orchestration_mode=applied.orchestration_mode,
            ultra_recommendation=applied.ultra_recommendation,
            ultra_approval=applied.ultra_approval,
            planned_worker_count=applied.planned_worker_count,
            workstream_count=applied.workstream_count,
            controlled_workstream_categories=(
                applied.controlled_workstream_categories
            ),
            dependency_shape=applied.dependency_shape,
            parallel_benefit=applied.parallel_benefit,
            shared_state_risk=applied.shared_state_risk,
            orchestration_work_mode=applied.orchestration_work_mode,
            write_isolation=applied.write_isolation,
            orchestration_resource_class=applied.orchestration_resource_class,
            ultra_human_approval_required=applied.ultra_human_approval_required,
            maximum_delegation_depth=applied.maximum_delegation_depth,
            recursive_delegation_allowed=applied.recursive_delegation_allowed,
            orchestration_reason_codes=applied.orchestration_reason_codes,
            orchestration_fallback_reason_code=(
                applied.orchestration_fallback_reason_code
            ),
            ultra_proposal=applied.ultra_proposal,
        )
