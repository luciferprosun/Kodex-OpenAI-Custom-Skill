# License, Redistribution, and Content-Risk Map

Evidence cutoff: 2026-07-18. This is publication-safety triage, not legal advice.

## Decision legend

- **Metadata-only:** source link, immutable revision, field coverage, license signal, and high-level counts may be recorded. No raw payload.
- **Derived-only after audit:** sanitized aggregates may be computed after a rights, privacy, and secret review. No raw payload is republished.
- **Local/private only:** operator-owned telemetry may be used locally with consent and sanitization; raw records remain private.
- **Blocked:** no acquisition or derivation until the named condition is resolved.

## Risk map

| Dataset or surface | License / rights signal | Commercial use | Attribution | Personal / secret risk | Reasoning-content risk | Safe 2A decision |
| --- | --- | --- | --- | --- | --- | --- |
| OpenAI Responses, Organization Usage/Costs, Agents SDK, Codex exec/app-server/rollout | MIT or Apache schema/implementation sources; captured records are operator/customer data | Depends on operator rights and service terms, not the code license | Cite exact official source/version | High for prompts, responses, org/account fields, tools, paths, and identifiers | High for raw traces; token counts alone are safe | Local/private only; publish sanitized aggregates and schemas |
| SWE-agent demonstration trajectories | MIT repository at pinned revision | MIT permits, with notice | Retain MIT notice and source revision | Medium; scan paths, repository text, and tool output | High because public files may contain thought text | Derived parser metadata only; no numerical prior |
| SWE-smith tasks and trajectories | MIT repository signal; asset-card applicability unresolved | Unknown for trajectory assets and embedded repos | Repository notice plus asset/source licenses | Medium | High for raw trajectories | Metadata-only; trajectories blocked pending card/file audit |
| SWE-bench Experiments and S3 submissions | No repository license declared; submission rights heterogeneous | Unknown | Source/submission attribution not sufficient to grant rights | Medium to high | High | Blocked pending human/license decision; no raw redistribution |
| OpenHands core/benchmarks and generated outputs | MIT core/harness; enterprise path and run releases separate | Clear only for MIT paths | Retain notices; cite run release separately | Medium to high in generated runs | High | Harness metadata only; each run release separately audited |
| Harbor / Terminal-Bench / public result rows | Apache-2.0 framework/tasks; row and embedded-asset rights can differ | Framework/task code generally permitted; rows/assets require review | Apache notice and row publisher | Medium | High in ATIF/raw runs | Metadata-only; bounded row only after row-level license audit |
| STATE-Bench and AgentRE-Bench | MIT public code/tasks; generated/private evaluations separate | MIT public material generally permitted | Retain MIT notice and cite benchmark | Medium; private evals must remain excluded | High for generated conversations/reasoning | Public task/verifier metadata only; no token prior |
| Multi-SWE-bench / Multi-SWE-RL | Apache-2.0 repository; HF assets and underlying repositories unresolved | Repository code permitted; asset use unresolved | Apache notice plus each underlying source | Medium | High for released trajectories | Metadata-only; payload blocked pending card audit |
| Nebius SWE-agent / OpenHands trajectory releases | Individual dataset-card license not verified | Unknown | Unknown beyond publisher/paper citation | Medium | High | Blocked for acquisition, redistribution, and derived statistics |
| ReAct / BabyAGI / MIT-scoped AutoGPT artifacts | MIT code; AutoGPT platform has path-specific Polyform Shield | Path-dependent for AutoGPT; MIT elsewhere | Exact-path license and paper citation | Low for source tree, high for raw user runs | Medium to high in examples/logs | Historical metadata and taxonomy only |
| AgentBench | Repository/data license unresolved | Unknown | Cite paper | Medium | High for Thought/Action histories | Metadata/outcome methodology only; heuristic token units excluded |
| WebArena / VisualWebArena separately hosted traces | Code is Apache/MIT; Drive artifact license not established | Unknown | Paper citation does not grant artifact rights | High for HTML, network, storage, cookies, screenshots | High for CoT/raw predictions | Blocked pending artifact license, size inventory, and security review |
| WebArena / VisualWebArena human traces | Artifact license not established | Unknown | Unknown beyond paper citation | High for browser/session state | Human content, not hidden model reasoning | Metadata-only; no model-token evidence |
| GAIA core and scored submissions | Earlier CC BY signal plus current gated/no-reshare conditions | Not established | Cite GAIA and comply with gate | Medium in attachments/submissions | Potentially high in submissions | High-level taxonomy only; no public raw copy |
| GAIA public results | No explicit dataset license found | Unknown | Cite GAIA and linked systems | Low | Low to medium | Link and high-level outcome summary only |
| AgentBoard | GPL-2.0 card plus embedded benchmark assets | GPL can permit commercial use subject to conditions; asset treatment unresolved | GPL notice and paper citation | Low to medium | Low for task definitions | Metadata-only after embedded-asset review |
| Mind2Web | CC BY 4.0 data and MIT code, but captured third-party pages remain | Nominally allowed for covered data; third-party/privacy constraints remain | CC BY attribution and paper citation | High for HAR, storage, network, video, HTML | Human traces | Structural aggregates only after privacy/rights audit |
| WebLINX / WebLINX-BrowserGym | CC BY-NC-SA 4.0 plus third-party/fair-use terms | Not permitted without separate permission | Attribution and share-alike required | Medium to high | Human traces | Metadata-only; no production-routing prior; 140 GB conversion not acquired |
| AgentLab 207 GB traces | No dataset license or schema | Unknown | Unknown | High | High | Blocked |
| MetaGPT and MegaAgent paper aggregates | Paper/repository publication terms; raw run rights separate | Aggregate citation only unless repository asset rights are checked | Cite papers; retain CC BY where applicable | Low for aggregates, higher for raw examples | High for raw inter-agent dialogues | Qualitative aggregate discussion only, quality D |
| AgencyBench aggregates | MIT code/scenarios; generated runs/dependencies separate | MIT material permitted; runs vary | Retain notice and cite paper | Medium to high | High | Aggregate qualitative use only, quality D |
| Trace Commons | CC BY 4.0 compilation metadata; each trace retains original license | Per trace | Attribute compilation and every underlying source | High despite best-effort scrubbing | High | Registry metadata only; raw/derived use blocked per trace |
| Independent OpenHands token archive | No dataset license; 41.9 GB | Unknown | Cite paper only | Medium | High | Paper aggregates only; raw archive blocked |

## Non-negotiable publication controls

1. A public URL is not a redistribution license.
2. A code license does not automatically cover datasets, model outputs, web captures, issue text, or operator telemetry.
3. Never publish raw prompts, private chats, hidden/visible reasoning traces, credentials, cookies, authorization headers, storage state, HAR/network data, private repository content, or unnecessary personal paths.
4. A hidden-reasoning token count is telemetry; hidden-reasoning text is neither needed nor approved.
5. Preserve attribution and source-repository license obligations even for a small lawful sample.
6. Keep raw redistribution and allowed derived statistics as separate decisions.
