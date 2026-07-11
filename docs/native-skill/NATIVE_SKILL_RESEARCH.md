# Native Skill Research

Status: Phase 1 research only

Checked: 2026-07-11 (Europe/Berlin)

Repository: `Codex Patch Smart Router`

Local Codex: `codex-cli 0.144.1`

## Scope and evidence policy

This dossier covers only the conversion of Codex Patch Smart Router into a repository-local Codex skill and its later packaging as a plugin with lifecycle hooks. No skill, hook, plugin, alias, Codex binary, or global configuration was created or changed in this phase.

Architecture claims are based on current OpenAI documentation, the official `openai/codex` repository, and read-only local CLI inspection. Open GitHub issues are treated as implementation-risk evidence, not as stronger contracts than the current release documentation.

## Local state

- Starting branch: `feature/knowledge-library-v0-2`
- Starting HEAD: `86a4192` (`2adeab6` is an ancestor and the user-designated baseline)
- Research branch: `feature/custom-skill-research`
- Worktree before documentation: clean
- Tests before documentation: `66 passed`
- `eval_set_002`: included in the suite and passed all 85 cases
- Codex features reported by `codex features list`: `hooks stable true`, `plugins stable true`, and `apps stable true`
- The literal `codex features` command requires a subcommand in 0.144.1; `codex features list` produced the feature table.

An isolated TUI was attempted with a disposable `CODEX_HOME` under `/tmp`. It stopped at the sign-in screen because credentials were intentionally not copied or read. Therefore `/skills`, `/plugins`, and `/hooks` were not exercised inside that isolated TUI. Their documented behavior was checked against the official docs, while plugin add/remove and marketplace command surfaces were verified through local `--help`. This is an explicit Phase 7 verification item.

## A. Codex skills

### Required structure and frontmatter

The minimum supported skill is a directory containing `SKILL.md`. The current official example requires exactly these frontmatter fields:

```yaml
---
name: codex-patch-smart-router
description: Route and assess Codex prompts with the repository's deterministic Smart Router when prompt risk, action danger, task weight, or routing policy matters.
---
```

`name` identifies the skill. `description` is both user-facing discovery metadata and the basis for implicit activation, so it must state when the skill should and should not trigger. The instructions follow the closing `---`.

Supported optional content is:

```text
codex-patch-smart-router/
|-- SKILL.md                 required
|-- scripts/                 optional executable code
|-- references/              optional documentation
|-- assets/                  optional templates/resources
`-- agents/
    `-- openai.yaml          optional UI, invocation, and tool-dependency metadata
```

`agents/openai.yaml` can define `interface` metadata, `policy.allow_implicit_invocation`, and tool dependencies. It is not required for a repository-local skill and does not provide an API for changing the active model, profile, sandbox, or approval policy.

Source: [Build skills](https://learn.chatgpt.com/docs/build-skills).

### Discovery locations

Current documented locations are:

- Repository: `.agents/skills` from the current working directory through every parent directory up to the repository root.
- User: `$HOME/.agents/skills`.
- Administrator: `/etc/codex/skills`.
- System: skills bundled by OpenAI.

The proposed repository path `.agents/skills/codex-patch-smart-router/` is therefore correct. A user-level copy under `~/.codex/skills` is not the current documented authoring location; use `$HOME/.agents/skills` for a user-authored skill.

Codex follows symlinked skill directories. If duplicate skills have the same `name`, Codex does not merge them; both may appear in selectors. This project should avoid publishing both a repo-local and plugin-installed copy with the same name during one test.

### Invocation and progressive disclosure

- Explicit: open `/skills` in CLI/IDE, or mention `$codex-patch-smart-router` in the prompt.
- Implicit: Codex may select the skill when the prompt matches its `description`.
- `agents/openai.yaml` may set `policy.allow_implicit_invocation: false`; explicit `$skill-name` use still works.
- Progressive disclosure: Codex initially loads each skill's `name`, `description`, and path. It reads the full `SKILL.md` only after selecting the skill. Referenced files should be loaded only when the instructions require them.

Codex detects skill file changes automatically. If a new or changed skill does not appear, restart Codex or start a new session. Changes to `~/.codex/config.toml` require a restart, but this project will not use global config for repository-local testing.

### Scripts and dependencies

Skills may contain executable scripts, but the official guidance prefers instructions unless deterministic behavior or external tooling is required. This router is precisely a deterministic use case, so one thin Python adapter is justified.

The skill format does not imply that Python packages are installed for a script. `agents/openai.yaml` can declare tool dependencies such as an MCP server; it is not a general Python dependency installer. The existing router has no runtime third-party dependencies, so the adapter should use the repository interpreter and import the existing package without installing anything globally.

Scripts must not:

- execute the prompt as shell text;
- use `shell=True`;
- tokenize the prompt with `shlex.split(prompt)`;
- install dependencies automatically;
- read secrets or transcripts;
- duplicate classification or safety rules from `smart_codex/` and `rules/`.

For later npm-backed plugin distribution, official docs state that Codex downloads the package without running npm lifecycle scripts. That packaging behavior does not remove the need to audit every bundled runtime script.

### Testing without global installation

The supported low-impact test path is:

1. Add the skill only under this repository's `.agents/skills/` path.
2. Start a new Codex session with this repository as `cwd` and conservative local flags.
3. Confirm discovery through `/skills`.
4. Invoke it explicitly with `$codex-patch-smart-router` using benign and high-risk fixtures.
5. Verify implicit activation separately only after explicit behavior is stable.
6. Remove the repository-local skill directory to roll back; no global config edit is needed.

App Server also exposes `skills/list` with `cwd` and `forceReload`, but using App Server solely to test the V0.3 skill would add unnecessary surface area. It remains an optional diagnostic, not the primary test path.

## B. Lifecycle hooks

### Discovery, configuration, and trust

Codex discovers hooks next to active config layers as `hooks.json` or inline `[hooks]` tables. Relevant locations are:

- `<repo>/.codex/hooks.json`
- `<repo>/.codex/config.toml`
- `~/.codex/hooks.json`
- `~/.codex/config.toml`
- enabled plugin hook configuration

Repository hooks load only when the repository `.codex/` layer is trusted. Non-managed command hooks require review and trust of the exact hook definition. Trust is hash-based: changed hooks are skipped until reviewed again. `/hooks` is the documented browser for sources, trust, and disable state.

Plugin-bundled hooks use the same non-managed trust flow. Installing or enabling a plugin does not automatically trust its hooks.

Only `type: "command"` handlers run today. `prompt` and `agent` handlers are parsed but skipped. Asynchronous handlers are parsed but unsupported and skipped. Hook commands receive JSON on `stdin`, run with the session `cwd`, and default to a 600-second timeout when `timeout` is omitted. This project should set a much smaller explicit timeout.

Source: [Hooks](https://learn.chatgpt.com/docs/hooks).

### Common command-hook input

Every command hook receives one JSON object on standard input. Common fields are:

```json
{
  "session_id": "string",
  "transcript_path": "string or null",
  "cwd": "string",
  "hook_event_name": "string",
  "model": "active model slug",
  "permission_mode": "default | acceptEdits | plan | dontAsk | bypassPermissions"
}
```

Turn-scoped events also document `turn_id`. The transcript format is explicitly not a stable hook interface. Smart Router adapters must ignore `transcript_path` and must not open it.

### UserPromptSubmit schema

`UserPromptSubmit` adds:

```json
{
  "turn_id": "string",
  "prompt": "the user prompt about to be sent"
}
```

`matcher` is ignored for this event.

Safe developer context output:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "Smart Router advisory: risk=high; action_danger=secret_touching_operation; do not read secret files; request confirmation before any action."
  }
}
```

The context is added as developer context. It should contain only bounded routing metadata and safety instructions, never the raw prompt, model inventions, or executable shell text.

Block output:

```json
{
  "decision": "block",
  "reason": "Smart Router blocked this turn because deterministic routing configuration could not be validated."
}
```

Exit behavior guaranteed by the release documentation:

- Exit `0` with no output: success; Codex continues.
- Exit `0` with plain text for `UserPromptSubmit`: text becomes additional developer context.
- Exit `0` with valid JSON: Codex applies the documented output fields.
- Exit `2` with a reason on `stderr`: blocks the submitted prompt.

The release page does not establish every other non-zero exit code as a safe block. The implementation must not rely on unspecified failure behavior. A validated decision should return structured JSON with exit `0`; an intentional blocking path may use structured `decision: "block"` or exit `2`. Phase 5 must test malformed input, timeout, and unexpected exceptions against the installed version before calling the adapter fail-closed.

### PreToolUse schema and limits

`PreToolUse` adds:

```json
{
  "turn_id": "string",
  "tool_name": "Bash | apply_patch | mcp__server__tool",
  "tool_use_id": "string",
  "tool_input": {}
}
```

For `Bash` and `apply_patch`, current docs describe the command under `tool_input.command`; MCP tools supply their argument object. Supported outcomes include:

- deny with `hookSpecificOutput.permissionDecision: "deny"` and `permissionDecisionReason`;
- allow and rewrite a supported input with `permissionDecision: "allow"` plus `updatedInput`;
- add model-visible context with hook-specific `additionalContext` as documented by the current release page;
- block with the legacy `decision: "block"` shape or exit `2`.

Current interception is deliberately incomplete. Official docs say it covers simple `Bash`, file edits through `apply_patch`, and MCP calls. It does not intercept every shell path under `unified_exec`, does not intercept `WebSearch`, and does not cover every other non-shell/non-MCP tool. Equivalent actions may be possible through a different supported path. Therefore `PreToolUse` is a guardrail, not a complete security boundary.

The official `openai/codex` issue tracker also records historical and version-specific coverage gaps. Those issues justify mandatory local coverage tests; they do not justify claiming broader enforcement than the current release docs.

### PermissionRequest schema and decisions

`PermissionRequest` runs only when Codex is about to ask for approval, such as shell escalation or managed-network approval. It does not run for actions that need no approval. It adds `turn_id`, `tool_name`, and `tool_input`; `tool_input.description` may be present but is not guaranteed.

Allow:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": { "behavior": "allow" }
  }
}
```

Deny:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": {
      "behavior": "deny",
      "message": "Blocked by Smart Router policy."
    }
  }
}
```

If multiple hooks decide, any deny wins; otherwise an allow bypasses the normal approval prompt. With no hook decision, Codex uses the normal approval flow. `updatedInput`, `updatedPermissions`, and `interrupt` are reserved and must not be returned. Smart Router should normally deny or defer; automatic allow conflicts with the project's `on-request` safety invariant and is out of scope for V0.3.

## C. Plugins

### Manifest and layout

Every plugin requires `.codex-plugin/plugin.json` as its entry point, and the official manifest reference treats `name` as the required stable plugin identifier. The official minimal skill plugin example uses:

```json
{
  "name": "codex-patch-smart-router",
  "version": "0.3.0",
  "description": "Deterministic prompt routing and safety guidance for Codex.",
  "skills": "./skills/"
}
```

Use a stable kebab-case `name`. `version`, `description`, component references, publisher metadata, and presentation metadata are optional in the general field guide, but a professional distributable manifest should include `version`, `description`, and the component path it actually ships.

Supported top-level metadata and component references are:

- identity: `name`, `version`, `description`;
- publisher/discovery: `author`, `homepage`, `repository`, `license`, `keywords`;
- components: `skills`, `mcpServers`, `apps`, `hooks`;
- install presentation: `interface` with display descriptions, developer, category, capabilities, URLs, starter prompts, color, icons, logo, and screenshots.

Manifest paths must start with `./`, resolve relative to the plugin root, and remain inside it. Only `plugin.json` belongs under `.codex-plugin/`; skills, hooks, MCP/app files, and assets remain at plugin root.

By default, Codex looks for plugin hooks at `hooks/hooks.json`. Current release documentation says a manifest `hooks` field can override that default with one path, multiple paths, inline hook objects, or arrays of inline objects. However, the current plugin-creator instructions in the official repository also warn that manifest validation may reject `hooks`. The conservative package therefore uses the default `hooks/hooks.json` location and omits the manifest field until the installed release accepts it in a local validation test. Hook commands receive `PLUGIN_ROOT` and writable `PLUGIN_DATA` environment variables.

Sources: [Build plugins](https://learn.chatgpt.com/docs/build-plugins), [Hooks](https://learn.chatgpt.com/docs/hooks).

### Local scaffolding and marketplace testing

Official docs expose `$plugin-creator` for scaffolding, but this phase did not invoke it because it would create runtime plugin files. Manual scaffolding is also supported.

For repository testing, the documented marketplace is `$REPO_ROOT/.agents/plugins/marketplace.json`, commonly pointing to plugin folders under `$REPO_ROOT/plugins/`. Marketplace entries need a name, a local or Git-backed source, installation/authentication policy, and category. `codex plugin marketplace add ./local-marketplace-root` can configure a local marketplace, but it mutates Codex state and is postponed to Phase 7 with explicit approval.

Local CLI 0.144.1 confirms:

- `codex plugin add PLUGIN@MARKETPLACE` installs from a configured marketplace snapshot;
- `codex plugin remove PLUGIN@MARKETPLACE` removes local config and cache state;
- `codex plugin marketplace add/list/upgrade/remove` manages marketplace sources.

The ChatGPT desktop app documentation requires a restart after adding or changing a local marketplace/plugin and recommends testing in a new task. For CLI testing, start a new Codex session after install or update. `/plugins` was not reachable in the isolated unauthenticated session and remains a Phase 7 verification item; the locally confirmed non-interactive install surface is `codex plugin add`. `/skills` and `/hooks` must likewise be verified in a new authenticated test session rather than assumed to hot reload.

Plugins can be enabled or disabled individually. The application stores that state in Codex config, so this is a later installation action, not a Phase 1 or repository-doc action.

### Official public submission

OpenAI currently accepts skills-only, MCP-only, and MCP-plus-skills plugins through the plugin submission portal. Later public submission requires, among other items:

- Apps Management write access and a verified developer or business identity;
- public listing metadata, support, website, privacy, and terms URLs;
- a final locally tested skill tree;
- realistic starter prompts;
- exactly five positive and three negative test cases;
- policy attestations and successful automated security/policy scanning;
- accurate disclosure of data handling and no unnecessary secrets, personal data, debug payloads, or internal identifiers.

No MCP server is needed for a skills-only Smart Router plugin. Public submission is Phase 8 work and must not shape V0.3 into an unnecessary network service.

Source: [Submit plugins](https://learn.chatgpt.com/docs/submit-plugins).

### Plugin-hook release risk

Current OpenAI docs explicitly state that enabled plugins can bundle hooks and that they use normal hook trust review. The official GitHub repository also contains historical issues reporting releases in which manifest-declared hooks were not loaded as documented. Because this phase prohibited installation and trust, plugin-hook execution was not locally proven on 0.144.1. The architecture may target plugin-bundled hooks, but Phase 6 and Phase 7 have a hard stop condition if they do not load and fire in the installed release.

Relevant official-repository evidence:

- [openai/codex issue 17331](https://github.com/openai/codex/issues/17331)
- [openai/codex issue 16430](https://github.com/openai/codex/issues/16430)

## D. Native routing limitations

### What a skill can and cannot do

A skill can supply instructions, deterministic scripts, references, and optional dependency metadata. The documented skill output surface does not expose a command that changes the already-active model, profile, sandbox, or approval policy for the current turn. Any selected model/profile/sandbox in a skill-produced routing decision is advisory context unless an outer launcher or client applies it before the thread starts.

### What UserPromptSubmit can and cannot do

`UserPromptSubmit` receives the active `model` as input, but its documented output can add developer context or block the prompt. It has no documented output field to replace `model`, select a profile, or mutate sandbox/approval settings. The same limitation applies to hook adapters generally: they can gate supported lifecycle events, not reconfigure the already-created thread.

### Advisory and enforced parts

Inside the normal Codex TUI:

- Advisory: category, complexity, recommended model, recommended profile, recommended sandbox, reasoning effort, evidence/context requirements, and warning text.
- Enforceable at prompt submission: block the entire submitted prompt on deterministic hard-safety or `CONFIG_ERROR` policy, or add bounded developer context.
- Enforceable on supported tool paths: deny or rewrite covered `Bash`, `apply_patch`, and MCP calls through `PreToolUse`.
- Enforceable at approval time: deny a covered approval request through `PermissionRequest`.
- Not fully enforceable: every shell path, web search, every built-in tool, equivalent actions through alternate paths, or dynamic model/profile/sandbox selection inside an existing TUI thread.

The Hook Adapter must describe itself as a layered guardrail, never as a complete policy enforcement boundary.

### What requires App Server or a fork

App Server `thread/start` accepts `model`, `approvalPolicy`, and `sandbox`, so a custom client can classify a prompt before creating a thread and apply those settings. It also exposes approvals and streamed events. This would create a separate orchestration client, not transparently alter each prompt inside the existing TUI. It substantially increases protocol, authentication, state, and approval-handling surface.

A Codex source fork could intercept the TUI submission path and alter per-turn behavior, but it would create the highest maintenance and security burden and risk diverging from official auth/sandbox behavior.

Postpone from V0.3:

- App Server or exec-server orchestration;
- Codex source fork or binary patch;
- aliases or wrappers named `codex`;
- dynamic model/profile/sandbox claims inside an active TUI;
- automatic PermissionRequest allows;
- global configuration mutation;
- MCP or network services that the deterministic local router does not need;
- claims of complete PreToolUse coverage.

## Final research conclusion

Choose **C. Skill packaged as plugin with hooks** as the target architecture, delivered incrementally: repository-local skill first, project-local hook validation second, plugin packaging only after hook schemas and coverage pass local tests.

Direct reason: skills provide the official reusable workflow surface, hooks provide the only official pre-prompt and supported pre-action gates in the normal Codex workflow, and plugins are the official distribution bundle for both. This target preserves the stock Codex binary and natural TUI. It does not solve dynamic model/profile/sandbox switching within an already-active TUI; that remains advisory unless a future App Server client or upstream Codex capability is adopted.

## Official sources

- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Hooks](https://learn.chatgpt.com/docs/hooks)
- [Build plugins](https://learn.chatgpt.com/docs/build-plugins)
- [Submit plugins](https://learn.chatgpt.com/docs/submit-plugins)
- [Codex App Server](https://learn.chatgpt.com/docs/app-server)
- [openai/codex configuration schema](https://github.com/openai/codex/blob/main/codex-rs/core/config.schema.json)
- [openai/codex plugin manifest reference](https://github.com/openai/codex/blob/main/codex-rs/skills/src/assets/samples/plugin-creator/references/plugin-json-spec.md)
- [openai/codex plugin-creator instructions](https://github.com/openai/codex/blob/main/codex-rs/skills/src/assets/samples/plugin-creator/SKILL.md)
- Local `codex --version`, `codex --help`, `codex plugin --help`, `codex plugin add --help`, `codex plugin remove --help`, `codex plugin marketplace --help`, and `codex features list` output checked on 2026-07-11.
