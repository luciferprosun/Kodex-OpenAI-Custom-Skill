from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .profiles import (
    AVAILABLE_PROFILES,
    load_profile,
    validate_approval_override,
    validate_profile_override,
    validate_sandbox_override,
)
from .scorer import RISK_ORDER, score


CATEGORY_TO_PROFILE = {
    "email": "fast",
    "simple_text": "fast",
    "literary": "literary",
    "normal_coding": "standard",
    "complex_coding": "deep",
    "architecture": "deep",
    "math_theory": "math",
    "security_audit": "security",
    "repo_operations": "repo",
    "research": "research",
    "grant_work": "research",
    "unknown": "standard",
}


SAFETY_ACTION_DANGERS = {
    "destructive_operation",
    "secret_touching_operation",
    "deployment_operation",
    "database_operation",
}

DESTRUCTIVE_GIT_SIGNALS = (
    "force push",
    "push --force",
    "push -f",
    "reset --hard",
    "delete branch",
    "rewrite history",
)

DATABASE_ACTION_SIGNALS = (
    "database",
    "db",
    "sql",
    "table",
    "schema",
    "alembic",
    "postgres",
    "mysql",
    "sqlite",
    "drop",
    "truncate",
    "delete from",
    "alter table",
)


@dataclass(frozen=True)
class RoutingDecision:
    prompt_hash: str
    category: str
    complexity: str
    risk: str
    selected_profile: str
    selected_model: str | None
    sandbox_mode: str
    approval_policy: str
    reasoning_effort: str
    model_verbosity: str
    confidence: float
    decision_reasons: list[str]
    override_used: bool
    dry_run: bool
    warning: str | None
    risk_level: str
    complexity_level: str
    action_danger: str
    evidence_requirement: str
    context_requirement: str
    repo_impact: str
    security_sensitivity: str
    destructiveness: str
    execution_scope: str
    score_source: str


def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def route_prompt(
    prompt: str,
    *,
    dry_run: bool = True,
    profile_override: str | None = None,
    model_override: str | None = None,
    sandbox_override: str | None = None,
    approval_override: str | None = None,
) -> RoutingDecision:
    score_card = score(prompt)
    risk_level = score_card.risk_level
    action_danger = score_card.action_danger
    reasons: list[str] = [
        f"classified as {score_card.category}",
        f"confidence {score_card.confidence:.2f}",
        f"risk {risk_level}",
        f"complexity {score_card.complexity_level}",
        f"action danger {action_danger}",
    ]
    reasons.extend(score_card.reasons)

    warning = "; ".join(score_card.warnings) if score_card.warnings else None
    selected_profile = score_card.profile
    if score_card.category == "unknown":
        selected_profile = "standard"
        warning = warning or "low confidence route"
        reasons.append("low confidence route uses standard profile")
    elif score_card.category == "email":
        selected_profile = "fast"
        reasons.append("V0 compatibility maps email to fast profile")
    else:
        reasons.append(f"category maps to {selected_profile} profile")

    override_used = False
    safety_forced = False

    if has_destructive_git_signal(prompt):
        action_danger = "destructive_operation"
        risk_level = max_risk(risk_level, "critical")
        selected_profile = "security"
        safety_forced = True
        warning = append_warning(warning, "REQUIRES_CONFIRMATION")
        reasons.append("destructive git signal forces security routing")
    elif action_danger == "database_operation" and not has_database_action_signal(prompt):
        action_danger = "read_only_analysis"
        reasons.append("non-database migration does not trigger database action gate")
    elif action_danger in SAFETY_ACTION_DANGERS:
        selected_profile = "security"
        safety_forced = True
        warning = append_warning(warning, "REQUIRES_CONFIRMATION")
        if action_danger == "destructive_operation":
            risk_level = max_risk(risk_level, "critical")
        else:
            risk_level = max_risk(risk_level, "high")
        reasons.append(f"{action_danger} forces security routing")
    elif action_danger == "git_operations":
        selected_profile = "repo"
        risk_level = max_risk(risk_level, "medium")
        reasons.append("git operation routes to repo profile")
    elif action_danger == "dependency_install":
        selected_profile = "repo"
        risk_level = max_risk(risk_level, "medium")
        warning = append_warning(warning, "dependency install requires confirmation")
        reasons.append("dependency install routes to repo profile")
    elif action_danger == "network_access":
        if selected_profile not in {"research", "repo", "security"}:
            selected_profile = "research" if score_card.category == "research" else "repo"
        risk_level = max_risk(risk_level, "medium")
        warning = append_warning(warning, "network access requires confirmation")
        reasons.append(f"network access routes to {selected_profile} profile")

    high_or_critical = RISK_ORDER.get(risk_level, 0) >= RISK_ORDER["high"]
    if high_or_critical:
        selected_profile = "security"
        safety_forced = True
        reasons.append("high or critical risk routes to security profile")

    if profile_override is not None:
        validate_profile_override(profile_override)
        override_used = True
        if safety_forced:
            warning = append_warning(warning, "manual profile override ignored by safety gate")
            reasons.append(f"profile override ignored by safety gate: {profile_override}")
        else:
            selected_profile = profile_override
            reasons.append(f"profile override used: {profile_override}")

    if selected_profile not in AVAILABLE_PROFILES:
        raise ValueError(f"selected profile is not available: {selected_profile}")

    profile = load_profile(selected_profile)

    selected_model = model_override or profile.model
    sandbox_mode = profile.sandbox_mode
    approval_policy = profile.approval_policy

    if safety_forced:
        sandbox_mode = "read-only"
        approval_policy = "on-request"

    if sandbox_override is not None:
        validate_sandbox_override(sandbox_override)
        override_used = True
        if safety_forced and sandbox_override != "read-only":
            warning = append_warning(warning, "sandbox override ignored by safety gate")
            reasons.append(f"sandbox override ignored by safety gate: {sandbox_override}")
        else:
            sandbox_mode = sandbox_override
            reasons.append(f"sandbox override used: {sandbox_override}")

    if approval_override is not None:
        validate_approval_override(approval_override)
        approval_policy = approval_override
        override_used = True
        reasons.append(f"approval override used: {approval_override}")

    if safety_forced:
        sandbox_mode = "read-only"
        approval_policy = "on-request"

    if model_override is not None:
        override_used = True
        reasons.append("model override used")

    return RoutingDecision(
        prompt_hash=hash_prompt(prompt),
        category=score_card.category,
        complexity=score_card.complexity_level,
        risk=risk_level,
        selected_profile=selected_profile,
        selected_model=selected_model,
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        reasoning_effort=profile.model_reasoning_effort,
        model_verbosity=profile.model_verbosity,
        confidence=score_card.confidence,
        decision_reasons=dedupe(reasons),
        override_used=override_used,
        dry_run=dry_run,
        warning=warning,
        risk_level=risk_level,
        complexity_level=score_card.complexity_level,
        action_danger=action_danger,
        evidence_requirement=score_card.evidence_requirement,
        context_requirement=score_card.context_requirement,
        repo_impact=score_card.repo_impact,
        security_sensitivity=score_card.security_sensitivity,
        destructiveness=score_card.destructiveness,
        execution_scope=score_card.execution_scope,
        score_source=score_card.source,
)


def append_warning(existing: str | None, addition: str) -> str:
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing}; {addition}"


def max_risk(current: str, minimum: str) -> str:
    current_value = RISK_ORDER.get(current, 0)
    minimum_value = RISK_ORDER.get(minimum, 0)
    return current if current_value >= minimum_value else minimum


def has_destructive_git_signal(prompt: str) -> bool:
    normalized = prompt.lower()
    return any(signal in normalized for signal in DESTRUCTIVE_GIT_SIGNALS)


def has_database_action_signal(prompt: str) -> bool:
    normalized = prompt.lower()
    return any(signal in normalized for signal in DATABASE_ACTION_SIGNALS)


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
