# Recommended evidence and adapter contract

## Safe artifact to retain

Retain `FIELD_INVENTORY.jsonl` as a derived integrity and schema-coverage fixture. It contains no prompt, thought, observation, action argument, patch, or response text.

## Normalization rule

For this exact corpus revision:

- set canonical token and monetary-cost fields to `null`;
- set their measurement method to `unknown`;
- add `placeholder_zero_in_demonstration` to `missing_fields` or equivalent provenance;
- set `task_success`, `verifier_result`, and `partial_score` to `null`;
- do not derive success from `exit_status = submitted`;
- do not map `api_calls` to canonical model-request count;
- set quality class to E;
- set `included_in_numerical_priors = false`.

## Resource-bounded acquisition adapter

The adapter should:

1. accept an immutable revision and an allowlisted directory;
2. enumerate Git tree metadata before reading blobs;
3. reject symlinks and non-blob entries;
4. enforce 25 files, 2 MiB aggregate, and 512 KiB per-file ceilings for this fixture;
5. stream or read each blob once, compute SHA-256, and parse JSON in memory;
6. emit safe structural fields and counts only;
7. explicitly detect placeholder-zero usage objects in non-empty trajectories;
8. recognize `history`, `trajectory`, and nested-message representations without summing overlaps;
9. discard raw bytes after inspection;
10. require the upstream MIT notice alongside any redistributed derived fixture.

## Tests this fixture can support

- old trajectory/history shape parsing;
- history-only shape parsing;
- optional `replay_config` handling;
- missing model identifier handling;
- absent versus zero distinction;
- placeholder-zero rejection;
- absent `total_cost` handling;
- non-success interpretation of `submitted`;
- duplicate representation detection;
- thought/reasoning-content exclusion;
- per-file checksum and size verification.

## Tests it cannot support

- provider token correctness;
- cached or reasoning-token parsing;
- cost reconstruction;
- request-level accounting;
- success-conditioned distributions;
- accepted-task cost;
- retry or escalation economics;
- latency prediction;
- model-comparison priors.

## Publication decision

Publish source references, immutable revision, hashes, field coverage, aggregate counts, and adapter tests. Do not commit the 1.5 MB of raw trajectories because it adds thought/task text but no valid token-economics measurement.
