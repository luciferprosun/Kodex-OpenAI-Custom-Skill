# Native Skill and Plugin Phase Plan

Phase 1 ends with documentation only. Every later phase must start from a clean worktree, run the existing suite, and use a separate commit. No phase may rename or replace the real `codex` command.

## Phase 2: Skill scaffold

### Files changed

- `.agents/skills/codex-patch-smart-router/SKILL.md`
- `.agents/skills/codex-patch-smart-router/references/routing-policy.md`
- focused static tests if needed to validate frontmatter and forbidden claims

Do not add scripts, hooks, plugin manifests, assets, or `agents/openai.yaml` yet.

### Acceptance criteria

- `SKILL.md` contains valid YAML frontmatter with only required `name` and `description` unless an official need for another field is demonstrated.
- Description has clear positive and negative trigger boundaries.
- Instructions distinguish advisory routing from enforcement.
- Instructions preserve all current safety and privacy invariants.
- The reference file describes the existing Router Core rather than restating JSON rules.
- No model, tool, or capability name is invented.

### Tests

- Run all existing `pytest` tests.
- Add a static test that checks the skill name, required frontmatter, and absence of claims such as "changes the active model" or "intercepts all tools."
- Inspect `git diff --check`.
- If an authenticated disposable/new local session is available without exposing credentials, confirm the skill appears in `/skills`; otherwise defer that runtime check to Phase 4 and record it.

### Stop conditions

- Skill discovery requires global config mutation.
- The skill conflicts with another discovered skill of the same name.
- Official docs no longer recognize `.agents/skills`.
- Any existing test fails.

### Rollback

Revert the Phase 2 commit or remove only the two repository-local skill files. Restart/new session if Codex cached discovery. No global state needs restoration.

## Phase 3: Skill adapter implementation

### Files changed

- `.agents/skills/codex-patch-smart-router/scripts/route_prompt.py`
- `tests/test_skill_adapter.py`
- minimal updates to `SKILL.md` and `routing-policy.md` for the settled input/output contract

Do not alter the Router Core unless a separately reviewed defect is proven. Do not add hooks.

### Acceptance criteria

- Adapter imports or safely invokes `smart_codex.router.route_prompt` from the repository.
- Prompt is passed as one string through structured stdin or one argv element.
- Adapter contains no scoring terms, profile map, hard override, or duplicate rules.
- Output is stable JSON with bounded routing fields and an explicit `advisory: true` marker for settings that cannot be applied natively.
- `ConfigError` returns a sanitized `CONFIG_ERROR` and no launch/execution instruction.
- Adapter never imports or invokes `launcher.py` and cannot honor `--execute`.
- No raw prompt is logged or returned in decision metadata.

### Tests

- Existing 66-test suite.
- Adapter parity against representative cases from both eval sets.
- Prompts containing spaces, quotes, newlines, semicolons, pipes, substitutions, and shell metacharacters remain one string and are never executed.
- Missing/malformed rules produce `CONFIG_ERROR`.
- Output contains `prompt_hash` but not the raw prompt.
- Static checks reject `shell=True`, `shlex.split(prompt)`, `danger-full-access`, and imports from the launcher.

### Stop conditions

- Adapter needs a second copy of the Knowledge Library for repo-local operation.
- Adapter needs a new runtime dependency or global install.
- Core and adapter decisions diverge.
- Any input can trigger Codex execution.
- Any safety regression or raw prompt leak appears.

### Rollback

Revert the Phase 3 commit. The instruction-only Phase 2 skill remains usable, or revert Phase 2 as well for complete removal.

## Phase 4: Skill tests

### Files changed

- `tests/test_skill_contract.py`
- `tests/fixtures/skill_prompts.jsonl` only if existing eval fixtures cannot express activation expectations
- documentation corrections discovered by runtime testing

No hook or plugin file is created.

### Acceptance criteria

- `/skills` shows exactly one `codex-patch-smart-router` entry in a new repository session.
- `$codex-patch-smart-router` invokes the expected workflow.
- Positive prompts activate the skill explicitly and produce core-parity decisions.
- Negative prompts demonstrate that unrelated work does not need the skill.
- Implicit activation, if enabled, is conservative and traceable to `description`.
- Skill changes are detected automatically or after the documented restart fallback.
- No user/global skill or config file is modified.

### Tests

- Full automated suite.
- Explicit invocation matrix: benign coding, security audit, secret-touching request, destructive Git request, unknown prompt, and malformed configuration.
- Negative activation matrix for unrelated writing/general chat.
- New-session discovery from repository root and one nested directory.
- Verify no prompt content appears in project logs.

### Stop conditions

- Implicit activation is broad or unpredictable.
- Explicit invocation cannot reach the adapter reliably.
- Discovery creates duplicate names.
- Codex requires global installation to use the repo-local skill.
- Runtime output suggests active settings were changed when they were not.

### Rollback

Disable implicit invocation in a later optional `agents/openai.yaml` only if that file is justified; otherwise narrow the description. If behavior remains unreliable, revert Phase 4 corrections and keep explicit invocation only. Revert Phase 2/3 to remove the skill entirely.

## Phase 5: Project-local hooks

### Files changed

- `.codex/hooks.json`
- `.codex/hooks/user_prompt_submit.py`
- `.codex/hooks/pre_tool_use.py`
- `.codex/hooks/permission_request.py`
- `tests/test_user_prompt_submit_hook.py`
- `tests/test_pre_tool_use_hook.py`
- `tests/test_permission_request_hook.py`
- hook fixtures containing synthetic prompts/tool inputs only

### Acceptance criteria

- Each adapter parses only its documented event schema and calls the canonical Router Core.
- `UserPromptSubmit` returns bounded `additionalContext` for advisory routes and a documented block for hard-safety/`CONFIG_ERROR` routes.
- `PreToolUse` denies tested destructive calls on every locally confirmed supported path.
- `PermissionRequest` denies or defers; it never automatically allows in V0.3.
- Hook output and stderr never contain raw prompts or secret values.
- Explicit short timeouts are configured.
- `/hooks` shows the project source and requires manual trust of the exact definitions.
- Documentation lists every uncovered tool path observed in 0.144.1.

### Tests

- Unit tests feed exact JSON fixtures on stdin and validate stdout/stderr/exit status.
- Exit 0/no-output, valid context, structured block, exit 2 block, malformed JSON, missing fields, `ConfigError`, exceptions, and timeout behavior.
- TUI tests for `UserPromptSubmit`, simple Bash, `apply_patch`, MCP if a harmless local test server already exists, and `PermissionRequest`.
- Negative coverage tests show that WebSearch and any unhooked paths are not claimed as protected.
- Full existing core/eval suite.

### Stop conditions

- A hard-safety or `CONFIG_ERROR` route proceeds because the adapter process failed.
- Installed Codex behavior differs from the documented schema and cannot be handled conservatively.
- `PreToolUse` misses a path that the product claims to enforce.
- Trust can be bypassed or is granted automatically.
- Hook requires transcript or secret access.
- Any automatic allow weakens normal approval.

### Rollback

Disable the hooks through `/hooks` and revert the Phase 5 commit. Start a new session and confirm `/hooks` no longer lists the project adapters. Skill behavior remains available without hook enforcement.

## Phase 6: Plugin packaging

### Files changed

- `packaging/codex-patch-smart-router/.codex-plugin/plugin.json`
- `packaging/codex-patch-smart-router/hooks/hooks.json`
- a deterministic packaging script under `tools/` if a self-contained build is required
- packaging validation tests
- `.gitignore` entry for generated plugin artifacts if needed

Generated artifacts may contain copies of canonical skill/core files, but independently edited duplicates must not be committed.

### Acceptance criteria

- Manifest name is stable kebab-case and paths are `./`-prefixed, root-relative, and contained in the plugin.
- Manifest omits `hooks` initially and uses the default `hooks/hooks.json` path; a custom field is added only after local validation.
- Package includes exactly the proven skill and hook adapters.
- Plugin hook commands resolve through `PLUGIN_ROOT`; V0.3 does not persist data in `PLUGIN_DATA`.
- A self-contained release artifact is generated from canonical sources and fails validation on checksum/content drift.
- No lifecycle installation script, dependency installer, secret, local absolute path, model placeholder, or private log is packaged.
- Plugin-hook loading remains labeled unverified until Phase 7 proves it.

### Tests

- Parse and validate `plugin.json` and `hooks.json`.
- Build twice and compare deterministic file lists/checksums.
- Run core, skill-adapter, and hook-adapter tests from the staged artifact where technically possible.
- Scan artifact text for forbidden paths, auth filenames, `.env`, raw test secrets, `danger-full-access`, and aliases named `codex`.
- Full repository suite.

### Stop conditions

- Packaging requires hand-maintained copies of Router Core or rules.
- Manifest validation rejects hooks or required paths.
- Plugin cannot be self-contained without an unreviewed installer.
- Artifact includes private/local machine state.
- Official plugin docs or local CLI no longer support the chosen manifest surface.

### Rollback

Delete generated artifacts and revert the Phase 6 packaging commit. Repository-local skill and project hooks remain independently testable.

## Phase 7: Local installation tests

This phase requires explicit authorization because marketplace/plugin commands mutate local Codex state and hook trust requires user review.

### Files changed

- `$REPO_ROOT/.agents/plugins/marketplace.json` for a repository-scoped test marketplace, if chosen
- test report under `docs/native-skill/`

Do not hand-edit `~/.codex/config.toml`. Any local cache/config changes must come from supported Codex plugin commands or UI and must be removed during rollback.

### Acceptance criteria

- Local marketplace is visible through `codex plugin marketplace list`; `/plugins` availability is checked and recorded rather than assumed.
- Plugin installs from the intended marketplace and appears once.
- New session shows the bundled skill in `/skills` and hooks in `/hooks`.
- Plugin hooks remain disabled/skipped until explicitly reviewed and trusted.
- After trust, all three adapters fire with the same results as project-local tests.
- Disable prevents activation; remove clears installed config/cache state.
- No real `codex` binary, alias, auth file, or unrelated config is changed.

### Tests

- Add/list/install/new-session/trust/functional/disable/remove sequence.
- Compare plugin results to core and project-local hook fixtures.
- Update one hook definition and confirm trust is invalidated.
- Confirm uninstall and marketplace removal leave stock Codex functional (`codex --version`, `codex --help`).
- Run the full repository suite before and after installation testing.

### Stop conditions

- Bundled hooks do not load on 0.144.1.
- Hook trust behavior differs from current documentation.
- Install modifies unexpected global files or credentials.
- Plugin cannot be fully disabled/removed.
- Installed copy and source tree produce different decisions.

### Rollback

Disable plugin, remove it with the verified `codex plugin remove` command, remove the test marketplace with the verified marketplace command, start a new session, and verify stock Codex help/version. Revert the repo marketplace commit if one was created.

## Phase 8: GitHub and public presentation

### Files changed

- `README.md`
- `SECURITY.md`
- `PRIVACY.md`
- public architecture and usage docs
- production-ready plugin listing metadata/assets only when available
- five positive and three negative submission test cases
- release notes and public package checksums

Do not submit or publish without separate explicit authorization.

### Acceptance criteria

- Public wording distinguishes advisory routing from hook enforcement and lists coverage limits.
- Installation and rollback are reproducible and use official plugin surfaces.
- Repository contains no local absolute paths, credentials, private logs, raw prompts, fake models, or unverified capability claims.
- Publisher identity, website, support, privacy, terms, and license material are consistent.
- Submission bundle is the same tree tested locally.
- Exactly five positive and three negative reviewer-ready cases exist.

### Tests

- Fresh-checkout documentation and package build.
- Link and manifest validation.
- Secret and private-path scan.
- Full automated suite and eval sets.
- Re-run Phase 7 install/remove flow from the release candidate.
- Independent review of safety claims against the official source matrix.

### Stop conditions

- Any public claim exceeds verified Codex behavior.
- Submission material exposes secrets, personal data, or internal paths.
- Release artifact differs from the locally tested artifact.
- Legal/publisher/support fields are incomplete.
- OpenAI submission requirements have changed and are not re-audited.

### Rollback

Do not publish. Revert presentation-only commits or prepare a corrected release candidate. If already submitted as a draft, withdraw/update it through the official portal only after explicit authorization; local Codex remains unchanged.

## Exact Phase 2 recommendation

Create the smallest repository-local, instruction-only scaffold:

```text
.agents/skills/codex-patch-smart-router/
|-- SKILL.md
`-- references/
    `-- routing-policy.md
```

Use explicit invocation first, do not add `agents/openai.yaml`, do not add any hook/plugin file, and add a static contract test that rejects claims of active model/profile/sandbox mutation or full tool interception. Commit Phase 2 separately only after all existing tests remain green.
