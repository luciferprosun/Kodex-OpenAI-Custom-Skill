# Statistical Analysis Plan

## Unit and strata

The primary unit is an agent run. Request-level records support amplification,
cache, retry, and context-growth analyses. Results are stratified by model,
framework, task domain and difficulty, benchmark version, tool profile,
reasoning effort, agent count, success criterion, context state, and price date.
Incompatible datasets are not pooled merely to increase sample size.

Compatibility keys also separate model provider, product surface, context
window, request-breakdown completeness, prompt/total token scopes, measurement
method profile, verifier type, normalized-cost scope, currency, price-table ID,
price-table date, and reconstruction basis. API, subscription, differently
scoped, differently measured, or differently priced observations therefore
cannot share a stratum by accident.

## Descriptive statistics

For compatible strata report count, missingness, p10, p50, p90, interquartile
range, and percentile-bootstrap 95% intervals for p50 and p90. The deterministic
bootstrap seed is `20260718`; the default is 2,000 resamples. Resampling occurs
at the `(dataset_id, task_id)` cluster, not the trajectory row, so repeated runs
of one task cannot manufacture precision. Samples below five independent task
clusters receive no interval. Samples below twenty runs are labeled small-sample.

Success is reported both as a trajectory-row diagnostic and as the primary
task-cluster rate. The latter first computes the success fraction within each
task, gives every task equal weight, and obtains its 95% interval by 2,000
task-cluster bootstrap resamples. This prevents repeated runs of a small task
set from manufacturing a narrow binomial interval.

Success- and failure-conditioned distributions remain separate. Budget-exhausted
or interrupted runs are marked censored; they are not treated as ordinary
completed failures or put in the ordinary success-rate denominator. A separate
explicit A-C, rights-cleared censoring cohort reports exposure and censor reason.
Survival analysis is fitted only when censoring time/budget and sufficient
comparable task clusters exist.

Association language is used unless a design supports causal inference.

## Derived metrics

Where compatible fields exist:

- accepted-task cost = the sum of model/API, retry, escalation, tool,
  verification, human-review, and failure-penalty components over a complete
  attempt chain ending in one accepted result; incomplete or partly costed
  chains remain `null` and are never success-only denominators;
- input amplification = cumulative prompt tokens / first-request prompt tokens;
- cache-hit ratio = cached input / prompt input;
- reasoning/output ratio = reasoning tokens / visible output tokens;
- tool burden = tokens attributable to tool outputs / cumulative prompt tokens;
- escalation cost = later-attempt and transition cost after the first route;
- marginal stronger-model benefit = success or accepted-cost difference within
  a comparable task stratum, never an unadjusted cross-benchmark average.

Zero denominators produce `null`, not infinity or zero.

An accepted chain must use contiguous attempt numbers beginning at one, refer
to one dataset/task, mark the last attempt as the sole accepted result, carry
run-scoped normalized costs on every attempt, and use one non-null currency,
price-table ID, and price-table date throughout. Chain-scoped totals are not
summed once per attempt.

## Baselines

Research-only baselines are evaluated without runtime integration:

1. median lookup by supported stratum;
2. p90/quantile lookup;
3. L2-regularized linear or generalized linear estimator with interpretable
   encoded task features;
4. shallow interpretable tree when dependencies and sample size permit.

Targets are p50 input tokens, p90 total tokens, task-success probability,
escalation probability, and expected accepted-task cost. Errors are reported by
stratum: median absolute error for token/cost point estimates, pinball loss for
quantiles, and Brier score for probability estimates. Lookup calibration uses
both held-out task groups and held-out source groups when support exists. Random
row splits are prohibited because they leak repeated tasks and source-specific
instrumentation. Regularized baselines require at least the greater of 100 runs
or ten runs per encoded feature. Their in-sample diagnostic is never treated as
calibration; a later nested task-group and source-group evaluation is mandatory
before they can become routing priors. Models are not trained for targets whose
observed support is insufficient.

Quality class A–C is necessary but not sufficient. A record enters a numerical
prior only when `included_in_numerical_priors` is explicitly true, its license
allows derived statistics, privacy review is complete, it is not censored, and
its measurement confidence is known. Censored A-C runs require the separate
`included_in_censoring_analysis` flag and never become ordinary success/failure
observations. The dataset registry must independently permit numerical routing.
D/E and rights-blocked records remain qualitative or discovery evidence.
