# Unknowns and Required Follow-up

## Provider/API unknowns

- No versioned official historical price-table API was established. Current prices cannot silently price historical runs.
- Responses usage does not directly expose visible-output tokens, tool-output tokens, tokens re-sent from history, tokens introduced by compaction, retry count, escalation count, verifier outcome, or accepted-task cost.
- The precise relationship between provider usage timestamps and end-to-end client wall time still requires client-side monotonic timestamps.
- Organization Usage API does not expose reasoning-token aggregates or task/run identifiers, and Organization Costs API is not per request.
- Rate-limit headers do not establish ChatGPT subscription usage or dollar cost.
- No official field maps API token usage to Codex/ChatGPT subscription-credit consumption.

## Agents SDK unknowns

- Exact trace export/retention behavior and content minimization must be configured and reviewed per deployment.
- Third-party model adapters can omit token details. The SDK's normalization of absent optional detail fields to zero makes upstream presence/absence provenance essential.
- Tool-output token burden and repeated-history burden are not separately reported by the SDK; local instrumentation must measure serialized request components or controlled deltas.
- Success, acceptance, verification, human-review time, retry semantics, and escalation semantics remain application-defined.

## Codex unknowns

- The `cache_write_input_tokens` field is present in the inspected current source definition but is not shown in the current manual's JSONL sample. Consumers must version-gate it.
- The locally generated app-server schema is valid for CLI 0.144.5; forward/backward compatibility was not established.
- The generated app-server token breakdown does not expose cache-write tokens in version 0.144.5.
- `modelContextWindow` is exposed by app-server telemetry, but exact current context occupancy and compaction savings are not exposed by `codex exec --json`.
- Rollout/session JSONL has no public stability contract. Its full type coverage, retention, size behavior, and schema migrations require source-version-specific study, not raw public ingestion.
- No private session file was opened, so the local population's completeness and rate-limit payload availability remain deliberately unmeasured.

## SmartRouter 2B fields that still require local collection

- `task_id`, `attempt_id`, `route_decision_id`, and parent/child agent IDs.
- Task taxonomy, SE/MATH/PHY level, repository size, files touched, ambiguity, risk, and verifier type.
- Per-request start/end timestamps and monotonic wall time.
- Tool invocation start/end, type, result status, retries, repeated calls, and allowlisted output byte/token estimates.
- Context occupancy before/after each request, explicit compaction events, and compaction trigger/cause.
- Retry, escalation, cancellation, budget exhaustion, and censoring reason.
- Verifier result, partial score, accepted/rejected result, and human-review minutes.
- Price-table snapshot and separately reconstructed versus provider-reported monetary cost.
- Field-level measurement method and missingness reason; never replace an absent provider field with measured zero.
