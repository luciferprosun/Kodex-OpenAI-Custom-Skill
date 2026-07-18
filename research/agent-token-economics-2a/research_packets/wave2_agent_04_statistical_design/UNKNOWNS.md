# Statistical Unknowns

- No normalized run or request records were present during this review; no
  distribution, predictor, calibration, or economic comparison can yet be
  validated empirically.
- It is unknown which accepted public sources contain both failures and successes
  under one sampling design. Success-only trajectory releases cannot estimate
  pass probability or accepted-task cost.
- Run-level `prompt_tokens` and `total_reported_tokens` scopes may differ by
  source; no universal reconciliation rule is established.
- It is unknown whether public sources expose route/attempt chains needed to
  attribute failed-first-route and escalation cost to eventual acceptance.
- Censoring budgets, exposure axes and termination reasons may be absent, making
  survival analysis impossible for many sources.
- Historical price currency, tier multipliers, caching rules, tool fees and
  timestamps may be incomplete. Current prices cannot fill these silently.
- Subscription quota consumption has no justified conversion to API dollars.
- Current/peak context occupancy is generally not derivable from cumulative
  token usage; local 2B telemetry is likely required.
- Tool-output token burden, resent history and compaction-introduced tokens may
  require request/event linkage unavailable in public datasets.
- Repository size and task size units are not fixed across sources; comparisons
  require explicit units or source-specific strata.
- Framework/model aliases may not resolve to exact versions, limiting
  model-specific priors even when token counts exist.
- Unknown and not-applicable capability levels are not yet encoded distinctly in
  baseline feature construction.
- Effective sample size after grouping repeated tasks/repositories may be far
  below raw run count.
- The appropriate human-review valuation and failure penalty are policy choices,
  not empirical constants. High-impact harm should remain a hard constraint.
- No causal claim about tools, retries, caching, agent count, or model strength is
  supported without controlled/matched task allocation and common budgets.
- External validity from benchmark trajectories to the user's Codex workflows is
  unknown until a temporally held-out local 2B dataset is collected.
