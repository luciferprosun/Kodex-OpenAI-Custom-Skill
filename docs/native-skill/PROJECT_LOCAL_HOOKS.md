# Project-Local Hooks

Status: **IMPLEMENTATION GREEN — MANUAL HOOK TRUST ACCEPTANCE PENDING**

The Phase 5 adapters add repository-local lifecycle guardrails while keeping
the deterministic Router Core and the root `rules/` Knowledge Library as the
only executable routing policy. They do not modify Codex, global Codex
configuration, or the normal human approval flow.

Session Control 1A now gates all three adapters through the local
`smart-codex-session-control-v1` state. They run only when the official Codex
session was launched through `codex-smart` and Smart Router is explicitly ON.
OFF, missing, or malformed state returns `{}` and leaves normal Codex behavior
unchanged. This gate adds no model, Ultra, subagent, provider, or approval
execution path.

## Codex version tested

The implementation was revalidated against `codex-cli 0.144.6`, with the stable
`hooks` feature enabled. The input, output, discovery, and trust contracts were
checked against the current
[official Codex Hooks documentation](https://learn.chatgpt.com/docs/hooks) and
the installed release before implementation.

## Architecture

The project configuration in `.codex/hooks.json` registers three command
hooks. Each Python entrypoint reads one JSON object from standard input, adds
only the repository root to `sys.path`, and calls
`smart_codex.session_hook_bridge`. The bridge reads only the wrapper marker and
local router-enabled boolean before delegating to the original handler in
`smart_codex.codex_hook_adapter`.

The adapter validates the documented event payload, creates one in-memory
classification string, calls `smart_codex.router.route_prompt`, normalizes an
allowlisted decision, and emits the documented hook response. It contains no
destructive-operation, Git, credential, publication, database,
security-control, or Codex-binary mutation patterns. Those remain centralized
in the Router Core and root Knowledge Library.

The standalone launcher is neither imported nor called. The hooks do not start
a Codex process or call a provider API.

The exact Phase 5 analysis fixture, `Analyze only whether deleting main would
be dangerous.`, exposed one missing shorthand in the central protected-branch
trigger. With explicit operator approval, one declarative term was added to
`rules/risk_triggers.json`; the adapter still contains no matching security
pattern and all three existing eval sets remain unchanged and green.

## Official hook shapes

`UserPromptSubmit` returns a `hookSpecificOutput` with
`hookEventName: UserPromptSubmit` and bounded `additionalContext`, or a
top-level `decision: block` with a sanitized reason on failure.

`PreToolUse` returns a `hookSpecificOutput` with
`permissionDecision: deny` only when the central policy denies the proposed
action. An ordinary action returns `{}`.

`PermissionRequest` returns a nested `decision` with `behavior: deny` only for
unsafe or unclassifiable requests. An ordinary request returns `{}`, leaving
Codex to present its normal approval question to the human.

All command adapters exit successfully after emitting exactly one compact JSON
object. This makes malformed input fail closed through the structured response
instead of depending on an unstructured process error.

## UserPromptSubmit behavior

The complete submitted prompt is passed to the Router Core as one Python
string. A successful route adds only these stable fields to developer context:

- schema, category, risk, complexity, and action danger;
- recommended profile, sandbox, and approval policy;
- evidence and context requirements;
- confidence and confirmation requirement.

The raw prompt and prompt excerpts are excluded. Recommendations are explicitly
advisory and have not been applied.

High-risk analysis remains possible. An analysis-only route receives a static
warning that no operation was executed and that side effects still require
human approval; it is not blocked merely for discussing a dangerous action.
Missing, empty, malformed, unclassifiable, or configuration-failing prompts are
blocked with `SMART_ROUTER_FAIL_CLOSED` and no internal details.

## PreToolUse behavior

The installed-release matcher covers `Bash`, `apply_patch`, the `Edit` and
`Write` aliases, and selected tool names beginning with `mcp__`. Bash and patch
commands are classified from `tool_input.command`. MCP arguments are converted
to a deterministic in-memory representation and are never persisted or logged.

Central critical-risk and execution-oriented safety decisions are denied.
This includes the centrally recognized destructive, secret-touching, database,
deployment/publication, privileged, security-control, and Codex-binary mutation
classes. Safe and ordinary calls return `{}`: the hook does not auto-allow,
rewrite input, or weaken the Codex sandbox or approval policy. A malformed
supported call, Router Core failure, or Knowledge Library failure is denied.

**PreToolUse is a guardrail, not a complete enforcement boundary.** Current
hook coverage does not intercept every shell path, every non-shell tool, or
every product-internal operation. In particular, aliases are release-specific,
and tools outside the configured Bash, patch/edit/write, and selected MCP
matchers are not claimed as protected by this hook.

## PermissionRequest behavior

The Smart Router never auto-allows a `PermissionRequest`. A centrally unsafe
or unclassifiable request is denied. A low- or medium-risk request returns `{}`
so that the normal Codex approval prompt remains visible and the human remains
the authority. The adapter never returns updated permissions, rewritten input,
or an automatic approval.

## Fail-closed policy

- Prompt validation, routing, configuration, or normalization failure blocks
  `UserPromptSubmit` with a static sanitized reason.
- Supported tool validation, routing, configuration, or normalization failure
  denies `PreToolUse` with a static sanitized reason.
- Permission validation, routing, configuration, or normalization failure
  denies `PermissionRequest` with a static sanitized reason.

The entrypoints also provide static event-specific failure responses if the
adapter cannot be imported. No exception message or submitted data is returned.

## Privacy guarantees

Each entrypoint reads standard input once. Prompts, commands, and MCP arguments
remain in memory; they are not placed in process arguments or temporary files.
The adapters do not read `transcript_path`, `.env`, `auth.json`, SSH private
keys, token stores, or credential stores. They do not log raw hook input and do
not use `shell=True`, `shlex.split`, `eval`, or `exec`.

Tests use synthetic filenames and the fake canary
`FAKE_CODEX_HOOK_SECRET_91E73A`; no real credentials are used.

## Automated validation

- Phase 5 configuration, adapter, and subprocess tests: 44/44 passed.
- Full repository suite: 227/227 passed (the previous 183 tests plus 44 new
  tests).
- `eval_set_001`: 51/51; `eval_set_002`: 85/85;
  `eval_set_003_safety_coverage`: 69/69.
- Direct stdin simulations passed for safe and failing `UserPromptSubmit`, safe
  and denied `PreToolUse`, and deferred and denied `PermissionRequest` inputs.
- Privacy canary, no-temporary-input-file, no-launcher, no-provider,
  no-auto-allow, and structured fail-closed checks passed.

## Human-control guarantees

- Hook recommendations do not change the active model, effort, profile,
  sandbox, or approval policy.
- Safe `PreToolUse` decisions defer to the normal Codex controls.
- `PermissionRequest` is never automatically approved.
- Hook trust is never bypassed or written by these files.
- No claim is made that all Codex tools are intercepted.

## Hook configuration

The definitions to review are:

| Event | Matcher | Command | Timeout | Status message |
| --- | --- | --- | ---: | --- |
| `UserPromptSubmit` | none | `/usr/bin/python3 "$(git rev-parse --show-toplevel)/.codex/hooks/user_prompt_submit.py"` | 15 s | `Checking Smart Router session gate` |
| `PreToolUse` | `^(Bash\|apply_patch\|Edit\|Write\|mcp__.*)$` | `/usr/bin/python3 "$(git rev-parse --show-toplevel)/.codex/hooks/pre_tool_use.py"` | 15 s | `Checking proposed tool action` |
| `PermissionRequest` | `^(Bash\|apply_patch\|Edit\|Write\|mcp__.*)$` | `/usr/bin/python3 "$(git rev-parse --show-toplevel)/.codex/hooks/permission_request.py"` | 15 s | `Reviewing permission request` |

No prompt or tool data is interpolated into these commands. Paths resolve from
the current Git repository root and contain no user-home-specific location.

## Review and trust procedure

1. Start a fresh `codex-smart` session from the repository root without any
   hook-trust bypass option.
2. Open `/hooks`.
3. Confirm that the source is project-local and compare all three definitions
   with the table above and `.codex/hooks.json`.
4. Review the three entrypoints, `smart_codex/session_hook_bridge.py`, and
   `smart_codex/codex_hook_adapter.py`.
5. Only the human operator may trust the reviewed definitions.
6. Start another fresh session after trust so the accepted definitions are
   loaded normally.

Trust is bound to the reviewed definitions. A changed definition requires a
new review. No trust state is stored in this repository.

## Manual acceptance procedure

After the human trusts the definitions in `/hooks`, use a fresh session and:

1. Run `$smart-router on`, then submit `Explain the current repository status.
   Do not modify files.` and confirm that `UserPromptSubmit` adds a sanitized
   router decision.
2. Request `git status --short` and confirm that `PreToolUse` does not deny it
   while normal sandbox behavior remains active.
3. Analyze, but do not execute, `git push --force origin main`; validate the
   denial separately with a synthetic `PreToolUse` payload.
4. If a disposable, no-side-effect operation naturally requests permission,
   confirm that the normal human prompt remains visible and is not auto-allowed.

Until that human review and fresh-session test are complete, the recorded status
must remain **IMPLEMENTATION GREEN — MANUAL HOOK TRUST ACCEPTANCE PENDING**.

The automated Phase 5 run started a fresh Codex TUI and reached the installed
release's directory-trust gate before project-local configuration could load.
The operator-facing `No, quit` choice was selected, so no trust was granted.
Consequently the three definitions have not yet been displayed inside `/hooks`
or exercised in a trusted normal session; those checks are intentionally part
of the pending human acceptance.

## Disable and rollback procedure

Run `smart-routerctl smart-router off` to disable the local session gate. To
disable the project definitions themselves, use `/hooks`, then start a fresh
Codex session and confirm that they are no longer active. To remove the
implementation, revert the Phase 5 commit and verify that `.codex/hooks.json`
and the three entrypoints are absent. No global configuration, trust-store
edit, binary replacement, or plugin removal is required.

## Known interception gaps

Codex invokes hooks only on documented event paths. `PreToolUse` does not cover
all possible shell execution, non-shell built-in tools, web operations, or
future/renamed tool aliases. Hook process failure behavior is also controlled by
the installed Codex release, so the adapter emits structured fail-closed output
for every handled input. These limitations are why existing Codex sandboxing,
approval prompts, repository protections, and operating-system controls remain
authoritative.

## Phase 6 plugin migration

Phase 6 may package the proven project-local implementation after manual Phase
5 acceptance. It must reuse these canonical sources without independently
edited policy copies, preserve human trust and approval, and revalidate paths
and hook schemas for the target Codex release. No plugin, marketplace, MCP
server, or App Server integration is part of Phase 5.
