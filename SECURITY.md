# Security

Project: Codex Patch Smart Router.

V0 is a safe local wrapper around official Codex CLI mechanisms.

Security boundaries:

- Do not store secrets.
- Do not read, copy, print, or modify `~/.codex/auth.json`.
- Do not read, copy, print, or modify API keys, tokens, SSH private keys, `.env` files, private logs, or private repository secrets.
- Do not bypass Codex approvals or sandbox behavior.
- Do not behave as a Codex fork, OpenAI internal patch, jailbreak, portal integration, website integration, AIOA integration, or uncontrolled auto-agent.
- Do not use `shell=True`.
- Do not use `danger-full-access` in V0 runtime profiles.
- Do not run destructive execution automatically.
- Security profiles default to `read-only`.
- High-risk actions require human confirmation through Codex approval behavior.

High-risk prompts containing secrets, credentials, sandbox, malware, exploit, destructive file operations, or permission changes route to the `security` profile with:

- `sandbox_mode = "read-only"`
- `approval_policy = "on-request"`
