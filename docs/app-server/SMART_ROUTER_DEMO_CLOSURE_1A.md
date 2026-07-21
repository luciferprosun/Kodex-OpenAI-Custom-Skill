# Smart Router Demo Closure 1A

## Honest release boundary

This is a demo-ready, pre-production runtime integration. `codex-smart`
launches the unmodified official Codex runtime. The project-local hook layer
can add a bounded advisory routing summary and can collect metadata through the
existing SmartRouter telemetry implementation.

It does not automatically change the Codex model or reasoning effort. It does
not run Ultra, spawn subagents, call a provider, approve actions, learn from
telemetry, or mutate policy.

## Supported controls

The canonical direct controls are:

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

Inside a trusted Codex session launched with `codex-smart`, the supported
native skill equivalents are:

```text
$smart-router status
$smart-router on
$smart-router on --telemetry
$smart-router off
$telemetry status
$telemetry start
$telemetry stop
```

Codex CLI 0.144.6 does not provide an arbitrary bare slash-command registration
point used by this project. `/smart-router` and `/telemetry` are therefore not
claimed. `/hooks` is the official built-in surface for reviewing and trusting
the project hook definitions.

## Independent state matrix

| Smart Router | Research telemetry | Runtime result |
| --- | --- | --- |
| OFF | OFF | Normal Codex path; no SmartRouter hook context or task record |
| ON | OFF | Advisory routing and existing safety hooks; no task record |
| OFF | ON | Normal Codex model path; schema-2.0.0 metadata capture only |
| ON | ON | Advisory routing plus independent schema-2.0.0 capture |

Turning the router OFF does not stop capture. Stopping capture does not disable
the router. Missing or malformed state fails closed to OFF/OFF.

## Runtime path

```text
official codex via codex-smart
  -> reviewed UserPromptSubmit hook
     -> session gate
     -> existing deterministic route_prompt (advisory when router ON)
     -> existing TelemetryService shell (only when telemetry ON)
  -> normal Codex execution and approval path
  -> reviewed PostToolUse hook (bounded tool category/count only)
  -> reviewed Stop hook
     -> existing schema 2.0.0 seal, privacy scan, hash validation, append
```

Raw prompts are used in memory for deterministic classification and HMAC task
signatures; they are not persisted. Raw paths, tool arguments, tool responses,
transcripts, credentials, and provider content are not stored. Provider-only
token, request, and retry fields remain unavailable (`null`) on the hook
surface.

## Failure behavior

- Router OFF bypasses routing influence completely.
- A malformed control file produces OFF/OFF.
- A router classification failure retains the existing fail-closed hook
  behavior when Router is ON.
- A telemetry initialization, preflight, or append failure produces a
  controlled degraded warning and does not change router state.
- Telemetry never changes model selection, approval, sandbox, Ultra admission,
  or checked-in policy.
- Automatic policy learning is OFF.

## Local smoke flow

Run:

```bash
./scripts/smart-router-demo-closure
```

This is an explicitly synthetic, provider-free hook simulation. It proves the
control matrix, routing summary, schema/hash validation, and existing telemetry
append path using a temporary directory. It does not fake or claim model
execution.

For an operator-controlled live demo:

```bash
smart-routerctl status
smart-routerctl smart-router on
codex-smart
smart-routerctl telemetry start
smart-routerctl status
smart-routerctl telemetry stop
smart-routerctl smart-router off
```

Within `codex-smart`, use the `$smart-router` and `$telemetry` skills. Review
changed hooks with `/hooks` before trusting them.

## Deferred work

Automatic per-turn application of model recommendations, stable provider usage
enrichment on the hook path, empirical Ultra execution, and offline policy
calibration remain separate post-demo milestones. Human-reviewed outcome labels
remain separate from run records.
