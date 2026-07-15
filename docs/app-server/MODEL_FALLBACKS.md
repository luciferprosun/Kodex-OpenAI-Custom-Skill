# Dynamic model fallbacks

Fallbacks are computed from the current process's live `model/list` snapshot.
The policy never treats a remembered model name as available and never invents
a reasoning effort.

## Resolution order

Hard capability filtering runs first. Only then is the declarative class order
used to rank remaining alternatives:

| Desired class | Fallback preference |
|---|---|
| Spark | Spark -> Luna -> Terra -> GPT-5.5 -> Sol |
| Luna | Luna -> Terra -> GPT-5.5 -> Sol |
| Terra | Terra -> GPT-5.5 -> Sol -> Luna |
| Sol | Sol -> Terra -> GPT-5.5 -> Luna |

The score can choose a later candidate when context, tool burden, latency,
quality, continuity, or underqualification makes it a better fit. This table is
a preference, not permission to bypass hard filters.

## Spark fallback

- Small targeted edit: Spark, otherwise Luna or Terra according to test burden
  and complexity.
- Ordinary coding: Spark is not the desired class; Terra is preferred.
- Complex coding or architecture: Spark is rejected; Terra or Sol is selected.
- Image input: Spark is rejected because its verified live modality is text.
- Temporary unavailability/rate-limit overlay: Spark is rejected for the
  current process and the next eligible live candidate is used.
- Implicit-test edit without supported routed developer context: Spark is not
  selected; the turn falls back instead of silently omitting validation.

A missing Spark model never fails the turn by itself.

## Reasoning effort fallback

The effort policy first derives a task effort independently of model class. If
that effort is missing from the selected model's live
`supportedReasoningEfforts`, the nearest live-supported non-Ultra effort is
selected. `Ultra` is never approximated: it requires a supported Terra/Sol
candidate and a concrete parallel-delegation reason.

## Visibility and temporary availability

Hidden models are recorded but not eligible in the Phase 5.3 default policy.
Models absent from `model/list`, marked unavailable by the current-process
overlay, or forbidden by workspace/account requirements are rejected before
scoring. The rejection appears as a bounded reason code, never as raw provider
data.

## Migration models

Live `upgrade`/`upgradeInfo` wins over static migration knowledge:

- a legacy model with a live upgrade target is normally rejected;
- an explicit request for that available legacy model may be honored with
  `legacy_model_selected_for_explicit_compatibility`;
- a verified capability gap may justify legacy use;
- when live metadata has no upgrade target, the static map does not invent one;
- an unexpected live target produces a sanitized migration-drift warning.

GPT-5.5 remains a compatibility fallback, not a preferred replacement for a
suitable live Sol or Terra.

## No eligible candidate

If every model fails hard capability filtering, the proxy returns the sanitized
JSON-RPC routing error `-32090` and does not forward the turn. It does not select
Sol Max by default and does not forward an unclassified side-effecting prompt.
The user can retry in explicit OFF mode with ordinary `codex`.

## Authority is unchanged

Fallback affects model and supported effort only. Router Core sandbox and
approval requirements remain authoritative. A stronger fallback cannot grant
write/network/destructive authority, and a weaker fallback cannot bypass a
safety block or approval request.
