# Installed App Server contract snapshot

The routed client is pinned to bindings generated locally from
`codex-cli 0.144.6` on 2026-07-19. The exact commands were:

```bash
codex app-server generate-json-schema --out /tmp/codex-app-server-schema
codex app-server generate-ts --out /tmp/codex-app-server-ts
codex app-server generate-json-schema --experimental --out /tmp/codex-app-server-schema-experimental
codex app-server generate-ts --experimental --out /tmp/codex-app-server-ts-experimental
```

The generated trees are reproducible build artifacts and are not vendored.
Checksums, file counts, and the comparison result are recorded in
`protocol_contract_0_144_6.json`. Canonical JSON hashes are authoritative for
semantic comparison because the generated V2 bundle can vary only in object
property order between identical invocations; raw hashes retain the exact
reviewed invocation.

## Version-to-version review

The retained `codex-cli 0.144.5` binary was used to regenerate the same stable
and experimental artifacts for a direct comparison.

- Stable JSON Schema: semantically identical after JSON object-key
  canonicalization.
- Experimental JSON Schema: semantically identical after JSON object-key
  canonicalization.
- Stable TypeScript: byte-identical across all 598 files.
- Experimental TypeScript: byte-identical across all 671 files.
- Methods and notifications added, removed, or shape-changed: none.
- Token-usage fields added, removed, or shape-changed: none.

The raw JSON diff consists only of property ordering. No protocol payload
field, required set, enum, method, notification, or type changed.

## Reviewed compatibility surface

- Lifecycle and discovery: `initialize`, `initialized`, `model/list`,
  `configRequirements/read`, `thread/start`, `thread/resume`, `turn/start`,
  `turn/steer`, `turn/interrupt`, `turn/started`, and `turn/completed`.
- Telemetry: `thread/tokenUsage/updated` exposes `last` and `total`
  breakdowns containing input, cached-input, output, reasoning-output, and
  total token counters. `modelContextWindow` remains nullable.
- Turn overrides: model, effort, sandbox, approval, approval reviewer,
  service tier, personality, and experimental collaboration settings retain
  their reviewed shapes.
- Compaction, model rerouting, model verification, approval, and user-input
  notifications retain their reviewed shapes.
- `currentTime/read` remains a transparent backend request. The proxy forwards
  it unchanged and gains no additional authority.
- The `permissions` profile remains mutually exclusive with structured
  `sandboxPolicy`; malformed combinations continue to fail closed.

The proxy changes only reviewed `turn/start` routing fields. It never fabricates
approval responses. WebSocket listeners remain bound to `127.0.0.1`.

Any installed version other than the exact string `codex-cli 0.144.6` is
rejected before routed mode opens. Updating that value requires a fresh schema
generation, semantic review, checksums, compatibility tests, and documentation
update.
