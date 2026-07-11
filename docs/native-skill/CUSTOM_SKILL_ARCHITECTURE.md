# Custom Skill Architecture

Status: proposed architecture; no runtime files created in Phase 1.

## Architecture decision

Select **C. Skill packaged as plugin with hooks** as the target architecture.

The delivery sequence is intentionally layered:

1. Develop and test a repository-local skill.
2. Add and test project-local hooks against the installed Codex release.
3. Package the proven skill and hook adapters as a plugin.
4. Test local marketplace installation, trust, disable, and removal.

This is the smallest official path that preserves the normal Codex TUI while adding both reusable routing guidance and pre-prompt/supported pre-action gates. It does not claim that a skill or hook can change the active model, profile, or sandbox for a current turn.

## Component boundaries

### Router Core

Canonical implementation:

- `smart_codex/knowledge.py`
- `smart_codex/preprocessor.py`
- `smart_codex/scorer.py`
- `smart_codex/risk.py`
- `smart_codex/router.py`
- existing support modules under `smart_codex/`
- canonical JSON policy under `rules/`

Responsibilities:

- normalize prompt text without execution;
- load and validate the Knowledge Library;
- classify category, complexity, risk, and action danger;
- apply hard overrides and final safety gates;
- return one deterministic `RoutingDecision`;
- hash the prompt for privacy-safe metadata;
- fail closed with `ConfigError` when policy is unavailable or invalid.

The core remains independent of Codex skill and hook wire formats.

### Skill Adapter

Responsibilities:

- explain when the router should be invoked;
- pass the user's prompt to the Router Core as one Python string;
- render a bounded, machine-readable routing decision;
- tell Codex which parts are advisory;
- never launch Codex and never claim to change the active session settings.

The adapter must not contain category terms, risk triggers, profile mappings, model names, or a second safety policy.

### Hook Adapter

Responsibilities:

- parse the documented JSON object from `stdin`;
- validate event name and required fields;
- call the same Router Core;
- translate the decision into event-specific Codex JSON;
- keep raw prompts in memory only;
- block on deterministic hard-safety/invalid-config conditions where the hook contract permits it;
- deny covered tool or approval requests when policy requires it;
- state coverage limits explicitly.

There are three separate translators because their schemas and authority differ:

- `UserPromptSubmit`: add bounded developer context or block the turn.
- `PreToolUse`: deny or rewrite only documented supported tool calls.
- `PermissionRequest`: deny or defer an approval request; V0.3 does not auto-allow.

### Plugin Package

Responsibilities:

- provide `.codex-plugin/plugin.json`;
- bundle the proven skill and hook adapters;
- provide install/distribution metadata;
- use plugin-relative paths and `PLUGIN_ROOT`/`PLUGIN_DATA` correctly;
- preserve the same hook trust workflow;
- contain no authentication material or global configuration mutation.

The first plugin manifest should omit a `hooks` field and rely on the documented default `hooks/hooks.json` path. This avoids the current conflict between release documentation and the official plugin-creator validator guidance. A custom manifest hook path is unnecessary for this design.

## Recommended development tree

Only the first three skill files are proposed for the repository-local implementation. Hook files appear here as future Phase 5 targets, not current files.

```text
codex-patch-smart-router/
|-- .agents/
|   `-- skills/
|       `-- codex-patch-smart-router/
|           |-- SKILL.md
|           |-- scripts/
|           |   `-- route_prompt.py
|           `-- references/
|               `-- routing-policy.md
|-- .codex/                              Phase 5 only
|   |-- hooks.json
|   `-- hooks/
|       |-- user_prompt_submit.py
|       |-- pre_tool_use.py
|       `-- permission_request.py
|-- smart_codex/                         existing canonical core
|-- rules/                               existing canonical policy/evals
|-- tests/                               existing and adapter tests
`-- docs/native-skill/                   Phase 1 documentation
```

### Evaluation of the proposed skill files

| Proposed file | Decision | Reason |
|---|---|---|
| `SKILL.md` | Keep | Required entry point and invocation workflow. |
| `scripts/route_prompt.py` | Keep | Deterministic, thin bridge to the tested Router Core. |
| `scripts/validate_router.py` | Remove | Validation belongs in repository tests/CI; a second runtime script adds no user capability. |
| `references/routing-policy.md` | Keep | Holds the concise advisory/enforcement contract without bloating `SKILL.md`. |
| `references/safety-invariants.md` | Remove | Put the small required invariant list in `SKILL.md`; `SECURITY.md` remains the project source of truth. |
| `references/knowledge-library-map.md` | Remove | The map belongs in architecture/developer docs, not runtime skill context. |
| `assets/routing-decision.example.json` | Remove | The JSON contract should be asserted in tests and shown briefly in the reference file. |
| `agents/openai.yaml` | Defer | Optional UI/invocation metadata; add only when an actual install surface needs it. |

This leaves one required file, one deterministic adapter, and one focused reference. It avoids loading maintenance material into skill context.

## Target plugin tree

Phase 6 should build a distributable directory from canonical sources:

```text
codex-patch-smart-router-plugin/
|-- .codex-plugin/
|   `-- plugin.json
|-- skills/
|   `-- codex-patch-smart-router/
|       |-- SKILL.md
|       |-- scripts/
|       |   `-- route_prompt.py
|       `-- references/
|           `-- routing-policy.md
|-- hooks/
|   |-- hooks.json
|   |-- user_prompt_submit.py
|   |-- pre_tool_use.py
|   `-- permission_request.py
`-- runtime/                              only if self-contained distribution requires it
    |-- smart_codex/
    `-- rules/
```

The `runtime/` copy is not authored independently. For repository-local development, adapters import the existing root package directly and no copy exists. If public installation must be self-contained, Phase 6 may generate `runtime/` from the canonical `smart_codex/` and `rules/` sources as a release artifact. A build-time equivalence test must reject drift. An alternative is a formally packaged Python dependency, but the plugin must not install it automatically. This distribution decision is postponed until local skill and hook behavior is proven.

## Data flow

```text
                         +------------------------------+
User prompt ------------>| Skill or UserPromptSubmit   |
                         | thin adapter                 |
                         +--------------+---------------+
                                        | one in-memory string
                                        v
                         +------------------------------+
                         | Router Core                  |
                         | preprocessor + knowledge +  |
                         | scorer + risk + router       |
                         +--------------+---------------+
                                        | validated RoutingDecision
                +-----------------------+------------------------+
                v                       v                        v
     +-------------------+  +----------------------+  +---------------------+
     | Skill rendering   |  | UserPromptSubmit     |  | Tool/permission     |
     | advisory decision |  | context or block     |  | deny/defer on       |
     | only              |  |                      |  | supported paths     |
     +-------------------+  +----------------------+  +---------------------+
```

No adapter writes a model/profile/sandbox change into an active Codex thread because the official skill and hook output schemas do not expose that operation.

## Router Core reuse map

| Existing asset | Reuse |
|---|---|
| `knowledge.py` | Single loader/validator for every adapter; `ConfigError` is authoritative. |
| `preprocessor.py` | Prompt normalization only; no files, tools, or execution. |
| `scorer.py` | Canonical weighted scoring and hard override evaluation. |
| `risk.py` | Existing compatibility/public risk API; no new hook-specific risk engine. |
| `router.py` | Sole producer of `RoutingDecision` and final action-danger gate. |
| prompt/category/risk/complexity/action JSON | Read in place by the core; never copied into the repo-local skill. |
| evidence/context/profile/tie-breaker JSON | Read in place by the core; exposed as bounded decision fields. |
| `eval_set_001.jsonl`, `eval_set_002.jsonl` | Regression fixtures for core and adapter parity. |

`launcher.py` is not used by the skill or hooks. It remains the standalone wrapper's explicit `--execute` path. This separation prevents skill activation from implying execution.

## Skill invocation flow

1. Codex discovers metadata from `.agents/skills/codex-patch-smart-router/SKILL.md`.
2. The user selects it with `/skills` or `$codex-patch-smart-router`, or Codex selects it by description when implicit invocation remains enabled.
3. Codex reads the full `SKILL.md` and only the referenced routing policy needed for the task.
4. Codex invokes `scripts/route_prompt.py` with the prompt as one argument or a structured standard-input value defined by the adapter contract.
5. The script imports `smart_codex.router.route_prompt` from the repository root and returns JSON.
6. Codex presents and follows the advisory safety instructions. It does not claim that the active model/profile/sandbox changed.

Preferred adapter input is JSON on `stdin` or a single argument after `--`; either form must preserve the entire prompt as one string. The final choice is made in Phase 3 and locked with metacharacter tests.

## Hook invocation flow

### UserPromptSubmit

1. Codex sends the documented event JSON on `stdin`.
2. Adapter validates `hook_event_name == "UserPromptSubmit"` and `prompt` is a string.
3. Adapter routes the in-memory prompt through the canonical core.
4. Low/medium routes return bounded `additionalContext` with category, risk, action danger, and safety guidance.
5. Hard-safety or invalid-policy routes return a documented block response.
6. No raw prompt is written or echoed.

### PreToolUse

1. Codex sends a covered tool name and `tool_input`.
2. Adapter validates against only documented names observed in local tests.
3. Adapter evaluates the proposed command/action with the same core policy and a hook-specific translation layer.
4. Dangerous covered calls are denied; benign calls are allowed without weakening normal Codex approvals.
5. Unsupported tool paths are not represented as protected.

### PermissionRequest

1. Codex invokes the hook only for an approval request.
2. Adapter evaluates the request data available in `tool_input`.
3. It returns deny for a deterministic prohibited case or no decision to preserve the normal approval prompt.
4. V0.3 never returns automatic allow.

## Error handling

| Condition | Skill behavior | Hook behavior |
|---|---|---|
| Valid decision | Return bounded JSON, exit 0 | Return documented event JSON, exit 0 |
| `ConfigError` | Return `ok: false`, `error: CONFIG_ERROR`; no execution advice | Return a documented prompt/tool block where supported |
| Malformed hook input | Not applicable | Return generic block without echoing input |
| Unknown category without risk | Preserve existing standard-profile advisory warning | Add conservative context; do not invent settings |
| High/critical risk | Report security/read-only recommendation | Block or deny only where the event contract supports it |
| Adapter exception | Return sanitized error; nonzero | Attempt documented block; Phase 5 must prove runtime failure behavior |
| Timeout/runtime cannot start | Stop implementation rollout | Do not claim fail-closed until local behavior is verified |

Application-level fail-closed behavior can be implemented for parsed events. Codex's behavior when the hook process itself cannot start, times out, or returns an undocumented status must be empirically verified; otherwise the rollout stops.

## Privacy model

- Raw prompt exists only in process memory for routing.
- Logs may contain `prompt_hash` and bounded routing metadata only.
- Hook adapters ignore `transcript_path` and never read transcripts.
- No adapter reads `.env`, auth files, keys, tokens, SSH material, or unrelated repositories.
- `additionalContext`, denial reasons, stderr, and test snapshots must never echo the raw prompt.
- Plugin data storage is unnecessary for V0.3; `PLUGIN_DATA` should remain unused unless a later, reviewed requirement appears.
- No network access is required for routing.

## Installation model

### Repository-local skill

Commit `.agents/skills/codex-patch-smart-router/`. Codex discovers it from the repository tree. No global config, alias, binary change, or plugin installation is required.

### Project-local hooks

Commit `.codex/hooks.json` and hook scripts only in Phase 5. The user reviews them through `/hooks` and explicitly trusts their current hashes. A changed definition requires review again.

### Plugin

Create a local repository marketplace only in Phase 7. Attempt installation through `/plugins` as an explicit runtime check; use the locally verified `codex plugin add` flow as the confirmed CLI path. Start a new session, review hook trust, and verify all component paths. Do not edit global config by hand.

## Uninstall and rollback

- Skill-only rollback: revert/remove the repository-local skill files.
- Hook rollback: disable the project hook through `/hooks` or revert the `.codex/` hook commit; do not bypass trust.
- Plugin rollback: disable it in the plugin UI or run the verified `codex plugin remove PLUGIN@MARKETPLACE` command, then start a new session.
- Marketplace rollback: remove the test marketplace using the verified marketplace command only after the plugin is removed.
- Code rollback: revert the phase-specific commit. The stock `codex` binary and original authentication state are unaffected.

Every phase has its own commit so rollback never requires `git reset --hard`, replacing `codex`, or restoring global configuration from a backup.

## Non-negotiable invariants

- one Router Core and one JSON policy source;
- no raw prompt logging;
- prompt hash only in persistent routing records;
- no `shell=True`;
- no `shlex.split(prompt)`;
- prompt remains one string;
- no `danger-full-access`;
- approval remains `on-request` or normal user review;
- no automatic PermissionRequest allow in V0.3;
- no invented model or tool names;
- no secret-file reads;
- `CONFIG_ERROR` blocks adapter progress;
- standalone execution still requires `--execute`;
- original Codex binary remains untouched;
- no claim of dynamic active-model/profile/sandbox mutation;
- no claim of full tool interception.
