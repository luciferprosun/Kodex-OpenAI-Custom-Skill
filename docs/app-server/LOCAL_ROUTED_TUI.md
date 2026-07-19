# Local routed Codex TUI

## ON mode

From the project root:

```bash
./scripts/start-routed-codex
```

The script starts a localhost App Server backend, discovers live model and
managed-policy metadata, starts the localhost routing proxy, and finally opens
the original installed Codex terminal UI with `--remote`. It does not pass a
prompt in process arguments. Enter prompts normally inside the TUI.

Startup prints three sanitized locations before the TUI opens:

- backend `ws://127.0.0.1:<port>`;
- proxy `ws://127.0.0.1:<port>`; and
- a mode-0600 JSONL routing-event file under `/tmp/codex-smart-router-<uid>/`.

The original repository skill and hooks load normally because the TUI working
directory remains `/home/l/codex-patch-smart-router`.

## Linux desktop launcher

The tracked launcher is:

```text
desktop/Kodex OpenAI Custom Skill.desktop
```

It is named **Kodex OpenAI Custom Skill**, opens a terminal, and calls only the
project script. Copy it into the desktop/application location appropriate for
the local Linux desktop if desired. It does not replace the installed `codex`
command or create an alias.

## OFF mode

Use ordinary Codex exactly as before:

```bash
codex
```

No global config, symlink, shell alias, or binary is modified, so routed mode is
never mandatory.

## Connect to an already-running local backend

For development, run the manager module directly:

```bash
./.venv/bin/python -m smart_codex.app_server_router.launcher \
  --backend-url ws://127.0.0.1:4501 \
  --proxy-port 4500 \
  --cwd /home/l/codex-patch-smart-router
```

The URL parser rejects non-loopback endpoints and credentials embedded in the
URL. The existing backend remains responsible for its authenticated Codex
session; the router never opens credential files.

Manager-only mode is available for protocol tests:

```bash
./.venv/bin/python -m smart_codex.app_server_router.launcher \
  --backend-port 4501 \
  --proxy-port 4500 \
  --manager-only
```

Then connect the original TUI yourself:

```bash
codex --remote ws://127.0.0.1:4500 -C /home/l/codex-patch-smart-router
```

## Stopping safely

Exit the TUI normally or press Ctrl-C in manager-only mode. The launcher closes
the proxy first, terminates only the backend process it started, waits up to
five seconds, and kills that child only if it does not exit. A backend supplied
with `--backend-url` is not owned or stopped by the manager.

If startup fails, routed mode exits with a sanitized error. Retry with ordinary
`codex`; do not mutate global configuration to work around the failure.

If a turn uses an experimental named permission profile, routed mode returns a
local safe-routing error because App Server forbids combining that selector
with the router's explicit `sandboxPolicy`. Retry that turn using ordinary
`codex`; the manager does not delete or rewrite the named profile.

## Upgrade procedure

Routed mode is pinned to the reviewed installed contract `codex-cli 0.144.5`.

Telemetry research uses the separate fail-closed launcher
`scripts/start-routed-codex-research`; it requires an explicit `aoia` or
`smart-router` window ID, a verified repository identity, enabled external
storage, and the exact protocol contract. It does not replace this ordinary
launcher or the official `codex` executable. See
[`../TELEMETRY_RESEARCH_LOOP_2B2.md`](../TELEMETRY_RESEARCH_LOOP_2B2.md).
After a CLI upgrade, regenerate both schema sets, review method and field
changes, update the contract snapshot and tests, then deliberately update the
supported version. Ordinary `codex` remains available during that review.

## Transport warning

The official App Server manual currently labels WebSocket transport
experimental and unsupported. Keep both listeners on `127.0.0.1`; do not expose
this prototype on a LAN or public interface.
