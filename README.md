# Codex Patch Smart Router

Codex Patch Smart Router is a safe local router for Codex that detects prompt type, task weight, complexity, and risk, then selects the appropriate Codex model, profile, sandbox, and settings before launching a Codex task.

This project builds a safe local Python CLI wrapper named `smart-codex` around the official `codex` CLI. V0 classifies a prompt, estimates risk and complexity, selects a conservative profile, explains the route, builds the planned Codex command, and logs only privacy-safe metadata.

## What It Is

- A deterministic local router for Codex CLI usage.
- A dry-run-first safety wrapper.
- A profile selector for task categories such as coding, research, writing, math, security, and repo operations.
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

For tests, install pytest if it is not already available:

```bash
python -m pip install pytest
```

## Examples

Dry-run is the default:

```bash
python -m smart_codex.cli "fix frontend bug"
```

Execute Codex only when explicitly requested:

```bash
python -m smart_codex.cli --execute "fix frontend bug"
```

Explain routing reasons:

```bash
python -m smart_codex.cli --explain "audit this repo for secrets and sandbox risks"
```

Override profile, model, sandbox, directory, approval policy, or config:

```bash
python -m smart_codex.cli --profile deep --model REPLACE_WITH_MODEL --sandbox workspace-write --cd /path/to/repo --config model_reasoning_effort=high "refactor this module"
```

Disable metadata logging:

```bash
python -m smart_codex.cli --no-log "write an email reply"
```

Audit local Codex models:

```bash
python -m smart_codex.cli audit-models
```

## Safety Model

- `smart-codex` never uses `shell=True`.
- Commands are built as argument lists.
- Prompts are passed as one argument.
- V0 rejects `danger-full-access`.
- High-risk tasks route to the `security` profile with `read-only` sandbox and `on-request` approval.
- Logs store prompt hashes and routing metadata only.
- Raw prompts are not stored by default.
- Human approval remains required for Codex actions.

## Limitations

- Classification is deterministic keyword and regex scoring, not an LLM judge.
- Model names are placeholders until the local machine runs `codex debug models`.
- V0 does not install profiles into global Codex config.
- V0 does not call SDKs, app-server, or remote tools.
