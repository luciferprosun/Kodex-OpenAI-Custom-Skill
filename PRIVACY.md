# Privacy

Project: Codex Patch Smart Router.

V0.2 stores privacy-safe routing metadata only.

Default log path:

```text
~/.codex-patch-smart-router/decisions.jsonl
```

Log fields:

- `timestamp`
- `prompt_hash`
- `prompt_redacted`
- `category`
- `complexity`
- `risk`
- `risk_level`
- `complexity_level`
- `action_danger`
- `evidence_requirement`
- `context_requirement`
- `repo_impact`
- `security_sensitivity`
- `destructiveness`
- `execution_scope`
- `selected_profile`
- `selected_model`
- `reasoning_effort`
- `sandbox_mode`
- `approval_policy`
- `confidence`
- `decision_reasons`
- `override_used`
- `dry_run`
- `warning`
- `source`

Prompt handling:

- Raw prompts are not stored by default.
- `prompt_hash` is a SHA-256 hash of the prompt.
- `prompt_redacted` is always `null` in V0.
- Knowledge Library scoring preserves the raw prompt only in memory.
- Full private prompts should not be published.
- Raw transcripts should remain private unless intentionally sanitized.

Disable logging:

```bash
python -m smart_codex.cli --no-log "write an email reply"
```
