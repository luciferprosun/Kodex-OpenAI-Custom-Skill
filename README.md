# Kodex OpenAI Custom Skill

**Independent community project for OpenAI Codex. Not affiliated with, maintained by, or endorsed by OpenAI.**

Kodex OpenAI Custom Skill combines a Smart Prompt Check, Task Router, and Model Configuration Selector for Codex repository work. Its deterministic Router Core classifies task weight, category, complexity, risk, action danger, context, and evidence requirements, then recommends a conservative profile, sandbox, and approval policy.

The repository-local Codex custom skill invokes the tested Router Core through a stdin-only adapter and renders a `SMART ROUTER DECISION` before task work. Phases through 5.3 are complete, including the calibrated dynamic model/effort policy, its 180-case evaluation, and a 12-turn routed-TUI soak. Phase 6 plugin packaging is next and has not started.

Skill and hook recommendations remain advisory. The opt-in App Server manager
adds a separate localhost layer that applies actual per-turn model, effort,
sandbox, and approval overrides before forwarding `turn/start`. Hooks preserve
normal human approval and remain defense-in-depth. Model availability,
visibility, modalities, upgrade targets, and supported efforts are refreshed
from live App Server metadata at startup.

The standalone `smart-codex` CLI remains available for explicit dry-run routing and approved launch workflows.

The internal Python package, import paths, rules, and standalone commands intentionally retain their Codex Patch Smart Router identifiers for compatibility.

## What It Is

- A deterministic local router for Codex CLI usage.
- A repository-local Codex custom skill under `.agents/skills/`.
- A Smart Prompt Check and Task Router for repository work.
- A Model Configuration Selector that recommends settings without claiming they were applied.
- A dry-run-first safety wrapper.
- A profile selector for task categories such as coding, research, writing, math, security, and repo operations.
- A JSON-backed Knowledge Library in `rules/` for prompt weights, hard safety triggers, action danger, complexity, context, evidence, tie breakers, and profile policy.
- A privacy-safe routing metadata logger.
- Disabled-by-default, append-only local Codex run telemetry with operator-authored outcomes.
- An isolated, opt-in App Server proxy for actual per-turn model rotation in the original Codex TUI.

## What It Is Not

- Not a fork of Codex.
- Not a modification of Codex internals.
- Not a jailbreak.
- Not an uncontrolled auto-agent.
- Not a browser automation hack.
- Not a replacement for human approval.
- Not a globally mandatory App Server replacement.
- Not an AIOA, AOIA-Core, LSC, grant, or website portal integration.
- Not a system that stores private prompts or touches secrets.
- Not an OpenAI internal patch.
- Not an official OpenAI project or an OpenAI-endorsed integration.

## Codex Custom Skill

Start Codex from the repository root. The skill can be invoked explicitly with:

```text
$codex-patch-smart-router Analyze only: fix a frontend bug and check for exposed API keys.
```

Implicit selection is model-selected and advisory, not a guaranteed security interceptor. The deterministic adapter reads the complete task through standard input and never calls the standalone launcher:

```bash
./.venv/bin/python .agents/skills/codex-patch-smart-router/scripts/route_prompt.py --stdin
```

## Project-Local Hooks

Phase 5 adds repository-local `UserPromptSubmit`, `PreToolUse`, and
`PermissionRequest` adapters in `.codex/`. Start Codex from this repository and
open `/hooks` to review the exact definitions. Trust must be granted manually;
it is not bypassed or stored in the repository.

Until that review and a fresh trusted-session test are complete, the status is:

**IMPLEMENTATION GREEN — MANUAL HOOK TRUST ACCEPTANCE PENDING**

The Smart Router never auto-allows a permission request. `PreToolUse` is a
guardrail rather than a complete enforcement boundary and does not claim to
intercept every Codex tool. See
[`docs/native-skill/PROJECT_LOCAL_HOOKS.md`](docs/native-skill/PROJECT_LOCAL_HOOKS.md)
for architecture, privacy guarantees, exact definitions, known gaps, and the
manual acceptance procedure.

## Opt-in App Server routed TUI

Actual per-turn model and reasoning-effort rotation is available through the
isolated localhost App Server prototype:

```bash
./scripts/start-routed-codex
```

This opens the original installed Codex TUI through `codex --remote`. Ordinary
`codex` remains the explicit OFF mode. The launcher does not replace the
installed command, edit global configuration, or auto-approve actions.
WebSocket App Server transport is experimental and unsupported.

See [dynamic routing](docs/app-server/DYNAMIC_MODEL_ROUTING.md), [local routed
TUI](docs/app-server/LOCAL_ROUTED_TUI.md), [security
model](docs/app-server/SECURITY_MODEL.md), and
[rollback](docs/app-server/ROLLBACK.md). Phase 5.3 policy details are in [model
selection policy](docs/app-server/MODEL_SELECTION_POLICY.md), [calibration
evaluation](docs/app-server/MODEL_CALIBRATION_EVAL.md), [fallbacks](docs/app-server/MODEL_FALLBACKS.md),
and [drift/refresh](docs/app-server/MODEL_DRIFT_AND_REFRESH.md). The RC2
candidate separates maximum single-agent reasoning (`max`) from approved
subagent orchestration (`ultra`); see [Ultra admission policy
1A](docs/app-server/ULTRA_ADMISSION_POLICY_1A.md). The slash-command and trusted
approval UI remain a later milestone.

## Installation

From the repository root:

```bash
python -m pip install -e .
```

After local installation, use the router command directly:

```bash
smart-codex --explain "fix frontend bug"
```

An optional standalone command can be used for daily work:

```bash
codex-smart --explain "audit repo for secrets"
```

Do not replace or mutate the official `codex` executable.

For tests, install pytest if it is not already available:

```bash
python -m pip install pytest
```

## Examples

Dry-run is the default:

```bash
smart-codex --explain "fix frontend bug"
```

Execute Codex only when explicitly requested:

```bash
smart-codex --execute "fix frontend bug"
```

Explain routing reasons:

```bash
smart-codex --explain "audit this repo for secrets and sandbox risks"
```

Override profile, model, sandbox, directory, approval policy, or config:

```bash
python -m smart_codex.cli --profile deep --model REPLACE_WITH_MODEL --sandbox workspace-write --cd /path/to/repo --config model_reasoning_effort=high "refactor this module"
```

Disable metadata logging:

```bash
smart-codex --no-log "write an email reply"
```

Audit local Codex models:

```bash
smart-codex audit-models
```

## Opt-in local telemetry

Local run telemetry is disabled by default. Enabling it is an explicit operator
action:

```bash
smart-codex telemetry enable
smart-codex telemetry status
```

The module stores only validated numeric and categorical metadata in bounded,
append-only local JSONL. It does not store prompts, responses, source code,
tool arguments or output, credentials, or private conversation content. It
does not change routing or authorize execution. Outcomes are recorded later by
the operator as separate hash-linked events:

```bash
smart-codex outcome <run-id> accepted
smart-codex telemetry summary --by-model
```

Render the read-only, metadata-only hackathon demo view without starting a
server or writing derived files:

```bash
./scripts/smart-codex telemetry dashboard
```

The dashboard preserves null as unavailable, keeps human outcomes separate
from advisory verification, withholds private linkage fields, and visibly
quarantines known-defective semantic classifier labels. See [Local Telemetry
Demo View 1A](docs/LOCAL_TELEMETRY_DEMO_VIEW_1A.md) for its panels, privacy
allowlist, demo sequence, and read-only guarantees.

The current deterministic classifier policy and its compatibility boundaries
are documented in [Classifier Semantic Repair
1A/1B](docs/CLASSIFIER_SEMANTIC_REPAIR_1A.md). The dashboard continues to
quarantine affected semantic labels until they have independent validation;
newer policy provenance, including `v0.3`, does not bypass that quarantine.

See [Local Codex Telemetry 2B-1](docs/LOCAL_CODEX_TELEMETRY_2B.md) for the
schema, privacy model, disk limits, supported event surfaces, missing-value
rules, and disable procedure. The opt-in external-storage and dual-window
foundation is documented in [Safe Routing and Telemetry Foundation
2B-2](docs/TELEMETRY_RESEARCH_LOOP_2B2.md). No learning engine or policy
candidate path is connected; the checked-in router remains the only authority.

## Knowledge Library

V0.2 loads deterministic rules from `rules/*.json`. Missing or malformed Knowledge Library files fail closed with `CONFIG_ERROR`; the router does not build or launch a Codex command in that state.

The main eval file is `rules/eval_set_002.jsonl`. Add one JSON object per line with `prompt`, `expected_category`, `expected_profile`, `expected_risk`, `expected_complexity`, and `reason`, then run:

```bash
./.venv/bin/pytest tests/test_eval_set_002.py
```

The App Server calibration set is `rules/model_selection_eval_001.jsonl` with
180 acceptable-route cases. Run it with:

```bash
./.venv/bin/pytest tests/test_model_selection_calibration_eval.py
```

### Model capability research 1A

The dated [model-selection research handbook](docs/model-research/README.md) and
machine-readable [research knowledge pack](knowledge/model-selection/README.md)
separate model identity from reasoning effort, agent count, tool access,
context, pricing, and action authority. They are evidence artifacts and are not
wired into runtime behavior by this research mission. Unassessed domains fail
closed as `no_route`.

## Safety Model

- `smart-codex` never uses `shell=True`.
- Commands are built as argument lists.
- The legacy standalone execute path passes its prompt as one argument; routed TUI prompts stay inside App Server frames and never enter launcher argv.
- Local `codex` wrapper execution calls the preserved `codex-real` entry point to avoid recursion.
- V0 rejects `danger-full-access`.
- Risk levels are `low`, `medium`, `high`, and `critical`.
- High-risk and critical-risk routes use `read-only` sandbox and `on-request` approval.
- Hard safety overrides run before normal classification for secrets, force push, production deploy, release publishing, destructive database/file operations, and pipe-to-shell patterns.
- Logs store prompt hashes and routing metadata only.
- Raw prompts are not stored by default.
- Human approval remains required for Codex actions.
- `--execute` is required for real Codex launch; routing never implies execute-now.

## Limitations

- Classification is deterministic keyword and regex scoring, not an LLM judge.
- Legacy profile model names remain placeholders; App Server routed mode uses
  the live startup `model/list` response instead.
- Profile TOML files intentionally keep model placeholders in the public repo.
- V0 does not install profiles into global Codex config.
- App Server routed mode is isolated, localhost-only, experimental, and opt-in.
- Installed App Server `model/list` currently omits context-window values;
  reviewed exact-model context classes and conservative future-model defaults
  cover that gap without overriding live availability or capability fields.
- Project-local hooks cover only their configured, release-supported event and
  tool paths; existing sandboxing and human approval remain authoritative.
