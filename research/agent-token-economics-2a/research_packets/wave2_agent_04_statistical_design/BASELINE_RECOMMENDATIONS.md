# Baseline and Chart Recommendations

## Estimands first

Define each target before fitting:

- `p50_input_tokens`: median cumulative compatible input for a complete route
  chain, conditional on a declared task stratum and budget.
- `p90_total_tokens`: conditional 0.90 quantile with budget-censored runs treated
  as censored/lower-bound observations rather than ordinary small totals.
- `probability_of_acceptance`: probability that the terminal verifier/human
  acceptance criterion passes within the declared token/time/attempt budget.
- `probability_of_escalation`: probability that the policy invokes a stronger
  route after the first attempt, conditional on the starting route and policy.
- `expected_accepted_task_cost`: expected total valued resources per accepted
  task chain, including spend on failed attempts and verification. State whether
  never-accepted chains enter via a finite failure penalty or a separate risk
  constraint.

## Evaluation design

1. Freeze a pre-route feature set. Never use observed files touched, retries,
   final tool calls, final context, or verifier outcome as predictors available
   at routing time.
2. Key records by dataset/version/task and route-chain ID. Split by source first;
   otherwise group by task/repository so repetitions never cross folds.
3. Fit encoders, imputers, category dictionaries, scaling and hyperparameters
   only inside training folds. Reserve `unknown` and out-of-distribution flags.
4. Report support by source, task, model, framework, quality class, measurement
   method, completion status and censoring. Do not train when one class has
   inadequate events or effective clusters.
5. Prefer leave-one-source-out validation. If only one source exists, use grouped
   task/repository folds and label it weaker. Keep a later local 2B temporal
   holdout untouched for calibration testing.

## Interpretable baselines

- **Lookup median/quantile:** hierarchical fallback from exact compatible
  stratum to carefully predeclared coarser strata. Publish fallback level and
  effective n. Use cluster bootstrap intervals.
- **Token/cost point model:** ridge on `log1p` is acceptable for a conditional
  median-style diagnostic, not arithmetic expectation. For expected positive
  cost, consider a regularized Gamma GLM with log link or an explicitly checked
  retransformation correction.
- **p90 model:** use quantile regression or lookup quantiles and held-out pinball
  loss; a mean/median ridge does not estimate p90.
- **Success/escalation:** regularized logistic GLM with grouped held-out Brier
  score, reliability bins, calibration intercept/slope and confidence intervals.
  Laplace-smoothed lookup is a useful small baseline when support is disclosed.
- **Tree:** at most a shallow tree with explicit missing branches, minimum leaf
  support based on effective task clusters, and grouped held-out evaluation.
- **Selection:** compare models against the same folds and estimands. Report
  median absolute error, pinball loss, Brier score, calibration error and coverage
  by stratum. Do not select using in-sample loss.

## Censoring and selection

- Report completed success rate, censoring rate, and conservative lower/upper
  success bounds. Use Kaplan-Meier or another survival method only with a common
  exposure axis, known budgets, and enough comparable chains.
- Preserve failed and aborted trajectories. If a source publishes successful
  runs only, it cannot estimate success probability, escalation risk, or
  accepted-task cost; it may describe conditional resource use only.
- Weighting or matching can address known sampling designs, but cannot repair
  unknown non-public failures. Use `associated with`, not `caused by`.

## Exact chart interpretations

| Chart | Defensible interpretation and required annotation |
| --- | --- |
| Token usage by task/model | Facet by compatible dataset/framework/accounting method; show n, IQR, p90 and cluster uncertainty. Differences are conditional associations, not intrinsic model constants. |
| p50/p90 total tokens | Mark p90 as unstable for small effective n and censored values as lower bounds. Never pool provider totals with different definitions. |
| Tokens per accepted task | Sum all linked attempts for each accepted chain; separately show never-accepted/censored chains. A success-only denominator is survivorship-biased. |
| Cost per accepted task | State currency, price date, route-chain scope and included components. Separate historical billed API cost, counterfactual current-price cost and subscription quota. |
| Success versus tokens | Include completed failures and censoring. More tokens can be a response to harder tasks; a trend is not a causal benefit curve. |
| Cache ratio | Only plot compatible prompt/cache definitions. Cache can reduce billed input price while logical processed context remains unchanged. |
| Tool calls versus tokens | Facet by tool type and report tool-output tokens; call count is not payload size and the relationship is associative. |
| Repository size versus input | Define size units, use log scales when suitable, and stratify by task/file scope; repository size is not the context actually read. |
| Retry count versus cost | Aggregate by route chain and include failed first routes. Retry is policy- and difficulty-dependent, not an isolated cause. |
| Agent count versus tokens/success | Sum tokens across agents and distinguish elapsed parallel time. Only matched/randomized task-model-budget comparisons support an agent-count effect. |
| Historical coverage | Plot observed telemetry releases/records, not inferred historical token usage. Missing eras mean unavailable evidence, not zero consumption. |
| Missingness heatmap | Show denominators by dataset and distinguish unsupported, not collected, withheld, structurally inapplicable and unknown. |
| Evidence quality | Show counts and individual quality components/classes; do not treat the 0-100 score as a continuous accuracy probability. |
| Escalation frontier | Plot feasible policies only, with accepted-cost uncertainty against a lower confidence bound on success; safety/capability gates precede the Pareto frontier. |
| Local fields required | Show public coverage versus 2B-required fields; absence is a collection requirement, not an estimated zero. |

## Routing objective formulation

Optimize over a route policy `pi`, not only model `m`:

`min_pi E[C_api + C_tools + value_time(T_wall, T_human) + C_verify + C_retry + C_escalate + L_failure | x, pi]`

subject to capability, risk, verifier, availability, approval and budget gates,
and a conservative success constraint such as a calibrated lower confidence
bound. If resource components cannot be put on a documented common scale, expose
a Pareto/vector decision rather than adding them. Subscription quota remains a
separate constraint unless the product exposes a defensible conversion.
