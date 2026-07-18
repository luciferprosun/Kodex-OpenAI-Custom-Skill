# Research-question unknowns

Unknown means not established from the inspected primary evidence. It does not
mean zero, unavailable in every private system, or impossible to measure later.

## Predictive questions

- Relative predictive importance of task domain, difficulty, repository size,
  requested file scope, ambiguity, risk, tool profile, horizon, context state,
  reasoning effort, and agent count.
- Stable p50/p90 token distributions for compatible task/model/framework strata.
- Failure, retry, escalation, censoring, and verifier-pass probabilities under a
  declared budget and route policy.
- Generalization to unseen repositories, task families, model snapshots, and
  product surfaces.

## Accepted-task economics

- Complete route chains that include failed first attempts, retries,
  escalations, verification, tool charges, wall time, and human review.
- The valuation of human time and non-acceptance penalties. These remain human
  policy choices even after resource use is measured.
- Historical billed prices and cache rules for heterogeneous public runs.
- Any API-dollar conversion for subscription credits or quotas.
- Break-even failure/escalation rates for a cheaper-versus-stronger model pair.

## Spark, Luna, Terra, and Sol

- Alias-to-immutable-model mapping at the evidence cutoff.
- Surface/account entitlement and whether the selected service model matches the
  displayed alias.
- Same-task, same-framework, same-effort, same-tool, same-budget run populations.
- Accepted-result cost and calibrated success lower bounds by task stratum.
- Any evidence-based Spark efficiency region, Luna cost-minimum region,
  Terra/Luna crossover, or Sol ambiguity/risk trigger.

## Tool, history, cache, and context attribution

- Tokens introduced by each tool result into each later model request.
- Re-sent system/developer/user/history tokens versus newly introduced tokens.
- Context occupancy before and after every request.
- Compaction input, summary output, trigger, and post-compaction context.
- Whether provider/framework aggregate usage includes failed API retries,
  evaluator calls, guardrails, handoffs, and subagents.
- Visible-output token counts distinct from provider output-token totals.
- Cache-write/read behavior and effective prices for every historical model/date.

## Multi-agent effects

- A causal or matched response curve from agent count to summed tokens, wall
  time, success, and accepted-task cost.
- Per-agent attribution without double-counting shared context.
- Interaction between topology, handoff count, parallelism, verifier strategy,
  and task decomposition quality.
- Whether failed/censored multi-agent attempts are retained in published samples.

## Public-corpus and rights unknowns

- Artifact-level license and exact schema for large AgentLab, OpenHands,
  SWE-smith, Nebius, and heterogeneous SWE-bench trajectory releases.
- Complete success/failure/censoring denominators for training-oriented datasets.
- Stable model snapshot, prompt/scaffold, evaluator, attempt policy, and inference
  timestamp for many leaderboard submissions.
- Privacy, secrets, hidden-reasoning, and third-party-content safety of individual
  traces.

## Minimum evidence needed to answer the model-selection questions

1. Resolve aliases to service-confirmed model IDs without inference from names.
2. Preregister compatible task strata and budgets.
3. Collect linked route/attempt/request/tool/verifier records, including all
   failures and censored outcomes.
4. Record dated billing semantics separately from subscription quota.
5. Use matched or randomized routing where permissible, grouped task/source
   holdouts, and calibration intervals.
6. Keep the numerical-prior gate closed until an effective sample of A-C quality
   records passes license, privacy, compatibility, and leakage checks.
