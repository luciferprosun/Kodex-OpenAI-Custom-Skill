"""Conservative Ultra admission, approval, and wire-translation policy.

Ordinary reasoning effort and orchestration are deliberately separate here.
The installed protocol currently encodes approved Ultra orchestration as the
``ultra`` reasoning-effort wire value, but that encoding never makes Ultra an
ordinary effort rung inside Smart Router.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import time
from typing import Mapping

from smart_codex.preprocessor import analyze_prompt_semantics

from .capability_filter import ModelProfile
from .model_registry import LiveModel
from .prompt_features import TaskFeatures


ORDINARY_REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")
ORCHESTRATION_MODES = ("single_agent", "ultra_subagents")
ULTRA_RECOMMENDATIONS = ("not_recommended", "recommended")
ULTRA_APPROVAL_STATES = ("not_requested", "pending", "approved", "denied", "invalid")
DEPENDENCY_SHAPES = ("unknown", "indivisible", "sequential", "mixed", "parallel")
PARALLEL_BENEFITS = ("none", "limited", "material")
SHARED_STATE_RISKS = ("unknown", "low", "medium", "high")
ORCHESTRATION_WORK_MODES = ("read_heavy", "write_heavy", "mixed")
WRITE_ISOLATION_STATES = ("not_applicable", "unproven", "proven_disjoint")
WORKSTREAM_COUNTS = ("0", "1", "2", "3", "4_plus")
EFFECTIVE_TURN_CONTEXT_SCHEMA_VERSION = "effective-turn-context-v1"
ULTRA_DECISION_SIGNATURE_VERSION = "ultra-decision-signature-v2"
ULTRA_APPROVAL_EVIDENCE_SCHEMA_VERSION = "ultra-approval-evidence-v2"

_HEX_64 = re.compile(r"^[a-f0-9]{64}$")


class OrchestrationPolicyError(RuntimeError):
    """Raised when the bounded policy cannot be validated or applied safely."""


@dataclass(frozen=True)
class UltraApprovalEvidence:
    """Short-lived approval supplied only by a future trusted human interface."""

    schema_version: str
    decision_signature_version: str
    decision_signature: str
    effective_turn_context_schema_version: str
    effective_turn_context_hash: str
    status: str
    policy_version: str
    issued_at_epoch_seconds: int
    expires_at_epoch_seconds: int


@dataclass(frozen=True)
class OrchestrationAnalysis:
    workstream_count: str
    dependency_shape: str
    parallel_benefit: str
    shared_state_risk: str
    work_mode: str
    write_isolation: str
    controlled_workstream_categories: tuple[str, ...]
    benefit_reason_codes: tuple[str, ...]
    expected_duration: str
    distinct_objectives: bool
    independent_start: bool
    bounded_results: bool
    coordinator_present: bool
    cost_minimizing: bool
    explicit_ultra_request: bool
    delegation_request: bool
    orchestration_veto_codes: tuple[str, ...]
    recursive_delegation_requested: bool
    peer_to_peer_requested: bool
    worker_history_authority_requested: bool
    workers_cannot_merge: bool
    workers_cannot_push: bool
    workers_cannot_rewrite_history: bool
    worker_git_instruction_conflict: bool
    plan_id: str

    @property
    def numeric_workstream_count(self) -> int:
        return {"0": 0, "1": 1, "2": 2, "3": 3, "4_plus": 4}[self.workstream_count]


@dataclass(frozen=True)
class OrchestrationAssessment:
    recommendation: str
    planned_worker_count: int
    reason_codes: tuple[str, ...]
    veto_codes: tuple[str, ...]
    fallback_reason_code: str | None
    force_max_single_agent: bool
    resource_class: str


@dataclass(frozen=True)
class UltraProposal:
    decision_signature_version: str
    decision_signature: str
    effective_turn_context_schema_version: str
    effective_turn_context_hash: str
    selected_model: str
    fallback_model: str
    ordinary_reasoning_effort: str
    fallback_reasoning_effort: str
    planned_worker_count: int
    controlled_workstream_categories: tuple[str, ...]
    plan_id: str
    policy_version: str
    sandbox_mode: str
    approval_policy: str
    resource_class: str


@dataclass(frozen=True)
class OrchestrationDecision:
    ordinary_reasoning_effort: str
    wire_reasoning_effort: str
    orchestration_mode: str
    ultra_recommendation: str
    ultra_approval: str
    planned_worker_count: int
    workstream_count: str
    controlled_workstream_categories: tuple[str, ...]
    dependency_shape: str
    parallel_benefit: str
    shared_state_risk: str
    work_mode: str
    write_isolation: str
    resource_class: str
    human_approval_required: bool
    max_delegation_depth: int
    recursive_delegation_allowed: bool
    reason_codes: tuple[str, ...]
    fallback_reason_code: str | None
    proposal: UltraProposal | None


@dataclass(frozen=True)
class _WorkerGitPolicy:
    cannot_merge: bool
    cannot_push: bool
    cannot_rewrite_history: bool
    instruction_conflict: bool
    authority_requested: bool


_WORKSTREAM_CATEGORY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("api_capabilities", (r"\bapi capabilit", r"\bapi surface")),
    ("security_review", (r"\bsecurity\b", r"\bthreat", r"\bvulnerabilit")),
    ("pricing_review", (r"\bpricing\b", r"\bcost structure")),
    ("deployment_constraints", (r"\bdeployment constraint", r"\bdeployability")),
    ("test_review", (r"\bmissing tests?\b", r"\btest(?:ing)? audit", r"\btest coverage")),
    ("compatibility_review", (r"\bbackward compat", r"\bcompatibility")),
    ("maintainability_review", (r"\bmaintainability\b", r"\bcode quality")),
    ("performance_review", (r"\bperformance\b", r"\bprofiling\b")),
    ("corpus_partition", (r"\bcorpus\b", r"\bindependent collections?\b")),
    ("log_analysis", (r"\blogs?\b", r"\btest[- ]result analysis")),
    ("repository_exploration", (r"\bcodebase exploration\b", r"\brepository scanning\b")),
    ("implementation", (r"\bimplement(?:ation|ing)?\b", r"\bcode modification")),
)

_COUNT_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "several": 3,
    "multiple": 2,
}


def analyze_orchestration_structure(
    prompt: str,
    features: TaskFeatures,
) -> OrchestrationAnalysis:
    """Extract bounded structural facts without retaining task text or paths."""

    semantics = analyze_prompt_semantics(prompt)
    text = semantics.actionable_text.casefold()
    raw_policy_text = prompt.casefold()

    categories = tuple(
        code
        for code, patterns in _WORKSTREAM_CATEGORY_PATTERNS
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
    )
    count = _substantive_workstream_count(text, len(categories))
    workstream_count = _bounded_count(count)

    explicit_ultra_request = _matches(
        text,
        (
            r"\b(?:use|enable|select|choose|run(?:\s+with)?|route(?:\s+this)?\s+to)\s+ultra\b",
            r"\b(?:reasoning\s+)?effort\s*(?:=|:|to|at)?\s*ultra\b",
        ),
    )
    delegation_request = _matches(
        text,
        (
            r"\bdelegat(?:e|ed|es|ing|ion)\b",
            r"\bspawn\b.*\b(?:agents?|workers?)\b",
            r"\buse\b.*\b(?:sub[- ]?agents?|multiple agents)\b",
            r"\bone agent per\b",
            r"\buse\s+(?:two|three|four|[2-4])\s+agents?\b",
        ),
    )
    orchestration_veto_codes = _orchestration_veto_codes(
        raw_policy_text,
        explicit_ultra_request=explicit_ultra_request,
        delegation_request=delegation_request,
    )
    if orchestration_veto_codes:
        explicit_ultra_request = False
        delegation_request = False

    indivisible = _matches(
        text,
        (
            r"\b(?:single|one) root cause\b",
            r"\bsmallest correct repair\b.*\broot cause\b",
            r"\b(?:one|single) (?:mathematical )?(?:proof|theorem|derivation)\b",
            r"\bcontinuous logical (?:proof|derivation|argument)\b",
            r"\bindivisible\b",
        ),
    )
    sequential = _matches(
        text,
        (
            r"\binspect\b.*\bthen\b.*\bdesign\b.*\bthen\b.*\bimplement\b",
            r"\bfrom (?:those|the) findings\b.*\bimplement\b",
            r"\bthen implement\b.*\bthen (?:run|execute)\b.*\btests?\b",
            r"\bstrict(?:ly)? sequential\b",
            r"\bmust finish before\b",
        ),
    )
    independent_language = _matches(
        text,
        (
            r"\bindependent\s+(?:areas?|workstreams?|collections?|packages?|modules?|reviews?|analyses?)\b",
            r"\bseparately\b.*\b(?:security|tests?|compatibility|maintainability|performance)\b",
            r"\bdivided into\b.*\bindependent collections?\b",
            r"\bparallel\s+(?:workstreams?|reviews?|analyses?)\b",
            r"\bdisjoint\s+(?:modules?|packages?|workstreams?)\b",
        ),
    )
    if count >= 2 and independent_language and not categories:
        categories = ("independent_general_workstreams",)
    distinct_objectives = count >= 2 and (len(categories) >= 2 or independent_language)
    independent_start = distinct_objectives and independent_language and not sequential
    if indivisible:
        dependency_shape = "indivisible"
    elif sequential and independent_language:
        dependency_shape = "mixed"
    elif sequential:
        dependency_shape = "sequential"
    elif independent_start:
        dependency_shape = "parallel"
    else:
        dependency_shape = "unknown"

    bounded_results = _matches(
        text,
        (
            r"\b(?:one|a) (?:evidence )?packet per\b",
            r"\bbounded (?:result|finding|summary)",
            r"\breturn\b.*\b(?:findings?|summary|packet|report)\b.*\b(?:per|from each)\b",
            r"\bcombine (?:the )?(?:findings|results|outputs) (?:at|in) the end\b",
            r"\b(?:at most|exactly)\s+\d+\s+(?:findings?|items?|points?)\b",
        ),
    )
    coordinator_present = _matches(
        text,
        (
            r"\bcentral(?:ized)? coordinator\b",
            r"\bone coordinator\b",
            r"\bcoordinator\b.*\b(?:synthesi[sz]e|validate|integrat|combine)\b",
            r"\bcombine (?:the )?(?:findings|results|outputs) (?:at|in) the end\b",
            r"\breturn\b.*\b(?:packet|findings?|summary|report)\b.*\b(?:per|from each)\b",
        ),
    )

    write_signal = features.work_mode == "editing" or _matches(
        text,
        (r"\b(?:edit|modify|implement|patch|refactor|write code|change code)\b",),
    )
    read_signal = features.work_mode == "analysis" or _matches(
        text,
        (r"\b(?:audit|review|research|inspect|analy[sz]e|explore|scan)\b",),
    )
    if write_signal and read_signal:
        work_mode = "mixed"
    elif write_signal:
        work_mode = "write_heavy"
    else:
        work_mode = "read_heavy"

    same_state = _matches(
        text,
        (
            r"\b(?:same|one)\s+(?:file|module|branch)\b.*\b(?:simultaneously|at the same time|in parallel)\b",
            r"\b(?:same|one)\b[^;\n]{0,50}\b(?:file|module|branch)\b[^;\n]{0,50}\b(?:simultaneously|at the same time|in parallel)\b",
            r"\boverlapping (?:files?|write scopes?|modules?)\b",
            r"\bshared mutable state\b",
            r"\bsame complete evolving context\b",
            r"\bconstant peer[- ]to[- ]peer communication\b",
        ),
    )
    coordinator_owns_integration = _matches(
        text,
        (
            r"\bcoordinator owns (?:the )?final integration\b",
            r"\bone central coordinator\b.*\bfinal integration\b",
        ),
    )
    disjoint_scope = _matches(
        text,
        (
            r"\bdisjoint (?:file|module|package|write) (?:scope|ownership|modules?|packages?)\b",
            r"\b(?:files?|modules?) do not overlap\b",
            r"\bnon[- ]overlapping (?:files?|modules?|write scopes?)\b",
        ),
    )
    isolated_execution = _matches(
        text,
        (r"\b(?:isolated|separate) worktrees?\b", r"\bequivalent safe separation\b"),
    )
    bounded_write_scope = _matches(
        text,
        (r"\bexplicit bounded write scope\b", r"\bbounded (?:file|module) ownership\b"),
    )
    worker_git_policy = _analyze_worker_git_policy(raw_policy_text)
    all_worker_git_restrictions = (
        worker_git_policy.cannot_merge
        and worker_git_policy.cannot_push
        and worker_git_policy.cannot_rewrite_history
        and not worker_git_policy.instruction_conflict
    )
    worker_history_authority_requested = worker_git_policy.authority_requested
    if work_mode == "read_heavy":
        write_isolation = "not_applicable"
    elif (
        disjoint_scope
        and isolated_execution
        and bounded_write_scope
        and coordinator_owns_integration
        and all_worker_git_restrictions
    ):
        write_isolation = "proven_disjoint"
    else:
        write_isolation = "unproven"

    if same_state:
        shared_state_risk = "high"
    elif work_mode != "read_heavy" and write_isolation == "unproven":
        shared_state_risk = "medium"
    elif work_mode != "read_heavy" and write_isolation == "proven_disjoint":
        shared_state_risk = "low"
    else:
        shared_state_risk = "low" if count >= 2 else "unknown"

    benefit_codes: list[str] = []
    if work_mode == "read_heavy" and count >= 2 and distinct_objectives:
        benefit_codes.append("read_heavy_breadth")
    if _matches(text, (r"\b(?:independent|adversarial) (?:verification|review)\b", r"\baudit\b.*\bseparately\b")):
        benefit_codes.append("independent_verification")
    if "corpus_partition" in categories and count >= 2:
        benefit_codes.append("large_corpus_partitioning")
    if _matches(text, (r"\b(?:very large|huge|multi-million-token|context pressure|context pollution|large repository)\b",)):
        benefit_codes.append("context_pressure_reduction")
    if len(categories) >= 2 or _matches(text, (r"\bdistinct specialist roles\b",)):
        benefit_codes.append("distinct_specialist_roles")
    if _matches(text, (r"\bdistinct (?:tools?|data domains?)\b",)) or {
        "api_capabilities",
        "pricing_review",
        "deployment_constraints",
    }.issubset(categories):
        benefit_codes.append("distinct_tool_or_data_domains")
    if write_isolation == "proven_disjoint":
        benefit_codes.append("proven_disjoint_writes")

    expected_duration = features.expected_duration
    if count >= 4 and benefit_codes:
        expected_duration = "large"
    elif count >= 2 and _matches(
        text,
        (
            r"\b(?:large|broad|repository[- ]wide|project[- ]wide|very large|long[- ]running)\b",
        ),
    ):
        expected_duration = "large"

    material = (
        count >= 2
        and dependency_shape == "parallel"
        and bool(benefit_codes)
        and expected_duration in {"large", "xlarge"}
    )
    parallel_benefit = "material" if material else "limited" if count >= 2 else "none"
    cost_minimizing = _matches(
        text,
        (
            r"\bas few tokens as possible\b",
            r"\bminimum (?:token|cost)s?\b",
            r"\bminimi[sz]e (?:token|cost)s?\b",
            r"\bcheapest\b",
            r"\bleast expensive\b",
        ),
    )
    recursive_delegation_requested = _matches(
        text,
        (
            r"\brecursive delegation\b",
            r"\bchild agents?\b.*\b(?:spawn|delegate to)\b",
            r"\bnested sub[- ]?agents?\b",
            r"\bdelegation depth\s*(?:=|:)?\s*(?:2|3|4|two|three|four)\b",
        ),
    )
    peer_to_peer_requested = _matches(text, (r"\bpeer[- ]to[- ]peer (?:swarm|coordination)\b", r"\bswarm topology\b"))

    plan_payload = {
        "workstream_count": workstream_count,
        "dependency_shape": dependency_shape,
        "work_mode": work_mode,
        "write_isolation": write_isolation,
        "categories": categories,
        "benefits": tuple(benefit_codes),
        "orchestration_vetoes": orchestration_veto_codes,
        "workers_cannot_merge": worker_git_policy.cannot_merge,
        "workers_cannot_push": worker_git_policy.cannot_push,
        "workers_cannot_rewrite_history": (
            worker_git_policy.cannot_rewrite_history
        ),
        "worker_git_instruction_conflict": worker_git_policy.instruction_conflict,
    }
    plan_id = hashlib.sha256(_canonical_json(plan_payload).encode("utf-8")).hexdigest()
    return OrchestrationAnalysis(
        workstream_count=workstream_count,
        dependency_shape=dependency_shape,
        parallel_benefit=parallel_benefit,
        shared_state_risk=shared_state_risk,
        work_mode=work_mode,
        write_isolation=write_isolation,
        controlled_workstream_categories=categories,
        benefit_reason_codes=tuple(benefit_codes),
        expected_duration=expected_duration,
        distinct_objectives=distinct_objectives,
        independent_start=independent_start,
        bounded_results=bounded_results,
        coordinator_present=coordinator_present,
        cost_minimizing=cost_minimizing,
        explicit_ultra_request=explicit_ultra_request,
        delegation_request=delegation_request,
        orchestration_veto_codes=orchestration_veto_codes,
        recursive_delegation_requested=recursive_delegation_requested,
        peer_to_peer_requested=peer_to_peer_requested,
        worker_history_authority_requested=worker_history_authority_requested,
        workers_cannot_merge=worker_git_policy.cannot_merge,
        workers_cannot_push=worker_git_policy.cannot_push,
        workers_cannot_rewrite_history=worker_git_policy.cannot_rewrite_history,
        worker_git_instruction_conflict=worker_git_policy.instruction_conflict,
        plan_id=plan_id,
    )


class OrchestrationPolicy:
    """Admit Ultra only for approved, structurally parallel bounded work."""

    def __init__(self, policy: object):
        if not isinstance(policy, Mapping):
            raise OrchestrationPolicyError("orchestration policy must be an object")
        self.policy_version = _required_string(policy, "policy_version")
        expected_literals = {
            "default_orchestration_mode": "single_agent",
            "ultra_orchestration_mode": "ultra_subagents",
            "wire_ultra_reasoning_effort": "ultra",
            "ordinary_ultra_fallback_effort": "max",
            "coordination_architecture": "centralized_orchestrator_worker",
        }
        for field, expected in expected_literals.items():
            if _required_string(policy, field) != expected:
                raise OrchestrationPolicyError(
                    f"orchestration policy {field} is unsupported"
                )
        self.ultra_profiles = frozenset(_string_tuple(policy.get("ultra_allowed_profiles"), "ultra_allowed_profiles"))
        self.minimum_workers = _bounded_integer(policy.get("minimum_worker_count"), "minimum_worker_count", 2, 4)
        self.maximum_workers = _bounded_integer(policy.get("maximum_worker_count"), "maximum_worker_count", 2, 4)
        if self.minimum_workers > self.maximum_workers:
            raise OrchestrationPolicyError("orchestration worker bounds are inverted")
        self.max_depth = _bounded_integer(policy.get("maximum_delegation_depth"), "maximum_delegation_depth", 1, 1)
        recursive = policy.get("recursive_delegation_allowed")
        if recursive is not False:
            raise OrchestrationPolicyError("recursive delegation must remain forbidden")
        if policy.get("peer_to_peer_swarm_allowed") is not False:
            raise OrchestrationPolicyError("peer-to-peer swarm must remain forbidden")
        if policy.get("live_model_list_authoritative") is not True:
            raise OrchestrationPolicyError("live model-list authority must remain enabled")
        if policy.get("telemetry_can_approve") is not False:
            raise OrchestrationPolicyError("telemetry approval must remain forbidden")
        if policy.get("telemetry_can_launch") is not False:
            raise OrchestrationPolicyError("telemetry launch must remain forbidden")
        self.approval_ttl_seconds = _bounded_integer(
            policy.get("approval_ttl_seconds"),
            "approval_ttl_seconds",
            1,
            900,
        )

    def assess(
        self,
        model: LiveModel,
        profile: ModelProfile,
        features: TaskFeatures,
        analysis: OrchestrationAnalysis,
    ) -> OrchestrationAssessment:
        vetoes: list[str] = list(analysis.orchestration_veto_codes)
        if not model.supports_ultra_orchestration:
            vetoes.append("ultra_live_capability_unavailable")
        if "max" not in model.ordinary_supported_efforts:
            vetoes.append("ultra_max_fallback_capability_unavailable")
        if profile.name not in self.ultra_profiles:
            vetoes.append("ultra_profile_not_permitted")
        if analysis.numeric_workstream_count < self.minimum_workers:
            vetoes.append("insufficient_substantive_workstreams")
        if analysis.dependency_shape != "parallel":
            vetoes.append(f"dependency_shape_{analysis.dependency_shape}")
        if not analysis.independent_start:
            vetoes.append("independent_start_unproven")
        if not analysis.distinct_objectives:
            vetoes.append("distinct_objectives_unproven")
        if not analysis.bounded_results:
            vetoes.append("bounded_worker_results_unproven")
        if analysis.parallel_benefit != "material":
            vetoes.append("material_parallel_benefit_unproven")
        if analysis.expected_duration not in {"large", "xlarge"}:
            vetoes.append("task_duration_below_large")
        if features.deterministic_eval:
            vetoes.append("deterministic_evaluation_veto")
        if analysis.shared_state_risk == "high":
            vetoes.append("high_shared_state_risk")
        if analysis.cost_minimizing:
            vetoes.append("cost_minimization_veto")
        if not analysis.coordinator_present:
            vetoes.append("central_coordinator_unproven")
        if not analysis.benefit_reason_codes:
            vetoes.append("additional_parallel_benefit_absent")
        if analysis.work_mode != "read_heavy" and analysis.write_isolation != "proven_disjoint":
            vetoes.append("write_isolation_unproven")
        if analysis.work_mode != "read_heavy":
            if not analysis.workers_cannot_merge:
                vetoes.append("worker_merge_restriction_unproven")
            if not analysis.workers_cannot_push:
                vetoes.append("worker_push_restriction_unproven")
            if not analysis.workers_cannot_rewrite_history:
                vetoes.append("worker_history_rewrite_restriction_unproven")
            if analysis.worker_git_instruction_conflict:
                vetoes.append("worker_git_instruction_conflict_veto")
        if analysis.recursive_delegation_requested:
            vetoes.append("recursive_delegation_veto")
        if analysis.peer_to_peer_requested:
            vetoes.append("peer_to_peer_swarm_veto")
        if analysis.worker_history_authority_requested:
            vetoes.append("worker_history_authority_veto")

        recommendation = "recommended" if not vetoes else "not_recommended"
        workers = (
            min(self.maximum_workers, max(self.minimum_workers, analysis.numeric_workstream_count))
            if recommendation == "recommended"
            else 0
        )
        reasons = tuple((*analysis.benefit_reason_codes, "ultra_structurally_eligible")) if not vetoes else ()
        structural_attempt = bool(
            analysis.explicit_ultra_request
            or analysis.delegation_request
            or analysis.numeric_workstream_count >= 2
            or analysis.dependency_shape in {"indivisible", "sequential", "mixed"}
        )
        force_max = recommendation == "recommended" or structural_attempt
        fallback = vetoes[0] if vetoes and force_max else None
        resource_class = "very_high" if workers >= 3 else "high" if workers == 2 else "ordinary"
        return OrchestrationAssessment(
            recommendation=recommendation,
            planned_worker_count=workers,
            reason_codes=reasons,
            veto_codes=tuple(vetoes),
            fallback_reason_code=fallback,
            force_max_single_agent=force_max,
            resource_class=resource_class,
        )

    def decide(
        self,
        *,
        analysis: OrchestrationAnalysis,
        assessment: OrchestrationAssessment,
        ordinary_reasoning_effort: str,
        selected_model: str,
        task_signature: str | None,
        effective_turn_context_schema_version: str | None,
        effective_turn_context_hash: str | None,
        policy_version: str,
        sandbox_mode: str,
        approval_policy: object,
        approval_evidence: UltraApprovalEvidence | None,
        now_epoch_seconds: int | None = None,
    ) -> OrchestrationDecision:
        if ordinary_reasoning_effort not in ORDINARY_REASONING_EFFORTS:
            raise OrchestrationPolicyError("ordinary reasoning effort is invalid")
        proposal = self._proposal(
            analysis=analysis,
            assessment=assessment,
            ordinary_reasoning_effort=ordinary_reasoning_effort,
            selected_model=selected_model,
            task_signature=task_signature,
            effective_turn_context_schema_version=(
                effective_turn_context_schema_version
            ),
            effective_turn_context_hash=effective_turn_context_hash,
            policy_version=policy_version,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
        )

        if assessment.recommendation != "recommended":
            approval_state = "invalid" if approval_evidence is not None else "not_requested"
            return self._single_agent_decision(
                analysis,
                assessment,
                ordinary_reasoning_effort,
                approval_state=approval_state,
                proposal=None,
            )
        if proposal is None:
            return self._single_agent_decision(
                analysis,
                assessment,
                ordinary_reasoning_effort,
                approval_state="invalid",
                proposal=None,
            )

        approval_state = self._approval_state(
            approval_evidence,
            proposal,
            now_epoch_seconds=int(time.time()) if now_epoch_seconds is None else now_epoch_seconds,
        )
        if approval_state != "approved":
            fallback = assessment.fallback_reason_code
            if approval_state == "pending":
                fallback = "ultra_approval_pending"
            elif approval_state == "denied":
                fallback = "ultra_approval_denied"
            elif approval_state == "invalid":
                fallback = "ultra_approval_invalid"
            return self._single_agent_decision(
                analysis,
                assessment,
                ordinary_reasoning_effort,
                approval_state=approval_state,
                proposal=proposal,
                fallback_reason=fallback,
            )

        return OrchestrationDecision(
            ordinary_reasoning_effort=ordinary_reasoning_effort,
            wire_reasoning_effort="ultra",
            orchestration_mode="ultra_subagents",
            ultra_recommendation="recommended",
            ultra_approval="approved",
            planned_worker_count=assessment.planned_worker_count,
            workstream_count=analysis.workstream_count,
            controlled_workstream_categories=analysis.controlled_workstream_categories,
            dependency_shape=analysis.dependency_shape,
            parallel_benefit=analysis.parallel_benefit,
            shared_state_risk=analysis.shared_state_risk,
            work_mode=analysis.work_mode,
            write_isolation=analysis.write_isolation,
            resource_class=assessment.resource_class,
            human_approval_required=True,
            max_delegation_depth=self.max_depth,
            recursive_delegation_allowed=False,
            reason_codes=tuple((*assessment.reason_codes, "task_bound_ultra_approval_valid")),
            fallback_reason_code=None,
            proposal=proposal,
        )

    def _proposal(
        self,
        *,
        analysis: OrchestrationAnalysis,
        assessment: OrchestrationAssessment,
        ordinary_reasoning_effort: str,
        selected_model: str,
        task_signature: str | None,
        effective_turn_context_schema_version: str | None,
        effective_turn_context_hash: str | None,
        policy_version: str,
        sandbox_mode: str,
        approval_policy: object,
    ) -> UltraProposal | None:
        if assessment.recommendation != "recommended":
            return None
        if policy_version != self.policy_version:
            return None
        if effective_turn_context_schema_version != EFFECTIVE_TURN_CONTEXT_SCHEMA_VERSION:
            return None
        if not _is_hash(task_signature) or not _is_hash(effective_turn_context_hash):
            return None
        normalized_approval = approval_policy if isinstance(approval_policy, str) else "granular"
        payload = {
            "decision_signature_version": ULTRA_DECISION_SIGNATURE_VERSION,
            "task_signature": task_signature,
            "selected_model": selected_model,
            "ordinary_reasoning_effort": ordinary_reasoning_effort,
            "orchestration_mode": "ultra_subagents",
            "worker_count": assessment.planned_worker_count,
            "workstream_plan_id": analysis.plan_id,
            "policy_version": policy_version,
            "sandbox_mode": sandbox_mode,
            "approval_policy": normalized_approval,
            "effective_turn_context_schema_version": (
                effective_turn_context_schema_version
            ),
            "effective_turn_context_hash": effective_turn_context_hash,
        }
        decision_signature = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        return UltraProposal(
            decision_signature_version=ULTRA_DECISION_SIGNATURE_VERSION,
            decision_signature=decision_signature,
            effective_turn_context_schema_version=(
                effective_turn_context_schema_version
            ),
            effective_turn_context_hash=effective_turn_context_hash,
            selected_model=selected_model,
            fallback_model=selected_model,
            ordinary_reasoning_effort=ordinary_reasoning_effort,
            fallback_reasoning_effort=ordinary_reasoning_effort,
            planned_worker_count=assessment.planned_worker_count,
            controlled_workstream_categories=analysis.controlled_workstream_categories,
            plan_id=analysis.plan_id,
            policy_version=policy_version,
            sandbox_mode=sandbox_mode,
            approval_policy=normalized_approval,
            resource_class=assessment.resource_class,
        )

    def _approval_state(
        self,
        evidence: UltraApprovalEvidence | None,
        proposal: UltraProposal,
        *,
        now_epoch_seconds: int,
    ) -> str:
        if evidence is None:
            return "pending"
        if not isinstance(evidence, UltraApprovalEvidence):
            return "invalid"
        if evidence.schema_version != ULTRA_APPROVAL_EVIDENCE_SCHEMA_VERSION:
            return "invalid"
        if evidence.decision_signature_version != ULTRA_DECISION_SIGNATURE_VERSION:
            return "invalid"
        if proposal.decision_signature_version != ULTRA_DECISION_SIGNATURE_VERSION:
            return "invalid"
        if (
            evidence.effective_turn_context_schema_version
            != EFFECTIVE_TURN_CONTEXT_SCHEMA_VERSION
            or proposal.effective_turn_context_schema_version
            != EFFECTIVE_TURN_CONTEXT_SCHEMA_VERSION
        ):
            return "invalid"
        if not _is_hash(evidence.effective_turn_context_hash):
            return "invalid"
        if (
            evidence.effective_turn_context_hash
            != proposal.effective_turn_context_hash
        ):
            return "invalid"
        if evidence.status not in {"approved", "denied"}:
            return "invalid"
        if evidence.policy_version != self.policy_version or evidence.policy_version != proposal.policy_version:
            return "invalid"
        if evidence.decision_signature != proposal.decision_signature:
            return "invalid"
        if not _is_hash(evidence.decision_signature):
            return "invalid"
        if isinstance(evidence.issued_at_epoch_seconds, bool) or not isinstance(evidence.issued_at_epoch_seconds, int):
            return "invalid"
        if isinstance(evidence.expires_at_epoch_seconds, bool) or not isinstance(evidence.expires_at_epoch_seconds, int):
            return "invalid"
        if evidence.expires_at_epoch_seconds < evidence.issued_at_epoch_seconds:
            return "invalid"
        if evidence.expires_at_epoch_seconds - evidence.issued_at_epoch_seconds > self.approval_ttl_seconds:
            return "invalid"
        if not evidence.issued_at_epoch_seconds <= now_epoch_seconds <= evidence.expires_at_epoch_seconds:
            return "invalid"
        return evidence.status

    def _single_agent_decision(
        self,
        analysis: OrchestrationAnalysis,
        assessment: OrchestrationAssessment,
        ordinary_reasoning_effort: str,
        *,
        approval_state: str,
        proposal: UltraProposal | None,
        fallback_reason: str | None = None,
    ) -> OrchestrationDecision:
        return OrchestrationDecision(
            ordinary_reasoning_effort=ordinary_reasoning_effort,
            wire_reasoning_effort=ordinary_reasoning_effort,
            orchestration_mode="single_agent",
            ultra_recommendation=assessment.recommendation,
            ultra_approval=approval_state,
            planned_worker_count=(
                assessment.planned_worker_count
                if assessment.recommendation == "recommended"
                else 0
            ),
            workstream_count=analysis.workstream_count,
            controlled_workstream_categories=analysis.controlled_workstream_categories,
            dependency_shape=analysis.dependency_shape,
            parallel_benefit=analysis.parallel_benefit,
            shared_state_risk=analysis.shared_state_risk,
            work_mode=analysis.work_mode,
            write_isolation=analysis.write_isolation,
            resource_class=assessment.resource_class,
            human_approval_required=assessment.recommendation == "recommended",
            max_delegation_depth=self.max_depth,
            recursive_delegation_allowed=False,
            reason_codes=tuple((*assessment.reason_codes, *assessment.veto_codes)),
            fallback_reason_code=fallback_reason or assessment.fallback_reason_code,
            proposal=proposal,
        )


def make_ultra_approval_evidence(
    proposal: UltraProposal,
    *,
    now_epoch_seconds: int,
    ttl_seconds: int = 300,
    approved: bool = True,
) -> UltraApprovalEvidence:
    """Build bounded evidence after a trusted UI records an explicit decision."""

    if not isinstance(proposal, UltraProposal):
        raise ValueError("approval proposal is invalid")
    if type(approved) is not bool:
        raise ValueError("approval decision must be a boolean")
    if isinstance(now_epoch_seconds, bool) or not isinstance(now_epoch_seconds, int):
        raise ValueError("approval time must be an integer")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 900:
        raise ValueError("approval ttl is invalid")
    if (
        proposal.decision_signature_version != ULTRA_DECISION_SIGNATURE_VERSION
        or proposal.effective_turn_context_schema_version
        != EFFECTIVE_TURN_CONTEXT_SCHEMA_VERSION
        or not _is_hash(proposal.effective_turn_context_hash)
        or not _is_hash(proposal.decision_signature)
    ):
        raise ValueError("approval proposal binding is invalid")
    return UltraApprovalEvidence(
        schema_version=ULTRA_APPROVAL_EVIDENCE_SCHEMA_VERSION,
        decision_signature_version=proposal.decision_signature_version,
        decision_signature=proposal.decision_signature,
        effective_turn_context_schema_version=(
            proposal.effective_turn_context_schema_version
        ),
        effective_turn_context_hash=proposal.effective_turn_context_hash,
        status="approved" if approved else "denied",
        policy_version=proposal.policy_version,
        issued_at_epoch_seconds=now_epoch_seconds,
        expires_at_epoch_seconds=now_epoch_seconds + ttl_seconds,
    )


def _substantive_workstream_count(text: str, category_count: int) -> int:
    counts: list[int] = []
    unit = r"(?:substantive\s+)?(?:independent\s+)?(?:areas?|workstreams?|collections?|packages?|modules?|reviews?|analyses?|streams?)"
    for match in re.finditer(rf"\b(one|two|three|four|five|six|several|multiple|[1-6])\s+{unit}\b", text):
        raw = match.group(1)
        counts.append(int(raw) if raw.isdigit() else _COUNT_WORDS[raw])
    if category_count >= 2 and _matches(text, (r"\b(?:independent|separate|separately|distinct|divided)\b",)):
        counts.append(category_count)
    return max(counts, default=0)


def _bounded_count(value: int) -> str:
    if value <= 0:
        return "0"
    if value == 1:
        return "1"
    if value == 2:
        return "2"
    if value == 3:
        return "3"
    return "4_plus"


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) is not None for pattern in patterns)


def _is_meta_or_quoted_orchestration_only(text: str) -> bool:
    """Suppress mentioned orchestration when no executable transition exists."""

    meta_framing = _matches(
        text,
        (
            r"^\s*(?:(?:please|kindly)\s+)?(?:explain|describe|document|define|review|summari[sz]e|analy[sz]e|translate|discuss|compare|evaluate|assess|determine)\s+(?:how|why|when|whether|what)\b",
            r"^\s*(?:(?:please|kindly)\s+)?(?:explain|describe|document|define|review|summari[sz]e|analy[sz]e|translate|discuss|compare|evaluate)\s+(?:(?:the|this|a)\s+)?(?:phrase|statement|sentence|documentation|example|quoted prompt)\b",
            r"^\s*(?:(?:please|kindly)\s+)?(?:explain|describe|define|discuss|compare|summari[sz]e|analy[sz]e|translate)\s+(?:ultra|orchestration|sub[- ]?agents?|multi[- ]agent)\b",
            r"^\s*(?:provide|give|write)\s+(?:(?:an?|the)\s+)?(?:explanation|description|summary|example|documentation)\b[^.;\n]{0,160}\b(?:ultra|orchestration|sub[- ]?agents?|multi[- ]agent)\b",
            r"^\s*(?:tell\s+me\s+about|give\s+me\s+information\s+about)\s+(?:ultra|orchestration|sub[- ]?agents?|multi[- ]agent)\b",
            r"^\s*(?:show|provide|give)\s+(?:(?:me|us)\s+)?(?:(?:an?|the)\s+)?(?:example|illustration)\b[^.;\n]{0,160}\b(?:ultra|orchestration|sub[- ]?agents?|multi[- ]agent)\b",
            r"^\s*(?:here is|consider)\s+(?:(?:an?|the)\s+)?(?:example|sample|illustration|quoted prompt)\b",
            r"^\s*(?:here|this|below|above)\s+is\s+(?:(?:the|an?)\s+)?(?:translation|quotation|paraphrase|summary|example|sample|illustration|quoted (?:text|prompt)|instruction example)\b",
            r"^\s*(?:the\s+)?following\s+is\s+(?:(?:the|an?)\s+)?(?:translation|quotation|paraphrase|summary|example|sample|illustration|quoted (?:text|prompt)|instruction example)\b",
            r"^\s*(?:the\s+)?(?:translation|quotation|paraphrase|summary|example|sample|illustration|quoted (?:text|prompt)|instruction example)\s+follows\b",
            r"^\s*(?:a|the)\s+user\s+(?:might|could|may)\s+(?:say|write|ask)\b",
            r"^\s*(?:audit|review|inspect|evaluate|analy[sz]e)\s+(?:(?:the|this)\s+)?(?:ultra|orchestration|sub[- ]?agent|multi[- ]agent)\s+(?:policy|admission|mode|feature|documentation)\b",
            r"^\s*(?:what|why|how|when|should|could|would|can)\b",
            r"^\s*(?:is|are)\s+(?:ultra|orchestration|sub[- ]?agents?|multi[- ]agent)\b",
            r"^\s*(?:wyjaśnij|opisz|zdefiniuj|udokumentuj|podsumuj|przeanalizuj|przetłumacz)\s+(?:jak|dlaczego|kiedy|czy|co)\b",
            r"^\s*(?:co|dlaczego|jak|czy)\b",
            r"^\s*(?:example|example only|instruction example|sample|translation|quotation|paraphrase|summary|illustration|quoted prompt|for example|przykład|przykładowo)\s*[:,-]",
            r"\b(?:the|this) (?:phrase|statement|sentence|documentation|example|quoted prompt)\b.*\b(?:means?|says?|mentions?|contains?)\b",
            r"^\s*(?:the\s+)?documentation\s+(?:says?|contains?|mentions?)\b",
            r"^\s*(?:review|explain|describe)\s+(?:this\s+)?quoted prompt\b",
        ),
    )
    executable_transition = _matches(
        text,
        (
            r"\b(?:then|and then|after that|next|subsequently)\b.*\b(?:use|run|enable|delegate|spawn)\b",
            r"\b(?:potem|następnie|a następnie|po tym)\b.*\b(?:użyj|uruchom|włącz|deleguj)\b",
        ),
    )
    return meta_framing and not executable_transition


def _mask_quoted_text(text: str) -> str:
    """Remove bounded quoted mentions without interpreting their contents."""

    for fence in ("```", "~~~"):
        if text.count(fence) % 2:
            text = text[: text.find(fence)] + " "
    if text.count("``") % 2:
        text = text[: text.find("``")] + " "
    if text.count("`") % 2:
        text = text[: text.find("`")] + " "
    if text.count('"') % 2:
        text = text[: text.find('"')] + " "
    for opening, closing in (("“", "”"), ("‘", "’"), ("‚", "’"), ("«", "»"), ("「", "」"), ("『", "』")):
        if text.count(opening) > text.count(closing):
            text = text[: text.find(opening)] + " "
    if text.count("„") > text.count("“") + text.count("”"):
        text = text[: text.find("„")] + " "
    return re.sub(
        r"(?s:```.*?```|~~~.*?~~~)"
        r"|(?m:^[ \t]*>.*$)"
        r"|(?m::[ \t]*>[ \t]*[^\n]*$)"
        r"|(?m:^(?: {4}|\t).*$)"
        r'|"(?:\\.|[^"\\])*"'
        r"|(?<!\w)'(?:\\.|[^'\\])*'(?!\w)"
        r"|``[^`\n]*``"
        r"|`[^`\n]*`"
        r"|“[^”]*”"
        r"|„[^“”]*[“”]"
        r"|‘[^’]*’"
        r"|‚[^’]*’"
        r"|«[^»]*»"
        r"|「[^」]*」"
        r"|『[^』]*』",
        " ",
        text,
    )


_ORCHESTRATION_IMPERATIVE_RE = re.compile(
    r"(?:^|[.;!?\n])\s*(?:(?:[-*+]|\d+[.)])\s+)?(?:please\s+)?(?:"
    r"(?:use|enable|select|choose|run(?:\s+with)?|route(?:\s+this)?\s+to)\s+"
    r"[\"'`“„‘‚«]?ultra[\"'`“”’»]?(?:\s+for\s+this\s+(?:task|request|turn))?"
    r"|(?:use|spawn|launch|delegate\s+to)\s+"
    r"[\"'`“„‘‚«]?(?:sub[- ]?agents?|agents?)[\"'`“”’»]?"
    r"|orchestrat(?:e|ing)(?:\s+this\s+(?:task|request|turn))?"
    r")\b",
    flags=re.IGNORECASE,
)


def _has_bounded_workstream_evidence(clause: str) -> bool:
    workstream_unit = (
        r"(?:workstreams?|areas?|collections?|packages?|modules?|objectives?|"
        r"reviews?|analyses?|streams?)"
    )
    return _matches(
        clause,
        (
            rf"\b(?:independent|parallel|distinct|separate|divided)\s+{workstream_unit}\b",
            rf"\b(?:two|three|four|[2-4])\s+(?:substantive\s+)?{workstream_unit}\b",
        ),
    )


def _is_bounded_task_continuation(clause: str) -> bool:
    if not _has_bounded_workstream_evidence(clause):
        return False
    return _matches(
        clause,
        (
            r"^\s*(?:(?:please|without\s+delay)\s+)?(?:analy[sz]e|assess|audit|build|compare|create|document|edit|evaluate|explore|fix|implement|inspect|investigate|modify|redesign|refactor|research|review|scan|summari[sz]e|test|verify|write)\b",
            r"^\s*(?:this|that)\s+(?:task|request|turn|work|job|analysis|research|audit|project)\b",
            r"^\s*(?:it|we)\s+(?:has|have|contains?|covers?|includes?|requires?|comprises?|consists?)\b",
        ),
    )


def _has_immediate_orchestration_reframe(text: str) -> bool:
    """Fail closed unless the next clause is a bounded task continuation."""

    for imperative in _ORCHESTRATION_IMPERATIVE_RE.finditer(text):
        next_clause = re.match(
            r"^\s*[.;!?\n]+\s*(?P<clause>[^.;!?\n]*)",
            text[imperative.end() :],
        )
        if next_clause is None:
            continue
        clause = re.sub(
            r"^\s*(?:(?:[-*+]|\d+[.)])\s+)",
            "",
            next_clause.group("clause"),
            count=1,
        )
        if _is_bounded_task_continuation(clause):
            continue
        return True
    return False


def _has_later_orchestration_cancellation(text: str) -> bool:
    """Recognize bounded revocation clauses ordered after an Ultra imperative."""

    for imperative in _ORCHESTRATION_IMPERATIVE_RE.finditer(text):
        for raw_clause in re.split(r"[.;!?\n]+", text[imperative.end() :]):
            clause = re.sub(
                r"^\s*(?:(?:[-*+]|\d+[.)])\s+)",
                "",
                raw_clause,
                count=1,
            )
            if _matches(
                clause,
                (
                    r"\b(?:do\s+not|don['’]t|never|must\s+not|mustn['’]t|cannot|can['’]t|should\s+not|shouldn['’]t|may\s+not|shall\s+not|will\s+not|need\s+not|not\s+to|not\s+(?:allowed|permitted|authorized)|forbid(?:s)?|prohibit(?:s)?|bar(?:s)?|forbidden|prohibited|barred|refuse(?:s)?|under\s+no\s+circumstances|by\s+no\s+means)\b[^.;!?\n]*\b(?:proceed|continue|execute|run|start|launch|act|carry\s+on|go\s+ahead)\b",
                    r"\b(?:forbidden|prohibited|barred)\b[^.;!?\n]*\b(?:proceeding|continuing|executing|running|starting|launching|acting)\b",
                    r"\b(?:proceed|continue|execute|run|act|carry\s+on|go\s+ahead)\s+(?:no\s+(?:further|farther)|no\s+more)\b",
                    r"\b(?:no|without)\s+(?:(?:further|more|additional)\s+)?(?:execution|action|work|processing|orchestration)\b",
                    r"\bthere\s+(?:must|should|can|may|will)\s+be\s+no\s+(?:(?:further|more|additional)\s+)?(?:execution|action|work|processing|orchestration)\b",
                    r"\b(?:(?:further|more|additional)\s+)?(?:execution|action|work|processing|orchestration)\s+(?:is|remains?)\s+(?:forbidden|prohibited|disallowed|not\s+(?:allowed|permitted|authorized))\b",
                    r"\b(?:the\s+)?(?:task|request|turn|execution|orchestration)\s+(?:must\s+not|cannot|can['’]t|should\s+not)\s+(?:proceed|continue|be\s+(?:executed|started|launched))\b",
                ),
            ):
                return True
            revocations = re.finditer(
                r"\b(?:cancel(?:s|l?ed|l?ing)?|abort(?:s|ed|ing)?|withdraw(?:s|ing|n)?|withdrew|revok(?:e|es|ed|ing)|retract(?:s|ed|ing)?|rescind(?:s|ed|ing)?|abandon(?:s|ed|ing)?|terminat(?:e|es|ed|ing)|halt(?:s|ed|ing)?|ceas(?:e|es|ed|ing)|stop(?:s|ped|ping)?|forget(?:s|ting)?|forgot(?:ten)?|disregard(?:s|ed|ing)?|ignor(?:e|es|ed|ing)|drop(?:s|ped|ping)?)\b",
                clause,
                flags=re.IGNORECASE,
            )
            for revocation in revocations:
                prefix = clause[: revocation.start()]
                bounded_task_prefix = _matches(
                    prefix,
                    (
                        r"^\s*(?:(?:please|without\s+delay)\s+)?(?:analy[sz]e|assess|audit|compare|document|evaluate|explain|inspect|investigate|research|review|summari[sz]e|verify)\b",
                    ),
                )
                analytical_subject_framing = _matches(
                    prefix,
                    (
                        r"\b(?:about|how|why|whether|ways?|behavior|behaviour|semantics|meaning|documentation|handling)\b",
                    ),
                )
                sequenced_revocation = _matches(
                    prefix,
                    (
                        r"\b(?:then|and\s+then|after\s+that|finally|next|subsequently)\b",
                        r"(?:,|\b(?:and|or)\b)[^.;!?\n]*$",
                        r"\b(?:before|after|once|when|while|until)\s+(?:you|we|they|workers?|agents?|the\s+(?:coordinator|orchestrator))\s*$",
                        r"\b(?:before|after|once|when|while|until)\s*$",
                        r"\b(?:prior\s+to|subsequent\s+to|in\s+advance\s+of)\s*$",
                        r"\bso(?:\s+that)?\s+(?:you|we|they|workers?|agents?|the\s+(?:coordinator|orchestrator))\s+(?:can|may|will|should|must)\s*$",
                    ),
                )
                gerund_temporal_revocation = (
                    revocation.group(0).casefold().endswith("ing")
                    and _matches(prefix, (r"\b(?:of|to)\s*$",))
                )
                if (
                    not bounded_task_prefix
                    or not analytical_subject_framing
                    or sequenced_revocation
                    or gerund_temporal_revocation
                ):
                    return True
            if _matches(
                clause,
                (
                    r"^\s*(?:never\s+mind|scratch\s+that|on\s+second\s+thought)\s*$",
                ),
            ):
                return True
    return False


def _orchestration_veto_codes(
    text: str,
    *,
    explicit_ultra_request: bool,
    delegation_request: bool,
) -> tuple[str, ...]:
    """Return hard vetoes that approval and structural signals cannot override."""

    codes: list[str] = []
    orchestration_mentioned = _matches(
        text,
        (
            r"\bultra\b",
            r"\borchestrat(?:e|ed|es|ing|ion)\b",
            r"\b(?:sub[- ]?agents?|multi[- ]agent|delegat(?:e|ed|es|ing|ion))\b",
        ),
    )
    if (
        orchestration_mentioned or explicit_ultra_request or delegation_request
    ) and _is_meta_or_quoted_orchestration_only(text):
        codes.append("orchestration_nonexecuting_language_veto")

    unquoted = _mask_quoted_text(text)
    unquoted_orchestration_mentioned = _matches(
        unquoted,
        (
            r"\bultra\b",
            r"\borchestrat(?:e|ed|es|ing|ion)\b",
            r"\b(?:sub[- ]?agents?|multi[- ]agent|delegat(?:e|ed|es|ing|ion))\b",
        ),
    )
    unquoted_explicit_request = _matches(
        unquoted,
        (
            r"\b(?:use|enable|select|choose|run(?:\s+with)?|route(?:\s+this)?\s+to)\s+ultra\b",
            r"\b(?:reasoning\s+)?effort\s*(?:=|:|to|at)?\s*ultra\b",
        ),
    )
    unquoted_delegation_request = _matches(
        unquoted,
        (
            r"\bdelegat(?:e|ed|es|ing|ion)\b",
            r"\bspawn\b[^.;\n]{0,80}\b(?:agents?|workers?)\b",
            r"\buse\b[^.;\n]{0,80}\b(?:sub[- ]?agents?|multiple agents)\b",
            r"\bone agent per\b",
            r"\buse\s+(?:two|three|four|[2-4])\s+agents?\b",
        ),
    )
    if _matches(
        unquoted,
        (
            r"(?:^|\n)\s*[^:\n]{1,120}:\s*(?:\n\s*)?(?:use|enable|select|choose|run(?:\s+with)?|route(?:\s+this)?\s+to)\s+ultra\b",
            r"(?:^|\n)\s*[^:\n]{1,120}:\s*(?:\n\s*)?(?:use|spawn|launch)\b[^.;\n]{0,60}\bsub[- ]?agents?\b",
            r"(?:^|\n)\s*(?:the\s+)?(?:translation|quotation|paraphrase|summary|example|sample|illustration|quoted (?:text|prompt)|instruction example)\s+follows\b[^\n]*\n\s*(?:use|enable|select|choose|run(?:\s+with)?|route(?:\s+this)?\s+to)\s+ultra\b",
            r"(?:^|\n)\s*(?:#{1,6}\s+|[-*]\s+)?(?:translation|quotation|paraphrase|summary|example|sample|illustration|quoted (?:text|prompt)|instruction example)\s*\n\s*(?:use|enable|select|choose|run(?:\s+with)?|route(?:\s+this)?\s+to)\s+ultra\b",
            r"(?:^|\n)\s*(?:#{1,6}\s+)?(?:for\s+(?:your\s+)?reference|reference only)\s*[:,]?\s*\n\s*(?:use|enable|select|choose|run(?:\s+with)?|route(?:\s+this)?\s+to)\s+ultra\b",
            r"(?:^|\n)\s*#{1,6}\s+[^\n]{1,120}\n\s*(?:use|enable|select|choose|run(?:\s+with)?|route(?:\s+this)?\s+to)\s+ultra\b",
        ),
    ):
        codes.append("orchestration_nonexecuting_language_veto")
    if _orchestration_question_present(unquoted):
        codes.append("orchestration_nonexecuting_language_veto")
    quoted_target_meta = _matches(
        text,
        (
            r"\b(?:use|enable|select|choose|run(?:\s+with)?)\s+[\"'`“„‘‚«]ultra[\"'`“”’»][^.;\n]{0,120}\b(?:as\s+(?:(?:an?|the)\s+)?(?:example|sample|illustration|term|word|phrase|label)|glossary|vocabulary|documentation)\b",
            r"\b(?:use|spawn|delegate to)\s+[\"'`“„‘‚«](?:sub[- ]?agents?|agents?)[\"'`“”’»][^.;\n]{0,120}\b(?:as\s+(?:(?:an?|the)\s+)?(?:example|sample|illustration|term|word|phrase|label)|glossary|vocabulary|documentation)\b",
            r"\b(?:use|enable|select|choose|run(?:\s+with)?|spawn|delegate to)\s+[\"'`“„‘‚«](?:ultra|sub[- ]?agents?|agents?)[\"'`“”’»][^.;\n]{0,160}\b(?:literal(?:ly)?|placeholder|(?:raw|plain)\s+text|literal\s+string|example|sample|illustration|glossary|vocabulary|documentation|non[- ]executing|not\s+as\s+(?:an?\s+)?execution\s+mode)\b",
        ),
    )
    quoted_target_match: re.Match[str] | None = None
    for pattern in (
        r"(?:^|[.;!?\n])\s*(?:use|enable|select|choose|run(?:\s+with)?)\s+[\"'`“„‘‚«]ultra[\"'`“”’»]\s+for\s+this\s+(?:task|request|turn)\b(?=\s*(?:[.;!?\n]|$))",
        r"(?:^|[.;!?\n])\s*(?:use|spawn|delegate to)\s+[\"'`“„‘‚«](?:sub[- ]?agents?|agents?)[\"'`“”’»]\s+for\s+this\s+(?:task|request|turn)\b(?=\s*(?:[.;!?\n]|$))",
    ):
        quoted_target_match = re.search(pattern, text, flags=re.IGNORECASE)
        if quoted_target_match is not None:
            break
    quoted_target_reframed = _has_immediate_orchestration_reframe(text)
    quoted_target_imperative = (
        quoted_target_match is not None
        and not quoted_target_meta
        and not quoted_target_reframed
    )
    if quoted_target_reframed:
        codes.append("orchestration_nonexecuting_language_veto")
    quoted_only_request = (
        (explicit_ultra_request or delegation_request)
        and not unquoted_explicit_request
        and not unquoted_delegation_request
        and not quoted_target_imperative
    )
    quoted_only_mention = (
        orchestration_mentioned
        and not unquoted_orchestration_mentioned
        and not quoted_target_imperative
    )
    if quoted_only_request or quoted_only_mention:
        codes.append("orchestration_nonexecuting_language_veto")

    # Any unquoted orchestration mention that is not a bounded imperative is
    # non-executing for admission purposes. Structural features may still be
    # analyzed, but cannot turn the mention into authority.
    for clause in re.split(
        r"[.;!?？\n]+|\b(?:but|however|yet|ale|lecz)\b",
        unquoted,
        flags=re.IGNORECASE,
    ):
        if not _matches(
            clause,
            (
                r"\bultra\b",
                r"\borchestrat(?:e|ed|es|ing|ion)\b",
                r"\b(?:sub[- ]?agents?|multi[- ]agent|delegat(?:e|ed|es|ing|ion))\b",
            ),
        ):
            continue
        if _matches(
            clause,
            (
                r"^\s*(?:(?:please|without delay)\s+)?(?:use|enable|select|choose|run(?:\s+with)?|route(?:\s+this)?\s+to)\s+ultra\b",
                r"^\s*(?:(?:please|without delay)\s+)?(?:use|spawn|launch)\b[^.;\n]{0,60}\bsub[- ]?agents?\b",
                r"^\s*(?:(?:please|without delay)\s+)?delegat(?:e|ing)\b",
                r"^\s*(?:(?:please|without delay)\s+)?orchestrat(?:e|ing)\b",
                r"^\s*(?:(?:please|without delay)\s+)?(?:audit|build|compare|create|edit|evaluate|explore|fix|implement|inspect|investigate|modify|redesign|refactor|research|review|scan|write)\b[^.;\n]{0,160}\b(?:delegat(?:e|ing)|spawn\b[^.;\n]{0,40}\b(?:agents?|workers?)|use\b[^.;\n]{0,40}\b(?:sub[- ]?agents?|multiple agents))\b",
            ),
        ):
            continue
        codes.append("orchestration_nonexecuting_language_veto")
        break
    ultra_prohibited = _matches(
        unquoted,
        (
            r"\b(?:do not|don['’]t|never|must not|mustn['’]t|must never|may not|should not|shouldn['’]t|shall not|cannot|can['’]t)\s+(?:(?:ever|for this (?:task|request|turn))\s+)?(?:use|enable|select|choose|run(?:\s+with)?|route(?:\s+this)?\s+to)\s+ultra\b",
            r"\bunder no circumstances\s+(?:use|enable|select|choose|run(?:\s+with)?)\s+ultra\b",
            r"\b(?:do not|don['’]t|never|must not|mustn['’]t|may not|should not|shouldn['’]t|cannot|can['’]t)\s*(?:,\s*)?(?:under (?:any|no) circumstances\s*,?\s*)?(?:switch|change|move)\s+to\s+ultra\b",
            r"\b(?:use|select|choose)\s+(?:max|normal|single[- ]agent(?: mode)?)\b[^.;\n]{0,50}\binstead of\s+ultra\b",
            r"\b(?:you|workers?|agents?|the system)\s+(?:are|is)\s+(?:not (?:allowed|permitted|authorized)|forbidden)\s+to\s+(?:use|enable|select|choose|run(?:\s+with)?)\s+ultra\b",
            r"\bultra\s+(?:must not|mustn['’]t|must never|may not|should not|shouldn['’]t|shall not|cannot|can['’]t)\s+be\s+(?:used|enabled|selected|chosen|run)\b",
            r"\bultra\s+(?:is|remains?)\s+(?:forbidden|prohibited|disabled|disallowed|not (?:allowed|permitted)|not to be used)\b",
            r"\b(?:disable|block)\s+ultra\b",
            r"\b(?:avoid|refrain from)\s+(?:using\s+)?ultra\b",
            r"\b(?:no|without)\s+ultra\b",
            r"\b(?:normal|single[- ]agent) mode\b[^.;\n]{0,40}\bnot\s+ultra\b",
            r"\b(?:normal|single[- ]agent) mode\b[^.;\n]{0,40}\binstead of\s+ultra\b",
            r"\bnot\s+ultra\s+(?:for|on)\s+this\s+(?:request|task|turn)\b",
            r"\b(?:nie|nigdy)\s+(?:używaj|włączaj|uruchamiaj)\s+ultra\b",
            r"\bbez\s+ultra\b",
        ),
    )
    subagents_prohibited = _matches(
        unquoted,
        (
            r"\b(?:do not|don['’]t|never|must not|mustn['’]t|must never|may not|should not|shouldn['’]t|shall not|cannot|can['’]t)\b[^.;\n]{0,80}\b(?:use|delegate|spawn|launch)\b[^.;\n]{0,50}\b(?:agents?|sub[- ]?agents?|workers?)\b",
            r"\b(?:do not|don['’]t|never|must not|must never|may not|should not|shall not|cannot|can['’]t)\s+(?:(?:ever|for this (?:task|request|turn))\s+)?delegat(?:e|ing|ion)\b",
            r"\b(?:sub[- ]?agents?|multi[- ]agent(?: execution)?|delegation)\s+(?:is|are|remains?)\s+(?:forbidden|prohibited|disabled|disallowed|not (?:allowed|permitted)|not to be used)\b",
            r"\b(?:sub[- ]?agents?|multi[- ]agent(?: execution)?|delegation)\s+(?:must not|mustn['’]t|must never|may not|should not|shouldn['’]t|shall not|cannot|can['’]t)\s+be\s+(?:used|enabled|launched|performed)\b",
            r"\b(?:you|workers?|agents?|the system)\s+(?:are|is)\s+(?:not (?:allowed|permitted|authorized)|forbidden)\s+to\s+(?:delegate|spawn|launch|use\s+sub[- ]?agents?)\b",
            r"\b(?:avoid|refrain from)\b[^.;\n]{0,50}\b(?:delegation|sub[- ]?agents?|multi[- ]agent|multiple agents)\b",
            r"\b(?:no|without)\s+(?:delegation|sub[- ]?agents?|multi[- ]agent)\b",
            r"\b(?:no|without)\s+workers?\s+(?:for|on)\s+(?:this|the)\s+(?:task|request|turn)\b",
            r"\b(?:use\s+)?(?:one\s+agent|a\s+single[- ]agent|single[- ]agent)\s+only\b",
            r"\bonly\s+(?:use\s+)?(?:one|a single)\s+agent\b",
            r"\b(?:nie|nigdy)\b[^.;\n]{0,80}\b(?:używaj|deleguj|uruchamiaj)\b[^.;\n]{0,50}\b(?:agentów|subagentów)\b",
            r"\bbez\s+(?:agentów|subagentów|delegowania)\b",
        ),
    )
    orchestration_prohibited = _matches(
        unquoted,
        (
            r"\b(?:do not|don['’]t|never|must not|mustn['’]t|must never|may not|should not|shouldn['’]t|shall not|cannot|can['’]t)\s+(?:(?:ever|for this (?:task|request|turn))\s+)?orchestrat(?:e|ing)\b",
            r"\b(?:this\s+(?:task|request|turn)|the\s+task)\s+(?:must not|must never|may not|should not|shall not|cannot|can['’]t)\s+be\s+orchestrat(?:ed|ing)\b",
            r"\borchestration\s+(?:must not|must never|may not|should not|shall not|cannot|can['’]t)\s+be\s+(?:used|enabled|performed)\b",
            r"\b(?:you|workers?|agents?|the system)\s+(?:are|is)\s+(?:not (?:allowed|permitted|authorized)|forbidden)\s+to\s+orchestrat(?:e|ing)\b",
            r"\borchestration\s+(?:is|remains?)\s+(?:forbidden|prohibited|disabled|disallowed|not (?:allowed|permitted)|not to be used)\b",
            r"\b(?:avoid|refrain from)\s+orchestrat(?:ion|ing)\b",
            r"\b(?:no|without)\s+orchestration\b",
            r"\b(?:nie|nigdy)\s+orkiestruj\b",
            r"\bbez\s+orkiestracji\b",
        ),
    )
    if ultra_prohibited:
        codes.append("orchestration_explicit_ultra_prohibition")
    if subagents_prohibited:
        codes.append("orchestration_explicit_subagent_prohibition")
    if orchestration_prohibited:
        codes.append("orchestration_explicit_orchestration_prohibition")

    contradictory = _matches(
        unquoted,
        (
            r"\b(?:use|enable|select|choose|run(?:\s+with)?)\s+ultra\b[^.;\n]{0,100}\b(?:but|however|yet)\b[^.;\n]{0,100}\b(?:do not|don't|never|not)\b[^.;\n]{0,40}\bultra\b",
            r"\b(?:use|spawn|delegate to)\s+(?:sub[- ]?agents?|agents?)\b[^.;\n]{0,100}\b(?:but|however|yet)\b[^.;\n]{0,100}\b(?:do not|don't|never|not)\b[^.;\n]{0,50}\b(?:sub[- ]?agents?|agents?)\b",
        ),
    )
    if contradictory:
        codes.append("orchestration_instruction_conflict_veto")
    if (explicit_ultra_request or delegation_request) and _matches(
        unquoted,
        (
            r"\b(?:but|however|actually|instead|on second thought|wait)\b[^.;\n]{0,60}\b(?:no|not|do not|don['’]t|never|cancel|stop|forget it|withdraw|revoke)\b",
            r"\b(?:then|and then|subsequently|next)\s+(?:do not|don['’]t|never|cancel(?:\s+(?:it|that|this(?:\s+(?:task|request|turn))?))?|stop|forget it|withdraw|revoke)\b",
            r"(?:^|[.;!?\n]\s*)(?:[-*]|\d+[.)])?\s*no\s*,?\s*(?:do not|don['’]t|never|cancel(?:\s+(?:it|that|this(?:\s+(?:task|request|turn))?))?|stop|forget it|withdraw|revoke)\s*(?:[.;!?\n]|$)",
            r"(?:^|[.;!?\n]\s*)(?:[-*]|\d+[.)])?\s*(?:(?:actually|wait|please|correction)\s*[:,]?\s*)?(?:no(?:\s+thanks)?|not anymore|never mind|scratch that|on second thought(?:\s*,?\s*[^.;!?\n]{0,80})?|i changed my mind(?:\s*,?\s*[^.;!?\n]{0,80})?|do not|don['’]t|never|(?:cancel|stop|forget|disregard|ignore|withdraw|revoke)(?:\s+(?:(?:it|that|this)|(?:the|this|that)\s+(?:request|task|turn|instruction|decision|plan|approval)))?)\s*(?:[.;!?\n]|$)",
            r"(?:^|[.;!?\n]\s*)(?:[-*]|\d+[.)])?\s*(?:(?:actually|correction)\s*[:,]?\s*)?(?:use|select|choose|switch\s+to|stay\s+in)\s+(?:max|normal|single[- ]agent(?:\s+mode)?)\b[^.;!?\n]{0,40}(?:instead\b)?",
            r"(?:^|[.;!?\n]\s*)(?:[-*]|\d+[.)])?\s*(?:that|this|the)\s+(?:instruction|request|decision|plan|approval)\s+(?:is|was|has\s+been)\s+(?:withdrawn|revoked|cancelled|canceled|retracted|void|superseded)\b",
            r"(?:^|[.;!?\n]\s*)(?:[-*]|\d+[.)])?\s*i\s+(?:hereby\s+)?(?:withdraw|revoke|cancel|retract|rescind)\s+(?:my|the|this)\s+(?:request|instruction|decision|plan|approval)\b",
        ),
    ):
        codes.append("orchestration_instruction_conflict_veto")
    if _has_later_orchestration_cancellation(text):
        codes.append("orchestration_instruction_conflict_veto")
    return tuple(dict.fromkeys(codes))


def _orchestration_question_present(text: str) -> bool:
    """Detect orchestration language in a complete question without a length cap."""

    clause_start = 0
    for index, character in enumerate(text):
        if character in ".;!\n":
            clause_start = index + 1
            continue
        if character not in "?？":
            continue
        clause = text[clause_start:index]
        if _matches(
            clause,
            (
                r"\bultra\b",
                r"\borchestrat(?:e|ed|es|ing|ion)\b",
                r"\b(?:sub[- ]?agents?|multi[- ]agent|delegat(?:e|ed|es|ing|ion))\b",
            ),
        ):
            return True
        clause_start = index + 1
    return False


_WORKER_POLICY_BOUNDARY_RE = re.compile(
    r"(?P<sentence>[.!?]+|\n+)"
    r"|(?P<continuation>;+)"
    r"|(?P<contrast>\s*,?\s*\b(?:but|however|while|whereas|ale|lecz)\b\s*)"
    r"|(?P<scope_switch>\s*,?\s*\b(?:because|although|when|if|since|as|so|so that|to ensure|leaving)\b\s+(?=(?:(?:the|a)\s+)?(?:coordinator|orchestrator|maintainers?|users?|owners?)\b))"
    r"|(?P<modal_transition>\s*,?\s*\b(?:and|or)\s+(?=(?:(?:(?:each|every|all)\s+)?(?:workers?|sub[- ]?agents?|agents?)\s+)?(?:do not|must not|must never|cannot|can not|may not|shall not|should not|are not (?:allowed|permitted) to|are (?:forbidden|prohibited) (?:to|from)|may|can|shall|will|should|must|are (?:allowed|permitted|required|authorized) to|have permission to)\b))"
    r"|(?P<subject_switch>\s*,?\s*\b(?:and|or)\s+(?=(?:(?:the|a)\s+)?(?:coordinator|orchestrator|maintainers?|users?|owners?)\b))",
    flags=re.IGNORECASE,
)


def _worker_policy_clauses(text: str) -> tuple[tuple[str, bool, bool, bool], ...]:
    """Split bounded clauses and mark contrast clauses that may inherit workers."""

    clauses: list[tuple[str, bool, bool, bool]] = []
    start = 0
    inherit_worker_subject = False
    for match in _WORKER_POLICY_BOUNDARY_RE.finditer(text):
        raw_clause = text[start : match.start()]
        clause = raw_clause.strip(" ,:\t")
        if clause:
            punctuation = match.group(match.lastgroup) if match.lastgroup else ""
            clauses.append(
                (
                    clause,
                    inherit_worker_subject,
                    "?" in punctuation,
                    match.lastgroup == "sentence"
                    and "\n" in punctuation
                    and raw_clause.rstrip().endswith(":"),
                )
            )
        inherit_worker_subject = match.lastgroup in {
            "contrast",
            "continuation",
            "modal_transition",
        }
        start = match.end()
    final = text[start:].strip(" ,:\t")
    if final:
        clauses.append((final, inherit_worker_subject, False, False))
    return tuple(clauses)


def _git_actions(text: str) -> frozenset[str]:
    actions: set[str] = set()
    if re.search(r"\bmerg(?:e|es|ed|ing)\b", text, flags=re.IGNORECASE):
        actions.add("merge")
    if re.search(r"\bpush(?:es|ed|ing)?\b", text, flags=re.IGNORECASE):
        actions.add("push")
    if re.search(
        r"\brewrit(?:e|es|ten|ing)\s+(?:(?:git|repository)\s+)?history\b",
        text,
        flags=re.IGNORECASE,
    ):
        actions.add("rewrite_history")
    if re.search(
        r"\b(?:rebas(?:e|es|ed|ing)|reset(?:s|ting)?|amend(?:s|ed|ing)?(?:\s+(?:a|the))?\s+commit|filter[- ](?:branch|repo))\b",
        text,
        flags=re.IGNORECASE,
    ):
        actions.add("rewrite_history")
    return frozenset(actions)


def _strict_worker_restriction_actions(text: str) -> tuple[frozenset[str], bool]:
    """Accept only a bounded coordinated Git-action list as restriction proof."""

    actions = _git_actions(text)
    residual = re.sub(
        r"\brewrit(?:e|es|ten|ing)\s+(?:(?:git|repository)\s+)?history\b"
        r"|\bmerg(?:e|es|ed|ing)\b"
        r"|\bpush(?:es|ed|ing)?\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    residual = re.sub(
        r"\b(?:and|or|nor|ever)\b"
        r"|\bunder\s+(?:any|all)\s+circumstances\b"
        r"|[,/&]",
        " ",
        residual,
        flags=re.IGNORECASE,
    )
    return actions, not residual.strip()


def _nonexecuting_worker_policy_clause(clause: str) -> bool:
    return _matches(
        clause,
        (
            r"^\s*(?:example|for example|documentation|the documentation)\b",
            r"^\s*(?:explain|describe|document|review|what|how|why)\b",
            r"^\s*(?:this|the) document\b.*\b(?:explains?|describes?|says?)\b",
            r"^\s*(?:the\s+)?(?:question|issue|discussion)\s+is\s+(?:whether|if)\b",
            r"^\s*(?:verify|check|confirm|determine|assess|consider|decide|review|explain|describe|audit|evaluate)\s+(?:whether|if)\b",
            r"^\s*(?:should|may|can|must|could|would|are|is|do|does)\s+(?:the\s+)?(?:workers?|sub[- ]?agents?|agents?)\b",
            r"\b(?:whether|if)\b[^.;\n]{0,160}\b(?:workers?|sub[- ]?agents?|agents?)\b",
            r"^\s*(?:is|are)\s+it\s+(?:true|correct)\s+that\b",
        ),
    )


def _meta_introduces_next_worker_clause(clause: str) -> bool:
    """Identify a bounded meta heading whose next clause is quoted content."""

    return _matches(
        clause,
        (
            r"^\s*(?:translate|repeat|quote|paraphrase|summari[sz]e|explain|describe|review)\b[^.;!?\n]{0,120}\b(?:following|below|rule|sentence|statement|text|prompt|example)\b",
            r"^\s*(?:#{1,6}\s+|[-*]\s+)?(?:example|sample|illustration|quoted (?:text|prompt))\s*$",
            r"^\s*(?:#{1,6}\s+|[-*]\s+)?(?:translation|quotation|paraphrase|summary)\s*$",
            r"^\s*(?:here|this|below|above)\s+is\s+(?:(?:the|an?)\s+)?(?:translation|quotation|paraphrase|summary|example|sample|illustration|quoted (?:text|prompt)|instruction example)\s*$",
            r"^\s*(?:the\s+)?(?:translation|quotation|paraphrase|summary|example|sample|illustration|quoted (?:text|prompt)|instruction example)\s+follows\s*$",
            r"^\s*(?:the\s+)?following\s+(?:is|shows?)\s+(?:an?\s+)?(?:example|rule|sentence|statement|text|prompt)\b",
        ),
    )


def _analyze_worker_git_policy(text: str) -> _WorkerGitPolicy:
    """Prove worker Git restrictions independently within bounded clauses."""

    masked = _mask_quoted_text(text)
    restricted: set[str] = set()
    permitted: set[str] = set()
    authority_requested = False

    worker_subject_pattern = r"(?:(?:the|each|every|all)\s+)?(?:workers?|sub[- ]?agents?|agents?)"
    negative_patterns = (
        rf"^\s*{worker_subject_pattern}\s*[:,-]?\s*(?:do not|must not|must never|cannot|can not|may not|shall not|should not|are not (?:allowed|permitted) to|are (?:forbidden|prohibited) (?:to|from))\s+(?P<actions>.+)$",
        rf"^\s*do not let\s+{worker_subject_pattern}\s+(?P<actions>.+)$",
        rf"^\s*no\s+{worker_subject_pattern}\s+(?:(?:may|can|shall)\s+|(?:is|are)\s+allowed\s+to\s+)?(?P<actions>.+)$",
    )
    positive_patterns = (
        rf"\b{worker_subject_pattern}\s+(?:(?:may|can|shall|will|should|must)(?!\s+not\b)|are (?:allowed|permitted|required|authorized|free|entitled) to|(?:have|retain) (?:permission|authority) to)\s+(?P<actions>.+)$",
        rf"\b{worker_subject_pattern}\s+independently\s+(?P<actions>.+)$",
        rf"^\s*(?:allow|let|permit|authorize)\s+{worker_subject_pattern}\s+(?:to\s+)?(?P<actions>.+)$",
        rf"^\s*(?:(?:the|a)\s+)?(?:coordinator|orchestrator|maintainers?|owners?)\s+(?:allows?|lets?|permits?|authorizes?)\s+{worker_subject_pattern}\s+(?:to\s+)?(?P<actions>.+)$",
        rf"^\s*(?:give|grant)\s+{worker_subject_pattern}\s+(?:permission|authority)\s+to\s+(?P<actions>.+)$",
    )
    workers_mentioned = re.search(
        rf"\b{worker_subject_pattern}\b",
        masked,
        flags=re.IGNORECASE,
    ) is not None
    ambiguous_instruction = False

    suppress_remaining_meta_block = False
    for clause, inherit_worker_subject, is_question, introduces_block in _worker_policy_clauses(masked):
        if suppress_remaining_meta_block:
            continue
        if {"merge", "push", "rewrite_history"}.issubset(restricted):
            ambiguous_instruction = True
            continue
        if introduces_block or _meta_introduces_next_worker_clause(clause):
            suppress_remaining_meta_block = True
            continue
        if is_question or _nonexecuting_worker_policy_clause(clause):
            continue
        if restricted and _matches(
            clause,
            (
                r"^\s*(?:unless|except|until|only if|subject to|provided that)\b",
                r"^\s*(?:this|the)\s+restriction\s+(?:does\s+not|doesn['’]t|may\s+not)\s+apply\b",
                r"^\s*(?:an?\s+)?exception\b",
                r"^\s*(?:this|the|these|those|all)\s+restrictions?\s+(?:do|does)\s+not\s+apply\b",
                r"^\s*(?:this|the|these|those|all)\s+restrictions?\s+(?:(?:is|are)\s+)?(?:lifted|waived|revoked|expired|suspended|overridden)\b",
            ),
        ):
            ambiguous_instruction = True
            continue
        explicit_worker = re.search(
            rf"\b{worker_subject_pattern}\b",
            clause,
            flags=re.IGNORECASE,
        ) is not None
        explicit_other_subject = _matches(
            clause,
            (
                r"\b(?:coordinator|orchestrator|maintainers?|users?|owners?)\b",
                r"\b(?:documentation|document|example)\b",
            ),
        )
        may_inherit = inherit_worker_subject and not explicit_other_subject

        negative_actions: set[str] = set()
        for pattern in negative_patterns:
            match = re.search(pattern, clause, flags=re.IGNORECASE)
            if match is not None:
                actions, exact = _strict_worker_restriction_actions(
                    match.group("actions")
                )
                negative_actions.update(actions)
                if actions and not exact:
                    ambiguous_instruction = True
        if may_inherit:
            match = re.search(
                r"^\s*(?:do not|must not|must never|cannot|can not|may not|shall not|should not|are not (?:allowed|permitted) to|are (?:forbidden|prohibited) (?:to|from))\s+(?P<actions>.+)$",
                clause,
                flags=re.IGNORECASE,
            )
            if match is not None:
                actions, exact = _strict_worker_restriction_actions(
                    match.group("actions")
                )
                negative_actions.update(actions)
                if actions and not exact:
                    ambiguous_instruction = True

        positive_actions: set[str] = set()
        if re.search(
            rf"\bno\s+{worker_subject_pattern}\b",
            clause,
            flags=re.IGNORECASE,
        ) is None:
            for pattern in positive_patterns:
                match = re.search(pattern, clause, flags=re.IGNORECASE)
                if match is not None:
                    positive_actions.update(_git_actions(match.group("actions")))
        if may_inherit:
            match = re.search(
                r"^\s*(?:(?:may|can|shall|will|should|must)(?!\s+not\b)|are (?:allowed|permitted|required|authorized|free|entitled) to|(?:have|retain) (?:permission|authority) to)\s+(?P<actions>.+)$",
                clause,
                flags=re.IGNORECASE,
            )
            if match is not None:
                positive_actions.update(_git_actions(match.group("actions")))
        if workers_mentioned:
            match = re.search(
                r"\b(?:they|those workers?)\s+(?:(?:may|can|shall|will|should|must)(?!\s+not\b)|are (?:allowed|permitted|required|authorized|free|entitled) to|(?:have|retain) (?:permission|authority) to)\s+(?P<actions>.+)$",
                clause,
                flags=re.IGNORECASE,
            )
            if match is not None:
                positive_actions.update(_git_actions(match.group("actions")))
            match = re.search(
                r"^\s*(?:allow|let|permit|authorize)\s+(?:them|those workers?)\s+(?:to\s+)?(?P<actions>.+)$",
                clause,
                flags=re.IGNORECASE,
            )
            if match is not None:
                positive_actions.update(_git_actions(match.group("actions")))

        clause_git_actions = _git_actions(clause)
        safe_direct_integrator_action = _matches(
            clause,
            (
                r"^\s*(?:(?:the|a)\s+)?(?:coordinator|orchestrator|maintainers?|owners?)\s+(?:may|can|shall|will|should|must|is\s+(?:allowed|permitted|authorized)\s+to|has\s+(?:permission|authority)\s+to)\s+(?:merge|push|rewrite\s+(?:(?:git|repository)\s+)?history|rebase|reset|amend)\b",
            ),
        ) and not explicit_worker
        worker_referential = explicit_worker or (
            workers_mentioned
            and _matches(
                clause,
                (r"\b(?:they|them|those workers?|their)\b",),
            )
        )
        if (
            clause_git_actions
            and worker_referential
            and not negative_actions
            and not positive_actions
        ):
            ambiguous_instruction = True
        if (
            clause_git_actions
            and _matches(
                clause,
                (
                    r"\b(?:allow(?:s|ed)?|let(?:s)?|permit(?:s|ted)?|authoriz(?:e|es|ed)|grant(?:s|ed)?|permission|may|can|shall|will|is\s+allowed|are\s+allowed)\b",
                ),
            )
            and not safe_direct_integrator_action
            and not negative_actions
            and not positive_actions
        ):
            ambiguous_instruction = True
        if (
            clause_git_actions
            and workers_mentioned
            and not negative_actions
            and not positive_actions
            and not safe_direct_integrator_action
        ):
            ambiguous_instruction = True

        if negative_actions and _matches(
            clause,
            (r"\b(?:except|unless|until|only if|subject to|provided that)\b",),
        ):
            ambiguous_instruction = True

        restricted.update(negative_actions)
        permitted.update(positive_actions)
        if explicit_worker and positive_actions:
            authority_requested = True

    conflicts = restricted & permitted
    return _WorkerGitPolicy(
        cannot_merge="merge" in restricted and "merge" not in permitted,
        cannot_push="push" in restricted and "push" not in permitted,
        cannot_rewrite_history=(
            "rewrite_history" in restricted and "rewrite_history" not in permitted
        ),
        instruction_conflict=bool(conflicts) or ambiguous_instruction,
        authority_requested=authority_requested,
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and _HEX_64.fullmatch(value) is not None


def _required_string(policy: Mapping[str, object], field: str) -> str:
    value = policy.get(field)
    if not isinstance(value, str) or not value:
        raise OrchestrationPolicyError(f"orchestration policy {field} is invalid")
    return value


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise OrchestrationPolicyError(f"orchestration policy {field} is invalid")
    if len(set(value)) != len(value):
        raise OrchestrationPolicyError(f"orchestration policy {field} has duplicates")
    return tuple(value)


def _bounded_integer(value: object, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise OrchestrationPolicyError(f"orchestration policy {field} is invalid")
    return value
