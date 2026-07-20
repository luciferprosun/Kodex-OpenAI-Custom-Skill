from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from smart_codex.app_server_router import make_ultra_approval_evidence
from smart_codex.app_server_router.orchestration_policy import (
    ORCHESTRATION_MODES,
    ORDINARY_REASONING_EFFORTS,
    EFFECTIVE_TURN_CONTEXT_SCHEMA_VERSION,
    ULTRA_APPROVAL_EVIDENCE_SCHEMA_VERSION,
    ULTRA_DECISION_SIGNATURE_VERSION,
    OrchestrationPolicy,
    UltraApprovalEvidence,
    analyze_orchestration_structure,
)
from smart_codex.app_server_router.prompt_features import extract_task_features
from smart_codex.app_server_router.turn_router import (
    RoutingFailure,
    canonical_effective_turn_context,
    effective_turn_context_hash,
)
from smart_codex.policy_version import (
    MODEL_POLICY_VERSION,
    normalize_policy_provenance,
)
from smart_codex.router import route_prompt
from smart_codex.runtime.telemetry.schema import RUN_RECORD_FIELDS, SCHEMA_VERSION

from app_server_test_helpers import live_model_data, turn_message, turn_router


ROOT = Path(__file__).resolve().parents[1]
NOW = 1_800_000_000

BROAD_RESEARCH = (
    "Research four independent areas: official API capabilities, security model, "
    "pricing structure, and deployment constraints. Return one evidence packet "
    "per area and combine the outputs at the end."
)
REPOSITORY_AUDIT = (
    "Audit this branch separately for security defects, missing tests, backward "
    "compatibility, and maintainability. Combine the findings at the end."
)
PARTITIONED_CORPUS = (
    "Review a very large document corpus divided into four independent collections "
    "and return bounded findings from each collection."
)
DISJOINT_WRITE_PLAN = (
    "Use gpt-5.6-sol to implement four independent modules in parallel. Each "
    "workstream returns a bounded result. Use disjoint module ownership in isolated "
    "worktrees with explicit bounded write scope. One central coordinator owns "
    "final integration. Workers must not merge, push, or rewrite history."
)
WRITE_ADMISSION_BASE = (
    "Use gpt-5.6-sol to implement four independent modules in parallel. Each "
    "workstream returns a bounded result. Use disjoint module ownership in isolated "
    "worktrees with explicit bounded write scope. One central coordinator owns "
    "final integration. "
)


def _tui_message(prompt: str, *, request_id: int = 7) -> dict[str, object]:
    message = turn_message(prompt, request_id=request_id)
    message["params"]["collaborationMode"] = {  # type: ignore[index]
        "mode": "default",
        "settings": {
            "model": "gpt-5.6-sol",
            "reasoning_effort": "max",
            "developer_instructions": None,
        },
    }
    return message


def _pending(prompt: str, *, data=None, request_id: int = 7):
    router = turn_router(data)
    message = _tui_message(prompt, request_id=request_id)
    routed = router.route_message(message, now_epoch_seconds=NOW)
    assert routed.ultra_recommendation == "recommended"
    assert routed.ultra_approval == "pending"
    assert routed.ultra_proposal is not None
    return router, message, routed


def _approved(prompt: str, *, data=None):
    router, message, pending = _pending(prompt, data=data)
    evidence = make_ultra_approval_evidence(
        pending.ultra_proposal,
        now_epoch_seconds=NOW,
    )
    approved = router.route_message(
        message,
        ultra_approval=evidence,
        now_epoch_seconds=NOW,
    )
    return router, message, pending, approved


def _analysis(prompt: str):
    decision = route_prompt(prompt, dry_run=True)
    features = extract_task_features(
        prompt,
        decision,
        required_modalities=("text",),
    )
    return analyze_orchestration_structure(prompt, features)


def _assert_changed_context_rejected(
    mutate,
    *,
    prompt: str = BROAD_RESEARCH,
) -> None:
    router, message, pending = _pending(prompt)
    evidence = make_ultra_approval_evidence(
        pending.ultra_proposal,
        now_epoch_seconds=NOW,
    )
    changed = deepcopy(message)
    mutate(changed)

    routed = router.route_message(
        changed,
        ultra_approval=evidence,
        now_epoch_seconds=NOW,
    )

    assert routed.ultra_approval in {"invalid", "not_requested"}
    assert routed.orchestration_mode == "single_agent"
    assert routed.effort != "ultra"


@pytest.mark.parametrize(
    ("model_name", "prompt"),
    [
        ("gpt-5.6-sol", "Use gpt-5.6-sol with reasoning effort max for a final audit."),
        ("gpt-5.6-terra", "Use gpt-5.6-terra with reasoning effort max for a final audit."),
        ("gpt-5.6-luna", "Use gpt-5.6-luna with reasoning effort max for a final audit."),
    ],
)
def test_max_is_ordinary_single_agent_for_all_gpt_5_6_profiles(
    model_name: str,
    prompt: str,
) -> None:
    routed = turn_router().route_message(_tui_message(prompt), now_epoch_seconds=NOW)

    assert routed.selected_model == model_name
    assert routed.ordinary_reasoning_effort == "max"
    assert routed.effort == "max"
    assert routed.orchestration_mode == "single_agent"
    assert routed.planned_worker_count == 0


def test_ordinary_effort_model_excludes_ultra() -> None:
    assert ORDINARY_REASONING_EFFORTS == (
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    )
    assert "ultra" not in ORDINARY_REASONING_EFFORTS
    assert ORCHESTRATION_MODES == ("single_agent", "ultra_subagents")


@pytest.mark.parametrize("prompt", [BROAD_RESEARCH, REPOSITORY_AUDIT, PARTITIONED_CORPUS])
def test_structurally_parallel_read_work_can_be_recommended_but_stays_max_pending(
    prompt: str,
) -> None:
    _, _, routed = _pending(prompt)

    assert routed.workstream_count in {"2", "3", "4_plus"}
    assert routed.dependency_shape == "parallel"
    assert routed.parallel_benefit == "material"
    assert routed.orchestration_work_mode == "read_heavy"
    assert routed.ordinary_reasoning_effort == "max"
    assert routed.effort == "max"
    assert routed.orchestration_mode == "single_agent"
    assert routed.ultra_human_approval_required is True


def test_two_large_independent_workstreams_are_sufficient_but_not_automatically_approved() -> None:
    prompt = (
        "Conduct a large research review across two independent areas: security and "
        "pricing. Return one bounded report per area and combine the outputs at the end."
    )
    _, _, routed = _pending(prompt)

    assert routed.workstream_count == "2"
    assert routed.planned_worker_count == 2
    assert routed.ultra_approval == "pending"
    assert routed.message["params"]["approvalPolicy"] == "on-request"
    assert routed.ultra_proposal.fallback_model == routed.selected_model
    assert routed.ultra_proposal.fallback_reasoning_effort == "max"


def test_task_bound_approval_emits_consistent_ultra_wire_for_sol() -> None:
    _, _, pending, approved = _approved(
        "Use gpt-5.6-sol. " + REPOSITORY_AUDIT
    )

    assert pending.effort == "max"
    assert approved.selected_model == "gpt-5.6-sol"
    assert approved.ordinary_reasoning_effort == "max"
    assert approved.orchestration_mode == "ultra_subagents"
    assert approved.ultra_approval == "approved"
    assert approved.effort == "ultra"
    params = approved.message["params"]
    assert params["effort"] == "ultra"
    assert params["collaborationMode"]["settings"]["reasoning_effort"] == "ultra"


def test_task_bound_approval_emits_consistent_ultra_wire_for_terra() -> None:
    _, _, _, approved = _approved(
        "Use gpt-5.6-terra. " + BROAD_RESEARCH
    )

    assert approved.selected_model == "gpt-5.6-terra"
    assert approved.ordinary_reasoning_effort == "max"
    assert approved.orchestration_mode == "ultra_subagents"
    assert approved.effort == "ultra"


def test_generic_on_request_policy_never_counts_as_ultra_approval() -> None:
    _, _, routed = _pending(BROAD_RESEARCH)

    assert routed.approval_policy == "on-request"
    assert routed.ultra_approval == "pending"
    assert routed.orchestration_mode == "single_agent"
    assert routed.effort != "ultra"


def test_denied_approval_falls_back_to_max() -> None:
    router, message, pending = _pending(BROAD_RESEARCH)
    evidence = make_ultra_approval_evidence(
        pending.ultra_proposal,
        now_epoch_seconds=NOW,
        approved=False,
    )

    denied = router.route_message(
        message,
        ultra_approval=evidence,
        now_epoch_seconds=NOW,
    )

    assert denied.ultra_approval == "denied"
    assert denied.orchestration_mode == "single_agent"
    assert denied.ordinary_reasoning_effort == "max"
    assert denied.effort == "max"
    assert denied.orchestration_fallback_reason_code == "ultra_approval_denied"


def test_stale_approval_is_invalid_and_falls_back_to_max() -> None:
    router, message, pending = _pending(BROAD_RESEARCH)
    evidence = make_ultra_approval_evidence(
        pending.ultra_proposal,
        now_epoch_seconds=NOW,
        ttl_seconds=30,
    )

    stale = router.route_message(
        message,
        ultra_approval=evidence,
        now_epoch_seconds=NOW + 31,
    )

    assert stale.ultra_approval == "invalid"
    assert stale.orchestration_mode == "single_agent"
    assert stale.effort == "max"


@pytest.mark.parametrize(
    "modified_prompt",
    [
        "Use gpt-5.6-sol. " + BROAD_RESEARCH,
        BROAD_RESEARCH.replace("four independent areas", "three independent areas"),
        BROAD_RESEARCH.replace("security model", "performance model"),
    ],
)
def test_approval_is_invalidated_by_model_worker_or_plan_change(
    modified_prompt: str,
) -> None:
    router, _, pending = _pending(BROAD_RESEARCH)
    evidence = make_ultra_approval_evidence(
        pending.ultra_proposal,
        now_epoch_seconds=NOW,
    )

    changed = router.route_message(
        _tui_message(modified_prompt),
        ultra_approval=evidence,
        now_epoch_seconds=NOW,
    )

    assert changed.ultra_approval in {"invalid", "not_requested"}
    assert changed.orchestration_mode == "single_agent"
    assert changed.effort != "ultra"


def test_approval_is_bound_to_current_turn_scope() -> None:
    router, _, pending = _pending(BROAD_RESEARCH, request_id=7)
    evidence = make_ultra_approval_evidence(
        pending.ultra_proposal,
        now_epoch_seconds=NOW,
    )

    changed = router.route_message(
        _tui_message(BROAD_RESEARCH, request_id=8),
        ultra_approval=evidence,
        now_epoch_seconds=NOW,
    )

    assert changed.ultra_approval == "invalid"
    assert changed.effort == "max"


def test_effective_turn_context_canonical_bytes_and_hash_are_deterministic() -> None:
    first = _tui_message(BROAD_RESEARCH)
    first["params"]["serviceTier"] = "priority"  # type: ignore[index]
    second = {
        "params": {
            key: value
            for key, value in reversed(list(first["params"].items()))  # type: ignore[union-attr]
        },
        "id": first["id"],
        "method": first["method"],
    }

    first_bytes = canonical_effective_turn_context(first)
    second_bytes = canonical_effective_turn_context(second)

    assert first_bytes == second_bytes
    assert effective_turn_context_hash(first) == effective_turn_context_hash(second)
    assert effective_turn_context_hash(first) == effective_turn_context_hash(first)
    assert len(effective_turn_context_hash(first)) == 64


def test_effective_turn_context_preserves_meaningful_input_order() -> None:
    first = _tui_message(
        BROAD_RESEARCH,
    )
    first["params"]["input"].extend(  # type: ignore[index,union-attr]
        [
            {"type": "image", "id": "image-a", "url": "memory://image-a"},
            {"type": "image", "id": "image-b", "url": "memory://image-b"},
        ]
    )
    second = deepcopy(first)
    second["params"]["input"][-2:] = reversed(  # type: ignore[index]
        second["params"]["input"][-2:]  # type: ignore[index]
    )

    assert canonical_effective_turn_context(first) != canonical_effective_turn_context(second)
    assert effective_turn_context_hash(first) != effective_turn_context_hash(second)


def test_effective_turn_context_distinguishes_missing_null_and_empty_values() -> None:
    missing = _tui_message(BROAD_RESEARCH)
    null = deepcopy(missing)
    empty = deepcopy(missing)
    null["params"]["serviceTier"] = None  # type: ignore[index]
    empty["params"]["serviceTier"] = ""  # type: ignore[index]

    hashes = {
        effective_turn_context_hash(missing),
        effective_turn_context_hash(null),
        effective_turn_context_hash(empty),
    }

    assert len(hashes) == 3


@pytest.mark.parametrize(
    "field",
    ["outputSchema", "serviceTier", "personality", "config"],
)
def test_every_other_forwarded_execution_field_is_approval_bound(field: str) -> None:
    values = {
        "outputSchema": {"type": "object"},
        "serviceTier": "priority",
        "personality": "pragmatic",
        "config": {"feature": "different"},
    }

    def mutate(message: dict[str, object]) -> None:
        message["params"][field] = values[field]  # type: ignore[index]

    _assert_changed_context_rejected(mutate)


def test_changed_image_identity_invalidates_approval() -> None:
    router = turn_router()
    message = _tui_message(BROAD_RESEARCH)
    message["params"]["input"].append(  # type: ignore[index,union-attr]
        {"type": "image", "id": "image-a", "url": "memory://image-a"}
    )
    pending = router.route_message(message, now_epoch_seconds=NOW)
    assert pending.ultra_proposal is not None
    evidence = make_ultra_approval_evidence(pending.ultra_proposal, now_epoch_seconds=NOW)
    changed = deepcopy(message)
    changed["params"]["input"][-1]["id"] = "image-b"  # type: ignore[index]

    routed = router.route_message(changed, ultra_approval=evidence, now_epoch_seconds=NOW)

    assert routed.ultra_approval == "invalid"
    assert routed.effort != "ultra"


def test_changed_image_order_invalidates_approval() -> None:
    router = turn_router()
    message = _tui_message(BROAD_RESEARCH)
    message["params"]["input"].extend(  # type: ignore[index,union-attr]
        [
            {"type": "image", "id": "image-a", "url": "memory://image-a"},
            {"type": "image", "id": "image-b", "url": "memory://image-b"},
        ]
    )
    pending = router.route_message(message, now_epoch_seconds=NOW)
    assert pending.ultra_proposal is not None
    evidence = make_ultra_approval_evidence(pending.ultra_proposal, now_epoch_seconds=NOW)
    changed = deepcopy(message)
    changed["params"]["input"][-2:] = reversed(  # type: ignore[index]
        changed["params"]["input"][-2:]  # type: ignore[index]
    )

    routed = router.route_message(changed, ultra_approval=evidence, now_epoch_seconds=NOW)

    assert routed.ultra_approval == "invalid"
    assert routed.effort != "ultra"


@pytest.mark.parametrize(
    ("item_type", "first_id", "second_id"),
    [
        ("skill", "skill-a", "skill-b"),
        ("mention", "mention-a", "mention-b"),
    ],
)
def test_changed_skill_or_mention_identity_invalidates_approval(
    item_type: str,
    first_id: str,
    second_id: str,
) -> None:
    router = turn_router()
    message = _tui_message(BROAD_RESEARCH)
    message["params"]["input"].append(  # type: ignore[index,union-attr]
        {"type": item_type, "id": first_id, "name": first_id}
    )
    pending = router.route_message(message, now_epoch_seconds=NOW)
    assert pending.ultra_proposal is not None
    evidence = make_ultra_approval_evidence(pending.ultra_proposal, now_epoch_seconds=NOW)
    changed = deepcopy(message)
    changed["params"]["input"][-1]["id"] = second_id  # type: ignore[index]

    routed = router.route_message(changed, ultra_approval=evidence, now_epoch_seconds=NOW)

    assert routed.ultra_approval == "invalid"
    assert routed.effort != "ultra"


def test_changed_cwd_invalidates_approval() -> None:
    def mutate(message: dict[str, object]) -> None:
        message["params"]["cwd"] = "/different/repository"  # type: ignore[index]

    _assert_changed_context_rejected(mutate)


def test_changed_collaboration_developer_instructions_invalidate_approval() -> None:
    def mutate(message: dict[str, object]) -> None:
        message["params"]["collaborationMode"]["settings"][  # type: ignore[index]
            "developer_instructions"
        ] = "Use a different bounded execution contract."

    _assert_changed_context_rejected(mutate)


def test_changed_thread_id_invalidates_approval() -> None:
    def mutate(message: dict[str, object]) -> None:
        message["params"]["threadId"] = "thread-other"  # type: ignore[index]

    _assert_changed_context_rejected(mutate)


def test_changed_request_id_invalidates_approval() -> None:
    def mutate(message: dict[str, object]) -> None:
        message["id"] = 8

    _assert_changed_context_rejected(mutate)


def test_changed_previous_model_session_state_invalidates_approval() -> None:
    router = turn_router()
    message = _tui_message(BROAD_RESEARCH)
    pending = router.route_message(
        message,
        previous_model="gpt-5.6-sol",
        now_epoch_seconds=NOW,
    )
    assert pending.ultra_proposal is not None
    evidence = make_ultra_approval_evidence(pending.ultra_proposal, now_epoch_seconds=NOW)

    routed = router.route_message(
        message,
        previous_model="gpt-5.6-terra",
        ultra_approval=evidence,
        now_epoch_seconds=NOW,
    )

    assert routed.ultra_approval == "invalid"
    assert routed.effort != "ultra"


def test_unsupported_effective_turn_value_is_rejected_not_ignored() -> None:
    message = _tui_message(BROAD_RESEARCH)
    message["params"]["opaque"] = object()  # type: ignore[index]

    with pytest.raises(RoutingFailure, match="effective turn context"):
        canonical_effective_turn_context(message)
    with pytest.raises(RoutingFailure, match="effective turn context"):
        turn_router().route_message(message, now_epoch_seconds=NOW)


def test_context_binding_schema_and_signature_versions_are_explicit() -> None:
    _, _, pending = _pending(BROAD_RESEARCH)
    proposal = pending.ultra_proposal
    evidence = make_ultra_approval_evidence(proposal, now_epoch_seconds=NOW)

    assert proposal.effective_turn_context_schema_version == EFFECTIVE_TURN_CONTEXT_SCHEMA_VERSION
    assert proposal.decision_signature_version == ULTRA_DECISION_SIGNATURE_VERSION
    assert len(proposal.effective_turn_context_hash) == 64
    assert evidence.schema_version == ULTRA_APPROVAL_EVIDENCE_SCHEMA_VERSION
    assert evidence.decision_signature_version == ULTRA_DECISION_SIGNATURE_VERSION
    assert evidence.effective_turn_context_schema_version == EFFECTIVE_TURN_CONTEXT_SCHEMA_VERSION
    assert evidence.effective_turn_context_hash == proposal.effective_turn_context_hash


@pytest.mark.parametrize(
    "evidence_change",
    [
        {"effective_turn_context_hash": ""},
        {"effective_turn_context_hash": "0" * 64},
        {"effective_turn_context_schema_version": "legacy-context-v0"},
        {"decision_signature_version": "ultra-decision-signature-v1"},
        {"schema_version": "ultra-approval-evidence-v1"},
    ],
)
def test_missing_malformed_or_legacy_context_evidence_is_rejected(
    evidence_change: dict[str, str],
) -> None:
    router, message, pending = _pending(BROAD_RESEARCH)
    evidence = make_ultra_approval_evidence(pending.ultra_proposal, now_epoch_seconds=NOW)
    malformed = replace(evidence, **evidence_change)

    routed = router.route_message(
        message,
        ultra_approval=malformed,
        now_epoch_seconds=NOW,
    )

    assert routed.ultra_approval == "invalid"
    assert routed.orchestration_mode == "single_agent"
    assert routed.effort == "max"


def test_legacy_evidence_object_without_context_binding_is_rejected() -> None:
    class LegacyEvidence:
        def __init__(self, decision_signature: str):
            self.decision_signature = decision_signature
            self.status = "approved"
            self.policy_version = MODEL_POLICY_VERSION
            self.issued_at_epoch_seconds = NOW
            self.expires_at_epoch_seconds = NOW + 60

    router, message, pending = _pending(BROAD_RESEARCH)
    legacy = LegacyEvidence(pending.ultra_proposal.decision_signature)

    routed = router.route_message(  # type: ignore[arg-type]
        message,
        ultra_approval=legacy,
        now_epoch_seconds=NOW,
    )

    assert routed.ultra_approval == "invalid"
    assert routed.effort == "max"


def test_evidence_for_one_effective_context_cannot_authorize_another() -> None:
    router, first_message, first = _pending(BROAD_RESEARCH)
    evidence = make_ultra_approval_evidence(first.ultra_proposal, now_epoch_seconds=NOW)
    second_message = deepcopy(first_message)
    second_message["params"]["cwd"] = "/another/repository"  # type: ignore[index]
    second_message["params"]["input"].append(  # type: ignore[index,union-attr]
        {"type": "skill", "id": "different-skill"}
    )

    second = router.route_message(
        second_message,
        ultra_approval=evidence,
        now_epoch_seconds=NOW,
    )

    assert first.ultra_proposal.effective_turn_context_hash != effective_turn_context_hash(
        second_message
    )
    assert second.ultra_approval == "invalid"
    assert second.effort != "ultra"


@pytest.mark.parametrize(
    "prompt",
    [
        "Find the single root cause of this nondeterministic transaction failure and produce the smallest correct repair.",
        "Inspect the schema, design the migration from the findings, then implement it, then run compatibility tests.",
        "Rename one button label.",
        "Run a deterministic benchmark case across four independent areas and combine bounded results at the end.",
        "Do this using as few tokens as possible, but use Ultra.",
        'Explain what the phrase "use Ultra with parallel subagents" means.',
        'The documentation says "delegate to four parallel agents". Explain it.',
        "Use four agents to edit the same router.py file simultaneously.",
        "Use Ultra for several speculative workstreams that may or may not exist.",
    ],
)
def test_hard_vetoes_never_emit_ultra(prompt: str) -> None:
    routed = turn_router().route_message(_tui_message(prompt), now_epoch_seconds=NOW)

    assert routed.orchestration_mode == "single_agent"
    assert routed.effort != "ultra"
    assert routed.ultra_recommendation == "not_recommended"


@pytest.mark.parametrize(
    ("prefix", "expected_reason"),
    [
        ("Do not use Ultra. ", "orchestration_explicit_ultra_prohibition"),
        ("Do not use subagents. ", "orchestration_explicit_subagent_prohibition"),
        ("Do not orchestrate this task. ", "orchestration_explicit_orchestration_prohibition"),
        ("Use normal mode, not Ultra. ", "orchestration_explicit_ultra_prohibition"),
        ("Explain what Ultra orchestration means. ", "orchestration_nonexecuting_language_veto"),
        ("Example: a user could say 'use subagents'. ", "orchestration_nonexecuting_language_veto"),
        ("The documentation says: 'use Ultra'. ", "orchestration_nonexecuting_language_veto"),
        ("Review this quoted prompt: 'Use Ultra for the task.' ", "orchestration_nonexecuting_language_veto"),
        ("'Use Ultra for this task.' ", "orchestration_nonexecuting_language_veto"),
    ],
)
def test_orchestration_prohibitions_and_nonexecuting_mentions_are_hard_vetoes(
    prefix: str,
    expected_reason: str,
) -> None:
    routed = turn_router().route_message(
        _tui_message(prefix + BROAD_RESEARCH),
        now_epoch_seconds=NOW,
    )

    assert routed.ultra_recommendation == "not_recommended"
    assert routed.ultra_approval == "not_requested"
    assert routed.ultra_proposal is None
    assert routed.orchestration_mode == "single_agent"
    assert routed.effort != "ultra"
    assert expected_reason in routed.orchestration_reason_codes


@pytest.mark.parametrize(
    ("prefix", "expected_reason"),
    [
        ("Workers must not use Ultra. ", "orchestration_explicit_ultra_prohibition"),
        ("Workers must not use subagents. ", "orchestration_explicit_subagent_prohibition"),
        ("Avoid Ultra for this task. ", "orchestration_explicit_ultra_prohibition"),
        ("Avoid using subagents. ", "orchestration_explicit_subagent_prohibition"),
        ("This task must not orchestrate work. ", "orchestration_explicit_orchestration_prohibition"),
        ("Use one agent only. ", "orchestration_explicit_subagent_prohibition"),
        ("Use single-agent only. ", "orchestration_explicit_subagent_prohibition"),
        ("Ultra must not be used. ", "orchestration_explicit_ultra_prohibition"),
        ("Ultra may not be used. ", "orchestration_explicit_ultra_prohibition"),
        ("You may not use Ultra. ", "orchestration_explicit_ultra_prohibition"),
        ("Do not ever use Ultra. ", "orchestration_explicit_ultra_prohibition"),
        ("Under no circumstances use Ultra. ", "orchestration_explicit_ultra_prohibition"),
        ("Do not, under any circumstances, switch to Ultra. ", "orchestration_explicit_ultra_prohibition"),
        ("Use Max instead of Ultra. ", "orchestration_explicit_ultra_prohibition"),
        ("You are not allowed to use Ultra. ", "orchestration_explicit_ultra_prohibition"),
        ("Subagents are forbidden. ", "orchestration_explicit_subagent_prohibition"),
        ("Subagents must not be used. ", "orchestration_explicit_subagent_prohibition"),
        ("Subagents may not be used. ", "orchestration_explicit_subagent_prohibition"),
        ("Delegation is prohibited. ", "orchestration_explicit_subagent_prohibition"),
        ("You are not allowed to delegate this task. ", "orchestration_explicit_subagent_prohibition"),
        ("Orchestration is prohibited. ", "orchestration_explicit_orchestration_prohibition"),
        ("This task must not be orchestrated. ", "orchestration_explicit_orchestration_prohibition"),
        ("Orchestration must not be used. ", "orchestration_explicit_orchestration_prohibition"),
        ("You are not allowed to orchestrate this task. ", "orchestration_explicit_orchestration_prohibition"),
        ("Don’t use Ultra. ", "orchestration_explicit_ultra_prohibition"),
        ("Summarize how to use Ultra. ", "orchestration_nonexecuting_language_veto"),
        ("Analyze whether Ultra should be used. ", "orchestration_nonexecuting_language_veto"),
        ("Evaluate whether Ultra is appropriate. ", "orchestration_nonexecuting_language_veto"),
        ("Determine whether Ultra should be used. ", "orchestration_nonexecuting_language_veto"),
        ("Decide whether Ultra should be used. ", "orchestration_nonexecuting_language_veto"),
        ("Is Ultra appropriate? ", "orchestration_nonexecuting_language_veto"),
        ("May Ultra be used? ", "orchestration_nonexecuting_language_veto"),
        ("Discuss Ultra orchestration. ", "orchestration_nonexecuting_language_veto"),
        ("Tell me about Ultra orchestration. ", "orchestration_nonexecuting_language_veto"),
        ("Tell us about Ultra orchestration. ", "orchestration_nonexecuting_language_veto"),
        ("Give an overview of Ultra orchestration. ", "orchestration_nonexecuting_language_veto"),
        ("Summarize Ultra orchestration. ", "orchestration_nonexecuting_language_veto"),
        ("Audit the Ultra policy. ", "orchestration_nonexecuting_language_veto"),
        ("Translate the phrase 'use Ultra'. ", "orchestration_nonexecuting_language_veto"),
        ("„Use Ultra for this task.” ", "orchestration_nonexecuting_language_veto"),
        ("„Use Ultra for this task.“ ", "orchestration_nonexecuting_language_veto"),
        ("‘Use subagents for this task.’ ", "orchestration_nonexecuting_language_veto"),
        ("「Use Ultra for this task.」 ", "orchestration_nonexecuting_language_veto"),
        ("『Use Ultra for this task.』 ", "orchestration_nonexecuting_language_veto"),
        ("``Use Ultra for this task.`` ", "orchestration_nonexecuting_language_veto"),
        ("> Use Ultra for this task.\n\n", "orchestration_nonexecuting_language_veto"),
        ("Here is a quote: > Use Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
        ("~~~text\nUse Ultra for this task.\n~~~\n", "orchestration_nonexecuting_language_veto"),
        ("    Use Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
        ("Sample:\nUse Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
        ("Translation:\nUse Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
        ("Quoted prompt:\nUse Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
        ("Instruction example:\nUse Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
        ("Here is the translation.\nUse Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
        ("Below is the translation.\nUse Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
        ("Quotation:\nUse Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
        ("Paraphrase:\nUse Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
        ("Summary:\nUse Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
        ("Illustration:\nUse Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
        ("The following is an example:\nUse Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
        ("Translation follows.\nUse Ultra for this task.\n", "orchestration_nonexecuting_language_veto"),
    ],
)
def test_extended_prohibition_meta_and_quote_forms_are_hard_vetoes(
    prefix: str,
    expected_reason: str,
) -> None:
    routed = turn_router().route_message(
        _tui_message(prefix + BROAD_RESEARCH),
        now_epoch_seconds=NOW,
    )

    assert routed.ultra_recommendation == "not_recommended"
    assert routed.ultra_approval == "not_requested"
    assert routed.ultra_proposal is None
    assert routed.orchestration_mode == "single_agent"
    assert routed.effort != "ultra"
    assert expected_reason in routed.orchestration_reason_codes


def test_later_explicit_prohibition_vetoes_an_earlier_ultra_request() -> None:
    prompt = "Use Ultra, but do not use Ultra for this request. " + BROAD_RESEARCH

    routed = turn_router().route_message(_tui_message(prompt), now_epoch_seconds=NOW)

    assert routed.ultra_recommendation == "not_recommended"
    assert routed.ultra_proposal is None
    assert routed.effort != "ultra"
    assert "orchestration_instruction_conflict_veto" in routed.orchestration_reason_codes


def test_later_global_cancellation_vetoes_after_task_description() -> None:
    for cancellation in (
        "Cancel everything now.",
        "Abort the operation.",
        "Now cancel everything.",
        "At this point, cancel everything.",
        "To be clear, cancel everything.",
        "Research this issue and cancel everything.",
        "Research the final detail, cancel everything.",
        "Research how to proceed before you cancel everything.",
        "Research why the API fails, and please cancel everything.",
        "Research how to proceed and kindly cancel everything.",
        "Research how to proceed before cancelling everything.",
        "Research how to proceed and after documenting every finding in the final "
        "evidence report for the operator kindly cancel everything.",
        "Research how to proceed prior to cancelling everything.",
        "Research how to proceed ahead of cancelling everything.",
        "Stop now.",
        "Do not proceed.",
        "Please do not continue.",
        "To be clear, do not proceed.",
        "There must be no further action.",
        "Proceed no further.",
        "I do not want you to proceed.",
        "You may not proceed.",
        "You are not authorized to proceed.",
        "Under no circumstances should you proceed.",
        "No more work.",
        "You are not to proceed.",
        "I forbid you to proceed.",
    ):
        routed = turn_router().route_message(
            _tui_message("Use Ultra. " + BROAD_RESEARCH + " " + cancellation),
            now_epoch_seconds=NOW,
        )

        assert routed.ultra_recommendation == "not_recommended"
        assert routed.ultra_approval == "not_requested"
        assert routed.ultra_proposal is None
        assert routed.orchestration_mode == "single_agent"
        assert routed.effort != "ultra"
        assert "orchestration_instruction_conflict_veto" in routed.orchestration_reason_codes


def test_cancellation_term_inside_bounded_research_is_not_a_revocation() -> None:
    _, _, routed = _pending(
        "Use Ultra. Research four independent areas about how systems abort requests: "
        "official API behavior, security controls, pricing, and deployment constraints. "
        "Return one bounded evidence packet per area and combine them at the end."
    )

    assert routed.ultra_recommendation == "recommended"
    assert routed.ultra_approval == "pending"
    assert routed.ultra_proposal is not None


@pytest.mark.parametrize(
    "prompt",
    [
        "Use Ultra, but don't. ",
        "Use Ultra — actually, don't. ",
        "Use Ultra, but do not actually do it. ",
        "Use Ultra. No, don't. ",
        "Use Ultra. Scratch that. ",
        "Use Ultra. Never mind. ",
        "Use Ultra. Cancel that. ",
        "Use Ultra. Disregard that. ",
        "Use Ultra. Please don't. ",
        "Use Ultra. I changed my mind. ",
        "Use Ultra. On second thought, use Max. ",
        "Use Ultra. Forget that. ",
        "Use Ultra. Cancel the request. ",
        "Use Ultra. Stop it. ",
        "Use Ultra. Withdraw that instruction. ",
        "Use Ultra. Revoke this instruction. ",
        "Use Ultra. Use Max instead. ",
        "Use Ultra. Actually use Max. ",
        "Use Ultra\nCancel the request\n",
        "Use Ultra. Ignore that. ",
        "Use Ultra. Correction: use Max. ",
        "Use Ultra\n- Cancel the request\n",
        "Use Ultra. That instruction is withdrawn. ",
        "Use Ultra. I withdraw my request. ",
        "Use Ultra, then cancel it. ",
        "Use Ultra? ",
        "Use Ultra？ ",
        "~~~text\nUse Ultra for this task.\n",
        "``Use Ultra for this task.\n",
    ],
)
def test_anaphoric_reversal_and_question_cannot_admit_ultra(prompt: str) -> None:
    routed = turn_router().route_message(
        _tui_message(prompt + BROAD_RESEARCH),
        now_epoch_seconds=NOW,
    )

    assert routed.ultra_recommendation == "not_recommended"
    assert routed.ultra_approval == "not_requested"
    assert routed.ultra_proposal is None
    assert routed.orchestration_mode == "single_agent"
    assert routed.effort != "ultra"


@pytest.mark.parametrize(
    "prefix",
    [
        "Use Ultra for " + ("a" * 201) + "? ",
        'Use "Ultra" as the example word in the glossary entry; '
        "this is only a vocabulary example. ",
        'Use "Ultra" literally as placeholder text, not as an execution mode. ',
        'Use "Ultra" as a literal string. ',
        'Use "Ultra" as plain text. ',
        'Use "Ultra" only for display. ',
        'Use "Ultra" for this task title. ',
        'As an example, use "Ultra" for this task. ',
        "For reference:\nUse Ultra for this task.\n",
        "For your reference,\nUse Ultra for this task.\n",
        BROAD_RESEARCH + "\nQuotation:\nUse Ultra for this task.\n",
        BROAD_RESEARCH + "\nQuotation\nUse Ultra for this task.\n",
        BROAD_RESEARCH + "\n## Quotation\nUse Ultra for this task.\n",
    ],
)
def test_long_questions_and_quoted_meta_targets_cannot_admit_ultra(
    prefix: str,
) -> None:
    routed = turn_router().route_message(
        _tui_message(prefix + BROAD_RESEARCH),
        now_epoch_seconds=NOW,
    )

    assert routed.ultra_recommendation == "not_recommended"
    assert routed.ultra_approval == "not_requested"
    assert routed.ultra_proposal is None
    assert routed.orchestration_mode == "single_agent"
    assert routed.effort != "ultra"


def test_matching_approval_evidence_cannot_override_a_prohibition_veto() -> None:
    router, _, pending = _pending(BROAD_RESEARCH)
    evidence = make_ultra_approval_evidence(pending.ultra_proposal, now_epoch_seconds=NOW)
    prohibited = _tui_message("Do not use Ultra. " + BROAD_RESEARCH)

    routed = router.route_message(
        prohibited,
        ultra_approval=evidence,
        now_epoch_seconds=NOW,
    )

    assert routed.ultra_recommendation == "not_recommended"
    assert routed.ultra_approval == "invalid"
    assert routed.ultra_proposal is None
    assert routed.orchestration_mode == "single_agent"
    assert routed.effort != "ultra"
    assert "orchestration_explicit_ultra_prohibition" in routed.orchestration_reason_codes


def test_write_heavy_structure_cannot_override_an_orchestration_veto() -> None:
    routed = turn_router().route_message(
        _tui_message("Do not use subagents. " + DISJOINT_WRITE_PLAN),
        now_epoch_seconds=NOW,
    )

    assert routed.write_isolation == "proven_disjoint"
    assert routed.ultra_recommendation == "not_recommended"
    assert routed.ultra_proposal is None
    assert routed.orchestration_mode == "single_agent"
    assert routed.effort != "ultra"
    assert "orchestration_explicit_subagent_prohibition" in routed.orchestration_reason_codes


def test_genuine_explicit_ultra_request_without_prohibition_remains_eligible() -> None:
    _, _, routed = _pending("Use Ultra for this task. " + BROAD_RESEARCH)

    assert routed.ultra_recommendation == "recommended"
    assert routed.ultra_approval == "pending"
    assert routed.ultra_proposal is not None
    assert routed.orchestration_mode == "single_agent"


def test_quoted_ultra_target_in_a_genuine_imperative_remains_executable() -> None:
    _, _, routed = _pending('Use "Ultra" for this task. ' + BROAD_RESEARCH)

    assert routed.ultra_recommendation == "recommended"
    assert routed.ultra_approval == "pending"
    assert routed.ultra_proposal is not None


@pytest.mark.parametrize(
    "reframe",
    [
        "That was only an example.",
        "This was merely documentation.",
        "The previous sentence was not an instruction.",
        "Treat that as an example.",
        "Regard this as documentation.",
        "It was only an example.",
        "It was merely a demonstration.",
        "It was merely illustrative.",
        "It merely illustrated the syntax.",
        "- It was merely a demonstration.",
        "Example only.",
        "It has only been an example.",
        "It has only been an example in a separate section.",
    ],
)
def test_later_meta_reframe_vetoes_quoted_ultra_imperative(reframe: str) -> None:
    routed = turn_router().route_message(
        _tui_message(f'Use "Ultra" for this task. {reframe} {BROAD_RESEARCH}'),
        now_epoch_seconds=NOW,
    )

    assert routed.ultra_recommendation == "not_recommended"
    assert routed.ultra_approval == "not_requested"
    assert routed.ultra_proposal is None
    assert routed.orchestration_mode == "single_agent"
    assert routed.effort != "ultra"
    assert "orchestration_nonexecuting_language_veto" in routed.orchestration_reason_codes


def test_later_meta_reframe_vetoes_unquoted_ultra_imperative() -> None:
    routed = turn_router().route_message(
        _tui_message(
            "Use Ultra for this task. It was merely a demonstration. " + BROAD_RESEARCH
        ),
        now_epoch_seconds=NOW,
    )

    assert routed.ultra_recommendation == "not_recommended"
    assert routed.ultra_approval == "not_requested"
    assert routed.ultra_proposal is None
    assert routed.orchestration_mode == "single_agent"
    assert routed.effort != "ultra"
    assert "orchestration_nonexecuting_language_veto" in routed.orchestration_reason_codes


def test_task_description_after_ultra_request_is_not_a_meta_reframe() -> None:
    _, _, routed = _pending(
        "Use Ultra for this task. This task has independent workstreams. "
        + BROAD_RESEARCH
    )

    assert routed.ultra_recommendation == "recommended"
    assert routed.ultra_approval == "pending"
    assert routed.ultra_proposal is not None


def test_indivisible_hard_problem_is_max_single_agent() -> None:
    routed = turn_router().route_message(
        _tui_message(
            "Find the single root cause of this nondeterministic transaction failure "
            "and produce the smallest correct repair."
        ),
        now_epoch_seconds=NOW,
    )

    assert routed.dependency_shape == "indivisible"
    assert routed.ordinary_reasoning_effort == "max"
    assert routed.orchestration_mode == "single_agent"


def test_overlapping_write_state_is_a_high_risk_veto() -> None:
    routed = turn_router().route_message(
        _tui_message("Use four agents to edit the same router.py file simultaneously."),
        now_epoch_seconds=NOW,
    )

    assert routed.shared_state_risk == "high"
    assert routed.write_isolation == "unproven"
    assert routed.ordinary_reasoning_effort == "max"
    assert routed.effort == "max"


def test_unproven_write_isolation_blocks_ultra() -> None:
    prompt = (
        "Use gpt-5.6-sol to implement four independent modules in parallel. Each "
        "workstream returns a bounded result. One central coordinator owns final integration."
    )
    routed = turn_router().route_message(_tui_message(prompt), now_epoch_seconds=NOW)

    assert routed.write_isolation == "unproven"
    assert routed.ultra_recommendation == "not_recommended"
    assert routed.orchestration_mode == "single_agent"
    assert routed.effort == "max"


def test_proven_disjoint_worktrees_may_be_approved_with_central_integration() -> None:
    _, _, pending, approved = _approved(DISJOINT_WRITE_PLAN)

    assert pending.write_isolation == "proven_disjoint"
    assert pending.planned_worker_count == 4
    assert pending.maximum_delegation_depth == 1
    assert pending.recursive_delegation_allowed is False
    assert approved.orchestration_mode == "ultra_subagents"


@pytest.mark.parametrize(
    ("restriction", "expected"),
    [
        ("Workers must not merge.", (True, False, False)),
        ("Workers must not push.", (False, True, False)),
        ("Workers must not rewrite history.", (False, False, True)),
        ("Workers must not merge or push.", (True, True, False)),
        ("Workers must not merge or rewrite history.", (True, False, True)),
        ("Workers must not push or rewrite history.", (False, True, True)),
        ("Workers must not merge, push, or rewrite history.", (True, True, True)),
        ("Workers may not merge, push, or rewrite history.", (True, True, True)),
        ("No worker may merge, push, or rewrite history.", (True, True, True)),
        (
            "Workers must not merge. Workers must not push. Workers must not rewrite history.",
            (True, True, True),
        ),
    ],
)
def test_worker_git_restrictions_are_independently_clause_scoped(
    restriction: str,
    expected: tuple[bool, bool, bool],
) -> None:
    analysis = _analysis(WRITE_ADMISSION_BASE + restriction)

    assert (
        analysis.workers_cannot_merge,
        analysis.workers_cannot_push,
        analysis.workers_cannot_rewrite_history,
    ) == expected

    routed = turn_router().route_message(
        _tui_message(WRITE_ADMISSION_BASE + restriction),
        now_epoch_seconds=NOW,
    )
    if expected == (True, True, True):
        assert routed.write_isolation == "proven_disjoint"
        assert routed.ultra_recommendation == "recommended"
        assert routed.ultra_approval == "pending"
        assert routed.orchestration_mode == "single_agent"
    else:
        assert routed.write_isolation == "unproven"
        assert routed.ultra_recommendation == "not_recommended"
        assert routed.ultra_proposal is None


@pytest.mark.parametrize(
    ("restriction", "expected"),
    [
        (
            "Workers must not merge. The coordinator may push.",
            (True, False, False),
        ),
        (
            "Workers cannot push, but this document explains how maintainers "
            "rewrite history.",
            (False, True, False),
        ),
        (
            "Do not let workers merge. Explain how a maintainer can rewrite history.",
            (True, False, False),
        ),
        (
            "Workers may edit files but must not merge, push, or rewrite history.",
            (True, True, True),
        ),
        (
            "Workers: must not merge; must not push; must not rewrite history.",
            (True, True, True),
        ),
        (
            "The coordinator must not merge, push, or rewrite history.",
            (False, False, False),
        ),
        (
            "The documentation says 'Workers must not merge, push, or rewrite history.'",
            (False, False, False),
        ),
    ],
)
def test_worker_git_review_examples_have_exact_clause_local_results(
    restriction: str,
    expected: tuple[bool, bool, bool],
) -> None:
    analysis = _analysis(WRITE_ADMISSION_BASE + restriction)

    assert (
        analysis.workers_cannot_merge,
        analysis.workers_cannot_push,
        analysis.workers_cannot_rewrite_history,
    ) == expected


@pytest.mark.parametrize(
    "restriction",
    [
        "Workers must not merge. The coordinator may push.",
        "Workers cannot push, but this document explains how maintainers rewrite history.",
        "Do not let workers merge. Explain how a maintainer can rewrite history.",
        "The coordinator must not merge, push, or rewrite history.",
        "The documentation says 'Workers must not merge, push, or rewrite history.'",
        "Example: workers must not merge, push, or rewrite history.",
        "Workers must not merge, and the coordinator may push and rewrite history.",
    ],
)
def test_unrelated_quoted_or_meta_git_language_does_not_prove_all_restrictions(
    restriction: str,
) -> None:
    analysis = _analysis(WRITE_ADMISSION_BASE + restriction)
    routed = turn_router().route_message(
        _tui_message(WRITE_ADMISSION_BASE + restriction),
        now_epoch_seconds=NOW,
    )

    assert (
        analysis.workers_cannot_merge,
        analysis.workers_cannot_push,
        analysis.workers_cannot_rewrite_history,
    ) != (True, True, True)
    assert routed.write_isolation == "unproven"
    assert routed.ultra_recommendation == "not_recommended"
    assert routed.ultra_proposal is None


@pytest.mark.parametrize(
    "restriction",
    [
        (
            "Workers must not merge. Workers may merge later. Workers must not push. "
            "Workers must not rewrite history."
        ),
        (
            "Workers must not merge, push, or rewrite history, but workers may push "
            "after review."
        ),
        (
            "Workers may rewrite history. Workers must not merge. Workers must not "
            "push. Workers must not rewrite history."
        ),
    ],
)
def test_contradictory_worker_git_instructions_fail_closed(restriction: str) -> None:
    analysis = _analysis(WRITE_ADMISSION_BASE + restriction)
    routed = turn_router().route_message(
        _tui_message(WRITE_ADMISSION_BASE + restriction),
        now_epoch_seconds=NOW,
    )

    assert analysis.worker_git_instruction_conflict is True
    assert analysis.write_isolation == "unproven"
    assert routed.write_isolation == "unproven"
    assert routed.ultra_recommendation == "not_recommended"
    assert "worker_git_instruction_conflict_veto" in routed.orchestration_reason_codes


@pytest.mark.parametrize(
    ("restriction", "expected_conflict"),
    [
        ("Workers must not merge and may push. Workers must not rewrite history.", False),
        ("Workers must not merge, push, or rewrite history. Workers must push.", True),
        (
            "Workers must not merge and workers may push. "
            "Workers must not rewrite history.",
            False,
        ),
        ("Workers must not merge, push, or rewrite history; workers must merge.", True),
    ],
)
def test_worker_git_modal_transitions_and_permissions_fail_closed(
    restriction: str,
    expected_conflict: bool,
) -> None:
    analysis = _analysis(WRITE_ADMISSION_BASE + restriction)
    routed = turn_router().route_message(
        _tui_message(WRITE_ADMISSION_BASE + restriction),
        now_epoch_seconds=NOW,
    )

    assert analysis.worker_git_instruction_conflict is expected_conflict
    assert analysis.write_isolation == "unproven"
    assert routed.write_isolation == "unproven"
    assert routed.ultra_recommendation == "not_recommended"
    assert routed.ultra_proposal is None
    if expected_conflict:
        assert "worker_git_instruction_conflict_veto" in routed.orchestration_reason_codes
    else:
        assert "worker_push_restriction_unproven" in routed.orchestration_reason_codes


@pytest.mark.parametrize(
    "restriction",
    [
        "Workers must not merge, push, or rewrite history unless approved.",
        "Workers must not merge, push, or rewrite history; unless approved.",
        "Workers must not merge, push, or rewrite history. Unless approved.",
        "Workers must not merge, push, or rewrite history.\nUnless approved.",
        "Workers must not merge, push, or rewrite history. Except during release work.",
        (
            "Workers must not merge, push, or rewrite history. "
            "This restriction does not apply after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "An exception is allowed after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "The restriction is lifted after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "These restrictions do not apply after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "The prior sentence is illustrative, not binding."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "That rule is no longer in force."
        ),
        "Workers must not merge, push, or rewrite history except during release work.",
        "Workers must not merge, push, or rewrite history until review completes.",
        "Workers must not merge, push, or rewrite history before review.",
        "Workers must not merge, push, or rewrite history without coordinator approval.",
        "Workers must not independently merge, push, or rewrite history.",
        "Workers must not directly merge, push, or rewrite history.",
        (
            "Workers must not merge, push, or rewrite history. "
            "They may push after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "They are allowed to merge after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "They are free to merge after review."
        ),
        (
            "Workers must not merge, push, or rewrite history unless authorized; "
            "they may merge after review."
        ),
        "Workers must not merge because the coordinator will push and rewrite history.",
        "Workers must not merge because maintainers will push and rewrite history.",
        "Workers must not merge as the coordinator will push and rewrite history.",
        "Workers must not merge so the coordinator can push and rewrite history.",
        "Workers must not merge, leaving the coordinator to push and rewrite history.",
        "The question is whether workers must not merge, push, or rewrite history.",
        "Verify whether workers must not merge, push, or rewrite history.",
        "Please verify whether workers must not merge, push, or rewrite history.",
        "Could you verify whether workers must not merge, push, or rewrite history.",
        "Discuss whether workers must not merge, push, or rewrite history.",
        "The task is to determine whether workers must not merge, push, or rewrite history.",
        "Is it true that workers must not merge, push, or rewrite history.",
        "Please confirm that workers must not merge, push, or rewrite history.",
        "Translate this rule: Workers must not merge, push, or rewrite history.",
        "Repeat this sentence: Workers must not merge, push, or rewrite history.",
        (
            "Workers must not merge, push, or rewrite history. "
            "Allow workers to push after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "Allow the workers to push after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "Allow them to push after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "The coordinator allows workers to push after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "Grant them permission to push after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "Worker 1 may push after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "Workers assigned to release may push after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "Push permission is granted to workers after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "The implementation team may push after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "Grant permission to push after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "Pushing is allowed after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "Workers may rebase after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "Pushing is okay after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "The coordinator gives the implementation team permission to push after review."
        ),
        (
            "Workers must not merge, push, or rewrite history. "
            "Let workers push after review."
        ),
        "Translate the following:\nWorkers must not merge, push, or rewrite history.",
        "Example:\nWorkers must not merge, push, or rewrite history.",
        "Translation:\nWorkers must not merge, push, or rewrite history.",
        "Here is the translation.\nWorkers must not merge, push, or rewrite history.",
        "Below is the translation.\nWorkers must not merge, push, or rewrite history.",
        "Translation follows.\nWorkers must not merge, push, or rewrite history.",
        (
            "Example:\nThis is only illustrative.\n"
            "Workers must not merge, push, or rewrite history."
        ),
        "~~~text\nWorkers must not merge, push, or rewrite history.\n",
        "\n> Workers must not merge, push, or rewrite history.\n",
        "\n    Workers must not merge, push, or rewrite history.\n",
        "Are workers forbidden to merge, push, or rewrite history?",
    ],
)
def test_conditional_pronoun_and_question_git_language_fails_closed(
    restriction: str,
) -> None:
    analysis = _analysis(WRITE_ADMISSION_BASE + restriction)
    routed = turn_router().route_message(
        _tui_message(WRITE_ADMISSION_BASE + restriction),
        now_epoch_seconds=NOW,
    )

    assert analysis.write_isolation == "unproven"
    assert routed.write_isolation == "unproven"
    assert routed.ultra_recommendation == "not_recommended"
    assert routed.ultra_proposal is None


def test_all_worker_git_restrictions_do_not_override_orchestration_veto() -> None:
    routed = turn_router().route_message(
        _tui_message("Do not orchestrate this task. " + DISJOINT_WRITE_PLAN),
        now_epoch_seconds=NOW,
    )

    assert routed.write_isolation == "proven_disjoint"
    assert routed.ultra_recommendation == "not_recommended"
    assert routed.ultra_proposal is None
    assert "orchestration_explicit_orchestration_prohibition" in routed.orchestration_reason_codes


def test_recursive_delegation_and_peer_swarm_are_hard_vetoes() -> None:
    for addition in (
        " Child agents may spawn nested subagents.",
        " Use peer-to-peer swarm coordination.",
        " Every worker may independently merge and push.",
    ):
        routed = turn_router().route_message(
            _tui_message(DISJOINT_WRITE_PLAN + addition),
            now_epoch_seconds=NOW,
        )
        assert routed.ultra_recommendation == "not_recommended"
        assert routed.effort != "ultra"


@pytest.mark.parametrize(
    ("count_word", "expected_workers"),
    [("two", 2), ("three", 3), ("four", 4), ("five", 4), ("six", 4)],
)
def test_worker_count_is_bounded_between_two_and_four(
    count_word: str,
    expected_workers: int,
) -> None:
    objectives = {
        "two": "security and pricing",
        "three": "security, pricing, and deployment",
        "four": "security, pricing, deployment, and API capabilities",
        "five": "security, pricing, deployment, API capabilities, and compatibility",
        "six": (
            "security, pricing, deployment, API capabilities, compatibility, "
            "and performance"
        ),
    }[count_word]
    prompt = (
        f"Conduct a large research program across {count_word} independent areas: "
        f"{objectives}. "
        "Return one bounded report per area and combine the outputs at the end."
    )
    _, _, routed = _pending(prompt)

    assert routed.planned_worker_count == expected_workers
    assert 2 <= routed.planned_worker_count <= 4
    assert routed.maximum_delegation_depth == 1
    assert routed.recursive_delegation_allowed is False


def test_luna_can_receive_max_but_never_ultra() -> None:
    prompt = "Use gpt-5.6-luna. " + BROAD_RESEARCH
    routed = turn_router().route_message(_tui_message(prompt), now_epoch_seconds=NOW)

    assert routed.selected_model == "gpt-5.6-luna"
    assert routed.ordinary_reasoning_effort == "max"
    assert routed.effort == "max"
    assert routed.ultra_recommendation == "not_recommended"
    assert routed.orchestration_mode == "single_agent"


def test_live_capability_drift_removing_ultra_prevents_wire_ultra() -> None:
    data = [
        {
            **item,
            "supportedReasoningEfforts": [
                option
                for option in item["supportedReasoningEfforts"]  # type: ignore[index]
                if option["reasoningEffort"] != "ultra"  # type: ignore[index]
            ],
        }
        if item["model"] == "gpt-5.6-sol"
        else item
        for item in live_model_data()
    ]
    routed = turn_router(data).route_message(
        _tui_message("Use gpt-5.6-sol. " + REPOSITORY_AUDIT),
        now_epoch_seconds=NOW,
    )

    assert routed.selected_model == "gpt-5.6-sol"
    assert routed.effort == "max"
    assert routed.ultra_recommendation == "not_recommended"
    assert "ultra_live_capability_unavailable" in routed.orchestration_reason_codes


def test_live_capability_drift_removing_max_prevents_ultra_admission() -> None:
    data = [
        {
            **item,
            "supportedReasoningEfforts": [
                option
                for option in item["supportedReasoningEfforts"]  # type: ignore[index]
                if option["reasoningEffort"] != "max"  # type: ignore[index]
            ],
        }
        if item["model"] == "gpt-5.6-sol"
        else item
        for item in live_model_data()
    ]
    routed = turn_router(data).route_message(
        _tui_message("Use gpt-5.6-sol. " + REPOSITORY_AUDIT),
        now_epoch_seconds=NOW,
    )

    assert routed.selected_model == "gpt-5.6-sol"
    assert routed.effort == "xhigh"
    assert routed.ultra_recommendation == "not_recommended"
    assert "ultra_max_fallback_capability_unavailable" in routed.orchestration_reason_codes


def test_malformed_or_untrusted_approval_never_emits_ultra() -> None:
    router, message, pending = _pending(BROAD_RESEARCH)
    evidence = UltraApprovalEvidence(
        schema_version=ULTRA_APPROVAL_EVIDENCE_SCHEMA_VERSION,
        decision_signature_version=ULTRA_DECISION_SIGNATURE_VERSION,
        decision_signature=pending.ultra_proposal.decision_signature,
        effective_turn_context_schema_version=EFFECTIVE_TURN_CONTEXT_SCHEMA_VERSION,
        effective_turn_context_hash=(
            pending.ultra_proposal.effective_turn_context_hash
        ),
        status="approved",
        policy_version="model-policy-calibration-v0.2",
        issued_at_epoch_seconds=NOW,
        expires_at_epoch_seconds=NOW + 60,
    )

    routed = router.route_message(
        message,
        ultra_approval=evidence,
        now_epoch_seconds=NOW,
    )

    assert routed.ultra_approval == "invalid"
    assert routed.effort == "max"


def test_missing_policy_provenance_cannot_create_an_approvable_proposal() -> None:
    router = turn_router()
    decision = route_prompt(BROAD_RESEARCH, dry_run=True)

    applied = router.mapper.apply(
        decision,
        BROAD_RESEARCH,
        required_modalities=("text",),
        task_signature=decision.prompt_hash,
        effective_turn_context_schema_version=EFFECTIVE_TURN_CONTEXT_SCHEMA_VERSION,
        effective_turn_context_hash="0" * 64,
    )

    assert applied.ultra_recommendation == "recommended"
    assert applied.ultra_approval == "invalid"
    assert applied.ultra_proposal is None
    assert applied.effort == "max"


def test_policy_v03_provenance_and_historical_versions_are_bounded() -> None:
    routed = turn_router().route_message(
        _tui_message("Write a two-sentence email."),
        now_epoch_seconds=NOW,
    )

    assert MODEL_POLICY_VERSION == "model-policy-calibration-v0.3"
    assert routed.policy_version == MODEL_POLICY_VERSION
    assert normalize_policy_provenance("model-policy-calibration-v0.1") == "model-policy-calibration-v0.1"
    assert normalize_policy_provenance("model-policy-calibration-v0.2") == "model-policy-calibration-v0.2"
    assert normalize_policy_provenance("model-policy-calibration-v0.3") == "model-policy-calibration-v0.3"
    assert normalize_policy_provenance(None) == "unknown"
    assert normalize_policy_provenance("v0.3") == "unknown"


def test_telemetry_schema_cannot_persist_approve_or_launch_orchestration() -> None:
    config = json.loads(
        (ROOT / "rules" / "orchestration_policy.json").read_text(encoding="utf-8")
    )

    assert SCHEMA_VERSION == "2.0.0"
    assert config["telemetry_can_approve"] is False
    assert config["telemetry_can_launch"] is False
    for forbidden in (
        "orchestration_mode",
        "ultra_approval",
        "ultra_proposal",
        "workstream_plan",
        "subagent_conversations",
    ):
        assert forbidden not in RUN_RECORD_FIELDS


def test_orchestration_config_forbids_recursive_or_peer_to_peer_execution() -> None:
    config = json.loads(
        (ROOT / "rules" / "orchestration_policy.json").read_text(encoding="utf-8")
    )
    policy = OrchestrationPolicy(config)

    assert policy.minimum_workers == 2
    assert policy.maximum_workers == 4
    assert policy.max_depth == 1
    assert config["recursive_delegation_allowed"] is False
    assert config["peer_to_peer_swarm_allowed"] is False


def test_model_or_orchestration_strength_never_expands_destructive_authority() -> None:
    routed = turn_router().route_message(
        _tui_message(
            "Use Ultra to delete the default branch after four parallel reviews."
        ),
        now_epoch_seconds=NOW,
    )

    assert routed.effort != "ultra"
    assert routed.orchestration_mode == "single_agent"
    assert routed.sandbox_mode == "read-only"
    assert routed.approval_policy == "on-request"
    assert routed.message["params"]["approvalsReviewer"] == "user"


def test_approval_evidence_is_immutable_and_decision_bound() -> None:
    _, _, pending = _pending(BROAD_RESEARCH)
    evidence = make_ultra_approval_evidence(
        pending.ultra_proposal,
        now_epoch_seconds=NOW,
    )

    with pytest.raises(Exception):
        evidence.status = "denied"  # type: ignore[misc]
    assert replace(evidence, decision_signature="0" * 64) != evidence


class _TruthyApproval:
    def __bool__(self) -> bool:
        return True


class _FalseyApproval:
    def __bool__(self) -> bool:
        return False


def test_actual_boolean_approval_values_are_accepted_with_exact_semantics() -> None:
    router, message, pending = _pending(BROAD_RESEARCH)
    approved = make_ultra_approval_evidence(
        pending.ultra_proposal,
        now_epoch_seconds=NOW,
        approved=True,
    )
    denied = make_ultra_approval_evidence(
        pending.ultra_proposal,
        now_epoch_seconds=NOW,
        approved=False,
    )

    assert approved.status == "approved"
    assert denied.status == "denied"
    routed = router.route_message(
        message,
        ultra_approval=approved,
        now_epoch_seconds=NOW,
    )
    assert routed.ultra_approval == "approved"
    assert routed.effort == "ultra"


@pytest.mark.parametrize(
    "invalid_approved",
    [
        "true",
        "false",
        "approved",
        "denied",
        "0",
        "1",
        0,
        1,
        None,
        [],
        {},
        (),
        _TruthyApproval(),
        _FalseyApproval(),
    ],
)
def test_non_boolean_approval_values_fail_closed(invalid_approved: object) -> None:
    _, _, pending = _pending(BROAD_RESEARCH)

    with pytest.raises(ValueError, match="approval decision must be a boolean"):
        make_ultra_approval_evidence(
            pending.ultra_proposal,
            now_epoch_seconds=NOW,
            approved=invalid_approved,  # type: ignore[arg-type]
        )
