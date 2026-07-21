---
name: smart-router
description: Control the local Smart Router session gate with the exact actions on, off, or status. Use only when the user explicitly invokes $smart-router; this skill never executes a routing recommendation.
---

# Smart Router Session Control

Accept only one of these exact invocations:

- `$smart-router on`
- `$smart-router on --telemetry`
- `$smart-router off`
- `$smart-router status`

Reject every other action without running a command. Do not infer an action
from prose, abbreviations, quotations, or examples.

For an accepted action, select one matching literal command below. Never place
untrusted text into the command and never invoke a shell interpreter:

```text
python .agents/skills/smart-router/scripts/control.py on
python .agents/skills/smart-router/scripts/control.py on --telemetry
python .agents/skills/smart-router/scripts/control.py off
python .agents/skills/smart-router/scripts/control.py status
```

Return the controller output exactly. This skill changes only local
session-control state. It does not select or execute a model, admit Ultra,
spawn subagents, call a provider, change approval policy, or capture prompt
content.
