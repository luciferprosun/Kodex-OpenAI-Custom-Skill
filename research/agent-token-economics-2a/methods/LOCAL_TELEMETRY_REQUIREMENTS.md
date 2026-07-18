# Local Telemetry Required for Research 2B

Public evidence is insufficient for a SmartRouter-specific accepted-cost model.
A future, separately authorized local telemetry mission should collect public-
safe derived records for:

- exact requested and service-confirmed model identity when exposed;
- product surface, Codex version, model alias and reasoning effort;
- per-request input, cached input, cache writes, reasoning and output tokens;
- last-turn versus cumulative-session usage;
- current/peak context occupancy when actually measured;
- request timestamps, latency, failures and rate-limit responses;
- tool-call type, duration, success, repeats, invalid calls and bounded output
  size/token estimate;
- compaction trigger, count and post-compaction context measurement;
- retry and escalation reason, source model and destination model;
- immutable attempt-chain ID, attempt sequence, chain-complete status, and the
  final accepted route decision;
- task taxonomy, repository size, files touched, ambiguity and risk;
- deterministic verifier identity/result and partial score;
- human-review minutes and final acceptance;
- API price-table date or explicit subscription-accounting source;
- currency, price-table ID, cost reconstruction basis, and separate model/API,
  tool, verification, human-review, and failure-penalty cost components;
- censored/budget-exhausted status;
- privacy-safe provenance and schema version.

Raw prompts, private conversation text, credentials, hidden reasoning, and raw
repository secrets are not required and should not be collected. Hashes,
categorical task features, counts, durations, outcomes, and aggregate tool-output
sizes are preferred.
