# Local Codex Telemetry 2B-1

## Purpose and authority boundary

This module records small, local metadata observations about runs launched by
the existing SmartRouter. It is disabled by default and becomes active only
after an operator runs:

```text
smart-codex telemetry enable
```

**Telemetry is evidence only. It does not grant authority and does not change
the selected model.** It does not choose a model, alter reasoning effort,
change sandbox or approval policy, authorize tools, retry work, or escalate a
run. The existing router remains the sole source of those launch decisions.

## Privacy model

Persisted records contain numeric and categorical metadata only. They never
contain:

- raw prompts or normalized prompt text;
- model responses or hidden reasoning;
- source code, diffs, tool arguments, or tool-output content;
- environment variables, credentials, API keys, tokens, cookies, email
  contents, private chats, or authorization headers;
- full absolute project paths.

The task identifier is an HMAC-SHA-256 signature. Its installation-specific
32-byte salt is generated with operating-system cryptographic randomness,
stored outside the repository at
`~/.local/state/smart-codex/telemetry_salt`, and restricted to mode `0600`.
Neither the salt nor normalized task text is printed or committed. Session IDs
are HMAC pseudonyms rather than raw Codex thread IDs.

The validator rejects unknown fields, probable prompt or response fields,
multiline content, absolute paths, personal email patterns, private-key
headers, authorization headers, cookies, and common API-token patterns. It logs
only a sanitized rejection category.

## Local storage and retention

Canonical storage is append-only JSONL below:

```text
~/.local/state/smart-codex/telemetry/
├── state.json
├── YYYY/
│   └── MM/
│       ├── codex_runs-0001.jsonl
│       └── codex_runs-0002.jsonl
└── summaries/
```

Run and outcome records are appended under an exclusive process lock. Each
line is written with `O_APPEND`, followed by `fsync`; prior JSONL records are
never rewritten. Files and lock state use mode `0600`, directories use `0700`,
and symlink targets are rejected. Lock acquisition is bounded; a writer that
cannot acquire it promptly disables only that telemetry write. A detected
trailing JSONL fragment also stops later writes without deleting or repairing
the prior evidence automatically.

Default hard limits are:

- 5 MiB per JSONL file;
- 50 MiB for all telemetry JSONL files;
- 1 GiB minimum free filesystem space before a write;
- 64 KiB maximum serialized record size.

At the file limit, collection rotates to the next numbered file. At the total
or free-space limit, it preserves all existing data, refuses the new write, and
reports `TELEMETRY_DISABLED_TOTAL_CAP` or
`TELEMETRY_DISABLED_LOW_DISK`. It never deletes records automatically. A
telemetry failure does not block the underlying Codex run.

## Operator commands

```text
smart-codex telemetry status
smart-codex telemetry enable
smart-codex telemetry disable
smart-codex telemetry summary
smart-codex telemetry summary --by-model
smart-codex telemetry summary --by-task-level
smart-codex telemetry inspect <run-id>
smart-codex telemetry inspect <run-id> --show-task-signature
```

Status reports enabled state, the canonical `~`-relative storage directory,
storage size, free disk bytes, schema version, run count, and last record time.
Inspect hides task signatures unless the operator explicitly requests one.

The operator, never the model, records the result separately:

```text
smart-codex outcome <run-id> accepted
smart-codex outcome <run-id> accepted-with-edits --tests-passed 12 --tests-failed 0
smart-codex outcome <run-id> rejected
smart-codex outcome <run-id> aborted --verification-unavailable
smart-codex outcome <run-id> accepted --escalated-to <model>
```

When test evidence is supplied, both `--tests-passed` and `--tests-failed`
must be present. Test counts cannot be combined with
`--verification-unavailable`.

An outcome is a new hash-linked record that references the immutable run
record. It cannot rewrite the original line, and there is no free-form comment
field that could accidentally capture private text.

## Supported observation surfaces

### Existing `smart-codex --execute` launcher

The classic launch path records the router classification, recommendation,
explicit model override when present, reasoning setting, sandbox, approval
policy, measured wall time, and process exit code. The command itself is
unchanged. Because this interactive path does not expose structured usage,
token, request, tool, retry, compaction, and backend-model fields remain
`null` unless a supported event source reports them. A profile-only launch
also leaves `launched_model` as `null`: the router recommendation is known,
but the effective model inside the local Codex profile is not exposed by this
launch path and is therefore not guessed.

### Existing routed Codex App Server proxy

The opt-in proxy observes, without modifying, these structured notifications:

- `thread/tokenUsage/updated` (`last` and cumulative `total` snapshots);
- `item/started` and `item/completed` for categorical tool counts;
- `turn/completed` for explicit completion status;
- `thread/compacted` and the `contextCompaction` item type;
- `thread/settings/updated` and `model/rerouted` for service-observed model
identity.

Run-shell creation and final append operations are moved off the App Server
async event loop. Startup observation has a short timeout, final writes use a
bounded lock, and telemetry timeouts produce sanitized warnings while the
authorized App Server turn continues normally.

App Server fields are version-specific observations. The installed schema used
during development was generated by Codex CLI 0.144.5; the repository's
existing App Server compatibility gate remains unchanged and continues to fail
closed when the installed version does not match its reviewed protocol
snapshot. Telemetry does not bypass that gate.

### `codex exec --json` event adapter

The parser supports the documented JSONL forms `thread.started`,
`turn.completed.usage`, `item.started`, `item.completed`, explicit request
usage events, and error-tolerant unknown event forwarding. This module does not
replace the existing launcher with a second `codex exec` launcher. When a
SmartRouter execution adapter supplies those structured events, the same
collector can consume them.

## Token and event reconciliation

The collector distinguishes:

- final or cumulative snapshots, which replace older snapshots;
- per-request records, which are summed only once by unique request ID;
- mixed streams, which are accepted only when overlapping counters agree;
- duplicate events, identified by a deterministic structural fingerprint;
- out-of-order App Server usage, resolved by the highest cumulative reported
  total rather than arrival order.

It records one of `per_request_sum`, `final_cumulative_snapshot`,
`mixed_reconciled`, or `unknown`. A conflict makes affected token fields
`null` and marks the run `partial_unreconciled`; cumulative totals are never
summed repeatedly.

The inspected Codex fields mirror the OpenAI Responses usage convention in
which reasoning tokens are a breakdown of output tokens. The versioned adapter
therefore reconstructs visible output only when output, reasoning, and any
reported total satisfy that convention:

```text
visible_output_tokens = output_tokens - reasoning_tokens
```

Likewise, non-cached input is reconstructed only when both input and cached
input are present. A source-reported zero is retained as zero. Absence is
always `null` with measurement status `unknown`.

## Record schema and integrity

The canonical schema is `schemas/local_codex_run.schema.json`, version
`1.0.0`. Each record includes the fields requested by Telemetry 2B-1 plus:

- `product_surface`;
- `counter_reconciliation`;
- duplicate and invalid event counts;
- collector status and process exit code.

Every populated measurement carries one of `measured`, `provider_reported`,
`client_reported`, or `reconstructed`. Missing measurements carry `unknown`.
`missing_fields` must exactly match all nullable fields that remain null.

`record_hash` is SHA-256 over canonical sorted JSON excluding the hash field.
The validator checks UUIDs, timezone-aware ISO timestamps, monotonic time,
nonnegative counters, cache/input arithmetic, output/reasoning/total
arithmetic, model-identity status, task levels, measurement provenance,
missingness, privacy, record size, and record-hash integrity before append.

The repository example is entirely synthetic:
`examples/sanitized_telemetry_record.json`.

## Summaries and calibration boundaries

Local summaries report run counts, known and unknown token counts, explicit
operator outcomes, p50/p90 tokens, wall time, retries, escalations, and outcome
success rate where compatible facts exist. Model strata also include product
surface and reconciliation method so incompatible measurements are not silently
combined.

The default reporting thresholds are:

- fewer than 5 measured comparable runs: `INSUFFICIENT_DATA` for median/p90;
- fewer than 30 outcome-labeled comparable runs: not ready for routing
  calibration.

These are reporting defaults, not permission to alter routing. No local
telemetry is uploaded, synchronized, or published automatically. Public reports
may use only reviewed aggregates and synthetic examples; the installation salt
and actual run records remain local.

## Protocol references

- <https://learn.chatgpt.com/docs/non-interactive-mode#make-output-machine-readable>
- <https://learn.chatgpt.com/docs/app-server.md>
- <https://platform.openai.com/docs/api-reference/responses/object>
