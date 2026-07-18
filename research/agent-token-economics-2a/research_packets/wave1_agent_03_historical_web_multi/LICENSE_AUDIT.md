# License, Redistribution, Privacy, and Reasoning-Content Audit

Evidence cutoff: 2026-07-18.

This is a research triage, not legal advice. A repository code license does not automatically license a separately hosted dataset, browser recording, model output, screenshot, or third-party page capture.

## Decision matrix

| Artifact | Stated license/terms | Raw redistribution | Commercial use | Attribution | Personal/secret risk | Reasoning-content risk | Derived-statistics decision |
|---|---|---|---|---|---|---|---|
| ReAct repository | MIT | Repository code/prompts under MIT; underlying task datasets keep their terms | Permitted for MIT material | Retain notice; cite paper | Low in repository, but exclude local API configuration | Visible reasoning demonstrations | Published outcomes/structural features may be cited; no token prior |
| AutoGPT repository | `autogpt_platform`: Polyform Shield; all other paths, including Original AutoGPT/Forge/AG Benchmark: MIT | Path-dependent | Platform license restricts competing products; MIT paths permit | Exact-path license required | Raw user runs/configuration can contain secrets and private tasks | Raw runs may expose private prompts/reasoning | Use only public framework metadata; do not ingest local runs |
| BabyAGI repository | MIT | Code permitted under MIT | Permitted | Retain notice | Raw logs may contain arguments, outputs, keys, and private tasks | Raw agent logs may expose reasoning | Timeline only; no standardized run corpus |
| WebArena code | Apache-2.0 | Code permitted; separate Google Drive traces have no stated artifact license on resource page | Unknown for trace archive | Cite paper; code notice for code | High for Playwright/network traces and login state | High for raw CoT predictions | Do not copy raw. Only aggregate after artifact-license and security review |
| WebArena human traces | No separate artifact license found | **Blocked** pending clarification | Unknown | Unknown beyond paper citation | High: HTML/network/session state | Human content, not hidden model reasoning | Task/action counts only after permission and scan |
| VisualWebArena code | MIT | Code permitted; separate agent/human Drive artifacts not clearly licensed by repository license | Unknown for traces | Cite VisualWebArena and WebArena | High for HTML/Playwright state | High for GPT-4V + SoM CoT outputs | Do not copy raw; derived statistics pending artifact license |
| GAIA core dataset | Paper indicates CC BY 4.0; current HF distribution is gated with explicit no-reshare conditions | Do not reshare outside gated/private Hugging Face | Not established by current card conditions | Cite GAIA and comply with gating | Attachments may carry third-party/privacy concerns | Core task data has no model reasoning | Only high-level task counts/taxonomy; never publish task/answer corpus |
| GAIA public results | No explicit dataset license metadata observed | Unclear | Unknown | Cite GAIA and linked system | Low | System prompts may be present; no trajectories | Cite high-level outcomes; do not republish table wholesale without clarification |
| GAIA public submissions | Gated no-reshare conditions | **Blocked** | Unknown | Cite GAIA | Potentially medium | Potentially high if raw reasoning is included | No public ingestion or redistribution |
| AgentBench | License not resolved in this packet | Unclear | Unknown | Cite paper | Medium for runtime logs | High for Thought/Action histories | Outcome/failure taxonomy only; heuristic “token” counts are not usage telemetry |
| AgentBoard dataset | GPL-2.0 on dataset card | Subject to GPL and embedded benchmark terms | GPL can permit commercial use, but treatment of data/assets needs review | GPL notice and paper citation | Generally low; embedded web/game assets vary | Low for task definitions | Aggregate task metadata only after license review; no raw republishing planned |
| Mind2Web | Dataset CC BY 4.0; code MIT | Nominally permitted with attribution, but captured third-party pages and privacy still constrain reuse | CC BY allows, subject to third-party rights | Required | **High**: HAR, storage, network, video, HTML, screenshots | Human traces, not model hidden reasoning | Structural aggregates only after secret/PII/third-party review |
| WebLINX | CC BY-NC-SA 4.0 plus explicit third-party/fair-use terms | Noncommercial/share-alike only; derivatives must retain terms | **Not permitted** without separate permission | Required; share-alike | Medium/high | Human demonstrations | Noncommercial aggregate feature research may be possible; public SmartRouter use requires license review |
| WebLINX-BrowserGym | Same CC BY-NC-SA terms | Same, and 140 GB makes raw acquisition inappropriate | Not permitted without permission | Required | Medium/high | Human demonstrations | Reject download; metadata only |
| BrowserGym code | Apache-2.0 | Code permitted | Permitted | Retain notice | Low for code; runtime data high | Runtime dependent | Framework telemetry semantics may be studied from code |
| AgentLab code | Apache-2.0 | Code permitted | Permitted | Retain notice | Low for code; runtime data high | Runtime dependent | Framework token-tracker design may be studied |
| AgentLab 207 GB traces | **No dataset license metadata/card schema** | **Blocked** | Unknown | Unknown | **High**: browser pages, prompts, logs, possibly credentials | **High**: raw model reasoning may be present | No ingestion until authors provide license/schema and a bounded auditable sample |
| AgentVerse repository | Apache-2.0 | Code permitted | Permitted | Retain notice; cite paper | Raw simulations/runs can contain private prompts or API configuration | High for dialogues | Timeline/framework only |
| MetaGPT paper aggregates | Paper publication terms; code repository is separately MIT | Cite aggregate statistics, not raw trajectories | Citation use generally possible; raw data rights separate | Cite paper | Low for aggregates | Low for aggregates | Qualitative aggregate discussion only |
| MegaAgent repository | CC BY 4.0 | Repository material permitted with attribution; generated/embedded content still needs review | Permitted under CC BY subject to embedded rights | Required | Medium for policy outputs/config | High for multi-agent dialogue | Cite paper aggregates; do not publish raw inter-agent conversations |
| AgencyBench repository | MIT | Code/scenarios permitted; dependencies and generated runs vary | Permitted for MIT material | Retain notice; cite paper | `.env`, web research, and run logs are high risk | High for raw model runs | Cite aggregate paper statistics; no raw run ingestion |
| Trace Commons | Compilation/metadata CC BY 4.0; individual traces retain original licenses | Per-trace review required; compilation license is not blanket relicensing of embedded code/content | Depends on each trace | Attribute Trace Commons and underlying content | **High despite best-effort scrubber**; card says anonymization is imperfect | **High** | Aggregate metadata only after per-trace provenance/license/privacy scan; no raw public copy |
| Independent OpenHands trajectory archive | No license metadata found | **Blocked** | Unknown | Cite paper; dataset terms unknown | Medium | High | Paper aggregates only until raw license/schema is clarified |

## Publication safety rules derived from the audit

1. Publish source URLs, checksums, schema mappings, and aggregate statistics—not raw browser or agent traces.
2. Never treat an Apache/MIT code license as permission for a linked Drive/Hugging Face artifact unless the artifact explicitly says so.
3. Reject or sanitize Playwright traces, HAR files, storage state, cookies, screenshots, HTML, environment files, authentication headers, raw prompts, and full inter-agent conversations.
4. Do not publish visible chain-of-thought or text labeled `reasoning`; the research needs counts and outcomes, not reasoning content.
5. For Trace Commons, re-run an independent secret/PII scan and resolve the license of embedded repository content before computing or publishing any trace-derived record.
6. Respect GAIA’s anti-leakage gating even where an earlier paper mentions CC BY 4.0.
7. Treat WebLINX as noncommercial/share-alike and preserve its extra third-party/fair-use terms in any allowed derivative.
8. Store `license: null` and block ingestion whenever artifact-level terms are absent.

## Size and acquisition guardrails

| Artifact | Stated size | Decision |
|---|---:|---|
| GAIA core | 110 MB | No download needed; gated and no token fields |
| GAIA submissions | 2.64 MB | Do not download/republish; gated |
| AgentBoard | 1.4 GB | Metadata/card sufficient; no token fields |
| WebLINX processed | 526 MB | If later approved, use `allow_patterns` for a few demonstrations |
| WebLINX-BrowserGym | 140 GB | Reject full download |
| AgentLab traces | 207 GB | Reject full download; request schema/license and bounded sample |
| Trace Commons | 127 MB at inspection | Stream/select metadata rows only after per-trace review |
| Independent OpenHands traces | 41.9 GB | Reject full download; request licensed stratified sample |
| WebArena / VisualWebArena Drive artifacts | `null` | Do not download until size and artifact license are known |
| Mind2Web raw dump | `null` on inspected page | Do not acquire; high-risk browser/network material |
