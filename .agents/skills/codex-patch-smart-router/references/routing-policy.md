# Routing Policy Reference

## Source of truth

Treat the tested Router Core under `smart_codex/` and the JSON files under the repository root `rules/` directory as the executable source of truth. Use this reference only to explain their policy. Do not add categories, triggers, precedence rules, or profile behavior here that the core does not implement.

The summarized rule sources are:

- `prompt_weight_dimensions.json`;
- `category_weights.json`;
- `risk_triggers.json`;
- `complexity_rules.json`;
- `action_danger_rules.json`;
- `evidence_rules.json`;
- `context_rules.json`;
- `profile_policy.json`;
- `tie_breakers.json`.

## Risk scale

- `low`: routine, bounded work with no meaningful destructive or sensitive signal.
- `medium`: repository writes, dependencies, network access, or other work requiring normal review.
- `high`: sensitive, privileged, secret-touching, deployment, database, or otherwise consequential work.
- `critical`: destructive or irreversible work, including destructive repository operations.

For high and critical risk, recommend:

- security profile;
- read-only sandbox;
- on-request approval;
- explicit human confirmation.

## Hard safety precedence

Apply this order before ordinary category scoring:

1. secrets and credentials;
2. destructive operations;
3. privilege and system changes;
4. production deployment or publishing;
5. destructive database operations;
6. irreversible repository operations;
7. ordinary category scoring.

When a hard safety result conflicts with convenience or category routing, keep the safer result.

## Canonical labels

Use one existing category label rather than a descriptive blend: `email`, `simple_text`, `literary`, `normal_coding`, `complex_coding`, `architecture`, `math_theory`, `security_audit`, `repo_operations`, `research`, `grant_work`, `unknown`, `debugging`, `testing`, `dependency_management`, `release_management`, `documentation`, `data_analysis`, `legal_admin`, `financial_admin`, `system_admin`, `incident_response`, `secret_handling`, or `prompt_engineering`.

Use exactly one existing action-danger label: `read_only_analysis`, `write_local_files`, `run_tests`, `git_operations`, `network_access`, `dependency_install`, `database_operation`, `deployment_operation`, `destructive_operation`, or `secret_touching_operation`.

## Profiles

| Profile | Intended task types | Recommended sandbox |
|---|---|---|
| `fast` | Harmless simple text, email, and low-complexity tasks | read-only |
| `standard` | Normal coding, debugging, testing, and bounded local implementation | workspace-write |
| `deep` | Complex coding, architecture, broad refactoring, and high-context reasoning | workspace-write |
| `math` | Mathematical theory, proofs, equations, LSC, and neutrino reasoning | read-only |
| `security` | Security audits, secrets, privileged work, destructive actions, deployment, and database risk | read-only |
| `literary` | Literary writing and non-operational language work | read-only |
| `research` | Research, grants, evidence-heavy work, and source-oriented analysis | read-only |
| `repo` | Non-destructive repository, release, dependency, and version-control operations | workspace-write |

Keep approval on-request. High or critical risk overrides an otherwise writable profile and recommends security with read-only access.

## Action-danger distinction

Classify intent separately from topic. Distinguish:

- discussing an operation: explain concepts without performing the action;
- reviewing an operation: inspect or assess a proposed action without performing it;
- requesting execution: ask Codex to carry out the action.

Examples:

- "Explain rm -rf" is read-only analysis.
- "Review this proposed deletion command" is read-only review.
- "Run rm -rf" is a destructive operation and requires the hard safety route.

Apply the same distinction to force push, deployment, publishing, database modification, permissions, and secret handling.

## Limitations

- This skill does not automatically change the active model.
- This skill does not automatically change the active profile or sandbox.
- This skill does not automatically change the approval policy.
- This skill does not intercept every possible Codex tool path.
- This skill provides an advisory workflow in Phase 2.
- Lifecycle hooks and plugin packaging belong to later phases.
