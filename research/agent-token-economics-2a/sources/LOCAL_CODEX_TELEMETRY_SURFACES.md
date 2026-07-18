# Codex Telemetry Surfaces - Direct Verification

Verified 2026-07-18 with Codex CLI `0.144.5`. This record contains field names
and schema hashes only. No local prompts, session content, account tokens, or
credentials were inspected or copied.

## Stable documented non-interactive surface

Official Codex documentation describes `codex exec --json` as a JSONL event
stream. A completed turn includes:

- `usage.input_tokens`
- `usage.cached_input_tokens`
- `usage.output_tokens`
- `usage.reasoning_output_tokens`

The stream also identifies thread/turn lifecycle, item types, command and MCP
tool events, web searches, file changes, plan updates, failures, and errors.
This supports per-turn usage and event counting. It does not by itself expose
current context occupancy, tool-output tokens, price, acceptance, or human
review.

Source:
https://learn.chatgpt.com/docs/non-interactive-mode#make-output-machine-readable

## Documented metrics surface

Official advanced configuration documents these relevant Codex metrics:

- `turn.token_usage`, grouped by `total`, `input`, `cached_input`, `output`, or
  `reasoning_output`;
- `turn.e2e_duration_ms`, time to first token, and time to first model output;
- `turn.tool.call`;
- `tool.call` and `tool.call.duration_ms`, with tool and success metadata;
- API, SSE, WebSocket, MCP, hook, and approval counters/durations.

Default metric context includes model and app version. Metric aggregation is not
a lossless trajectory and must not be represented as one.

Source:
https://learn.chatgpt.com/docs/config-file/config-advanced#otel-metrics-emitted

## Experimental App Server observation

Command used locally:

`codex app-server generate-json-schema --out <temporary-directory>/schema`

App Server is documented as experimental. Generated schema evidence is therefore
a versioned observation, not a stable compatibility promise.

`ThreadTokenUsageUpdatedNotification` contains thread and turn IDs plus:

- `tokenUsage.last`: input, cached input, output, reasoning output, and total;
- `tokenUsage.total`: the same cumulative breakdown;
- nullable `modelContextWindow`.

The `last`/`total` split supports per-turn versus cumulative-session accounting.
`modelContextWindow` is capacity, not current occupancy.

The generated `ContextCompactedNotification` identifies a compaction event but
is marked deprecated in favor of the `ContextCompaction` item type. It contains
thread and turn IDs, not token counts attributable to compaction.

`GetAccountTokenUsageResponse` exposes optional daily token buckets and summary
fields such as lifetime and peak-daily tokens. Account-level usage is not an
API-cost record and is not a per-task context measurement.

Generated schema checksums:

| Schema | Size | SHA-256 |
| --- | ---: | --- |
| `ThreadTokenUsageUpdatedNotification.json` | 1,600 B | `fe70a73653ae9e3fffb0db84d1312f47ac47d92526c2d44461492cd864ada3ad` |
| `ContextCompactedNotification.json` | 362 B | `e0b92779009971631d385970cc0389d4f19e351466f84806df36c29f4b9d5ffd` |
| `GetAccountTokenUsageResponse.json` | 1,589 B | `b4cb098e35c43a7e3b8c9211c3c1b12a79e5d89afdcf40304e6b777e25a8c74b` |

The temporary generated schema tree was not selected for publication because it
was 3.5 MiB and the three derived field summaries are sufficient for this
research question.

## Missing locally observable fields

No verified Codex surface above directly supplies all of:

- tokens introduced specifically by tool output;
- exact repeated-history tokens;
- current or peak context occupancy;
- token count attributable to compaction summaries;
- verifier acceptance;
- human-review time;
- price-table date or billed monetary cost;
- causal retry or escalation reason.

Research 2B must instrument these separately and preserve nulls when a field is
not actually measured.
