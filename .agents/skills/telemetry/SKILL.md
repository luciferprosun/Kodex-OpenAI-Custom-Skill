---
name: telemetry
description: Control metadata-only local Smart Codex research capture through the existing telemetry schema with the exact actions start, stop, or status. Use only when the user explicitly invokes $telemetry; this skill never persists prompt content.
---

# Research Telemetry Session Control

Accept only one of these exact invocations:

- `$telemetry start`
- `$telemetry stop`
- `$telemetry status`

Reject every other action without running a command. Do not infer an action
from prose, abbreviations, quotations, or examples.

For an accepted action, select one matching literal command below. Never place
untrusted text into the command and never invoke a shell interpreter:

```text
python .agents/skills/telemetry/scripts/control.py start
python .agents/skills/telemetry/scripts/control.py stop
python .agents/skills/telemetry/scripts/control.py status
```

Return the controller output exactly. This skill changes only the selective,
metadata-only research-capture gate. When the gate is ON, reviewed hooks reuse
the existing schema-2.0.0 collector and privacy validator. The skill does not
enable the router, persist prompt or response content, select a model, call a
provider, or grant execution authority.
