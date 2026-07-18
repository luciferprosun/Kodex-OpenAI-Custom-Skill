# Findings: Historical, Web, Autonomous, and Multi-Agent Public Telemetry

Evidence cutoff: 2026-07-18 (Europe/Berlin).

## Scope and method

This packet covers public primary sources for early tool-using agents, autonomous-general-agent projects, web/computer-use benchmarks, GAIA implementations, multi-agent systems, and recent public trajectory releases. It uses official repositories, original papers, and official dataset cards. No corpus was downloaded, no paid inference was run, and no social-media estimate was admitted as routing evidence.

Every candidate was evaluated separately for:

1. exact model identity;
2. exact agent/framework identity;
3. task identity and objective verifier;
4. token-field semantics and measurement method;
5. request-level versus aggregate resolution;
6. trajectory completeness and failed-run coverage;
7. license, redistribution, privacy, secret, and hidden-reasoning risk;
8. resource-bounded access options.

Unknown values remain `null`. The packet does not reconstruct usage from text lengths unless such a reconstruction is explicitly labeled and a tokenizer/model version is fixed.

## Executive findings

### 1. Public trajectory availability is not the same as token telemetry

The historical record is rich in prompts, actions, screenshots, DOM/accessibility observations, tool outputs, and success labels. It is sparse in provider-reported input, cached-input, output, and reasoning-token fields. In particular:

- ReAct, AutoGPT, BabyAGI, GAIA public results, AgentBench, AgentBoard, Mind2Web, WebLINX, AgentVerse, and Magentic-One do not provide a comparable public run-level token corpus in the inspected artifacts.
- WebArena and VisualWebArena provide unusually useful trajectories and objective execution outcomes, but the published trajectory descriptions do not document provider-usage fields.
- A visible chain-of-thought trace is content, not a provider’s `reasoning_tokens` counter.
- A context-length limit or heuristic word/character counter is not billed input-token usage.

### 2. Three aggregate sources are informative but not sufficient for priors

**MetaGPT (SoftwareDev).** The ICLR paper reports aggregate token use and run time for ChatDev and two MetaGPT variants. The main comparison uses a small sampled task set and gives 19,292, 24,613, and 31,255 tokens respectively. An appendix configuration reports a different MetaGPT total with an input/completion split. These figures must remain separate because sample, feedback configuration, and possibly paper version differ. There is no request-level record, cache field, price-table date, or failed-run distribution. Preliminary quality: **D (aggregate/partially specified)**.

**MegaAgent.** The ACL paper reports aggregate input/output totals for a seven-agent Gobang implementation and a 590-agent national-policy simulation. These examples make the multi-agent amplification mechanism concrete: inter-agent dialogue dominates input volume. They are, however, bespoke demonstrations with very small sample counts, incomplete request-level accounting, and different backbone models. They are not population estimates. Preliminary quality: **C/D boundary; use descriptively, not as a general routing prior**.

**AgencyBench.** The ACL 2026 paper reports average total tokens, wall time, tool-calling turns, model scores, and tool mix across 138 tasks/32 scenarios. It is valuable evidence that scaffold and model are coupled, and that long-horizon tasks can reach million-token totals. The paper does not provide request-level input/output/cache/reasoning separation or a sufficiently explicit accounting pipeline for direct normalization. Preliminary quality: **D for this corpus**.

### 3. AgentLab traces are the strongest web-agent acquisition candidate, but currently blocked

The BrowserGym paper states that AgentLab automatically adds a cost/token tracker to agent information. The associated public archive is 207 GB and covers multiple browser benchmarks and models. However, the Hugging Face repository has only an 85-byte assembly instruction, no schema, no license metadata, and no dataset viewer. Therefore:

- do not download the five large archive parts;
- do not assume the Apache-2.0 code license covers the trace archive;
- first request or locate an explicit data license and schema;
- then inspect a byte-range or author-provided bounded sample;
- scan for prompts, rendered pages, cookies, network records, credentials, personal data, and visible reasoning before any normalization;
- verify that token counts are provider- or framework-reported per request rather than estimates.

Decision: **accepted as a discovery candidate; rejected for current numerical ingestion pending license/schema/privacy audit**.

### 4. Trace Commons is small and accessible, but biased and legally heterogeneous

At inspection, Trace Commons contained 30 volunteered sessions totaling 127 MB. The compilation and metadata are CC BY 4.0. The dataset card explicitly warns that individual trace content retains original licensing, contributor certification is not independently verified, anonymization is best-effort, and the sample is not representative.

The normalized viewer exposes session/harness, prompts, messages, tools, timestamps, message counts, tool-call counts, and raw trace metadata, but no explicit canonical token columns. Native raw metadata may contain harness-specific usage, which must be audited rather than assumed.

Decision: **candidate for tool/context-structure research after per-trace audit; not yet numerical routing evidence**. Never republish raw sessions in the SmartRouter public repository.

### 5. Web trajectories have elevated secret and privacy risk

WebArena, VisualWebArena, Mind2Web, and AgentLab artifacts can contain page HTML, screenshots, accessibility trees, raw model predictions, Playwright traces, HAR/network traffic, storage state, cookies, and login material. Even self-hosted benchmark sites can expose credentials or reset tokens in traces. Safe publication should default to:

- aggregate counts and derived statistics;
- source references and checksums;
- no raw browser recording, network archive, storage state, or full prompt/reasoning transcript;
- an additional secret/PII scan even when upstream claims anonymization;
- explicit separation of human-demonstration text lengths from model token usage.

### 6. GAIA is useful for outcomes, not public token economics

GAIA’s public results dataset has 3.61k rows with model/system/score/date information and no token fields. The core dataset is 110 MB and gated; the validation-submission repository is 2.64 MB and gated. Current access conditions prohibit redistribution outside gated/private Hugging Face repositories. These assets may support task taxonomy and outcome labels, but not token priors. Public leaderboard results must not be paired with guessed token costs.

### 7. Human web datasets cannot establish model efficiency

Mind2Web and WebLINX are valuable for task/action structure, web-context size, trajectory length, ambiguity, and tool-intensity features. Their human demonstrations do not identify model requests or provider token usage. Tokenizing those traces can produce a **derived text-length feature**, not historical model consumption. WebLINX is additionally CC BY-NC-SA 4.0 with third-party-content and fair-use conditions.

## Preliminary source decisions

| Source family | What is actually public | Token measurement status | Preliminary quality | Numerical-routing decision |
|---|---|---|---|---|
| ReAct | Prompts/notebooks/results | Absent | E for token economics | Reject |
| AutoGPT / BabyAGI | Framework code and examples | No standardized historical run corpus found | E | Reject |
| WebArena / VisualWebArena | Agent/human trajectories, actions, screenshots, pass/fail | No documented usage fields | D/E | Reject; retain structural features |
| GAIA | Gated tasks/submissions and public scores | Absent from public results | E | Reject; retain outcomes |
| AgentBench | Multi-turn histories and results | Heuristic history counter only | D/E | Reject as measured usage |
| AgentBoard | Task/subgoal/difficulty records | Absent | E | Reject; retain taxonomy |
| Mind2Web / WebLINX | Human interaction traces and web state | Absent | E | Reject; retain structural features |
| BrowserGym / AgentLab archive | Large run archive; framework tracks token/cost | Potentially present, schema/license unverified | `null` pending audit | Blocked pending audit |
| MetaGPT comparison | Aggregate time/token totals | Aggregate, incompatible configurations | D | Qualitative only |
| MegaAgent appendix | Aggregate input/output/time/agent counts | Aggregate for bespoke examples | C/D | Descriptive only |
| AgencyBench | Aggregate token/time/turn/tool statistics | Aggregate; accounting method under-specified | D | Qualitative only |
| Trace Commons | Native donated coding-agent sessions | No canonical token columns; raw metadata varies | `null` pending audit | Structural candidate only |
| Independent OpenHands token study | Paper aggregates and 41.9 GB trajectory archive | Promising token categories; raw license absent | `null` pending audit | Paper only; raw ingestion blocked |

## SmartRouter implications

Public data from this scope cannot reliably estimate all of the target fields. SmartRouter must collect local telemetry for at least:

- provider-reported `input_tokens`, `cached_input_tokens`, `output_tokens`, and reasoning-token fields when exposed;
- request count and exact model/version per request;
- system/developer/user/tool-result token contributions;
- current context occupancy versus cumulative tokens re-sent;
- compaction count, compaction input/output size, and post-compaction context;
- retries, failed first choices, escalation events, and verifier outcomes;
- tool calls by type, invalid/repeated calls, and tool-output byte/token burden;
- wall time, rate-limit waits, human-review minutes, and price-table date;
- agent count and per-agent request/token attribution.

The public sources can still support priors for **structure**: expected number of steps, tool intensity, long-horizon risk, task/verifier type, browser-observation burden, and possible multi-agent amplification. Those features must be kept separate from billed-token targets.

## Resource-bounded acquisition recommendation

1. Keep a metadata-only registry first.
2. Reject full downloads of AgentLab (207 GB), WebLINX-BrowserGym (140 GB), and the independent OpenHands archive (41.9 GB) on this machine.
3. Seek explicit data licenses and published schemas before requesting samples.
4. If cleared, use one archive member, byte-range request, or author-provided small sample stratified by model, benchmark, success, and trajectory length.
5. Hash the sample and store only normalized counts/derived features if redistribution of raw content is unclear.
6. Run secret, PII, hidden-reasoning, and embedded third-party-license review before any public artifact is committed.

## Non-claims

- This is not an exhaustive history of every agent system.
- Absence of a public field is not evidence that the field was never measured privately.
- Aggregate paper totals are not interchangeable with request-level provider usage.
- Tool-observation text length is not automatically model input-token usage.
- Visible chain-of-thought is not equivalent to hidden reasoning tokens.
- Million-token task totals do not imply a million-token context window or concurrent context occupancy.
- No causal claim about agent count and success is supported by the narrow multi-agent examples in this packet.
