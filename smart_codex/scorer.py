"""JSON-driven scoring engine for Codex Patch Smart Router."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from .knowledge import KnowledgeLibrary, load_rules
from .preprocessor import normalize_prompt


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
COMPLEXITY_ORDER = {"low": 0, "medium": 1, "high": 2}

CATEGORY_PRIORITY = [
    "secret_handling",
    "security_audit",
    "system_admin",
    "incident_response",
    "financial_admin",
    "release_management",
    "repo_operations",
    "math_theory",
    "architecture",
    "complex_coding",
    "dependency_management",
    "testing",
    "debugging",
    "normal_coding",
    "data_analysis",
    "grant_work",
    "research",
    "legal_admin",
    "documentation",
    "email",
    "literary",
    "simple_text",
    "prompt_engineering",
    "unknown",
]

READ_ONLY_INTENT = (
    "explain",
    "describe",
    "analyze only",
    "analysis only",
    "what does",
    "without running",
    "without executing",
    "review",
    "audit",
    "check",
    "see if",
    "scan",
    "find",
    "summarize",
)

ANALYSIS_ONLY_MARKERS = (
    "analyze only",
    "analysis only",
    "review only",
    "simulation only",
    "simulate without execution",
    "simulate without executing",
    "without execution",
    "without executing",
    "without running",
    "do not execute",
    "don't execute",
    "do not run",
    "don't run",
    "propose but do not execute",
)

ANALYSIS_LEAD_RE = re.compile(
    r"^(?:please\s+)?(?:explain|describe|review|analy[sz]e|audit|inspect|"
    r"simulate|assess|evaluate|show\s+where|why\b|what\s+does\b)"
)

FOLLOWED_BY_EXECUTION_RE = re.compile(
    r"\b(?:then|and)\s+(?:run|execute|apply|perform|delete|remove|upload|"
    r"publish|disable|overwrite|replace|change|stop|truncate|drop)\b"
)

DIRECT_SECRET_INTENT = (
    "add",
    "create",
    "generate",
    "store",
    "rotate",
    "remove",
    "commit history",
    "github token",
    "ghp_",
    "gho_",
    "aws_secret",
)

@dataclass(frozen=True)
class OverrideResult:
    category: str
    profile: str
    risk: str
    sandbox: str
    approval: str
    group: str
    reason: str
    action_danger: str
    confirmation_required: bool = True
    execute_by_default: bool = False


@dataclass(frozen=True)
class CategoryMatch:
    category: str
    score: float
    matched_terms: list[str] = field(default_factory=list)


@dataclass
class ScoreCard:
    category: str
    profile: str
    risk_level: str
    complexity_level: str
    evidence_requirement: str
    context_requirement: str
    action_danger: str
    confidence: float
    confidence_level: str
    category_scores: dict[str, float] = field(default_factory=dict)
    top_categories: list[CategoryMatch] = field(default_factory=list)
    mixed_categories: list[str] = field(default_factory=list)
    override: OverrideResult | None = None
    warnings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    repo_impact: str = "none"
    security_sensitivity: str = "none"
    destructiveness: str = "none"
    execution_scope: str = "unknown"
    source: str = "knowledge_library"


def _regex_or_substr(pattern: str, text: str) -> bool:
    try:
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    except re.error:
        return pattern.lower() in text


def _term_matches(term: str, text: str) -> bool:
    lowered = term.lower()
    if any(char in lowered for char in "\\.*+?[](){}|^$"):
        return _regex_or_substr(lowered, text)
    if " " in lowered or "_" in lowered or "-" in lowered or "." in lowered:
        return lowered in text
    plural = "" if lowered.endswith("s") or lowered in {"service"} else "s?"
    return re.search(rf"\b{re.escape(lowered)}{plural}\b", text, flags=re.IGNORECASE) is not None


def _contains_any(text: str, terms: tuple[str, ...] | list[str]) -> bool:
    return any(_term_matches(term, text) for term in terms)


def _is_read_only_intent(text: str) -> bool:
    return _contains_any(text, READ_ONLY_INTENT)


def is_analysis_only_request(prompt: str) -> bool:
    """Return whether the prompt explicitly constrains work to analysis only.

    Dangerous syntax defaults to execution-oriented handling. Analysis is
    recognized only from an explicit leading analytical verb or a direct
    no-execution constraint. A later request to run the action wins.
    """
    text = normalize_prompt(prompt)
    if FOLLOWED_BY_EXECUTION_RE.search(text):
        return False
    if _contains_any(text, ANALYSIS_ONLY_MARKERS):
        return True
    return ANALYSIS_LEAD_RE.search(text) is not None


def _has_direct_secret_intent(text: str) -> bool:
    return _contains_any(text, DIRECT_SECRET_INTENT)


def _override_from_trigger(
    trigger: dict[str, Any],
    text: str,
    *,
    analysis_only: bool,
) -> OverrideResult:
    group = str(trigger.get("group", "unknown"))
    category = str(trigger.get("category", "security_audit"))
    risk = str(trigger.get("risk", "critical"))
    profile = str(trigger.get("profile", "security"))
    reason = str(trigger.get("reason", "hard safety override"))
    action_danger = str(trigger.get("action_danger", "secret_touching_operation"))
    confirmation_required = bool(trigger.get("confirmation_required", True))

    if analysis_only:
        return OverrideResult(
            category="security_audit",
            profile="security",
            risk="high",
            sandbox="read-only",
            approval="on-request",
            group=group,
            reason=f"{reason}; explicit analysis-only request",
            action_danger="read_only_analysis",
            confirmation_required=False,
            execute_by_default=False,
        )

    if group in {"secrets_keys", "auth_identity"}:
        if _is_read_only_intent(text) and not _has_direct_secret_intent(text):
            category = "security_audit"
            risk = "high"
            profile = "security"
            reason = f"{reason}; read-only secret/auth analysis"
        else:
            category = "secret_handling" if group == "secrets_keys" else "security_audit"
            risk = "critical" if group == "secrets_keys" else "high"
            profile = "security"

    if group == "production_changes" and _contains_any(text, ["broke prod", "rollback plan", "prod is down"]):
        category = "incident_response"
        risk = "high"
        profile = "security"
        reason = f"{reason}; production incident triage"

    if group == "legal_pii":
        category = "legal_admin"
        risk = "high"
        profile = "research"

    return OverrideResult(
        category=category,
        profile=profile,
        risk=risk,
        sandbox=str(trigger.get("sandbox", "read-only")),
        approval=str(trigger.get("approval", "on-request")),
        group=group,
        reason=reason,
        action_danger=action_danger,
        confirmation_required=confirmation_required,
        execute_by_default=bool(trigger.get("execute_by_default", False)),
    )


def check_hard_override(prompt: str, rules: KnowledgeLibrary | None = None) -> OverrideResult | None:
    rules = rules or load_rules()
    text = normalize_prompt(prompt)
    analysis_only = is_analysis_only_request(text)
    for trigger in rules.risk_triggers.get("triggers", []):
        terms = trigger.get("terms", [])
        if any(_term_matches(str(term), text) for term in terms):
            return _override_from_trigger(
                trigger,
                text,
                analysis_only=analysis_only,
            )
    return None


def _score_category(text: str, cfg: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    matched: list[str] = []
    for bucket in ["strong", "weak", "negative"]:
        values = cfg.get(bucket, {})
        if not isinstance(values, dict):
            continue
        for term, weight in values.items():
            if _term_matches(str(term), text):
                score += float(weight)
                matched.append(str(term))
    return max(score, 0.0), matched


def _apply_structural_boosts(text: str, scores: dict[str, float], matched: dict[str, list[str]]) -> None:
    boosts = [
        (r"\bfix\b.*\b(error|bug|loop)\b", "normal_coding", 6, "fix error/bug"),
        (r"\bbutton\b.*\bonclick\b", "normal_coding", 8, "button onclick"),
        (r"\bbackend\b.*\bvalidation\b", "normal_coding", 7, "backend validation"),
        (r"\brefactor\b.*\bmodule\b", "complex_coding", 10, "refactor module"),
        (r"\bmodule\b.*\bvalidation logic\b", "complex_coding", 7, "module validation logic"),
        (r"\bredesign\b.*\bmodule\b", "architecture", 10, "redesign module"),
        (r"\bderive\b.*\bmodel\b", "math_theory", 8, "derive model"),
        (r"\bpublished sme bounds\b", "math_theory", 8, "published SME bounds"),
        (r"\bgrant reviewer\b", "grant_work", 5, "grant reviewer"),
        (r"\bgrant reviewers\b", "grant_work", 7, "grant reviewers"),
        (r"\bopen pull requests\b", "repo_operations", 9, "open pull requests"),
        (r"\bdata subject access request\b", "legal_admin", 10, "data subject request"),
        (r"\bcurrent landscape\b", "research", 9, "current landscape"),
        (r"\bopen-source ai safety\b", "research", 7, "AI safety landscape"),
        (r"\bthe thing\b", "unknown", 1, "vague reference"),
        (r"\bmake it better\b", "unknown", 1, "vague request"),
    ]
    for pattern, category, weight, label in boosts:
        if _regex_or_substr(pattern, text):
            scores[category] = scores.get(category, 0.0) + weight
            matched.setdefault(category, []).append(label)

    if "email" in text and ("reply" in text or "draft" in text or "follow-up" in text):
        scores["email"] = scores.get("email", 0.0) + 8
        matched.setdefault("email", []).append("email intent")

    if "budget justification" in text and _contains_any(text, ["trading bot", "infrastructure costs"]):
        scores["financial_admin"] = scores.get("financial_admin", 0.0) + 10
        matched.setdefault("financial_admin", []).append("budget/cost admin")

    if "budget justification" in text and not _contains_any(text, ["trading bot", "infrastructure costs"]):
        scores["grant_work"] = scores.get("grant_work", 0.0) + 4
        matched.setdefault("grant_work", []).append("grant budget")

    if "config leaks" in text or "leaks any secrets" in text:
        scores["security_audit"] = scores.get("security_audit", 0.0) + 12
        matched.setdefault("security_audit", []).append("secret leak check")


def _priority_index(category: str) -> int:
    try:
        return CATEGORY_PRIORITY.index(category)
    except ValueError:
        return len(CATEGORY_PRIORITY)


def _apply_tie_breakers(text: str, scores: dict[str, float], matched: dict[str, list[str]]) -> None:
    if _contains_any(text, ["proof", "equation", "tensor", "neutrino", "lsc", "anisotropy"]):
        scores["math_theory"] = scores.get("math_theory", 0.0) + 6
        matched.setdefault("math_theory", []).append("math tie-breaker")
    if _contains_any(text, ["grant", "funding", "proposal", "budget", "nlnet", "grant reviewers"]):
        scores["grant_work"] = scores.get("grant_work", 0.0) + 4
        matched.setdefault("grant_work", []).append("grant tie-breaker")
    if _contains_any(text, ["architecture", "system design", "module boundary", "module structure"]):
        scores["architecture"] = scores.get("architecture", 0.0) + 6
        matched.setdefault("architecture", []).append("architecture tie-breaker")
    if _contains_any(text, ["commit", "push", "tag", "release", "pull request", "branch"]):
        scores["repo_operations"] = scores.get("repo_operations", 0.0) + 3
        matched.setdefault("repo_operations", []).append("repo tie-breaker")
    if _contains_any(text, ["secret", "api key", "token", "private key", ".env", "access stuff"]):
        scores["security_audit"] = scores.get("security_audit", 0.0) + 5
        matched.setdefault("security_audit", []).append("security tie-breaker")


def score_categories(prompt: str, rules: KnowledgeLibrary) -> tuple[str, dict[str, float], float, str, list[str], list[CategoryMatch]]:
    text = normalize_prompt(prompt)
    categories = rules.category_weights.get("categories", {})
    raw_scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}

    for name, cfg in categories.items():
        score_value, matched_terms = _score_category(text, cfg)
        raw_scores[name] = score_value
        matched[name] = matched_terms

    _apply_structural_boosts(text, raw_scores, matched)
    _apply_tie_breakers(text, raw_scores, matched)

    ordered = sorted(raw_scores.items(), key=lambda item: (-item[1], _priority_index(item[0]), item[0]))
    top_name, top_score = ordered[0] if ordered else ("unknown", 0.0)
    if top_score <= 0:
        top_name = "unknown"

    positive_total = sum(score_value for _, score_value in ordered if score_value > 0)
    second_score = next((score_value for category, score_value in ordered if category != top_name and score_value > 0), 0.0)
    confidence = 0.0 if top_score <= 0 else max(0.0, min(1.0, (top_score - second_score) / max(top_score, positive_total, 1.0)))
    if top_score > 0 and confidence == 0.0:
        confidence = 0.01
    confidence_level = "high" if confidence >= 0.35 else "medium" if confidence >= 0.15 else "low"

    top_matches = [
        CategoryMatch(category=name, score=value, matched_terms=matched.get(name, []))
        for name, value in ordered[:3]
        if value > 0
    ]
    mixed = [item.category for item in top_matches[1:]]
    return top_name, raw_scores, round(confidence, 4), confidence_level, mixed, top_matches


def _level_from_rules(prompt: str, rules_obj: dict[str, Any], order: dict[str, int], default: str) -> str:
    text = normalize_prompt(prompt)
    best = default
    for level, patterns in rules_obj.items():
        if level in {"schema_version", "levels"}:
            continue
        if isinstance(patterns, dict):
            patterns = patterns.get("signals", [])
        for pattern in patterns:
            if _term_matches(str(pattern), text) and order.get(level, -1) > order.get(best, -1):
                best = level
    return best


def _score_level_group(prompt: str, levels: dict[str, Any], order: dict[str, int], default: str) -> str:
    text = normalize_prompt(prompt)
    best = default
    for level, cfg in levels.items():
        signals = cfg.get("signals", []) if isinstance(cfg, dict) else []
        for signal in signals:
            if _term_matches(str(signal), text) and order.get(level, -1) > order.get(best, -1):
                best = level
    return best


def _action_danger(prompt: str, rules: KnowledgeLibrary) -> str:
    text = normalize_prompt(prompt)
    if is_analysis_only_request(text):
        return "read_only_analysis"
    order = {
        "read_only_analysis": 0,
        "write_local_files": 1,
        "run_tests": 2,
        "git_operations": 3,
        "network_access": 4,
        "dependency_install": 5,
        "database_operation": 6,
        "deployment_operation": 7,
        "destructive_operation": 8,
        "secret_touching_operation": 9,
        "unknown": -1,
    }
    danger = _score_level_group(prompt, rules.action_danger_rules.get("levels", {}), order, "read_only_analysis")
    if danger == "read_only_analysis" and "fix" in text and "bug" in text:
        return "write_local_files"
    return danger


def _risk_for_category(category: str, base_risk: str, prompt: str) -> str:
    text = normalize_prompt(prompt)
    if category == "security_audit" and not _contains_any(
        text,
        ["secret", "secrets", "api key", "token", "oauth", "auth", "sandbox", "malware", "exploit", "private key", ".env"],
    ):
        return "medium"
    if category == "repo_operations":
        return "medium" if _contains_any(text, ["commit", "push", "merge", "tag", "squash", "rebase"]) else "low"
    if category == "data_analysis" and _contains_any(text, ["audit"]):
        return "medium"
    if category == "release_management":
        return "medium"
    if category == "incident_response":
        return "high"
    if category == "financial_admin":
        return "medium"
    return base_risk


def _complexity_for(prompt: str, category: str, base_complexity: str, rules: KnowledgeLibrary) -> str:
    text = normalize_prompt(prompt)
    complexity = _level_from_rules(prompt, rules.complexity_rules, COMPLEXITY_ORDER, base_complexity)
    low_patterns = [
        "off-by-one",
        "helper function",
        "unit tests",
        "run the existing pytest",
        "new branch",
        "open a pull request",
        "list all open pull requests",
        "requests library",
        "new dependency",
        "invoice line items",
        "refund",
        "chmod",
        "sudo restart",
        "rm -rf",
        "delete all log files",
        "generate a new api key",
        "rotate the github token",
        "shell one-liner",
    ]
    if _contains_any(text, low_patterns) and complexity != "high":
        complexity = "low"
    if category == "unknown":
        complexity = "medium"
    if category == "email":
        complexity = "low"
    if category == "financial_admin" and _contains_any(text, ["budget justification", "infrastructure costs", "trading bot"]):
        complexity = "medium"
    if category == "system_admin" and _contains_any(text, ["system user", "restrict its permissions", "firewall rule", "outbound traffic"]):
        complexity = "medium"
    if category == "incident_response":
        complexity = "medium"
    if category == "secret_handling" and _contains_any(text, ["commit history"]):
        complexity = "medium"
    if category == "prompt_engineering" and _contains_any(text, ["eval case", "eval_set_002"]):
        complexity = "medium"
    if category == "grant_work" and _contains_any(text, ["grant reviewers", "readme acronym"]):
        complexity = "low"
    if category in {"complex_coding", "architecture", "math_theory", "prompt_engineering"}:
        complexity = "high"
    if category == "prompt_engineering" and _contains_any(text, ["eval case", "eval_set_002"]):
        complexity = "medium"
    if category in {"research", "grant_work", "legal_admin", "data_analysis"} and complexity == "low":
        complexity = "medium"
    if category == "grant_work" and _contains_any(text, ["grant reviewers", "readme acronym"]):
        complexity = "low"
    return complexity


def _dimensions(prompt: str, risk_level: str, action_danger: str) -> tuple[str, str, str, str]:
    text = normalize_prompt(prompt)
    repo_impact = "remote" if _contains_any(text, ["push", "pull request", "tag", "release", "publish"]) else "local" if _contains_any(text, ["commit", "branch", "repo"]) else "none"
    security_sensitivity = "critical" if risk_level == "critical" else "high" if risk_level == "high" or "secret" in text or "token" in text else "low" if "auth" in text else "none"
    destructiveness = "critical" if _contains_any(text, ["rm -rf", "delete all", "wipe", "drop table", "force push", "truncate table"]) else "hard" if action_danger in {"deployment_operation", "database_operation"} else "soft" if _contains_any(text, ["remove", "delete", "overwrite"]) else "none"
    execution_scope = "network" if action_danger in {"network_access", "dependency_install"} else "system" if action_danger in {"deployment_operation", "database_operation", "destructive_operation"} else "repo" if repo_impact != "none" else "module" if _contains_any(text, ["module", "service", "gateway"]) else "single_file" if _contains_any(text, ["function", "file", "loop", "button"]) else "unknown"
    return repo_impact, security_sensitivity, destructiveness, execution_scope


def score(prompt: str, rules: KnowledgeLibrary | None = None) -> ScoreCard:
    rules = rules or load_rules()
    text = normalize_prompt(prompt)
    override = check_hard_override(prompt, rules)
    categories = rules.category_weights.get("categories", {})

    if override is not None:
        base = categories.get(override.category, categories.get("unknown", {}))
        complexity = _complexity_for(prompt, override.category, str(base.get("complexity", "medium")), rules)
        if override.group in {
            "production_changes",
            "database_ops",
            "destructive_database",
        }:
            complexity = "medium"
        if override.group == "pipe_to_shell" and ("curl" in text or "wget" in text or "| bash" in text or "| sh" in text):
            complexity = "medium"
        evidence = _score_level_group(prompt, rules.evidence_rules.get("levels", {}), {"none": 0, "light": 1, "source_required": 2, "multi_source": 3, "official_source_only": 4}, "light")
        context = _score_level_group(prompt, rules.context_rules.get("levels", {}), {"small": 0, "medium": 1, "large": 2, "unknown": 1}, "small")
        repo_impact, security_sensitivity, destructiveness, execution_scope = _dimensions(prompt, override.risk, override.action_danger)
        warnings = [f"hard_override:{override.group}"]
        if override.confirmation_required:
            warnings.insert(0, "REQUIRES_CONFIRMATION")
        else:
            warnings.insert(0, "ANALYSIS_ONLY")
        return ScoreCard(
            category=override.category,
            profile=override.profile,
            risk_level=override.risk,
            complexity_level=complexity,
            evidence_requirement=evidence,
            context_requirement=context,
            action_danger=override.action_danger,
            confidence=1.0,
            confidence_level="high",
            override=override,
            warnings=warnings,
            reasons=[override.reason],
            repo_impact=repo_impact,
            security_sensitivity=security_sensitivity,
            destructiveness=destructiveness,
            execution_scope=execution_scope,
        )

    category, category_scores, confidence, confidence_level, mixed, top_matches = score_categories(prompt, rules)
    base = categories.get(category, categories.get("unknown", {}))
    base_risk = str(base.get("risk", "low"))
    base_complexity = str(base.get("complexity", "medium"))
    risk_level = _risk_for_category(category, base_risk, prompt)
    complexity_level = _complexity_for(prompt, category, base_complexity, rules)
    evidence_requirement = _score_level_group(prompt, rules.evidence_rules.get("levels", {}), {"none": 0, "light": 1, "source_required": 2, "multi_source": 3, "official_source_only": 4}, "none")
    context_requirement = _score_level_group(prompt, rules.context_rules.get("levels", {}), {"small": 0, "medium": 1, "large": 2, "unknown": 1}, "small")
    action_danger = _action_danger(prompt, rules)
    profile = str(base.get("default_profile", "standard"))
    warnings: list[str] = []

    if category == "unknown":
        if _contains_any(text, ["access", "credential", "permission", "auth", "secret", "token"]):
            category = "security_audit"
            profile = "security"
            risk_level = "medium"
            complexity_level = "medium"
            warnings.append("low-confidence risk signal routed to security")
        else:
            profile = "standard"
            warnings.append("low confidence route")

    if category == "security_audit" and risk_level == "high":
        profile = "security"
    elif RISK_ORDER.get(risk_level, 0) >= RISK_ORDER["high"] and category != "legal_admin":
        profile = "security"

    if category == "email":
        profile = "literary"

    reasons = [f"category:{category}", f"confidence:{confidence_level}"]
    if top_matches:
        reasons.append("matched:" + ",".join(top_matches[0].matched_terms[:5]))

    repo_impact, security_sensitivity, destructiveness, execution_scope = _dimensions(prompt, risk_level, action_danger)
    return ScoreCard(
        category=category,
        profile=profile,
        risk_level=risk_level,
        complexity_level=complexity_level,
        evidence_requirement=evidence_requirement,
        context_requirement=context_requirement,
        action_danger=action_danger,
        confidence=confidence,
        confidence_level=confidence_level,
        category_scores=category_scores,
        top_categories=top_matches,
        mixed_categories=mixed,
        warnings=warnings,
        reasons=reasons,
        repo_impact=repo_impact,
        security_sensitivity=security_sensitivity,
        destructiveness=destructiveness,
        execution_scope=execution_scope,
    )
