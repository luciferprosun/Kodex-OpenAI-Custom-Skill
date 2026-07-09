# Project Main Plan - codex-auto-model-router

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

