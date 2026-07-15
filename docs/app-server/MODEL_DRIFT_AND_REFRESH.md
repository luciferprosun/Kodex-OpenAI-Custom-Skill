# Live model drift and refresh

The App Server manager discovers capabilities once at startup and keeps the
sanitized snapshot in process memory. Restart routed mode after a Codex update,
account entitlement change, model availability change, or policy edit.

## Source of truth

At startup the manager calls:

1. `initialize` and `initialized`;
2. paginated `model/list` with `includeHidden=true`;
3. `configRequirements/read`.

The live response wins over static rules, old reports, upstream registry files,
and remembered model names for:

- model identifiers and current presence;
- hidden status;
- `upgrade` and `upgradeInfo`;
- supported/default reasoning effort;
- input modalities;
- service-tier and availability-notice metadata;
- managed sandbox and approval requirements.

The process-local snapshot stores retrieval time, Codex version, and sanitized
capability metadata. It stores no prompt, access token, cookie, authentication
file, or provider response body beyond the validated fields.

## Installed-schema limitation

Codex CLI `0.144.4` does not expose a context-window field in `model/list`.
Known exact models use reviewed versioned context classes informed by the
official OpenAI Codex model registry. This auxiliary metadata never overrides
live presence, modality, effort, visibility, or upgrade fields. Future family
models receive a conservative small-context default until their capability
profile is reviewed or explicitly overridden.

The official upstream registry is supporting evidence, not the runtime source
of truth: [openai/codex model registry](https://github.com/openai/codex/blob/main/codex-rs/models-manager/models.json).

## Drift behavior

| Drift | Behavior |
|---|---|
| New unknown model | Reject; emit `unknown_model_capabilities` |
| New known-family model with expected live shape | Permit small-context work; emit conservative-family warning |
| New known-family model with changed effort/modal shape | Reject until reviewed |
| Known model disappears | Exclude; use normal live fallback |
| Supported effort changes | Use only the new live set; emit `effort_drift` |
| Upgrade target appears | Suppress normal legacy use; emit upgrade warning |
| Model becomes hidden | Reject by default; emit visibility warning |
| Input modality changes | Enforce live modalities; emit `modality_drift` |
| Reviewed context override changes | Enforce the new class; emit context warning |
| Temporary unavailability overlay | Exclude for the current process until cleared/restarted |

Warnings are bounded codes containing only sanitized model identifiers. The
event logger emits no raw prompt or provider credential material.

## Recalibration after a Codex update

1. Keep ordinary `codex` as OFF mode.
2. Record `codex --version` and generate the installed App Server JSON schema
   and TypeScript bindings.
3. Query visible and hidden `model/list` plus `configRequirements/read` without
   starting a paid/model turn.
4. Compare live effort/modal/upgrade fields with the declarative profiles.
5. Review the official App Server docs, OpenAI Codex registry, and relevant
   model announcements.
6. Add drift fixtures before changing policy.
7. Run the 180-case calibration eval and the full test suite.
8. Require zero unavailable models, unsupported efforts, modality/context
   violations, migration violations, and critical under-routing.
9. Perform a limited harmless routed-TUI soak and verify forwarded and active
   model events.
10. Commit only after proxy transparency, approvals, hooks, privacy, and
    localhost-only tests remain green.

WebSocket App Server transport is still experimental and unsupported. A schema
or behavior change that prevents transparent approval forwarding, safe
per-turn overrides, or active-model evidence is a stop condition, not a reason
to guess: [Codex App Server](https://learn.chatgpt.com/docs/app-server).
