# Installed App Server contract snapshot

The routed client is pinned to bindings generated locally from
`codex-cli 0.144.5` on 2026-07-19. The exact commands were:

```bash
codex app-server generate-json-schema --out /tmp/codex-app-server-schema
codex app-server generate-ts --out /tmp/codex-app-server-ts
codex app-server generate-json-schema --experimental --out /tmp/codex-app-server-schema-experimental
codex app-server generate-ts --experimental --out /tmp/codex-app-server-ts-experimental
```

The large generated bundles are reproducible build artifacts and are not
vendored. Their combined-bundle SHA-256 values are recorded in
`protocol_contract_0_144_5.json`.

## Reviewed compatibility surface

- Lifecycle and discovery: `initialize`, `initialized`, `model/list`,
  `configRequirements/read`, `thread/start`, `thread/resume`, `turn/start`,
  `turn/steer`, `turn/interrupt`, `turn/started`, and `turn/completed`.
- Telemetry: `thread/tokenUsage/updated` still exposes `last` and `total`
  breakdowns containing input, cached-input, output, reasoning-output, and
  total token counters. `modelContextWindow` remains nullable.
- Turn overrides: model, effort, sandbox, approval, approval reviewer, and the
  existing experimental collaboration settings retain the reviewed shapes.
- Approval requests remain transparent. Version 0.144.5 adds
  `currentTime/read`; it is forwarded unchanged like every other backend
  request and grants the router no new authority.
- The `permissions` profile remains mutually exclusive with structured
  `sandboxPolicy`; malformed combinations continue to fail closed.

The proxy changes only reviewed `turn/start` routing fields. It never fabricates
approval responses. WebSocket listeners remain bound to `127.0.0.1`.

Any installed version other than the exact string `codex-cli 0.144.5` is
rejected before routed mode opens. Updating that value requires a fresh schema
generation, review, checksums, compatibility tests, and documentation update.
