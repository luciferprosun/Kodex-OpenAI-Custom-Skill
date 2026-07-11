---
name: codex-patch-smart-router
description: Analyze Codex tasks for prompt weight, category, complexity, risk, action danger, context, and evidence requirements before implementation. Use for coding, architecture, repository, security-sensitive, mathematical, research, grant, deployment, secret-handling, and destructive-operation tasks. Do not claim to change the active Codex model, profile, sandbox, or approval policy automatically.
---

# Codex Patch Smart Router

## Purpose

Apply the Codex Patch Smart Router policy before planning or executing a repository task. Treat this skill as an instruction and workflow adapter around the existing deterministic router core. It does not replace Codex, modify Codex internals, or automatically change the active model, profile, sandbox, or approval policy.

## When to use

Use this skill for tasks involving:

- normal or complex coding;
- architecture and refactoring;
- debugging and testing;
- repository and release operations;
- dependency management;
- security audits;
- credentials, secrets, authentication, and permissions;
- system administration and incident response;
- destructive or irreversible actions;
- mathematical or LSC/neutrino reasoning;
- research and grant work;
- uncertain or mixed-signal prompts.

Do not use it merely to rewrite a harmless sentence unless the user explicitly requests routing analysis.

## Workflow

1. Inspect the supplied task without executing the underlying request.
2. Invoke the deterministic adapter with the complete task text through standard input.
3. Read only the adapter's JSON result; do not reproduce routing rules in the skill.
4. Render the routing recommendation before planning or implementation.
5. Stop on adapter errors or confirmation-required results.
6. Continue only when permitted by the decision behavior below and by the current Codex session.

## Deterministic adapter

For an explicitly invoked routing task, use:

```text
python .agents/skills/codex-patch-smart-router/scripts/route_prompt.py --stdin
```

When the repository-local `.venv/bin/python` exists, use it as the interpreter for the same interface:

```text
./.venv/bin/python .agents/skills/codex-patch-smart-router/scripts/route_prompt.py --stdin
```

Do not install Python or create an alias when the bare `python` command is unavailable.

Pass the complete task text through standard input as one UTF-8 string. Do not place it in shell arguments, split it into words, pipe it through a helper command, or write it to a temporary file. Read the returned JSON and render the `SMART ROUTER DECISION` block from its fields.

The adapter is advisory only. It does not launch Codex, execute the task, or change the active model, profile, sandbox, or approval policy.

Apply this decision behavior in order:

1. If `status != ok`, show the sanitized error and stop; do not continue the task.
2. If `requires_confirmation == true`, show the routing block and stop for explicit human confirmation; do not continue the task.
3. If the user's request says "analyze only" or "without executing," show the routing block and stop.
4. Otherwise, show the routing block and continue only within the current Codex session's already-granted permissions.
5. Never claim that recommended settings were applied.

## Required output

Before implementation, provide this compact routing block:

```text
SMART ROUTER DECISION
Category: <category>
Risk: <low | medium | high | critical>
Complexity: <low | medium | high>
Action danger: <action danger>
Evidence requirement: <requirement>
Context requirement: <requirement>
Confidence: <score>
Recommended profile: <fast | standard | deep | math | security | literary | research | repo>
Recommended sandbox: <read-only | workspace-write>
Recommended approval: <on-request>
Confirmation required: <yes | no>
Application status: advisory only; current Codex settings are unchanged
```

Do not perform the underlying task when the decision behavior requires a stop.

## Safety invariants

- Do not log or reproduce raw secrets.
- Do not read environment files, private keys, tokens, or authentication stores merely to classify a task.
- Do not invoke a shell interpreter for prompt handling.
- Keep the user prompt as one string; do not split it into shell arguments.
- Do not recommend unrestricted sandbox access.
- Do not imply complete interception of Codex tool paths.
- Do not imply automatic per-turn model switching.
- Do not modify global Codex configuration.
- Do not replace the real Codex binary.
- Require explicit user approval for destructive, deployment, secret-touching, database, or privileged operations.

## Reference

Read [references/routing-policy.md](references/routing-policy.md) only when detailed category, precedence, profile, or adapter-contract guidance is needed. Keep the executable Knowledge Library in the repository root as the source of truth; do not copy it into this skill.
