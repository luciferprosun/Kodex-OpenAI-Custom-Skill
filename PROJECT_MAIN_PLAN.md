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

Local production usage is `smart-codex --explain "task"` first, then `smart-codex --execute "safe task"` only after reviewing the route. For patched-Codex workflow, the local PATH-level `codex` wrapper may delegate prompt tasks to `smart-codex`, while the original Codex entry point remains available as `codex-real` for router execution and emergency bypass.

## Phase 5.2 - Opt-in App Server Routing

Implemented on a separate opt-in path without changing the historical V0.2
wrapper. A localhost JSON-RPC proxy discovers live App Server models, preserves
approval traffic and streaming notifications, and applies actual supported
per-turn model/effort/sandbox/approval fields for the original Codex TUI.

## Phase 5.3 - Dynamic Policy Calibration

Implemented as a deterministic, capability-aware, dynamically refreshed policy:

- hard live capability filtering before model scoring;
- Sol/Terra/Luna/Spark task boundaries and GPT-5.5/legacy fallbacks;
- independent live-supported effort selection;
- explainable candidate scores and controlled model-switch hysteresis;
- 180 curated acceptable-route cases plus drift, fallback, privacy, and safety
  regression coverage;
- no safety-rule duplication, global configuration mutation, binary change,
  prompt persistence, or automatic approval.

## Phase 6 - Plugin Packaging

Not started. Phase 5.3 is accepted; package the opt-in surface next without
making routed mode globally mandatory.

## Postponed V1 Items

- SDK integration.
- Local LLM judge.
- Learned classifier.
- Automatic profile installer.
- Global Codex config mutation.
- `danger-full-access`.
- Web, MCP, and tool configuration.
- GitHub release workflow.
