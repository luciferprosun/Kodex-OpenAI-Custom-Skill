# Tasks

Project: Codex Patch Smart Router.

Purpose: safely route Codex tasks to the appropriate local Codex CLI profile, model, sandbox, and settings from prompt type, complexity, and risk.

## V0 Checklist

- [x] Create repository structure
- [x] Add README
- [x] Add main project plan
- [x] Add security and privacy docs
- [x] Add Python package scaffold
- [x] Add deterministic classifier
- [x] Add risk and complexity assessment
- [x] Add profile loading and validation
- [x] Add TOML profile placeholders
- [x] Add router decision pipeline
- [x] Add safe launcher
- [x] Add privacy-safe logging
- [x] Add model audit command
- [x] Add JSON rules and eval set
- [x] Add pytest tests
- [x] Run full test suite
- [x] Run acceptance CLI commands

## V0.2 Knowledge Library Checklist

- [x] Add JSON Knowledge Library rules
- [x] Add weighted category scoring
- [x] Add hard safety overrides before normal classification
- [x] Add independent action danger dimension
- [x] Add `low`, `medium`, `high`, and `critical` risk levels
- [x] Add `eval_set_002.jsonl`
- [x] Add tests for eval set, hard overrides, action danger, execute gate, no raw prompt logging, config validation, and no V0 `danger-full-access`
- [x] Keep dry-run default and `--execute` gate
- [x] Keep model placeholders instead of inventing model names
- [x] Verify local `smart-codex` command usage
- [x] Document optional `codex-smart` wrapper without replacing the official `codex` binary

## Postponed V1 Items

- [ ] SDK integration
- [ ] App-server integration
- [ ] Local LLM judge
- [ ] Learned classifier
- [ ] Automatic profile installer
- [ ] Global Codex config mutation
- [ ] `danger-full-access`
- [ ] Web/MCP/tools config
- [ ] GitHub release workflow
