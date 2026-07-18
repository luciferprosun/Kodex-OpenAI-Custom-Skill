# Unknowns and required follow-up

Unknown means “not established from the inspected primary evidence,” not zero.

## Blocking unknowns for numerical ingestion

1. **SWE-bench Experiments license:** no repository license was declared. Obtain a human/legal decision and, ideally, submission-author or benchmark-owner clarification before raw use.
2. **S3 size and inventory:** exact object count, compressed bytes, extracted bytes, ETags/checksums, and per-submission schema distribution are unknown. Query inventory by one selected prefix only.
3. **SWE-bench per-request usage:** public SWE-agent trajectories generally expose whole-instance statistics, not request-level input/output/cache/reasoning tokens. Do not reconstruct without tokenizer/model/provider pinning.
4. **SWE-smith trajectory card:** exact HF revision, file list, total bytes, trajectory license, models, reward/outcome fields, token fields, and failed-run retention were not established.
5. **OpenHands run corpus:** no single official homogeneous trajectory archive with exact token fields, task outcomes, model versions, and licenses was identified. Audit each release separately.
6. **Harbor Hub result schema coverage:** determine which adapters populate input, cached input, reasoning, output, cost, and timing fields, and whether missing values are null or omitted.
7. **Harbor result licensing:** framework Apache-2.0 does not prove that every uploaded leaderboard trajectory is redistributable.
8. **STATE-Bench baseline artifacts:** determine whether all five repeats and run-level input/output/retrieval token counts are publicly downloadable, and whether cost uses provider billing or reconstruction.
9. **AgentRE-Bench reports:** establish whether public reports contain observed token usage or only response/tool budgets; identify any publicly licensed failed run traces.
10. **Multi-SWE-bench trajectories:** determine whether inference trajectories for the nine-model/three-framework study were released, and locate exact usage fields if so.
11. **Nebius releases:** verify dataset-card licenses, exact Xet sizes, row schemas, task/repository duplication, success/failure labels, tokenizer/model versions, and filtering procedures.
12. **Price dates:** none of the mixed historical trajectory archives can be assumed to use the current model price table. Preserve reported cost and reconstructed cost separately.

## Comparability unknowns

- prompt templates, system instructions, tool schemas, max-turn/cost budgets, and model reasoning settings for many leaderboard runs;
- whether “tokens sent” includes tool output, repeated history, images, cached input, or provider-specific accounting;
- whether “tokens received” includes hidden reasoning tokens;
- whether SDK retries and failed API calls are included in aggregate usage;
- whether context condensation/compaction is logged and how its generated tokens are counted;
- inference timestamp versus evaluation/upload timestamp;
- whether model aliases resolve to immutable snapshots;
- failure categories for missing or truncated trajectories;
- number of independent attempts behind best-of-k submissions;
- repository size at the exact task base commit and tool-output burden by file operation;
- complete population denominators for training trajectory releases.

## Follow-up queries that do not require corpus download

1. Use Hugging Face dataset APIs to retrieve `siblings`/file indexes, revisions, byte sizes, licenses, and Parquet schemas for SWE-smith and Nebius releases.
2. Use Harbor Hub/API metadata to enumerate a single Terminal-Bench model row and inspect one trial manifest without fetching terminal recordings.
3. Enumerate `SWE-bench/experiments` submission metadata and choose one complete, single-attempt SWE-agent run with an explicit model snapshot; do not fetch trajectories until license approval.
4. Compare schema keys across a maximum of five immutable trajectory blobs using HTTP range/individual blob retrieval.
5. Contact maintainers about raw-trajectory redistribution and per-call usage preservation where licenses or fields are unclear.

## Required SmartRouter local telemetry because public data cannot answer it reliably

- provider-reported input, cached input, reasoning, and visible output tokens per request;
- request ID, immutable model ID, reasoning effort, price-table date, and API-vs-subscription surface;
- history tokens re-sent, tool-output tokens added, compaction input/output, and peak context occupancy;
- retry reason, failed-call usage, escalation reason, and attempt linkage;
- tool call start/end, output bytes/tokens, invalid/repeated call classification;
- exact verifier type/result, infrastructure failure versus task failure, and accepted-result timestamp;
- wall time partitioned into model, tool, environment, verifier, queue, and human-review time;
- agent count, handoffs, and per-agent usage to avoid double-counting shared context;
- repository/task size features measured at run start;
- censored-budget outcome and remaining budget.
