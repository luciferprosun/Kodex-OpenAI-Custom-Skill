# SmartRouter Safe Routing and Telemetry Foundation 2B-2

## Purpose and authority boundary

This opt-in foundation measures the route selected by the existing SmartRouter.
Telemetry is evidence only. It cannot select a model, alter reasoning effort,
change sandbox or approval policy, authorize tools, update routing rules, or
modify source code.

No learning engine, policy candidate generator, automatic calibration,
contextual bandit, nightly job, or promotion path is connected. The current
checked-in routing policy remains the only routing authority.

The ordinary `codex` executable and ordinary routed launcher remain available.
The dedicated fail-closed launcher is:

```text
scripts/start-routed-codex-research
```

It supports the explicit window IDs `aoia` and `smart-router`. The prompt is
entered inside the original Codex TUI and never appears in launcher arguments.

## Privacy model

Persisted records contain validated numeric or categorical metadata only. They
never contain prompts, responses, hidden reasoning, source, diffs, commands,
tool arguments or output, environment variables, credentials, authorization
headers, email/chat content, or absolute workspace paths.

A random installation salt remains on the internal system disk with mode
`0600`. HMAC-SHA-256 produces task, session, and workspace identifiers; source
text is not retained. The salt is never copied to external storage or Git.

Run schema `2.0.0` adds `window_id`, `workspace_signature`,
`router_policy_version`, `codex_protocol_version`, and a synthetic-validation
marker. Readers retain compatibility with immutable schema `1.0.0` records.

## External storage and configuration

Authoritative configuration is a strict, atomic JSON document at:

```text
~/.config/smart-codex/telemetry.json
```

The directory is `0700` and the file is `0600`. Unknown fields are rejected.
Configuration contains no secret, prompt, response, task signature, or source
path. The external root and exact filesystem UUID must be configured
explicitly. Reset removes only the configuration reference and never deletes
telemetry data.

External layout:

```text
SmartRouterTelemetry/
├── raw/                 # state and append-only run JSONL
├── outcomes/            # append-only operator outcome JSONL
├── manifests/           # collection metadata only
├── derived/             # reserved; no routing or learning policy
├── reports/             # collection metadata only
├── runtime-events/      # bounded sanitized routing events
└── quarantine/          # rejected metadata-only records when explicitly used
```

External defaults are 16 MiB per JSONL file, 2 GiB total run/outcome storage,
a 1 GiB free-space floor, and 64 KiB per record. Files rotate. Existing
evidence is never automatically deleted. Without an external configuration,
the original 2B-1 internal defaults remain 5 MiB per file and 50 MiB total.

## Mount identity safety

Before each research startup and each telemetry append, SmartRouter verifies:

- the configured root is named `SmartRouterTelemetry`;
- the root is below the expected non-root mount;
- the current filesystem UUID exactly matches configuration;
- the mount point and filesystem type match configuration;
- no root or parent component is a symlink;
- the mount is writable and the root is owned by the operator;
- minimum free space and active storage limits remain satisfied.

If removable storage disappears, an empty mount-point directory resolves to the
internal root filesystem and is rejected. External configuration never falls
back to internal telemetry storage. Ordinary Codex can continue when optional
telemetry is unavailable; the dedicated research launcher refuses startup.

The runtime-event sink repeats the same preflight before every append, uses
`O_APPEND`, flushes with `fsync`, rejects symlinks, and stops at a bounded file
size. A failed event write cannot change or block the authorized Codex turn.

## Exact Codex App Server contract

Routed mode is pinned to `codex-cli 0.144.6` by exact string comparison.
Stable and experimental JSON Schema and TypeScript artifacts were generated
from the installed binary and compared directly with regenerated `0.144.5`
artifacts.

JSON schemas are semantically identical after object-key canonicalization, and
both TypeScript trees are byte-identical. No method, notification, token field,
required set, enum, or payload shape changed. Raw JSON ordering changes are
recorded separately from canonical semantic hashes in:

```text
smart_codex/app_server_router/schemas/protocol_contract_0_144_6.json
```

Any other Codex version fails before the backend starts. A future update
requires fresh stable and experimental generation, comparison, checksums,
tests, and documentation. WebSocket transport remains experimental and both
listeners bind only to `127.0.0.1`.

## Dual-window launchers

The launcher requires `--window-id` and `--cwd`, verifies the exact Git root
and expected remote, selects loopback ports automatically, verifies storage and
the Codex contract, discovers App Server metadata, and then opens the original
TUI. Two simultaneous windows receive independent HMAC workspace signatures
and separate sanitized runtime-event files.

`--print-command` performs manager startup and discovery without submitting a
model turn or printing the absolute workspace path.

## Operator outcomes

Outcomes are separate append-only, hash-linked events. Supported values are:

- `accepted`;
- `accepted-with-edits`;
- `rejected`;
- `aborted`.

Categorical evidence includes edit magnitude, failure category, paired test
counts, verification-unavailable status, follow-up turns, and escalation
target. Rejected outcomes require an explicit failure category. Corrections
append a new event linked to the preceding outcome; existing evidence is never
mutated.

Production outcome commands require a foreground interactive operator
terminal. Non-interactive processes and processes launched beneath Codex cannot
mark their own run accepted. There is no free-form comment field.

## Commands

```bash
smart-codex telemetry storage discover
smart-codex telemetry storage configure --root MOUNT/SmartRouterTelemetry --device-uuid UUID
smart-codex telemetry storage status
smart-codex telemetry enable
smart-codex telemetry preflight
smart-codex telemetry status

scripts/start-routed-codex-research --window-id aoia --cwd AOIA_GIT_ROOT
scripts/start-routed-codex-research --window-id smart-router --cwd SMARTROUTER_GIT_ROOT

smart-codex telemetry pending --window-id aoia
smart-codex outcome latest --window-id aoia accepted --edit-magnitude none
smart-codex outcome latest --window-id smart-router accepted-with-edits --edit-magnitude minor --followup-turns 1
smart-codex outcome latest --window-id aoia rejected --failure-category test_failure --tests-passed 10 --tests-failed 2

smart-codex telemetry summary
smart-codex telemetry summary --by-model
smart-codex telemetry summary --by-task-level
smart-codex telemetry disable
```

## Filesystem limitation

Filesystems such as exFAT apply permissions through mount-wide masks rather
than per-file POSIX modes. The operator must retain a private parent mount
boundary. Internal configuration and the HMAC salt still enforce `0600`, and
external records remain metadata-only.

## Collection boundary

This foundation only collects and summarizes operator-controlled evidence.
Token Intelligence, automated experimentation, policy optimization, automatic
calibration, and self-learning routing remain outside this mission and are not
connected.
