# Codex Patch Smart Router

Codex Patch Smart Router is a safe local router for Codex that detects prompt type, task weight, complexity, and risk, then selects the appropriate Codex model, profile, sandbox, and settings before launching a Codex task.

This project builds a safe local Python CLI wrapper named `smart-codex` around the official `codex` CLI. V0.2 classifies a prompt with a deterministic Knowledge Library, estimates risk and complexity, scores action danger independently, selects a conservative profile, explains the route, builds the planned Codex command, and logs only privacy-safe metadata.

## What It Is

- A deterministic local router for Codex CLI usage.
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

## Installation

From the repository root:

```bash
python -m pip install -e .
```

After local installation, use the router command directly:

```bash
smart-codex --explain "fix frontend bug"
```

An optional local wrapper can be used for daily work:

```bash
codex-smart --explain "audit repo for secrets"
```

For local patched-Codex workflow, `$HOME/.local/bin/codex` may be a router wrapper that delegates prompt tasks to `smart-codex`. The original Codex entry point is preserved as `$HOME/.local/bin/codex-real`, and the router uses `codex-real` internally for `--execute`.

```bash
codex --explain "fix frontend bug"
codex --execute "safe small task"
codex-real --help
```

Do not delete or mutate the official Codex package. The local `codex` wrapper is only a PATH-level router entry point.

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
