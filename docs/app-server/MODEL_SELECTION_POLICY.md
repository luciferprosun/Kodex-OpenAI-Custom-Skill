# Dynamic model selection policy

Phase 5.3 implements a **deterministic, capability-aware, dynamically refreshed
routing policy**. It does not train a classifier and does not replace Router
Core. The policy applies only after Router Core has classified task category,
risk, action danger, sandbox, and approval requirements.

The live App Server response is authoritative for availability, visibility,
upgrade targets, supported reasoning efforts, and input modalities. The
declarative files describe task boundaries and fallback preferences; they are
not a permanent model catalog.

## Decision pipeline

1. `model/list` and `configRequirements/read` are read at manager startup.
2. Router Core classifies task and safety dimensions.
3. `prompt_features.py` derives coarse workload features in memory.
4. `capability_filter.py` rejects incompatible live candidates.
5. `model_policy.py` scores the remaining candidates.
6. `effort_policy.py` selects an independently justified live-supported effort.
7. Hysteresis decides whether a marginal model change is worth making.
8. The proxy rewrites only supported `turn/start` fields and forwards the turn.

Prompt text is never added to the model registry, score objects, routing event
logs, launcher arguments, or a persistent cache.

## Stable workload features

The feature extractor uses stable size classes: `tiny`, `small`, `medium`,
`large`, `xlarge`, and `unknown`. It deliberately avoids precise token-count or
duration predictions. Features cover:

- coding/non-coding and editing/analysis;
- likely file count, edit surface, tools, tests, duration, and repository scope;
- text/image input, web research, source verification, and external-tool work;
- latency, quality, architecture, mathematics, ambiguity, and context class;
- independent workstreams, delegation, parallel agents, and deterministic evals;
- side effects, reversibility, Router Core risk/action danger, and explicit
  model or effort preferences.

## Hard capability filters

A candidate is rejected before scoring when live metadata or local policy makes
it unsafe or impossible to use. Rejection reasons include:

- absent, hidden, temporarily unavailable, or workspace-forbidden model;
- unsupported input modality or explicit effort;
- context class beyond verified capacity;
- coding-only model for a non-coding task;
- live upgrade target without an explicit compatibility request or verified
  capability gap;
- Spark task outside its risk, duration, ambiguity, or edit-surface boundary;
- unknown model with no capability profile;
- future family model whose live effort/modal shape does not match the known
  family profile.

The installed `0.144.4` `model/list` schema does not expose a context-window
field. Exact known-model context classes therefore come from versioned policy
metadata checked against the official Codex registry. A future family match is
assigned a conservative `small` context class unless an explicit reviewed
override exists. No context capability is inferred from a display name alone.

## Model boundaries

### Luna

Luna is preferred for direct writing transformations, grammar, concise email
drafts, simple summaries/classification, harmless documentation, short code
explanations, deterministic scripts, simple tests, and small isolated fixes.
Typical effort is `low` or `medium`. Luna is excluded from high architecture,
broad repository understanding, high ambiguity, deep security reasoning,
delegation, and unsupported modality/effort combinations. Luna never receives
`ultra`.

### Spark

Spark is considered only when it exists in live `model/list`. It requires a
text-only coding task, small context and edit surface, low architectural depth,
low ambiguity, bounded duration, and low/medium Router Core risk. It is intended
for a targeted function, copy, label, CSS, or rapid prototype edit.

When correctness depends on tests and the user did not already request one, the
stock routed TUI's supported `collaborationMode.settings.developer_instructions`
receives a bounded instruction to run the smallest relevant test. If the client
does not provide that safe context field, Spark is not selected for that turn.
The original user input is never modified.

This matches OpenAI's description of GPT-5.3-Codex-Spark as a text-only research
preview for rapid coding iteration that favors targeted edits and may not run
tests automatically: [Introducing GPT-5.3-Codex-Spark](https://openai.com/index/introducing-gpt-5-3-codex-spark/).

### Terra

Terra is the default for normal professional work: ordinary bugs and features,
several-file changes, test repair, maintenance, medium refactors, dependency
updates, code review, implementation plus documentation, bounded research, and
ordinary connector/tool workflows. Effort is normally `medium` or `high`, with
`xhigh` reserved for unusually complex but non-frontier work. `Ultra` requires
an explicit, reproducible delegation benefit.

### Sol

Sol is preferred for high architectural depth, broad cross-module refactors,
hard debugging with uncertain causes, deep security analysis, difficult
mathematics, large-context synthesis, final audits, ambiguous mixed-domain
work, novel algorithms, difficult incidents, and strategic research. Effort is
normally `high`/`xhigh`; `max` is for the hardest bounded work and final audits.
`Ultra` requires independent parallel workstreams for which delegation is
materially beneficial.

Side effects, connector use, or human approval do not by themselves select Sol.
The model-selection dimension never broadens sandbox or action authority.

### Compatibility and legacy models

GPT-5.5 is a compatibility fallback for complex coding, research, and
multi-step work when suitable Sol/Terra candidates are unavailable. GPT-5.4 and
GPT-5.4 Mini are legacy compatibility profiles. They are suppressed only when
the live record actually advertises an upgrade target. An explicit live legacy
request is allowed with a migration warning. A static research file cannot
invent a live upgrade.

## Explainable scoring

Every eligible candidate receives named score components for capability, task,
complexity, context, latency, quality, tools, modality, availability,
continuity, preview status, migration, over/underqualification, explicit
preference, and fallback distance. The result includes candidate totals,
rejections, fallback order, confidence, score margin, switch reason, and a
bounded explanation code. None of those objects contains prompt text.

## Reasoning effort

Effort is selected independently from model identity and risk:

| Effort | Intended use |
|---|---|
| `low` | direct transformations, grammar, classification, trivial edits |
| `medium` | everyday coding, ordinary debugging, small research/tool work |
| `high` | multi-file work, deeper debugging, substantial sourced research |
| `xhigh` | architecture, broad refactors, difficult analysis/security |
| `max` | hardest bounded work, final audits, difficult mathematics |
| `ultra` | only justified parallel delegation on a supported live model |

If the preferred effort is absent, the nearest supported live effort is used.
The router never emits an effort not present in that model's live record.

## Hysteresis

The default switch threshold is `8.0` score points. A stronger model is selected
immediately when the previous model lacks a required capability or is below the
task's required strength. De-escalation requires a capability-compatible lower
model and a material score margin. A smaller margin retains the current model
and records `retained_marginal_score_difference`. Starting on Sol is not a
reason to remain on Sol.

## Declarative and implementation files

- `rules/model_selection_policy.json`
- `rules/reasoning_effort_policy.json`
- `rules/model_fallback_policy.json`
- `smart_codex/app_server_router/prompt_features.py`
- `smart_codex/app_server_router/capability_filter.py`
- `smart_codex/app_server_router/model_policy.py`
- `smart_codex/app_server_router/effort_policy.py`
- `smart_codex/app_server_router/routing_explanation.py`

The official App Server interface documents per-turn overrides and streamed
events. WebSocket transport remains experimental and unsupported:
[Codex App Server](https://learn.chatgpt.com/docs/app-server).
