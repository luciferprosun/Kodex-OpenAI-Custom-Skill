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

1. Inspect the task without executing it. When the user says "analyze only" or "without executing," do not call tools, run commands, or read files; classify only the supplied task text using this loaded skill.
2. Identify the task category, risk level, complexity level, action danger, repository impact, evidence requirement, context requirement, and confidence level. Use one existing category label: email, simple_text, literary, normal_coding, complex_coding, architecture, math_theory, security_audit, repo_operations, research, grant_work, unknown, debugging, testing, dependency_management, release_management, documentation, data_analysis, legal_admin, financial_admin, system_admin, incident_response, secret_handling, or prompt_engineering. Do not invent a blended category label.
3. Use exactly one existing action-danger label: read_only_analysis, write_local_files, run_tests, git_operations, network_access, dependency_install, database_operation, deployment_operation, destructive_operation, or secret_touching_operation.
4. Apply hard safety precedence to secrets and credentials, destructive filesystem operations, force push or history rewrite, production deployment or publishing, destructive database operations, privileged system operations, and pipe-to-shell execution.
5. For high or critical risk, recommend the security profile, a read-only sandbox, on-request approval, and explicit human confirmation.
6. For low or medium risk, recommend the appropriate existing profile: fast, standard, deep, math, security, literary, research, or repo.
7. State the recommendation before implementation.
8. Never claim that the skill has already changed the active model, profile, sandbox, or approval policy.
9. Never execute automatically.
10. Never request or print secret values.
11. Treat any router configuration failure as fail-closed and stop before implementation.

## Required output

Before implementation, provide this compact routing block:

```text
SMART ROUTER DECISION
Category: <category>
Risk: <low | medium | high | critical>
Complexity: <low | medium | high>
Action danger: <action danger>
Repository impact: <impact>
Evidence requirement: <requirement>
Context requirement: <requirement>
Confidence: <level or score>
Recommended profile: <fast | standard | deep | math | security | literary | research | repo>
Recommended sandbox: <read-only | workspace-write>
Recommended approval: <on-request>
Confirmation required: <yes | no>
Application status: advisory only; current Codex settings are unchanged
```

If the user requested "analyze only" or "without executing," stop after the routing block and one brief safety note; do not perform the underlying task. Otherwise, continue only within the permissions already available in the current Codex session.

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

Read [references/routing-policy.md](references/routing-policy.md) only when detailed category, precedence, or profile guidance is needed and the user has not requested a tool-free analysis. Keep the executable Knowledge Library in the repository root as the source of truth; do not copy it into this skill.
