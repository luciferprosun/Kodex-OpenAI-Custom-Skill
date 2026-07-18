# Unknowns, Conflicts, and Required Follow-Up

Evidence cutoff: 2026-07-18.

## Critical blockers before quantitative ingestion

1. **AgentLab trace license.** The 207 GB Hugging Face archive has no dataset license metadata. The Apache-2.0 licenses for AgentLab and BrowserGym do not automatically cover run artifacts.
2. **AgentLab trace schema.** The archive card does not define token, cost, timing, request, failure, or model-identity fields. A bounded sample is required after licensing is resolved.
3. **WebArena/VisualWebArena artifact rights.** The Google Drive traces are linked from MIT/Apache repositories, but the resource pages do not state that the repository license applies to the archives.
4. **Trace Commons per-trace rights and privacy.** Compilation metadata is CC BY 4.0, but embedded content has heterogeneous licenses and contributor-certified—not independently verified—provenance. Anonymization is explicitly imperfect.
5. **Independent OpenHands archive license.** The 41.9 GB dataset has no license metadata. Only paper-level aggregates are usable now.
6. **Raw hidden-reasoning policy.** Several trace sources include text labeled thought, rationale, or reasoning. The corpus must record counts/metadata only and must not republish the content.

## Token-accounting unknowns

- Whether AgentLab public trace members preserve provider-reported prompt, cached, completion, and reasoning token fields per request.
- Whether image tokens and multimodal input are included consistently in VisualWebArena/AgentLab totals.
- Whether AgencyBench’s “Tok (M)” is the sum of provider-reported prompt and completion tokens, tokenizer reconstruction, or another counter.
- Whether AgencyBench totals include evaluator/user-simulation model calls or only the evaluated agent.
- Whether MegaAgent’s reported input/output totals include every subagent, evaluator, retry, and coordination request.
- Whether MetaGPT’s Table 1 and appendix use the same task sample, feedback configuration, code version, and model snapshot. They should be treated as different strata until resolved.
- Historical price tables and cache discounts for all aggregate paper results.
- Failed-run and budget-exhausted-run inclusion in aggregate totals.
- Current-context occupancy and compaction data: none of the accepted public sources in this packet exposes them reliably.
- Subscription-quota consumption: no inspected source maps it safely to API-billed tokens.

## Dataset-count and version unknowns

- Exact first public release date of the current AutoGPT repository lineage; only the historical 2023 era is established here.
- Exact number of runs/trajectories inside the AgentLab 207 GB archive.
- Compressed and extracted sizes of WebArena and VisualWebArena Google Drive traces.
- Size of the Mind2Web raw Globus dump.
- Exact per-harness composition of Trace Commons at the inspection cutoff; the viewer exposed 30 rows but supported formats do not guarantee that every harness was represented.
- Exact task/run count of the independent OpenHands trajectory archive should be verified from the primary paper/schema before registry normalization.
- AgentBench repository/data license and whether all paper runs are publicly recoverable.
- Explicit license metadata for GAIA `results_public`.

## Comparability conflicts

### MetaGPT / ChatDev

The MetaGPT paper’s main comparison reports aggregate token totals of 19,292 (ChatDev), 24,613 (MetaGPT without feedback), and 31,255 (MetaGPT). Another appendix configuration reports a different input-plus-completion total. These must not be averaged. The likely explanation is a different task sample/configuration, but this is not resolved by the inspected source.

### MegaAgent examples

The Gobang and national-policy examples use different models, agent counts, tasks, and output requirements. Their token totals demonstrate scale, not an agent-count response curve. No causal effect of adding agents can be estimated.

### AgencyBench model comparisons

Models were accessed through OpenRouter in the main experiment, and the paper also shows large scaffold-dependent score changes. Model identity, reasoning mode, provider routing, scaffold, tool definitions, and evaluator setup must all be strata—not averaged into a single model prior.

### Human web trajectories versus model runs

Mind2Web, WebLINX, and human WebArena/VisualWebArena traces are useful for step/action/context features. Any tokenizer-derived text length from them is a constructed feature and must not be labeled historical model input tokens or cost.

## Questions for source maintainers

1. Can AgentLab authors publish an artifact-level license, schema, archive manifest, checksum, uncompressed size, and 1–10 run sample with sensitive content removed?
2. Which AgentLab fields are provider-reported versus reconstructed, and are evaluator calls counted separately?
3. Do WebArena/VisualWebArena trajectory archives inherit the repository license, and may aggregate derived statistics be published?
4. Can AgencyBench publish per-run usage records with prompt/completion/cache/reasoning split and evaluator-call attribution?
5. Can MegaAgent publish request-level usage by agent and stage, including failed/retried requests?
6. Will Trace Commons add canonical optional usage fields, verifier outcomes, model snapshots, and per-trace source-license identifiers?
7. Can the independent OpenHands token archive receive an explicit license and schema card?

## Required SmartRouter local telemetry because public evidence cannot answer it

- exact per-request usage and model snapshot;
- cache-read/cache-write semantics;
- reasoning-token fields where exposed;
- tool-output bytes and tokens introduced into subsequent requests;
- context occupancy versus cumulative re-sent history;
- compaction triggers and before/after sizes;
- retry and escalation attribution;
- verifier result linked to total accepted-task cost;
- evaluator/handoff/subagent usage separated from primary-agent usage;
- price table and billing surface at run time;
- failed and censored runs retained, not only successes.
