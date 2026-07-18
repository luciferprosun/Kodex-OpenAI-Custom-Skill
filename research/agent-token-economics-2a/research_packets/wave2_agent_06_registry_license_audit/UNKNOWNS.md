# Unresolved Questions

Unknown means not established from the inspected primary packet evidence; it never means zero.

## Rights and licensing

1. What exact license and redistribution terms apply to each SWE-bench Experiments submission and its external S3 objects?
2. Do the SWE-smith trajectory assets carry the repository MIT license, and what licenses apply to embedded source-repository content?
3. What are the exact licenses, commercial-use terms, and per-file provenance for the two Nebius trajectory datasets?
4. Do WebArena and VisualWebArena authors authorize derived aggregate statistics from the separately hosted Drive traces?
5. Will AgentLab publish an artifact-level license, schema, manifest, checksums, and a privacy-reviewed bounded sample?
6. What license applies to GAIA `results_public`, independent of the gated core/submission terms?
7. What license applies to AgentBench data and public run logs?
8. Do Trace Commons records expose a machine-readable license and provenance field for every embedded trace component?
9. What license governs the independent OpenHands 41.9 GB trajectory archive?

## Dates, versions, and identity

1. What is the verified first release date of each dataset asset, distinct from its paper date and parent repository creation date?
2. Which immutable Hugging Face revisions were inspected for SWE-smith, Nebius, GAIA, AgentLab, Trace Commons, and the independent OpenHands archive?
3. Can every model alias in public trajectories be resolved to an immutable provider model ID and price-table date?
4. Which OpenHands legacy/V1 and SWE-agent schema versions are represented in each release?

## Size and sampling

1. What are compressed, extracted, and container/environment bytes for each candidate?
2. What is the bounded prefix/object inventory for a single SWE-bench submission?
3. Can AgentLab, Nebius, and independent OpenHands expose metadata-only Parquet/file indexes or range-readable samples without multi-gigabyte acquisition?
4. Are reported Hugging Face display sizes compressed transfer bytes, repository storage bytes, or extracted content sizes?

## Telemetry quality

1. Which candidate files contain provider-reported rather than framework-estimated token totals?
2. Are cached input, cache writes, reasoning tokens, and visible output independently available?
3. Are failed, censored, retried, and escalated attempts retained without survivor filtering?
4. Can run totals be reconciled exactly to per-request records without double-counting cumulative lifecycle events?
5. Are tool outputs, repeated history, and compaction-generated context measurable separately?
6. Is cost reported by the provider/framework, or reconstructed; if reconstructed, what dated price table and service tier were used?

## Publication and privacy

1. Can a future adapter produce only allowlisted counts, hashes, timestamps, tool categories, and outcomes while discarding prompt/reasoning/tool content immediately?
2. What independent secret/PII scan is sufficient for browser traces, agent logs, and donated sessions?
3. Which absolute paths or identifiers are necessary for reproducibility, and which must be generalized before Build Week publication?

Until these questions are answered, the corresponding fields stay null and the affected raw/derived/numerical gates remain closed.
