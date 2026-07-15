# Routed-mode rollback

Routed mode is opt-in and makes no global Codex changes, so rollback is simply
returning to the ordinary command.

## Immediate rollback

1. Exit the routed TUI or press Ctrl-C in manager-only mode.
2. Confirm the manager terminal has returned to the shell.
3. Start ordinary Codex:

```bash
codex
```

The normal command does not pass through this project.

## If a child remains

The launcher normally terminates the backend child it owns. If the terminal was
forcibly closed, inspect local processes and stop only the specific manager or
App Server instance whose command line contains this project's selected
localhost ports. Do not kill unrelated Codex sessions and do not modify the
installed binary or symlink.

## Desktop entry rollback

The repository desktop file is only a prepared launcher. Removing a separately
copied desktop/application entry does not affect `codex`. The tracked source is:

```text
desktop/Kodex OpenAI Custom Skill.desktop
```

## Event logs

Sanitized per-run JSONL files live under
`/tmp/codex-smart-router-<uid>/` unless `--event-log` supplied another path.
They contain prompt hashes, not prompt content. They can be deleted using the
normal operating-system cleanup flow after the manager stops.

## Code rollback

The semantic correction and App Server prototype are separate commits. Use a
normal `git revert` of the App Server prototype commit if code-level rollback is
required; do not reset or discard the semantic safety fix by accident. No
branch is pushed or merged by this phase.

## Do not use as rollback

Do not edit global `config.toml`, replace `codex`, change its symlink, create a
shell alias, recursively restart Codex from a hook, remove hooks, or loosen
sandbox/approval policy. Those actions are neither required nor supported.
