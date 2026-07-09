# Routing Examples

```bash
python -m smart_codex.cli "fix frontend bug"
```

Expected route:

- category: `normal_coding`
- profile: `standard`
- sandbox: `workspace-write`
- dry-run: `true`

```bash
python -m smart_codex.cli --explain "audit repo for secrets and sandbox risks"
```

Expected route:

- category: `security_audit`
- risk: `high`
- profile: `security`
- sandbox: `read-only`

```bash
python -m smart_codex.cli "fix bug; rm -rf /"
```

Expected route:

- prompt remains one argument
- risk: `high`
- profile: `security`
- sandbox: `read-only`
- dry-run unless `--execute` is passed

