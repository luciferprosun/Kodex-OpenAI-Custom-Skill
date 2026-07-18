# Historical Coverage and Missing-Data Map

Evidence cutoff: 2026-07-18. This is a discovery map, not a claim of exhaustive historical telemetry.

| Era | Period | Public evidence | Token telemetry | Routing use |
| --- | --- | --- | --- | --- |
| early_tool_using_and_react | 2022-10 through 2023-02 | papers, prompts, demonstrations, benchmark outcomes | not located | task taxonomy and historical context only |
| autonomous_general_agents | 2023-03 onward | framework code, examples, benchmark infrastructure | no standardized historical corpus located | framework history only |
| web_and_computer_use_agents | 2023-06 onward | actions, screenshots, page state, tool traces, verifier outcomes | usually absent; one very large archive remains license/schema blocked | structural and tool-intensity features, not token priors |
| software_engineering_agents | 2023 onward | tasks, patches, trajectories, objective verifier outcomes | heterogeneous, often aggregate/cost-only, and frequently license-ambiguous | future bounded adapters after source-specific audit |
| multi_agent_systems | 2023-07 onward | frameworks, outcomes, a few aggregate token/cost examples | mostly absent or aggregate and non-comparable | qualitative amplification evidence only |
| long_horizon_terminal_agents | 2024 onward | tasks, tools, deterministic verifiers, some aggregate usage | adapter- and release-dependent | future locally measured strata |
| current_codex_and_agents_sdk | 2025 through evidence cutoff 2026-07-18 | documented usage/tracing interfaces and versioned schemas | interfaces exist; no universal public task/outcome corpus | preferred collection surfaces for local telemetry 2B |

## Registry field coverage

Counts below indicate candidates whose registry metadata mentions a field. They do not establish comparable, complete, or provider-reported measurements.

| Field | Candidate records |
| --- | ---: |
| input_tokens | 8 |
| cached_tokens | 6 |
| reasoning_tokens | 4 |
| output_tokens | 8 |
| request_count | 2 |
| cost | 4 |
| timing | 11 |
| tool_calls | 17 |
| verifier_result | 29 |
| raw_trajectory | 28 |
| complete_failure_coverage | 0 |

## Critical gaps

- comparable provider-reported per-request token breakdowns joined to objective outcomes
- complete failed, censored, retry, and escalation attempt chains
- current context occupancy distinct from cumulative usage
- tool-output and repeated-history token attribution
- compaction input/output and post-compaction context
- subscription quota consumption with documented semantics
- price-date-correct accepted-task cost including verification and human review
- representative multi-agent runs with per-agent attribution
- SmartRouter-specific tasks and route decisions

A missing public measurement is stored as `null` with provenance; it is never replaced by zero or guessed from an era, model name, text length, or current price table.
