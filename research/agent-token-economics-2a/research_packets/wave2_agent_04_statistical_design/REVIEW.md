# Statistical and Prediction-Design Review

## Scope

This packet reviews the current 2A schemas, taxonomy, methods,
`validate_corpus.py`, `compute_statistics.py`, and `fit_baselines.py`. It does
not alter those files and does not make a final routing recommendation. At the
time of review the normalized corpus contains zero runs, so every finding below
is a design finding rather than an empirical result.

## What is already sound

- Missing token measurements are represented as `null`, not zero.
- API-billed tokens, subscription quota units, cumulative session usage, and
  current context occupancy are conceptually separated.
- Historical price joins require a date, and current-price reconstructions are
  described as counterfactual.
- The plan prefers robust percentiles, bootstrap intervals, stratification,
  success/failure separation, and association rather than causal language.
- Quality classes D and E are intended to be excluded from numerical priors.
- The routing objective places capability, safety, verification, availability,
  budget, and approval gates before cost.
- Empty support produces null/untrained outputs rather than fabricated priors.

## Priority findings

### Critical before any non-empty quantitative publication

1. **Accepted-task cost has survivorship bias.** Both the lookup and ridge
   baselines filter to successful runs and model only `normalized_cost` of the
   successful run. That is cost conditional on a successful run, not total
   accepted-task cost. Failed attempts, retries, escalation, verification, and
   human review must be linked into a route-attempt chain and charged to the
   eventual accepted result. Completely unaccepted chains must remain in the
   risk/penalty model rather than disappear.
2. **Censoring is not honored by the implementation.** `compute_statistics.py`
   can count a record with `task_success=false` and `censored=true` as an
   ordinary failure. Completed-outcome rates must exclude censored outcomes and
   separately report censoring; budget-limited success requires time/budget
   exposure data or bounds/survival methods.
3. **The numerical-prior inclusion gate is ineffective.** The validator checks
   `included_in_numerical_priors`, but strict schemas do not permit that field,
   while both analysis scripts include every A-C record. Class C is therefore
   not limited to an explicitly compatible stratum. Add a schema field and
   enforce it, or remove the dead check and implement a documented compatibility
   gate used by validation and both scripts.
4. **Validation can leak task/source information.** Lookup calibration leaves
   out one run, not all runs for the same task/source. Repeated trajectories can
   predict one another. Task enrichment is keyed only by `task_id`, so equal IDs
   in different datasets can be joined incorrectly. Group by `(dataset_id,
   task_id)` at minimum and evaluate by held-out source/task groups.

### High priority

- Implemented strata omit difficulty, benchmark/version, tool profile,
  reasoning effort, agent count, success criterion, context state, accounting
  definition, and price date even though the plan requires them. Dataset ID is
  not a sufficient compatibility guarantee.
- `reported_cost` and `normalized_cost` lack currency, cost scope, price-table
  identifier, and reconstruction basis. Minutes, tokens, dollars, tool fees,
  subscription quota, and failure penalties must never be added as if they share
  units.
- Run-level `prompt_tokens` has no explicit scope. The dormant amplification
  code assumes it is cumulative and references a schema-absent
  `first_request_prompt_tokens`; the methods describe request input. Derive
  amplification from linked request records or add explicit scoped fields.
- Cache ratio and tool burden are computed without checking accounting
  compatibility. They are valid only where numerator and denominator share
  source semantics and measurement scope.
- Ridge with a clipped binary response is a linear probability model, not a
  calibrated logistic model. It should be labeled accordingly or replaced by a
  regularized logistic GLM with held-out calibration.
- Fixed `n >= 12` is inadequate when one-hot feature width can greatly exceed
  sample size. Training and evaluation use the same records for ridge/tree;
  reported errors are diagnostics, not generalization evidence.
- Numeric median imputation has no missingness indicators. Null capability
  levels can mean not applicable, not merely missing; imputing them as typical
  levels changes meaning. Categorical nulls are conflated with the reference
  category.
- The stump chooses among many splits in-sample, ignores rows missing the split
  feature when calculating loss, uses leaves of three, and reports summed loss.
  This can favor highly missing features and overstate fit.
- The validator enforces missingness/measurement methods for only a subset of
  token fields. Request-level cache writes, tool output, context before/after,
  and non-token telemetry are not covered. It also does not reconcile run
  aggregates with requests, check unique keys, sequence continuity, task/source
  references, quality-score gates, license gates, or censor-reason consistency.
- Bootstrap intervals treat repeated runs as independent. Use task/source
  cluster bootstrap where repetitions share a task, repository, or trajectory
  generator. Report p90 uncertainty as well as median uncertainty.

## Accounting-confusion audit

- **API cost versus subscription quota:** conceptually separated in
  `TOKEN_ACCOUNTING.md`; current scripts do not convert quota to API dollars.
  Preserve this separation in schemas, tables, and charts. A monetary objective
  must use an explicit cost basis and cannot infer subscription consumption from
  API prices.
- **Cumulative usage versus context occupancy:** conceptually separated. No
  current script equates them. Do not use cumulative session tokens as peak
  context; occupancy remains unknown unless directly measured.
- **Association versus causation:** the plan uses correct association language.
  Charts involving tokens, tools, retries, agent count, repository size, and
  success remain observational unless the same tasks are randomized under
  controlled budgets.

## Publication condition

With zero normalized runs, null tables and untrained baselines are the only
defensible numerical output. Before adding non-null priors, resolve the Critical
items, label every comparison by compatible stratum and measurement method, and
carry the High items either as corrections or explicit non-influence gates.
