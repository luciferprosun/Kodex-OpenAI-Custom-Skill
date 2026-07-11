
# Prompt Weight Knowledge Library - Master Spec

## Purpose

Prompt weight is the operational cost and safety weight of a prompt before Codex runs it. The router must estimate task category, risk, complexity, context, evidence needs, action danger, and confidence before launching Codex.

## Prompt weight dimensions

- task_category
- risk_level
- complexity_level
- execution_scope
- repo_impact
- security_sensitivity
- destructiveness
- evidence_requirement
- context_requirement
- math_reasoning_requirement
- creative_requirement
- research_requirement
- approval_requirement
- confidence_level
- action_danger

## Hard order

1. Hard safety override first.
2. Then category scoring.
3. Then secondary dimensions.
4. Then tie-breakers.
5. Then profile policy.
6. Then launcher gate.

## Important distinction

Risk is not the same as action danger.

Example:

```text
Explain what rm -rf does -> read_only_analysis, security/audit context, no destructive execution.
Run rm -rf on build directory -> destructive_operation, critical, security/read-only.
```

## Config/rule failure behavior

If any rule file is malformed or missing, the correct behavior is:

```text
CONFIG_ERROR
no execution
no Codex command launch
clear error naming bad file/key
```

Do not silently fall back to a guessed route.
