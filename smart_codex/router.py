from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .classifier import classify_prompt
from .profiles import (
    AVAILABLE_PROFILES,
    load_profile,
    validate_approval_override,
    validate_profile_override,
    validate_sandbox_override,
)
from .risk import assess_risk


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
    classification = classify_prompt(prompt)
    risk = assess_risk(prompt, classification.category)
    reasons: list[str] = [
        f"classified as {classification.category}",
        f"confidence {classification.confidence:.2f}",
        f"risk {risk.risk}",
        f"complexity {risk.complexity}",
    ]
    reasons.extend(risk.reasons)

    warning = classification.warning
    selected_profile = CATEGORY_TO_PROFILE.get(classification.category, "standard")
    if classification.category == "unknown" or classification.confidence <= 0.30:
        selected_profile = "standard"
        warning = warning or "low confidence route"
        reasons.append("low confidence route uses standard profile")
    else:
        reasons.append(f"category maps to {selected_profile} profile")

    override_used = False
    if risk.risk == "high" and profile_override is None:
        selected_profile = "security"
        reasons.append("high risk routes to security profile")

    if profile_override is not None:
        validate_profile_override(profile_override)
        selected_profile = profile_override
        override_used = True
        reasons.append(f"profile override used: {profile_override}")
        if risk.risk == "high":
            warning = append_warning(warning, "high risk prompt with manual profile override")

    if selected_profile not in AVAILABLE_PROFILES:
        raise ValueError(f"selected profile is not available: {selected_profile}")

    profile = load_profile(selected_profile)

    selected_model = model_override or profile.model
    sandbox_mode = profile.sandbox_mode
    approval_policy = profile.approval_policy

    if risk.risk == "high" and profile_override is None:
        sandbox_mode = "read-only"
        approval_policy = "on-request"

    if sandbox_override is not None:
        validate_sandbox_override(sandbox_override)
        sandbox_mode = sandbox_override
        override_used = True
        reasons.append(f"sandbox override used: {sandbox_override}")
        if risk.risk == "high" and sandbox_mode != "read-only":
            warning = append_warning(warning, "high risk prompt with non-read-only sandbox override")

    if approval_override is not None:
        validate_approval_override(approval_override)
        approval_policy = approval_override
        override_used = True
        reasons.append(f"approval override used: {approval_override}")

    if model_override is not None:
        override_used = True
        reasons.append("model override used")

    return RoutingDecision(
        prompt_hash=hash_prompt(prompt),
        category=classification.category,
        complexity=risk.complexity,
        risk=risk.risk,
        selected_profile=selected_profile,
        selected_model=selected_model,
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        reasoning_effort=profile.model_reasoning_effort,
        model_verbosity=profile.model_verbosity,
        confidence=classification.confidence,
        decision_reasons=dedupe(reasons),
        override_used=override_used,
        dry_run=dry_run,
        warning=warning,
    )


def append_warning(existing: str | None, addition: str) -> str:
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing}; {addition}"


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

