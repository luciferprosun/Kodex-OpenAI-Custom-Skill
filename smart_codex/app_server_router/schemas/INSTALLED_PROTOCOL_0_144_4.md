# Installed App Server contract snapshot

This prototype was implemented against bindings generated locally by
`codex-cli 0.144.4` on 2026-07-15:

```bash
codex app-server generate-json-schema --out /tmp/codex-app-server-schema
codex app-server generate-ts --out /tmp/codex-app-server-ts
codex app-server generate-json-schema --experimental \
  --out /tmp/codex-app-server-schema-experimental
codex app-server generate-ts --experimental \
  --out /tmp/codex-app-server-ts-experimental
```

The generated installed-version files remain the source of truth. This note is
an audit index, not a replacement schema and not a permanent model catalog.

## Verified lifecycle and discovery methods

- `initialize` request and `initialized` notification
- `model/list`, including `includeHidden` and cursor pagination
- `configRequirements/read`
- `thread/start` and `thread/resume`
- `turn/start`, `turn/steer`, and `turn/interrupt`
- `turn/started` and `turn/completed`

`RequestId` is `string | integer`. Messages omit the `jsonrpc` member on the
wire. Responses echo the request ID with either `result` or `error`.

## Verified turn overrides

`TurnStartParams` supports these optional fields, which are the only fields
the router rewrites:

- `model: string | null`
- `effort: ReasoningEffort | null`
- `sandboxPolicy: SandboxPolicy | null`
- `approvalPolicy: AskForApproval | null`
- `approvalsReviewer: ApprovalsReviewer | null`

The stock remote TUI opts into the installed experimental protocol and sends
`collaborationMode`. Its schema explicitly says that its nested settings take
precedence over top-level model and effort. When, and only when, that object is
already present, the router also replaces:

- `collaborationMode.settings.model`
- `collaborationMode.settings.reasoning_effort`

It preserves `collaborationMode.mode`, `developer_instructions`, and every
other experimental field. A malformed collaboration object fails closed.

Routed mode sets `approvalsReviewer` to `user` so an inherited automatic
reviewer cannot replace human approval. The experimental `permissions` profile
field cannot be combined with `sandboxPolicy`; a turn that supplies a named
profile therefore fails closed and can be retried in ordinary Codex.

The installed schema describes `ReasoningEffort` as a non-empty advertised
string. Supported values therefore come from each live `model/list` entry; the
router does not treat a static effort list as authoritative.

`turn/steer` contains only `threadId`, `clientUserMessageId`, `input`, and
`expectedTurnId`; it has no model or policy override and is never modified.

## Verified policy wire values

Thread-level sandbox modes use `read-only`, `workspace-write`, and
`danger-full-access`. Turn-level structured policy discriminators use
`readOnly`, `workspaceWrite`, `externalSandbox`, and `dangerFullAccess`.
Routed mode locally permits only `read-only` and `workspace-write`, emitted as
`readOnly` and `workspaceWrite`, with network access disabled.

Approval policies use `untrusted`, `on-request`, `never`, or a granular object.
Routed mode locally permits only `on-request` and the stricter `untrusted`
fallback. It never emits `never` and never changes `approvalsReviewer` to an
automatic reviewer.

## Verified server requests

All backend-initiated requests are forwarded unchanged, including:

- `item/commandExecution/requestApproval`
- `item/fileChange/requestApproval`
- `item/permissions/requestApproval`
- `item/tool/requestUserInput`
- `mcpServer/elicitation/request`
- `item/tool/call`
- `account/chatgptAuthTokens/refresh`
- `attestation/generate`
- legacy `applyPatchApproval` and `execCommandApproval`

The proxy never fabricates a response to any of them.

## Transport status

The installed CLI supports `ws://IP:PORT`, but the official Codex App Server
manual labels WebSocket transport experimental and unsupported. The prototype
therefore binds exactly to `127.0.0.1`, rejects `Origin` requests, accepts no
credentials in URLs, and is opt-in only.
