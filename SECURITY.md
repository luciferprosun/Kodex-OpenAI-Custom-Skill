# Security

Project: Codex Patch Smart Router.

V0.2 is a safe local wrapper around official Codex CLI mechanisms.

Security boundaries:

- Do not store secrets.
- Do not read, copy, print, or modify `~/.codex/auth.json`.
- Do not read, copy, print, or modify API keys, tokens, SSH private keys, `.env` files, private logs, or private repository secrets.
- Do not bypass Codex approvals or sandbox behavior.
- Do not behave as a Codex fork, OpenAI internal patch, jailbreak, portal integration, website integration, AIOA integration, or uncontrolled auto-agent.
- Do not use `shell=True`.
- Do not use `danger-full-access` in V0 runtime profiles.
- Do not run destructive execution automatically.
- Do not let routing imply `execute now`; only `launcher.py` honors execution, and only when `--execute` is explicitly passed.
- Do not overwrite or replace the official `codex` binary; use `smart-codex` or the optional `codex-smart` wrapper.
- Security profiles default to `read-only`.
- High-risk actions require human confirmation through Codex approval behavior.

Hard safety overrides run before normal category scoring. High-risk and critical-risk prompts containing secrets, credentials, force push, production deployment, release publishing, sandbox escape, malware, exploit, destructive file/database operations, pipe-to-shell patterns, or permission changes route conservatively with:

- `sandbox_mode = "read-only"`
- `approval_policy = "on-request"`

Knowledge Library config errors are fail-closed `CONFIG_ERROR` states. A malformed rule file must not silently fall back to a weaker route or launch Codex.
