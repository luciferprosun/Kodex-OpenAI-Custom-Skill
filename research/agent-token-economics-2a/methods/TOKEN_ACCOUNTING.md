# Token-Accounting Semantics

These quantities are never silently merged:

- `prompt_tokens`: provider/framework input tokens for the request, normally
  including any cached subset when that surface defines it that way;
- `non_cached_input_tokens`: input tokens not served from cache, measured or
  explicitly reconstructed only when compatible fields exist;
- `cached_input_tokens`: input tokens read from cache;
- `cache_write_tokens`: input tokens written to a provider cache when the
  surface exposes this model/version-specific field;
- `reasoning_tokens`: non-visible reasoning-token count when the provider
  exposes it; never reconstructed from private reasoning text;
- `visible_output_tokens`: tokens in visible/model output as defined by source;
- `total_reported_tokens`: the source's reported total, not a forced sum across
  incompatible definitions;
- `cumulative_session_tokens`: total processing accumulated across a session;
- `current_context_occupancy`: content occupying the current model context;
- `tokens_resent_from_history`: history serialized again on later requests;
- `tokens_from_tool_output`: tool results introduced into later model input;
- `tokens_from_compaction`: compacted summaries introduced into later input;
- `api_billed_tokens`: tokens used by an API bill under the historical price
  semantics;
- `subscription_quota_units`: product-plan accounting, never inferred from API
  price tables.

`cached_input_tokens` reduces billed input cost on compatible API surfaces, but
does not mean the model processed a smaller logical prefix. Cache-hit ratio is
reported only when input and cache fields share one accounting definition.

Codex JSONL `turn.completed` exposes a per-turn usage object. Generated Codex
App Server schemas separately expose `last` and `total` token breakdowns plus a
model context-window field. The total is cumulative usage; the context-window
field is capacity. Neither establishes current occupancy without an additional
measurement.

Historical prices are joined only by model/surface and an applicable price date.
Reconstructed current-price comparisons are labeled counterfactual and are not
presented as the original billed amount.

## Scope and cost-chain rules

Run totals carry an explicit scope: `single_request`, `per_run_cumulative`, or
`unknown`. Request totals may be summed into a run only when the request
breakdown is declared complete and the definitions agree. Missing components
stay `null`; they are not treated as measured zero.

`normalized_cost` denotes the model/API component for the declared scope.
`tool_cost`, `verification_cost`, `human_review_cost`, and
`failure_penalty_cost` remain separate. Accepted-task cost is computed only from
a complete, ordered `attempt_chain_id` with one `route_final_accepted` run and
every required component observed under one currency and compatible price
table. This rule prevents survivorship bias and double counting.
