# Contradictions and apparent conflicts

These conflicts must be resolved by separating measurement scopes rather than
averaging values or choosing the more convenient interpretation.

## 1. Cache savings versus context reduction

- Official usage and caching sources (`OA-OFFICIAL-001`, `OA-OFFICIAL-002`,
  `OA-OFFICIAL-005`, `OA-OFFICIAL-006`) support a cache-specific billing
  category and show that cached input remains processed input and counts toward
  token rate limits.
- A common but unsupported interpretation treats cached tokens as absent from
  context or total input.
- Resolution: retain total input, cached reads, cache writes, and non-cached
  input as distinct fields. Describe savings only for a dated billing surface.

## 2. Output tokens versus visible output

- `OA-OFFICIAL-001`, `OA-OFFICIAL-003`, and `OA-OFFICIAL-004` distinguish total
  output usage from reasoning details and explain that output can include
  non-visible tokens.
- Subtracting reasoning tokens from output is therefore not guaranteed to equal
  visible text tokens.
- Resolution: tokenize the visible response separately and label it
  reconstructed, or leave visible output unknown.

## 3. Aggregate totals versus task-level routing evidence

- `HWM-S027`, `HWM-S029`, and `HWM-S031` report aggregate token/time examples
  that are useful for mechanism discovery.
- Their configurations, tasks, models, agent topologies, and accounting scopes
  differ, and failed-run inclusion is incomplete or unclear.
- Resolution: quality D, qualitative only. Do not average or use them as
  model/task priors.

## 4. More agents versus better outcomes

- Multi-agent examples show coordination traffic and sometimes reported task
  success.
- They do not isolate agent count: task, model, scaffold, budget, and topology
  change at the same time.
- Resolution: “can amplify token use” is permitted; “more agents cause higher
  pass rate” or a numerical response curve is not.

## 5. Public availability versus publication permission

- Several repositories are open and their code is MIT or Apache-2.0.
- Separately hosted trajectories may lack a data license, include third-party
  content, or expose private/hidden material (`HWM-S023`, `HWM-S035`,
  `SE-SRC-001`).
- Resolution: code/schema license and trajectory/data rights are separate.
  Retain references and lawful derived statistics unless artifact rights are
  explicit.

## 6. Objective outcomes versus complete attempt economics

- SWE-bench, Harbor/Terminal-Bench, STATE-Bench, AgentRE-Bench, and web
  benchmarks provide verifier or outcome structures.
- Those outcome structures are not generally joined to exact provider token
  fields, retry/escalation chains, or dated costs.
- Resolution: they support taxonomy and verifier design, not accepted-task-cost
  estimates in 2A.

## 7. Current pricing versus historical reconstruction

- `OA-OFFICIAL-006` is authoritative for the current inspected price surface.
- Historical runs may have used different models, tiers, cache rules, or prices.
- Resolution: never label a current-price reconstruction as historical billed
  cost. Preserve price-table date, model identity, currency, and reconstruction
  basis.

## 8. Model alias versus immutable model identity

- The mission asks about Spark, Luna, Terra, and Sol.
- The canonical 2A token registries contain no matched run populations for
  those labels and this packet does not establish their mapping to immutable
  provider model IDs.
- Resolution: do not infer capability or economics from alias wording or
  version ordering. Record requested alias and service-confirmed model ID
  separately in 2B.

## 9. Cumulative usage versus live context occupancy

- `OA-OFFICIAL-011` through `OA-OFFICIAL-015` expose run, turn, and sometimes
  last-versus-total usage.
- These cumulative counters are sometimes mistaken for current context size.
- Resolution: current/peak context occupancy remains separate and unknown unless
  explicitly measured. Count compactions as events; do not infer them from token
  drops.

## 10. “Strongest predictor” language versus observational evidence

- Public papers contain associations under heterogeneous scaffolds and budgets.
- Difficulty, policy, tools, and model choice jointly affect both tokens and
  outcomes, so naive correlations can reverse or reflect confounding.
- Resolution: 2A may name candidate predictors. Ranking requires grouped,
  compatible, held-out local evidence and association language unless a
  controlled design justifies causality.
