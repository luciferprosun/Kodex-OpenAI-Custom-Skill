# Kodex OpenAI Custom Skill

**Independent community project for OpenAI Codex. Not affiliated with, maintained by, or endorsed by OpenAI.**

Kodex OpenAI Custom Skill combines a Smart Prompt Check, Task Router, and Model Configuration Selector for Codex repository work. Its deterministic Router Core classifies task weight, category, complexity, risk, action danger, context, and evidence requirements, then recommends a conservative profile, sandbox, and approval policy.

The current repository-local Codex custom skill is advisory: it invokes the tested Router Core through a stdin-only adapter and renders a `SMART ROUTER DECISION` before task work. It does not automatically change the active model, profile, sandbox, or approval policy. Project-local lifecycle hooks are planned for Phase 5 to add deterministic pre-execution gates within their officially supported coverage.

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

## What It Is Not

- Not a fork of Codex.
- Not a modification of Codex internals.
- Not a jailbreak.
- Not an uncontrolled auto-agent.
- Not a browser automation hack.
- Not a replacement for human approval.
- Not an SDK or app-server integration in V0.
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

## Knowledge Library

V0.2 loads deterministic rules from `rules/*.json`. Missing or malformed Knowledge Library files fail closed with `CONFIG_ERROR`; the router does not build or launch a Codex command in that state.

The main eval file is `rules/eval_set_002.jsonl`. Add one JSON object per line with `prompt`, `expected_category`, `expected_profile`, `expected_risk`, `expected_complexity`, and `reason`, then run:

```bash
./.venv/bin/pytest tests/test_eval_set_002.py
```

## Safety Model

- `smart-codex` never uses `shell=True`.
- Commands are built as argument lists.
- Prompts are passed as one argument.
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
- Model names are placeholders until the local machine runs `codex debug models`.
- Profile TOML files intentionally keep model placeholders in the public repo.
- V0 does not install profiles into global Codex config.
- V0 does not call SDKs, app-server, or remote tools.
