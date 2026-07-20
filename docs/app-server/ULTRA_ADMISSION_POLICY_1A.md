# Research-grounded Ultra admission policy 1A

## Contract

Smart Router policy `model-policy-calibration-v0.3` separates three decisions:

1. live model selection;
2. ordinary single-agent reasoning effort from `minimal` through `max`; and
3. orchestration mode: `single_agent` or `ultra_subagents`.

`max` is maximum ordinary reasoning depth. It never means delegation. `ultra`
means maximum reasoning plus approved subagent orchestration. Codex 0.144.6
currently advertises Ultra for Sol and Terra, while Luna advertises Max but not
Ultra. The live `model/list` response is authoritative; the checked-in
inventory is only a dated sanitized observation and not entitlement proof.

## Default and admission

Every decision starts as `single_agent`. Difficulty alone and words such as
“agent”, “parallel”, “delegate”, or “Ultra” do not prove admission.

Ultra can be recommended only when the selected live model advertises it, its
reviewed profile permits it, and all of these structural facts are proven:

- at least two substantive workstreams with distinct objectives;
- parallel dependency shape and independent start;
- one bounded result per workstream;
- material parallel benefit and large or xlarge duration;
- a centralized coordinator that can synthesize and validate outputs;
- no deterministic-evaluation or token/cost-minimization request;
- shared mutable-state risk below high; and
- at least one controlled benefit: read breadth, independent verification,
  corpus partitioning, context-pressure reduction, specialist roles, distinct
  tool/data domains, or proven disjoint writes.

Descriptions, quotations, questions, examples, prohibitions, and ambiguous
decomposition do not admit orchestration. Non-executing orchestration language
and explicit prohibitions are retained as hard veto reason codes; they are not
reduced to cleared request flags and cannot be overridden by structural scores
or approval evidence.

## Hard vetoes

The policy stays single-agent for an indivisible proof or root-cause
investigation, a strict sequential chain, a small/medium task, reproducibility
evaluation, cost minimization, high shared-state risk, overlapping writes,
unproven write isolation, recursive delegation, peer-to-peer swarms, worker
merge/push/history authority, unavailable live Ultra, or invalid approval.
An explicit Ultra request cannot bypass a veto.

Read-heavy independent review is the preferred RC2 shape. Write-heavy work can
remain eligible only when disjoint ownership, isolated worktrees, bounded write
scopes, and central integration are explicit. Worker restrictions are parsed in
bounded clauses and proven independently for merge, push, and Git-history
rewrites. All three must be unambiguous and non-contradictory; one restriction
never stands in for the other two.

## Resources

- minimum workers: 2;
- maximum workers: 4;
- delegation depth: exactly 1;
- recursive delegation: forbidden;
- topology: centralized orchestrator/worker;
- peer-to-peer swarm: forbidden.

Five or more proven workstreams are consolidated into at most four workers.
The policy does not create one worker per file.

## Approval and fallback

Eligibility produces an advisory recommendation, not execution:

```text
ordinary_reasoning_effort = max
orchestration_mode = single_agent
ultra_recommendation = recommended
ultra_approval = pending
wire effort = max
```

The proposal exposes only bounded categories and reason codes: selected model,
Max fallback, worker count, controlled workstream categories, material-benefit
codes, shared-state risk, resource class, and approval requirement. It does not
retain workstream prose, paths, prompts, or agent instructions.

Approval evidence is short-lived and bound by decision-signature contract
`ultra-decision-signature-v2` to the task hash, selected model, ordinary effort,
proposed mode, worker count, controlled plan ID, policy version, sandbox,
approval policy, and `effective-turn-context-v1` hash. The effective context is
the complete original `turn/start` request plus the session `previous_model`
input. It therefore binds request and thread IDs, ordered text/image/skill/
mention inputs and their complete supplied identities, cwd, output schema,
service/personality/config fields, collaboration mode and developer
instructions, and every other forwarded request field. Mapping keys are sorted,
sequence order is preserved, unsupported or non-finite values fail closed, and
only the SHA-256 digest enters the proposal/evidence contract.

Evidence schema `ultra-approval-evidence-v2` repeats the context schema, context
hash, and decision-signature version. Legacy or malformed evidence without the
complete binding is rejected rather than upgraded. The approval builder accepts
only the exact Python booleans `True` and `False`; strings, integers, collections,
and custom truthy objects fail closed. A changed task, attachment, skill,
mention, cwd, developer instruction, session model, model, plan, worker count,
policy, or turn invalidates approval. A generic `on-request` setting, prior
permission, telemetry, or mention of Ultra is not approval.

Only matching explicit approval produces:

```text
ordinary_reasoning_effort = max
orchestration_mode = ultra_subagents
wire effort = ultra
```

Top-level `effort` and an already-present
`collaborationMode.settings.reasoning_effort` are rewritten consistently. A
denied, missing, stale, malformed, mismatched, unsupported, or drifted case
falls back to Max/single-agent when live Max exists, otherwise to the nearest
supported non-Ultra ordinary effort.

## Authority, privacy, and current limitation

Model strength and orchestration never expand sandbox, filesystem, network,
Git, or approval authority. The existing human reviewer remains the only
authority for protected effects. Admission is denied unless the proposed
worker plan separately prohibits merge, push, history rewrite, and recursive
delegation; no worker runtime or enforcement UI is introduced in this step.

Telemetry remains local, collection-only, non-authoritative schema 2.0.0. It
cannot approve or launch Ultra. Because that schema has no orchestration fields,
the state remains internal and the dashboard labels the observability gap; no
schema or historical record was changed.

RC2 implements the bounded internal approval input and deterministic tests only.
It does not implement `/smart-router on`, a slash command, a trusted live
approval UI, or canonical live integration. No paid Ultra or subagent run is
claimed.
