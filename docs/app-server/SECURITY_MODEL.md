# App Server router security model

## Trust boundaries

```text
human <-> original Codex TUI <-> localhost proxy <-> local Codex App Server
                                      |
                                      +-> sanitized event log
```

The TUI and App Server are the official installed Codex components. The proxy
is an opt-in local policy boundary. App Server owns authentication and upstream
provider communication. The proxy neither reads auth files nor persists
credentials.

## Preserved defense-in-depth

Phase 5 project-local protections remain intact:

- the custom skill;
- `UserPromptSubmit` advisory developer context;
- `PreToolUse` blocking;
- `PermissionRequest` blocking/defer-to-human behavior;
- fail-closed rule validation;
- no raw prompt logging;
- no automatic approval;
- no `danger-full-access`; and
- no launcher invocation from hooks.

The App Server proxy adds actual per-turn configuration. It does not replace or
weaken the hook layer.

## Data handling

Raw prompts are received from the TUI because the proxy must classify and
forward `turn/start`. They remain in process memory only. Logs permit a SHA-256
prompt hash and sanitized capability/policy fields. Untrusted string request
and thread IDs are hashed before logging.

All original input items are forwarded. The proxy does not inspect local image
files, skills, mentions, transcript files, auth stores, environment-secret
files, browser state, tokens, or cookies. It does not cache provider messages
or authentication exchanges.

App Server may initiate auth-token refresh or attestation requests as part of
its normal protocol. These frames transit the proxy unchanged in memory and are
never interpreted, answered, or logged by the router.

## Network boundary

Both backend and proxy use `ws://127.0.0.1:<port>`. The proxy constructor rejects
`0.0.0.0`, non-loopback client URLs, credentials embedded in URLs, and requests
with an `Origin` header. It does not implement remote authentication or TLS.

Plain WebSockets are acceptable only for this local experimental flow. Do not
expose either listener outside localhost.

## Turn authority

Only `turn/start` is rewritten, and only these installed fields:

- `model`;
- `effort`;
- `sandboxPolicy`; and
- `approvalPolicy`; and
- `approvalsReviewer`, fixed to the human `user` reviewer.

If the stock TUI already supplied the installed experimental
`collaborationMode`, only its precedence-bearing `settings.model` and
`settings.reasoning_effort` values are aligned with the top-level route. The
router does not add this experimental object, change its mode, or change its
developer instructions.

No other request is modified. In particular, `turn/steer`, initialization,
thread lifecycle, streamed notifications, errors, server approval requests,
and client approval responses pass through unchanged.

Local routed policy excludes `danger-full-access` and `never`. Network access
inside emitted sandbox policies is false. Managed requirements may tighten a
route but may not force a locally forbidden mode. Existing `readOnly` and
`untrusted` settings are retained when stricter.

The installed experimental named `permissions` selector cannot coexist with a
`sandboxPolicy` override. The router does not remove or reinterpret a named
profile; it fails the turn locally so the user can retry with routing off.

The proxy never sets `approvalsReviewer` to `auto_review`, never constructs an
approval decision, and never suppresses a backend request. It explicitly keeps
the reviewer human in routed turns. A model selection is quality capacity only;
it grants no execution authority.

## Failure behavior

Malformed `turn/start`, no routable text, invalid Router Core configuration,
no compatible visible model, unsupported safe policy intersection, or other
routing failure returns code `-32090` with a sanitized message. The request is
not forwarded. Users can retry with normal `codex` (routing off).

There is no hidden fallback to Sol Max. Backend connection failures close the
frontend connection with a generic backend-unavailable reason.

## Threats and controls

| Threat | Control |
|---|---|
| Prompt leaks through logging | strict event whitelist, prompt hash only |
| Model catalog drift | startup `model/list`, hidden filter, upgrade target, version pin |
| Unsupported effort | nearest value from selected live model only |
| Model choice weakens safety | separate Router Core sandbox/approval mapping |
| Approval spoofing | bidirectional raw forwarding; proxy never responds |
| Remote listener exposure | exact `127.0.0.1` bind and loopback URL validation |
| Global Codex mutation | subprocess argument lists only; no config/binary/symlink writes |
| Unsafe route failure | sanitized error and no backend forward |

## Residual risk

WebSocket transport is experimental and unsupported. The local implementation
is intentionally narrow, and changes in future App Server framing/schema may
require review. Provider-side model rerouting is outside the proxy's control;
use emitted active-settings/reroute evidence rather than assuming the forwarded
slug remained active.
