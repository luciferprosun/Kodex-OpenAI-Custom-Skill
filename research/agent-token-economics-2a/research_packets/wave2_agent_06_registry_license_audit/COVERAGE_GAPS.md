# Coverage Gaps

Evidence cutoff: 2026-07-18.

## Historical coverage

- **2022–2023 ReAct and autonomous-agent era:** framework papers, prompts, and outcomes exist; provider-reported request token telemetry, cache fields, verified retries, and standardized failed-run archives do not.
- **2023–2024 browser-agent era:** WebArena, VisualWebArena, Mind2Web, GAIA, AgentBench, and AgentBoard cover tasks/actions/outcomes, but not a licensed, request-level token corpus. Browser artifacts also carry substantial privacy and secret risk.
- **2023–2025 multi-agent era:** MetaGPT and MegaAgent provide small aggregate tables, not request distributions, cache use, failure-conditioned costs, or comparable verifier chains.
- **2024–2026 software-agent era:** SWE-agent, SWE-bench, OpenHands, Harbor, and related benchmarks expose useful outcomes and some framework totals, but public samples lack a common request schema, exact model identity, cache/reasoning separation, complete failed attempts, and uniform license terms.
- **Current OpenAI/Codex era:** official interfaces define strong local telemetry surfaces, but public task-linked Codex runs with verifier outcomes, retries, compactions, escalation chains, and publication-safe licenses were not located.

## Telemetry-field gaps

No accepted public dataset currently supplies all of the following on the same run:

- exact immutable model and framework/version;
- per-request input, cached input, cache write, reasoning, visible output, and total tokens;
- current context occupancy versus cumulative session usage;
- tool-output token burden and history re-send burden;
- compaction count and before/after context sizes;
- retries and a complete escalation chain;
- objective verifier outcome, including failed and budget-censored attempts;
- wall time with rate-limit/tool/human-wait separation;
- dated reported and reconstructed cost components;
- clear raw and derived-statistics rights.

## Dataset and task gaps

- Mathematics and physics agent trajectories with objective verifiers and provider token telemetry are effectively absent from the discovered corpus.
- Web and computer-use traces with provider usage exist as possible framework artifacts, but their public archive licenses and schemas are unresolved.
- Long continuing Codex sessions have no public-safe dataset separating cumulative tokens, active context, re-sent history, compactions, and cache reads.
- Multi-agent datasets do not isolate the effect of agent count from task, model, scaffold, and budget.
- Failure, timeout, budget exhaustion, and abandoned trajectories are underrepresented; successful/training-selected trajectories dominate several releases.
- Human-review time and verification cost are rarely recorded.
- Repository size, exact base commit, files touched, and tool-output bytes are rarely joined to usage.
- Subscription quota consumption cannot be reconstructed from API token prices and is absent from public benchmark data.

## Licensing and acquisition gaps

- Missing artifact licenses block SWE-bench submission reuse, AgentLab traces, both Nebius trajectory candidates, WebArena/VisualWebArena Drive artifacts, and the independent OpenHands archive.
- Gating/no-reshare blocks public GAIA task/submission redistribution.
- Noncommercial/share-alike terms limit WebLINX reuse.
- Exact compressed and extracted sizes are unknown for many linked archives; GitHub `diskUsage` cannot fill this gap.
- No approved public raw sample has both exact provider-reported run tokens and an objective task outcome.

## Registry-engineering gaps

- Stable source and dataset identities are not yet implemented.
- Availability, count, decision, rights, and size fields lack a strict registry schema.
- Dataset-to-source referential integrity is not enforced.
- Contradictory license/date/field claims do not trigger a hard review gate.
- The Markdown registry does not expose enough rights and risk information for publication approval.

## Minimum local collection needed for 2B

SmartRouter should collect authorized local, content-minimized run/request records with exact model/surface/version, task stratum, request usage fields, tool categories and byte counts, context/compaction events, retry/escalation chain IDs, timestamps, verifier result, censoring reason, price-table ID, and human-review minutes. Raw prompts, tool contents, and reasoning text are not required for token-economics modeling.
