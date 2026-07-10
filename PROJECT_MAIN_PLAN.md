# Project Main Plan - Codex Patch Smart Router

Codex Patch Smart Router is a safe local wrapper around official Codex CLI mechanisms. It routes prompts by task type, task weight, complexity, and risk before choosing the Codex profile, model, sandbox, approval policy, and config settings used for the next task.

It is not AIOA, AOIA-Core, portal work, website work, a Codex fork, an OpenAI internal patch, a jailbreak, or an uncontrolled auto-agent.

## Phase 0 - Repository Scaffold

Create a clean Python repository with routing code, profile placeholders, rules, examples, tests, and safety documentation.

## Phase 1 - V0 Wrapper

Implement a deterministic local CLI wrapper named `smart-codex` that:

- classifies prompts,
- estimates risk,
- estimates complexity,
- selects a conservative profile,
- builds a Codex CLI argument list,
- dry-runs by default,
- executes only with `--execute`,
- logs only privacy-safe metadata.

## Phase 2 - Model Audit

Add `smart-codex audit-models` to run `codex debug models`, parse available model data when possible, and write `rules/model_catalog.json` without storing secrets.

## Phase 3 - Validation

Add pytest coverage for classification, routing, risk, launcher safety, privacy logging, model audit parsing, config validation, and the eval set.

## Phase 4 - V0 Release Candidate

Run all tests, verify dry-run commands, document known limitations, and keep global Codex config untouched.

## Phase 5 - V0.2 Knowledge Library

Add a deterministic JSON-backed Knowledge Library under `rules/`:

- weighted category scoring,
- hard safety overrides before category trust,
- independent action danger,
- evidence and context requirements,
- low, medium, high, and critical risk levels,
- profile policy validation,
- fail-closed `CONFIG_ERROR` for malformed rules,
- eval coverage in `rules/eval_set_002.jsonl`.

V0.2 keeps all V0 boundaries: dry-run by default, `--execute` required for launch, prompt passed as one argv element, no raw prompt logging, no `shell=True`, no `danger-full-access`, no invented tools or model names, no SDK/app-server integration, and no global Codex config mutation.

## Postponed V1 Items

- SDK integration.
- App-server integration.
- Local LLM judge.
- Learned classifier.
- Automatic profile installer.
- Global Codex config mutation.
- `danger-full-access`.
- Web, MCP, and tool configuration.
- GitHub release workflow.
