# Local measurement priorities for SmartRouter 2B

The priorities below are ordered by how many currently unanswerable routing
questions they unlock. They describe a future telemetry mission, not a runtime
implementation in 2A.

## P0 — Identity, task, route chain, and terminal outcome

Collect before fitting any model:

- immutable `task_id`, benchmark/version, repository/base revision, domain,
  difficulty, ambiguity, risk, requested file scope, and verifier criterion;
- `route_decision_id`, `attempt_chain_id`, ordered attempt IDs, retry reason,
  escalation source/destination/reason, cancellation and censoring reason;
- requested alias, service-confirmed model ID/version, product surface,
  reasoning effort, framework/version, agent count and parent/child IDs;
- terminal verifier result, partial score, final acceptance, and human-review
  minutes.

Why first: without a complete chain and acceptance label, “cost per accepted
task,” failure predictors, escalation risk, and model comparisons are undefined.

## P0 — Per-request provider usage and timing

- request ID and sequence within attempt;
- provider-reported input, cached input, cache write, reasoning and output token
  fields with field-level measurement status;
- request start/end monotonic timestamps, status, retryability, rate-limit wait,
  model ID and service tier;
- reported API cost where available, currency, price-table ID/date, and a
  separate reconstruction record when needed.

Preferred surfaces: Responses usage (`OA-OFFICIAL-001`), Agents SDK usage
(`OA-OFFICIAL-011`, `OA-OFFICIAL-012`), and Codex JSONL events
(`OA-OFFICIAL-013`, `OA-OFFICIAL-014`). Never convert subscription quota to API
dollars without an official mapping.

## P1 — Component-aware input amplification

For each request, measure or safely reconstruct allowlisted token/byte counts for:

- system/developer/user additions;
- re-sent conversation history;
- tool results by tool type;
- file/repository excerpts;
- verifier/evaluator messages;
- subagent/handoff context;
- compaction summaries.

Do not retain raw prompts, hidden reasoning, private tool output, or secrets.
Component hashes, counts, categories, and tokenizer/model-version metadata are
sufficient for most analyses.

Why: this unlocks tool-output burden, repeated-history burden, context-growth
models, and action-specific amplification estimates. Tool-call count alone is
not enough.

## P1 — Context and compaction state

- last-turn versus cumulative-session usage;
- measured current and peak context occupancy where the surface exposes it;
- explicit compaction events, cause, input size, summary size, and post-event
  occupancy;
- context-window capacity as a separate field.

Why: cumulative usage, context capacity, and current occupancy are different
quantities. This is essential for predicting compaction and long-session cost.

## P1 — Tool and environment telemetry

- tool type, start/end, success, invalid/repeated classification, and bounded
  result byte/token size;
- model requests triggered by tools, guardrails, handoffs, or evaluators;
- wall time partitioned into model, tool, environment, verifier, queue, and
  human review.

Why: enables tool-heavy versus tool-light task strata and separates resource
cost from elapsed parallel time.

## P1 — Multi-agent attribution

- per-agent requests/tokens/tools/outcomes;
- handoff graph, shared-context identifiers, and concurrency intervals;
- summed resource use plus end-to-end wall time without double-counting shared
  context.

Why: required before estimating agent-count associations, and matched or
randomized designs are required before causal language.

## P2 — Controlled evidence program

After P0/P1 collectors are validated:

1. Define common task strata and fixed verifier/budget policies.
2. Compare available models on the same tasks, framework, tools, effort, and
   price date; record every failure and censored run.
3. Include low/medium/high ambiguity and risk strata without violating human
   approval boundaries.
4. Randomize or counterbalance route order when safe to limit session/order
   bias.
5. Hold out entire task/repository/source groups and a later temporal sample.
6. Report p10/p50/p90, clustered uncertainty, completed success, censoring,
   calibration, and accepted-chain cost.

This is the minimum credible route to Spark/Luna/Terra/Sol conditions. Until
those aliases are resolved and matched evidence exists, all model-specific rules
remain `unknown`.

## P2 — Data-quality and publication gates

- Preserve null instead of zero for unsupported fields.
- Require license, provenance, objective outcome, exact identity, request
  coverage, and repeatability scoring.
- Allow only compatible A-C records into numerical priors; D is descriptive and
  E is excluded.
- Validate task/source/attempt/request referential integrity and sequence.
- Scan derived exports for secrets, personal data, private paths, and raw
  reasoning before publication.

## Research-question unlock map

| Question | Required priority set |
| --- | --- |
| Token predictors | P0 task features + P0 usage + P1 components/context |
| Failure/retry predictors | P0 complete outcomes/chains + P0 usage |
| Cheap-model break-even | P0 chains + P0 dated cost + verifier/human cost |
| Spark/Luna/Terra/Sol regions | All P0 + controlled P2 comparisons |
| Tool share | P1 component-aware input + tool telemetry |
| Repeated-history share | P1 component-aware input + context state |
| Cache economics | P0 provider usage + dated price semantics |
| Agent-count effect | P1 multi-agent attribution + controlled P2 design |
