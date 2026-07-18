# Wave 1 / Agent 02 — Software-engineering and terminal-agent trajectories

Evidence cutoff: 2026-07-18 (Europe/Berlin)
Scope: primary repositories, papers, dataset cards, and official benchmark pages only.
Acquisition policy: metadata and source inspection only; no trajectory corpus was cloned or downloaded and no paid inference was used.

## Executive finding

The public software-engineering-agent ecosystem contains many *trajectories*, but very few releases are immediately usable as a model-routing token corpus. Three independent gates must pass:

1. the run must expose sufficiently exact token and cost fields;
2. the task, model, framework, verifier, version, and outcome must be identifiable;
3. the trajectory asset—not merely its surrounding code—must have redistribution and derived-statistics rights that are clear enough for the planned use.

No inspected release passed all three gates strongly enough to recommend committing a raw token-telemetry sample in this mission. This is a useful negative result, not an absence of public data:

- `SWE-bench/experiments` is the strongest *discovery index* for outcome-linked software-agent runs, but the repository declares no license and the S3 trajectories have submission-specific schemas and unknown total size.
- SWE-agent records whole-run `tokens_sent`, `tokens_received`, `api_calls`, and `instance_cost` in its current `InstanceStats`; historical `.traj` files can contain compatible aggregate statistics. However, per-request token accounting is not normally present in the public SWE-bench trajectory files, and old/current formats differ.
- The 19 demonstration `.traj` files currently committed in the MIT-licensed SWE-agent repository form an excellent bounded parser fixture (1,503,861 bytes total at commit `3ea751c…`). Inspection did not establish uniform run-level token fields, so this sample must not become a numerical prior.
- SWE-smith advertises 52,000 task instances and 26,000 SWE-agent trajectories, but the trajectory asset card, exact byte size, per-run telemetry coverage, and dataset-license applicability must be checked before sampling.
- Harbor provides the most promising current normalization layer through trial results and the Agent Trajectory Interchange Format (ATIF), but usage completeness is agent-adapter-dependent. A Harbor trajectory is not automatically provider-measured telemetry.
- OpenHands exposes reproducible evaluation harnesses, rich tool-call logging, outcomes, and framework metrics. There is no single official, homogeneous OpenHands trajectory corpus with stable token fields across versions and benchmarks.
- STATE-Bench, AgentRE-Bench, Terminal-Bench, and Multi-SWE-bench are valuable task/verifier sources. Their public task releases alone are not historical token corpora.

## Repository snapshot and storage implications

GitHub repository metadata was queried without cloning. `diskUsage` is GitHub's approximate repository disk usage in KiB and does **not** include external object stores, container images, Hugging Face/Xet assets, or extracted task environments.

| Repository | Inspected HEAD | Approx. GitHub disk usage | License signal | Implication |
|---|---:|---:|---|---|
| `SWE-bench/experiments` | `2f15350c…` | 344,242 KiB | none declared | Metadata repo is already ~336 MiB; S3 logs/trajectories are additional and described by maintainers as very large. Use per-submission metadata/API access only. |
| `SWE-bench/SWE-smith` | `9b74ac08…` | 14,518 KiB | MIT | Code clone is modest, but HF tasks, trajectories, and 250+ container environments are external and much larger. Query file indexes first. |
| `SWE-agent/SWE-agent` | `3ea751c0…` | 72,038 KiB | MIT | A sparse/contents-API sample is preferable to cloning for trajectory parser work. |
| `OpenHands/OpenHands` | `11d4ecf2…` | 357,887 KiB | mixed (`NOASSERTION`) | Core is described as MIT; `enterprise/` has separate terms. Never bulk-copy the mixed tree. |
| `harbor-framework/harbor` | `678bbb6d…` | 45,229 KiB | Apache-2.0 | Shallow/sparse source inspection is practical; run artifacts live outside the code repo. |
| `harbor-framework/terminal-bench-2` | `2fd12b88…` | 46,843 KiB | Apache-2.0 | Task source is bounded, but evaluation environments/container layers can be large. |
| `microsoft/STATE-Bench` | `4efcbf2d…` | 4,019 KiB | MIT | Small code/task repository; running its 450 tasks five times would incur inference and environment costs and was not authorized. |
| `agentrebench/AgentRE-Bench` | `9b995bf9…` | 3,197 KiB | MIT | Small, 13-task public benchmark; existing public runs do not expose a normalized token corpus. |
| `multi-swe-bench/multi-swe-bench` | `24f493f8…` | 5,205 KiB | Apache-2.0 | Harness code is small; datasets, patches, images, and evaluation artifacts are external. |

## Source-by-source findings

### 1. SWE-bench experiments archive

The official repository describes each submission directory as containing predictions, metadata, a README, evaluation logs, and—when supplied—reasoning trajectories. The canonical evaluator produces per-instance `report.json`, `test_output.txt`, and `patch.diff`. Split sizes documented in the repository include 300 Lite, 500 Verified, 300 Multilingual, and 2,294 Test evaluation artifact folders, although an individual submission can be incomplete or target a different split/version.

Strengths:

- exact task instance IDs and generated patches;
- objective verifier artifacts for resolved and unresolved instances when a complete submission is present;
- submission metadata requires model identifiers, organization, system openness, and attempt policy;
- supports success- and failure-conditioned sampling rather than survivorship-only analysis;
- trajectory and log files often expose tool interactions and framework-specific usage totals.

Telemetry limits:

- formats vary by submitter and framework;
- in public SWE-agent `.traj` records, usage is normally a whole-run aggregate rather than a request ledger;
- cached input, reasoning tokens, context occupancy, compactions, retries inside SDKs, and price-table date are generally absent;
- `total_cost` can mean a process-wide cumulative counter, while `instance_cost` is the task value—these must never be interchanged;
- model aliases in directory names are insufficient; use `metadata.yaml` plus trajectory/config evidence;
- evaluation timestamps and inference timestamps may differ.

Acquisition and license:

- repository metadata can be read without downloading trajectories;
- official scripts fetch one submission from a public S3 bucket, but an AWS account/configuration is required;
- maintainers warn that broad bucket download is “a ton of data”; no bounded size is published;
- no repository license was declared at the inspected revision. Public accessibility is not permission to republish.

Recommendation: **accept as a discovery and local-derived-statistics source; do not redistribute raw trajectories or use mixed submissions as one population.** A candidate run becomes quality C or better only after field-level inspection, model/framework pinning, evaluator-version pinning, and a license decision.

### 2. SWE-agent framework and demonstrations

Current SWE-agent source defines per-instance fields:

- `instance_cost`;
- `tokens_sent`;
- `tokens_received`;
- `api_calls`.

The framework updates these from LiteLLM input/output counts and its cost calculator. These names are cumulative *within one instance*. They do not distinguish cached input, provider reasoning tokens, tool-output tokens, or tokens re-sent from history. Per-call values are logged by current code, but maintainers confirmed in an official issue that the public SWE-bench `.traj` files generally do not preserve per-call sent/received counts; reconstructing them from messages would be tokenizer- and provider-dependent.

The documented trajectory format contains thought/action/observation or newer role/message/tool-call histories. Companion files may include configuration, batch exit statuses, logs, and predictions. Format changes across releases make version identification mandatory.

Bounded fixture inspection at `3ea751c…` found 19 demonstration `.traj` blobs totaling 1,503,861 bytes. They include CTF tasks, HumanEvalFix, a synthetic function-calling example, and multiple replays of one Marshmallow issue. This sample is:

- legally low-risk under the repository's MIT license, subject to preserving the license notice;
- small enough for direct GitHub contents/blob retrieval;
- useful for parser compatibility and tool-call extraction;
- badly duplicated and domain-skewed for statistical modeling;
- not verified to have uniform run-level token fields.

Recommendation: **accept as parser fixtures only; reject for token priors.** No raw hidden/thought text should be copied into the public SmartRouter repository even when MIT permits it; derived counts and schema fixtures are sufficient.

### 3. SWE-smith

The official project reports:

- 52,000 synthesized task instances;
- 26,000 SWE-agent trajectories;
- 250+ repository environments;
- an MIT license for the repository.

This is attractive for stratifying by success/failure and trajectory length, but the public project summary does not establish that all 26,000 trajectories contain exact provider token totals, per-request usage, timestamps, or historical price tables. Training trajectories may also be filtered in ways that over-represent usable/completed rollouts.

Recommendation: **accept into the dataset registry; defer quantitative ingestion.** Before sampling, query the Hugging Face file index for exact bytes/checksums, inspect the dataset card's license (not only the code repository license), identify reward/outcome fields, and compute a stratified list without downloading payloads.

### 4. OpenHands and OpenHands/benchmarks

The original OpenHands paper and repository establish a general software-agent platform and evaluation framework. The newer `OpenHands/benchmarks` repository is the official evaluation harness for the OpenHands Agent SDK and is MIT-licensed. Its documentation reports rich run logging with task ID, patch state, assistant/user message counts, tool-call count, agent/conversation errors, and end condition. Individual benchmark adapters provide verifier results and generated patches.

Comparability hazards are severe:

- legacy OpenHands and V1 SDK/benchmarks have different event and metrics structures;
- benchmark code must be pinned to a compatible SDK commit;
- LLM provider adapters can expose different usage detail;
- model configuration, budget limits, runtime image, prompt template, condenser, and microagents materially alter token use;
- evaluation may run in Docker or a remote runtime;
- core OpenHands is MIT, but the monorepo contains a separately licensed `enterprise/` directory.

Recommendation: **accept the harness as a future locally measured source and accept individually licensed public run datasets only after card-level audit.** Do not treat rich console summaries as token telemetry, and do not combine legacy and V1 runs.

### 5. Terminal-Bench 2.x and Harbor

Terminal-Bench 2.0 comprises 89 containerized terminal tasks with tests and human-written solutions; Harbor Hub lists 89 tasks for both 2.0 and 2.1. The task repository and Harbor are Apache-2.0. Harbor is the official harness for Terminal-Bench 2.x and supports standardized trial artifacts and ATIF trajectory conversion.

Harbor is promising because one trial can bind:

- task and dataset version;
- agent and model configuration;
- start/end timing;
- terminal/tool trajectory;
- verifier reward/result;
- adapter-reported usage and cost when the adapter provides them.

It is not safe to infer that every leaderboard row has complete provider usage. Release notes themselves show continuing adapter-specific work such as populating `cost_usd` for one CLI agent. ATIF normalizes event shape, not measurement provenance.

Recommendation: **accept task metadata and licensed framework schemas; accept a public result only after checking its individual result license and usage fields.** Use Harbor Hub/API row manifests for discovery, then retrieve a bounded trial by ID rather than cloning all leaderboard logs.

### 6. STATE-Bench

Microsoft's official release describes 450 tasks across customer support, travel, and shopping. Each task is run five times in the baseline. Metrics include task completion, pass^5 reliability, turns, unnecessary tool calls, all input/output/retrieval tokens, and average cost. State-mutating tasks use deterministic final-state assertions; other procedural/informational tasks can use an LLM judge.

This source is valuable for session-history amplification, repeated attempts, and tool efficiency, but it is not a software-repository coding corpus. The inspected sources did not establish a downloadable, run-level baseline trajectory archive with exact model request usage.

Recommendation: **accept as a task/verifier and future locally measured source; do not use published aggregate figures as per-run priors.** Any new baseline requires paid inference and separate approval.

### 7. AgentRE-Bench

The public MIT-licensed benchmark currently documents 13 binary reverse-engineering tasks. It supplies deterministic/scored ground truth, tool-use loops, a default 25-tool-call budget, and a 4,096 maximum-token setting per response. These are *budgets*, not observed usage. The benchmark can produce reports and tool traces, but the inspected public release did not establish provider-reported run-level token counts or a reusable public results corpus.

Recommendation: **accept tasks and verifier metadata; reject from numerical token priors until measured runs with explicit model/version and usage fields exist.** Raw reasoning/report text is unnecessary for SmartRouter.

### 8. Multi-SWE-bench and Multi-SWE-RL

Multi-SWE-bench expands issue resolution beyond Python and reports evaluations of nine models across Agentless, SWE-agent, and OpenHands. The official repository documents:

- Mini: 400 instances across eight languages;
- Flash: 300 instances;
- Multi-SWE-RL initial release: 4,723 instances.

The repository and harness are Apache-2.0, with data hosted on Hugging Face and evaluation images outside the small code repository. Public result patches and leaderboard scores do not by themselves establish token telemetry. Cross-language differences, agent prompts, container images, and task-selection variants prevent naive aggregation.

Recommendation: **accept as task/verifier strata; reject as a token corpus unless a run release provides exact trajectories and usage.** Inspect the data asset license separately because source repositories referenced by tasks retain their own licenses.

### 9. Additional reputable trajectory releases

Two large independent releases are discovery candidates:

- Nebius `SWE-agent-trajectories`, reported as 80,036 software-engineering trajectories;
- Nebius `SWE-rebench-openhands-trajectories`, reported as 67,074 OpenHands trajectories across 3,800 resolved issues and 1,800+ Python repositories.

These scale claims are useful for discovery, but neither was accepted for quantitative SmartRouter priors in this pass. Exact file sizes, dataset-card license, complete failure coverage, token field provenance, model checkpoints, filtering, and duplicate/task leakage require direct card and file-index audits.

SWE-Gym/SWE-smith-style training releases are similarly useful for trajectory-shape research but are commonly filtered for training value. They must not be used to estimate unconditioned task success or accepted-task cost without restoring the sampling/selection mechanism.

## Failure-trajectory and survivorship findings

- SWE-bench submission directories *can* contain all evaluated instances, including unresolved runs, but completeness must be checked against the split size and prediction list.
- Training datasets often select valid, parseable, reward-bearing, or successful trajectories. Their failure rate is not the deployment failure rate.
- Public leaderboards preferentially receive competitive systems and successful configurations. They omit abandoned experiments and routing failures.
- A missing trajectory may mean “not attempted,” “failed before agent start,” “upload omitted,” or “submission policy did not require it.” It must never be interpreted as zero usage.
- Budget-exhausted, context-overflow, and infrastructure-error runs need separate censoring labels. Grouping them with verifier failures biases both token and capability estimates.

## Recommended bounded acquisition sequence

1. Commit only registries, schemas, and code that can read remote indexes.
2. Use GitHub/Hugging Face metadata APIs to obtain path, byte size, revision, checksum, and license before any payload.
3. Use the 19 SWE-agent demonstrations only as parser fixtures; record no numerical token prior from them.
4. Select one `SWE-bench/experiments` submission by model/framework/version only after a human license decision. Fetch its metadata and prediction/result index before any `.traj`.
5. If raw redistribution remains unclear, compute local aggregates and commit only task ID hashes, field-coverage counts, distribution summaries, source revision, and analysis code.
6. For Harbor, select trials by immutable row/trial IDs and require adapter-reported usage provenance.
7. Stratify successes, verifier failures, budget exhaustion, context failures, invalid tool calls, and infrastructure failures separately.

## Safe-sample decision

**No legally and methodologically safe small sample with verified actual run-level token telemetry was accepted for publication in this pass.**

Nearest candidates:

- `SWE-agent/SWE-agent` demonstrations: license clear and only ~1.50 MB, but telemetry coverage is not uniform/verified; parser-only.
- `SWE-bench/experiments`: outcome and some aggregate token/cost fields exist, but license is absent and schemas vary; local metadata/derived-statistics only after human review.

This decision prevents a weak sample from being mislabeled as provider-measured evidence.
