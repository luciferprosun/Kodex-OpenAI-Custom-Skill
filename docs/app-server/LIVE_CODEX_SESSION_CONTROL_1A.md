# Live Codex Session Control 1A

## Status

The router control plane is live and demo-ready. Automatic per-turn model
execution is not enabled in this release.

This milestone adds a local control surface around the unmodified official
Codex CLI. It does not replace `codex`, patch Codex, connect a provider, apply
model recommendations, admit Ultra, or spawn subagents.

## Components

- `codex-smart` resolves and replaces itself with the official `codex`
  executable using an argument-list `exec`. Standard input, standard output,
  standard error, process exit status, and normal signals remain attached to
  the official process.
- `smart-routerctl` owns versioned local ON/OFF state.
- `$smart-router` and `$telemetry` are repository-native Codex skills that map
  allowlisted actions to the same controller.
- Existing project-local hooks read the router gate only in a session launched
  by `codex-smart`. OFF, missing, or malformed state returns control to normal
  Codex behavior.
- Research-capture START and STOP create metadata-only local lifecycle markers.
- While capture is ON, the reviewed `UserPromptSubmit`, `PostToolUse`, and
  `Stop` hooks bridge the turn into the existing SmartRouter telemetry schema
  2.0.0. No second telemetry schema or storage platform is introduced.

## Install or activate

From the repository root, install the local console entry points with the
existing package definition:

```bash
python -m pip install -e .
```

Then start the normal official Codex runtime through the separate wrapper:

```bash
codex-smart
```

All normal Codex arguments are forwarded unchanged, for example:

```bash
codex-smart --no-alt-screen -C /path/to/project
```

The original command remains unchanged and recoverable:

```bash
codex
```

The wrapper never installs an alias named `codex`, rewrites a symlink, or
modifies the official executable.

## Control commands

Direct CLI commands are deterministic and are useful for testing or recovery:

```bash
smart-routerctl smart-router status
smart-routerctl smart-router on
smart-routerctl smart-router off

smart-routerctl telemetry status
smart-routerctl telemetry start
smart-routerctl telemetry stop

smart-routerctl smart-router on --telemetry
smart-routerctl status --json
```

`smart-router on` changes only `router_enabled`. `telemetry start` changes only
the selective research-capture gate. `smart-router on --telemetry` persists
both values in one atomic state replacement, so no half-enabled state is
observable from the state file.

Repeated ON, OFF, START, and STOP actions are idempotent. Repeated START keeps
the current telemetry session instead of rotating it.

Status is read-only and reports the actual package, policy, and telemetry
schema versions together with these explicit boundaries:

```text
Automatic Model Execution: OFF
Ultra Automatic Execution: OFF
Automatic Policy Learning: OFF
```

## Native Codex command surface

The installed `codex-cli 0.144.6` supports repository-native skills. In a
Codex session launched from this trusted repository, use:

```text
$smart-router on
$smart-router on --telemetry
$smart-router off
$smart-router status

$telemetry start
$telemetry stop
$telemetry status
```

These skills accept only the listed action tokens and call the same local
controller as `smart-routerctl`. They do not interpolate user text into a
shell command.

Codex 0.144.6 also exposes the built-in `/hooks` command for reviewing and
trusting project-local hook definitions. Hook trust remains an explicit human
action.

Arbitrary bare slash-command registration is not an official extension point
used by this implementation. This release does not register or claim that
surface: these commands are **not** claimed or
registered by this release:

```text
/smart-router
/telemetry
```

Deprecated custom prompts could use `/prompts:name`, but this release does not
install user-home prompt files. Skills are the supported native surface.

## State contract and location

The state schema is `smart-codex-session-control-v1`. The default path is:

```text
$XDG_STATE_HOME/smart-codex/session-control/session-control.json
```

When `XDG_STATE_HOME` is unset, the fallback is:

```text
~/.local/state/smart-codex/session-control/session-control.json
```

Normal operation rejects a state root inside this source repository. The
directory is mode `0700`; state, lock, and marker files are mode `0600` on
platforms that support POSIX permissions. Writes use a process lock, a thread
lock, `fsync`, and atomic replacement.

Only exact JSON booleans are accepted. Missing state, invalid JSON, an unknown
schema, insecure file permissions, string booleans such as `"false"`, and
integer booleans all fail safely to:

```text
Smart Router: OFF
Research Telemetry: OFF
Telemetry Session: NONE
```

An explicit control command can replace malformed state with a reviewed valid
state. To return both switches to their safe defaults without deleting
records, run:

```bash
smart-routerctl reset
```

## Selective research telemetry

This is a gate over the existing run-telemetry system, not a second telemetry
system. START and STOP markers live under the same local state directory in
`research-markers/`. They contain only:

- marker and telemetry-session identifiers;
- transition (`capture_started` or `capture_stopped`);
- timestamp;
- policy version;
- router-enabled boolean;
- integration and marker schema versions.

They contain no prompts, responses, attachments, image data, tool payloads,
provider output, credentials, environment dumps, or inferred human ratings.
For an active turn, a temporary envelope contains only the unsealed metadata
record, HMAC turn/tool identifiers, the capture-session identifier, and a
monotonic start value. `Stop` seals and validates that record through the
existing collector and append-only storage, then removes the envelope.

The final record preserves schema `2.0.0`, record hashing, exact-field
validation, HMAC task/session/workspace identities, and separate human outcome
events. The hook protocol does not expose provider token usage, provider
request counts, or retry lifecycle evidence, so those fields remain `null`.
Tool counts are recorded only after `PostToolUse` and duplicate tool IDs are
deduplicated. Research telemetry cannot enable the router, approve an action,
change policy, or launch work.

If the configured sink is unavailable, status reports a controlled `DEGRADED`
state and the hook emits a sanitized telemetry warning. The router decision and
normal Codex execution path remain usable. No successful delivery is
fabricated.

## Hook behavior

The installed runtime advertises stable hooks and the repository contains
reviewable `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
`PermissionRequest`, and `Stop` adapters. The bridge checks two facts:

1. the session was launched through `codex-smart`;
2. the exact local `router_enabled` value is `true`.

Only then does it call the existing deterministic hook adapter. Router OFF does
not block a normal prompt, tool request, or permission request. Router ON still
produces only bounded advisory context or the pre-existing fail-closed safety
denials. It never changes model, reasoning effort, sandbox, or approval state.
Telemetry ON may classify a prompt for record metadata even when Router is OFF,
but that classification is never added to model context or applied to dispatch.

The Ultra hardening contracts remain separate and unchanged:

- `effective-turn-context-v1`;
- `ultra-decision-signature-v2`;
- explicit orchestration prohibitions remain vetoes;
- approval cannot override a veto;
- worker Git restrictions and strict approval booleans remain enforced.

## Privacy and authority

- State contains no prompt or response content.
- Lifecycle markers contain metadata only.
- No transcript is read.
- No API key, credential store, or provider configuration is accessed.
- Status is read-only.
- Neither switch grants execution authority.
- Existing Codex sandboxing, approvals, and explicit human authority remain in
  force.

## Minimal demo

Launch:

```bash
codex-smart
```

Use the native skill surface in the session:

```text
$smart-router status
$smart-router on
$telemetry status
$telemetry start
$smart-router status
$telemetry status
$telemetry stop
$smart-router off
```

Equivalent direct checks:

```bash
smart-routerctl smart-router status
smart-routerctl smart-router on
smart-routerctl telemetry start
smart-routerctl status
smart-routerctl telemetry stop
smart-routerctl smart-router off
```

Every status display says `Automatic Model Execution: OFF` and `Ultra
Automatic Execution: OFF`.

For a repeatable no-provider proof, run:

```bash
./scripts/smart-router-demo-closure
```

It creates temporary local state, demonstrates all four switch combinations,
runs the real classifier and hook bridge, validates one synthetic schema-2.0.0
record, and deletes the temporary directory. It is labeled `LOCAL MOCKED HOOK
FLOW` and does not claim a model execution or provider response.

## Disable and uninstall

Turn both controls off:

```bash
smart-routerctl reset
```

Use `codex` instead of `codex-smart` to bypass the wrapper integration. To
remove the installed local console entry points, uninstall the local
`codex-patch-smart-router` package using the same Python environment that was
used for installation. Neither action modifies the official Codex package.

## Deferred next step

A later, separately reviewed milestone may connect advisory recommendations to
an explicit live per-turn execution boundary and enrich hook records from a
stable provider-usage event surface. It must preserve task-bound Ultra
approval, orchestration vetoes, privacy, and human authority. No automatic
model execution, autonomous learning, or telemetry-driven policy mutation
exists in this release.
