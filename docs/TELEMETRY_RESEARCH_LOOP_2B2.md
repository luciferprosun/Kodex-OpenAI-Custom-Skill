# SmartRouter Telemetry Research Loop 2B-2

## Purpose and authority boundary

This opt-in research loop measures the existing SmartRouter route and builds
reviewable shadow evidence. It does not select a different live model, change
reasoning effort, modify source code, alter sandbox or approval policy, grant
tool/network/write authority, or promote a candidate policy. Raw telemetry is
evidence only. A future promotion requires an explicit human decision bound to
an immutable candidate hash.

The ordinary `codex` executable and ordinary SmartRouter launcher remain
untouched. The dedicated launcher is only:

```text
scripts/start-routed-codex-research
```

It supports two explicit window identities, `aoia` and `smart-router`, and
verifies the corresponding Git remote before opening the original Codex TUI.
The prompt is entered inside that TUI and never appears in launcher arguments.

## Privacy model

Records contain numeric or categorical metadata only. They never contain raw
prompts, responses, source, diffs, commands, tool arguments/output,
environment variables, credentials, emails, chats, or absolute workspace
paths. A random installation salt remains on the internal system disk with
mode `0600`. HMAC-SHA-256 produces task, session, and workspace identifiers;
the normalized source text is not retained. The salt is never copied to the
external device or Git.

Run schema `2.0.0` adds `window_id`, `workspace_signature`,
`router_policy_version`, `codex_protocol_version`, and a synthetic-validation
marker. The reader remains compatible with immutable `1.0.0` evidence.
Synthetic records are always excluded from the research dataset.

Operator outcomes are separate append-only records. Production outcome writes
require the foreground interactive terminal and reject a Codex ancestor
process. Models and non-interactive child processes cannot mark work accepted.
Outcome corrections append another hash-linked event. There is no free-form
notes field.

## External storage and mount identity

Authoritative configuration is an atomic, strict JSON document at:

```text
~/.config/smart-codex/telemetry.json
```

The directory is `0700` and the file is `0600`. Unknown keys are rejected. An
environment variable cannot override the configured storage root.

Configuration stores the exact filesystem UUID and mount identity. Before a
research startup and every raw append, SmartRouter verifies:

- the configured root is named `SmartRouterTelemetry` and is below the
  expected non-root mount;
- no root or parent component is a symlink;
- the current filesystem UUID is the configured UUID;
- the mount is read/write, owned/writable by the current operator, and has
  sufficient free space.

If the card is removed, the empty mount-point directory resolves to the system
filesystem and the UUID/root-mount checks reject it. There is no internal-disk
fallback. Ordinary Codex remains usable; the dedicated research launcher
refuses to start.

External layout:

```text
SmartRouterTelemetry/
├── raw/                 # immutable state and append-only JSONL
├── derived/             # reproducible datasets and manifests
├── manifests/
├── policy-candidates/   # immutable, non-authoritative proposals
├── reports/
└── runtime-events/      # sanitized route/shadow events
```

External defaults are 16 MiB per raw JSONL, 2 GiB total raw storage, a 1 GiB
free-space floor, and 64 KiB per record. Files rotate; no evidence is deleted
automatically. Without an external configuration, the safer 2B-1 internal
defaults remain 5 MiB per file and 50 MiB total.

`telemetry storage reset` removes only the configuration reference. It never
removes telemetry data.

Filesystems such as exFAT apply permissions through mount-wide masks instead of
per-file POSIX modes. On those media, the operator must retain a private parent
mount boundary; the internal configuration and HMAC salt still remain `0600`.
The raw format remains metadata-only even when the removable filesystem cannot
represent a per-file `0600` mode.

## Commands

Discovery and setup:

```bash
smart-codex telemetry storage discover
smart-codex telemetry storage configure --root MOUNT/SmartRouterTelemetry --device-uuid UUID
smart-codex telemetry storage status
smart-codex telemetry enable
smart-codex telemetry preflight
```

Research windows:

```bash
scripts/start-routed-codex-research --window-id aoia --cwd AOIA_GIT_ROOT
scripts/start-routed-codex-research --window-id smart-router --cwd SMARTROUTER_GIT_ROOT
```

Outcome labeling:

```bash
smart-codex telemetry pending --window-id aoia
smart-codex outcome latest --window-id aoia accepted --edit-magnitude none --tests-passed 12 --tests-failed 0
smart-codex outcome latest --window-id smart-router accepted-with-edits --edit-magnitude minor --followup-turns 1
smart-codex outcome latest --window-id aoia rejected --failure-category test_failure --tests-passed 10 --tests-failed 2
```

Learning and status:

```bash
smart-codex learning build-dataset
smart-codex learning dataset-status
smart-codex learning refresh
smart-codex learning shadow-status
smart-codex learning candidate-report
smart-codex learning propose-policy
smart-codex learning validate-candidate CANDIDATE_ID
smart-codex research status
smart-codex telemetry disable
```

## Dataset construction

The builder validates every JSONL record and record hash, rejects duplicates,
orphaned outcomes and broken correction links, selects the latest valid outcome,
and records exclusion counts. Missing token fields stay null. Rows without a
measured/reported total are retained for non-token analyses but excluded from
token comparisons.

Schema and exact Codex protocol versions are separated into deterministic
contract-group files and are never silently pooled. The complete input hash,
derived dataset hash, exclusion counts, evidence cutoff, and contract map are
recorded in `dataset_manifest.json`. Rebuilding the same input yields identical
bytes and hashes. Raw JSONL remains the source of truth; derived files can be
discarded and rebuilt.

## Fixed shadow algorithm

Comparable strata include schema/protocol, HMAC workspace, window, task domain
and subdomain, difficulty, scope, risk, verifier availability, product surface,
counter-reconciliation method, backend identity status, sandbox, and approval
policy. AOIA and SmartRouter observations therefore cannot be combined merely
because they are contemporaneous.

For each model-and-effort action the learner reports valid and labeled counts,
acceptance and verified-success rates, major-edit/rejection rates, median and
p90 measured tokens and wall time, retry/compaction rates, and unknown-field
rate. Acceptance uncertainty uses a two-sided 95% Wilson interval:

```text
center = (p + z²/(2n)) / (1 + z²/n)
margin = z * sqrt((p(1-p) + z²/(4n))/n) / (1 + z²/n)
z = 1.959963984540054
```

Fewer than five comparable measurements are descriptive
`INSUFFICIENT_DATA`. Fewer than 30 valid outcome labels for an action cannot
produce a candidate. A candidate also needs a comparable incumbent, a Wilson
lower bound within 0.05 of the incumbent lower bound, and at least 10% lower
median measured tokens or wall time. High/critical-risk strata abstain from
learned model changes. A 20 percentage-point recent quality shift after at
least 60 labels is `DRIFT_DETECTED`.

Possible results are `INSUFFICIENT_DATA`, `NO_COMPARABLE_ALTERNATIVE`,
`CANDIDATE_AVAILABLE`, `CANDIDATE_REJECTED_BY_SAFETY`, and `DRIFT_DETECTED`.
An empty dataset produces `ABSTAIN — INSUFFICIENT_DATA`.

Shadow decisions are separate hash-linked metadata events. `applied` and
`authority` are always false. Candidate files bind the algorithm version,
dataset-manifest hash, affected strata, evidence counts, and every abstention.
There is intentionally no promotion command.

## Exact Codex protocol contract

Routed research mode is pinned to `codex-cli 0.144.5`. Stable and experimental
JSON Schema and TypeScript bindings were regenerated from that installed
binary. The reviewed methods, notification shapes, token fields, and bundle
hashes are indexed under `smart_codex/app_server_router/schemas/`.

Any other version fails before the routed TUI opens. The gate is an exact
string comparison, not a range, wildcard, or warning. A future upgrade requires
fresh generated artifacts, field review, checksums, tests, and documentation.

## Retention and limitations

No telemetry is uploaded automatically. Aggregate export is an explicit future
operator action. Public reports must never contain real records, HMACs, salts,
filesystem UUIDs, private mount paths, prompts, or responses.

Token/caching/backend fields remain null when Codex does not expose them. The
learner does not infer missing values. Public or local observations cannot make
telemetry an authorization source. Thirty labels are only the minimum candidate
barrier, not proof that promotion is appropriate.
