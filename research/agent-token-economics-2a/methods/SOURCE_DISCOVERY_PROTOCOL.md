# Exhaustive Source-Discovery Protocol

“Exhaustive” describes the repeatable search procedure, not historical data
coverage. No complete universal agent-token dataset is known.

## Search passes

1. Official OpenAI documentation, OpenAPI schemas, Codex manual, Codex source,
   generated App Server schemas, Agents SDK documentation, tracing, pricing,
   usage, caching, context, and rate-limit interfaces.
2. Canonical benchmark and agent repositories, release pages, experiment
   directories, dataset cards, artifact indexes, and maintainers' papers.
3. Paper and dataset-card searches by benchmark, framework, “trajectory”,
   “token usage”, “cost”, “usage”, “completion_tokens”, “model_stats”,
   “tool calls”, and “runtime”.
4. Reproducible independent evaluations only when model, agent, task set,
   measurement method, outcomes, and limitations are stated.
5. Citation chaining backward to original methods and forward to public
   trajectory releases or corrections.
6. Negative-evidence pass: record datasets that expose outcomes but no usable
   token accounting, missing failures, ambiguous model aliases, or no license.

## Required candidates

The discovery register explicitly searches SWE-bench experiments, SWE-smith,
SWE-agent, OpenHands and its benchmarks, Terminal-Bench and Harbor,
STATE-Bench, AgentRE-Bench, GAIA implementations, WebArena/browser agents,
Multi-SWE-bench trajectories, ReAct-era agents, autonomous general agents,
multi-agent systems, long-horizon terminal agents, Codex, and OpenAI Agents SDK
workflows.

## Source acceptance

A source is accepted for the registry when its canonical identity and relevance
can be verified. Acceptance into the registry does not mean its data is suitable
for numerical routing. Quantitative influence additionally requires quality
class A-C, compatible semantics, license clarity, and an explicit stratum.

Tier priority:

1. Official OpenAI documentation and primary interfaces.
2. Original agent/benchmark repositories.
3. Primary papers and dataset cards.
4. Reproducible independent evaluations.

Affiliate comparisons, unsupported blog estimates, and social-media numbers are
excluded from numerical evidence.

## Versioning and reproducibility

Each record stores canonical URL, inspected release/commit where available,
access date, license, estimated size, acquisition method, and limitations.
Duplicate datasets are linked rather than counted twice. Mutable pages are
identified as mutable. A future refresh repeats all passes, checks releases and
licenses, and appends changes without rewriting historical price or evidence
dates.

## Resource gate

Before content acquisition, record compressed and extracted size, license,
privacy and hidden-reasoning risk, available streaming/range/sparse methods, and
the smallest useful stratified sample. Unknown size or license defaults to
metadata-only inspection.
