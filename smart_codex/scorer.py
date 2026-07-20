"""JSON-driven scoring engine for Codex Patch Smart Router."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import re
from typing import Any

from .knowledge import KnowledgeLibrary, load_rules
from .preprocessor import (
    PromptSemantics,
    analyze_prompt_semantics,
    is_document_comparison,
    normalize_prompt,
)


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
COMPLEXITY_ORDER = {"low": 0, "medium": 1, "high": 2}
TASK_SUBDOMAINS = frozenset(
    {
        "document_comparison",
        "read_only_analysis",
        "test_execution",
        "code_generation",
        "code_modification",
        "security_audit",
        "architecture_design",
        "general_research",
    }
)

_CODE_MODIFICATION_RE = re.compile(
    r"\b(?:change|edit|fix|modify|patch|refactor|repair|rename|replace|update|"
    r"delete|remove|move|append|overwrite|save|commit|push|merge|"
    r"zapisz|edytuj|zmodyfikuj|zmień|zmien|napraw|usuń|usun|przenieś|"
    r"przenies|dopisz|nadpisz|zacommituj|wypchnij)\b",
    flags=re.IGNORECASE,
)
_CODE_GENERATION_RE = re.compile(
    r"\b(?:add|create|generate|implement|write|utwórz|utworz)\b",
    flags=re.IGNORECASE,
)
_NEGATED_CODE_CHANGE_RE = re.compile(
    r"\b(?:modify\s+nothing|(?:do\s+not|don['’]t|never)\s+"
    r"(?:append|change|commit|create|delete|edit|generate|implement|merge|modify|"
    r"move|overwrite|patch|push|refactor|remove|rename|repair|replace|save|"
    r"update|write)|without\s+(?:appending|changing|creating|deleting|editing|"
    r"modifying|moving|overwriting|removing|renaming|saving|writing)|"
    r"(?:nie|bez)\s+(?:dopisywania|edycji|modyfikowania|naprawiania|"
    r"nadpisywania|przenoszenia|usuwania|zapisywania|zmieniania)|"
    r"no\s+(?:code|file|repository)\s+changes?)\b",
    flags=re.IGNORECASE,
)
_EXTERNAL_RESEARCH_RE = re.compile(
    r"\b(?:api|browse|browser|download|fetch|internet|network|online|web|"
    r"search\s+the\s+web|web\s+research|external\s+(?:api|service|source)|"
    r"(?:call|query|request|use)\s+(?:an\s+|the\s+)?api|current\s+landscape|"
    r"latest\s+(?:information|sources|documentation)|zewnętrzne\s+api|"
    r"zewnetrzne\s+api|przeszukaj\s+internet|pobierz|wyślij\s+żądanie|"
    r"wyslij\s+zadanie)\b|https?://",
    flags=re.IGNORECASE,
)
_SENSITIVE_ANALYSIS_SUBJECT_RE = re.compile(
    r"\b(?:security|privacy|compliance|incident(?:[- ]response)?|credentials?|"
    r"authorization|authentication|secret(?:[- ]handling|s)?|threats?)\b|"
    r"\b(?:bezpieczeństw\w*|bezpieczenstw\w*|prywatnoś\w*|prywatnos\w*|"
    r"zgodnoś\w*|zgodnos\w*|incydent\w*|poświadcze\w*|poswiadcze\w*|"
    r"autoryzac\w*|uwierzyteln\w*|sekret\w*|zagroże\w*|zagroze\w*)\b",
    flags=re.IGNORECASE,
)
_INCIDENT_ANALYSIS_RE = re.compile(
    r"\b(?:incident|incident[- ]response|incydent\w*)\b",
    flags=re.IGNORECASE,
)
_COMPLIANCE_ANALYSIS_RE = re.compile(
    r"\b(?:compliance|zgodnoś\w*|zgodnos\w*)\b",
    flags=re.IGNORECASE,
)
_NON_COMPLIANCE_SECURITY_SUBJECT_RE = re.compile(
    r"\b(?:security|privacy|incident(?:[- ]response)?|credentials?|"
    r"authorization|authentication|secret(?:[- ]handling|s)?|threats?)\b|"
    r"\b(?:bezpieczeństw\w*|bezpieczenstw\w*|prywatnoś\w*|prywatnos\w*|"
    r"incydent\w*|poświadcze\w*|poswiadcze\w*|autoryzac\w*|"
    r"uwierzyteln\w*|sekret\w*|zagroże\w*|zagroze\w*)\b",
    flags=re.IGNORECASE,
)
_SENSITIVE_ANALYSIS_ACTION_RE = re.compile(
    r"\b(?:audit|review|analy[sz]e|assess|compare|comparison|investigate|"
    r"inspect|summarize|summary|list|report|identify|explain|describe|"
    r"differences|findings|"
    r"przeprowadź|przeprowadz|audyt|porównaj|porownaj|przeanalizuj|"
    r"oceń|ocen|zbadaj|podsumuj|podaj|wymień|wymien)\b",
    flags=re.IGNORECASE,
)
_SENSITIVE_ANALYSIS_COMPOUND_RE = re.compile(
    r"\b(?:security\s+controls?|privacy\s+protections?|compliance\s+review|"
    r"incident\s+(?:report|investigation|response)|authentication\s+(?:and\s+)?"
    r"authorization\s+(?:rules?|controls?)|secret[- ]handling|threat\s+analysis)\b|"
    r"\b(?:zasad\w*\s+prywatnoś\w*|zasad\w*\s+prywatnos\w*|"
    r"audyt\w*\s+bezpieczeństw\w*|audyt\w*\s+bezpieczenstw\w*)\b",
    flags=re.IGNORECASE,
)
_ARCHITECTURE_SYNTHESIS_RE = re.compile(
    r"\b(?:architecture|architectural|system\s+design|broad\s+synthesis|"
    r"synthesize|synthesis|architektura|projekt\s+systemu|synteza)\b",
    flags=re.IGNORECASE,
)
_EXHAUSTIVE_SCOPE_RE = re.compile(
    r"\b(?:exhaustive(?:ly)?|complete(?:ly)?|every\s+clause|clause[- ]by[- ]clause|"
    r"all\s+files|entire|whole|large\s+corpus|pełn\w*|pel[nł]\w*|każd\w*\s+"
    r"(?:klauzul|plik)|cał\w*)\b",
    flags=re.IGNORECASE,
)
_LARGE_CORPUS_RE = re.compile(
    r"\b(?:large|huge|entire|whole|all)\s+(?:corpus|dataset|document\s+set|"
    r"knowledge\s+base)|\b(?:hundreds|thousands|millions)\s+of\s+(?:files|documents)\b",
    flags=re.IGNORECASE,
)
_COMPLEX_TOOL_CHAIN_RE = re.compile(
    r"\b(?:pipeline|tool\s+chain|multiple\s+tools|install|compile|build\s+and\s+run|"
    r"shell\s+script|docker|container)\b",
    flags=re.IGNORECASE,
)
_BOUNDED_OUTPUT_RE = re.compile(
    r"\b(?:(?:brief|concise|short)\s+(?:summary|comparison|report)|"
    r"summar(?:ize|y)\s+(?:briefly|concisely)|"
    r"(?:report|list|give|identify)\s+(?:exactly\s+|at\s+most\s+)?"
    r"(?:one|two|three|four|five|\d+)\s+"
    r"(?:differences|points|items|bullets|findings|sentences|paragraphs)|"
    r"(?:exactly|at\s+most)\s+(?:one|two|three|four|five|\d+)\s+"
    r"(?:differences|points|items|bullets|findings|sentences|paragraphs)|"
    r"(?:one|two|three|four|five|\d+)\s+(?:differences|points|bullets))\b",
    flags=re.IGNORECASE,
)
_DOCUMENT_READ_RE = re.compile(
    r"\b(?:compare|comparison|differences?|read|review|summarize|summary|"
    r"inspect|describe|przeczytaj|porównaj|porownaj|podsumuj)\b",
    flags=re.IGNORECASE,
)
_KNOWN_TOOL_RE = re.compile(
    r"\b(?:awk|curl|git|grep|jq|make|pytest|sed|wget)\b",
    flags=re.IGNORECASE,
)


def _has_code_change_intent(text: str) -> bool:
    actionable = _NEGATED_CODE_CHANGE_RE.sub(" ", text)
    return (
        _CODE_MODIFICATION_RE.search(actionable) is not None
        or _CODE_GENERATION_RE.search(actionable) is not None
    )


def _has_multi_tool_workflow(text: str) -> bool:
    if _COMPLEX_TOOL_CHAIN_RE.search(text) is not None:
        return True
    return len({match.group(0).casefold() for match in _KNOWN_TOOL_RE.finditer(text)}) >= 2


def _is_sensitive_analysis(semantics: PromptSemantics, text: str) -> bool:
    """Use only internal semantic evidence; never emit filenames or fragments."""

    if semantics.sensitive_document_reference:
        return True
    return bool(
        _SENSITIVE_ANALYSIS_SUBJECT_RE.search(text)
        and (
            _SENSITIVE_ANALYSIS_ACTION_RE.search(text)
            or _SENSITIVE_ANALYSIS_COMPOUND_RE.search(text)
        )
    )

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
    "nie uruchamiaj",
    "nie wykonuj",
    "nie używaj",
    "nie uzywaj",
    "bez uruchamiania",
    "bez wykonywania",
)

ANALYSIS_LEAD_RE = re.compile(
    r"^(?:please\s+)?(?:explain|describe|review|analy[sz]e|audit|inspect|"
    r"simulate|assess|evaluate|show\s+where|why\b|what\s+does\b|"
    r"wyjaśnij|wyjasnij|opisz|udokumentuj|przeanalizuj|"
    r"dokumentacja\s+(?:zawiera|mówi|mowi))"
)

FOLLOWED_BY_EXECUTION_RE = re.compile(
    r"\b(?:then|and)\s+(?:run|execute|apply|perform|delete|remove|upload|"
    r"publish|disable|overwrite|replace|change|stop|truncate|drop)\b"
)

DIRECT_SECRET_ACTION_RE = re.compile(
    r"\b(?:access|add|cat|copy|cp|create|display|dump|edit|export|extract|"
    r"generate|move|mv|modify|open|patch|print|read|remove|retrieve|reveal|"
    r"rotate|show|store|update|upload|write)\b"
)

DIRECT_SECRET_TARGET_RE = re.compile(
    r"\b(?:passwords?|credentials?|secrets?|tokens?|api\s+keys?|"
    r"private\s+keys?|ssh\s+keys?|cookies?|auth(?:entication)?(?:\.json)?|"
    r"credential\s+stores?)\b|(?<!\w)\.env(?!\w)|\.codex/auth\.json|"
    r"\.ssh/id_(?:rsa|ed25519|ecdsa|dsa)",
    flags=re.IGNORECASE,
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
    safety_constraints: list[str] = field(default_factory=list)
    source: str = "knowledge_library"
    task_subdomain: str | None = None
    semantic_reason_codes: list[str] = field(default_factory=list)


@lru_cache(maxsize=2048)
def _compiled_rule_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, flags=re.IGNORECASE)


def _regex_or_substr(pattern: str, text: str) -> bool:
    try:
        return _compiled_rule_pattern(pattern).search(text) is not None
    except re.error:
        return pattern.lower() in text


def _term_matches(term: str, text: str) -> bool:
    lowered = term.lower()
    if any(char in lowered for char in "\\.*+?[](){}|^$"):
        return _regex_or_substr(lowered, text)
    if " " in lowered or "_" in lowered or "-" in lowered or "." in lowered:
        return lowered in text
    # Most rule terms are absent from a given prompt. Avoid compiling a word
    # boundary expression when the required literal stem cannot occur; this
    # preserves matching semantics while keeping first-turn routing bounded.
    if lowered not in text:
        return False
    plural = "" if lowered.endswith("s") or lowered in {"service"} else "s?"
    return (
        _compiled_rule_pattern(rf"\b{re.escape(lowered)}{plural}\b").search(text)
        is not None
    )


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
    return (
        DIRECT_SECRET_ACTION_RE.search(text) is not None
        and DIRECT_SECRET_TARGET_RE.search(text) is not None
    )


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
        if not _has_direct_secret_intent(text):
            category = "security_audit"
            risk = "high"
            profile = "security"
            reason = f"{reason}; read-only secret/auth analysis"
            action_danger = "read_only_analysis"
            confirmation_required = False
        else:
            category = "secret_handling"
            risk = "critical"
            profile = "security"
            action_danger = "secret_touching_operation"
            confirmation_required = True

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
    semantics = analyze_prompt_semantics(prompt)
    text = semantics.actionable_text
    analysis_only = is_analysis_only_request(prompt)
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


def _apply_structural_boosts(
    text: str,
    scores: dict[str, float],
    matched: dict[str, list[str]],
    semantics: PromptSemantics,
) -> None:
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

    if semantics.test_intent in {"positive", "mixed"}:
        scores["testing"] = scores.get("testing", 0.0) + 12
        matched.setdefault("testing", []).append("positive_test_action")

    if _is_sensitive_analysis(semantics, text):
        if _INCIDENT_ANALYSIS_RE.search(text) is not None:
            scores["incident_response"] = scores.get("incident_response", 0.0) + 18
            matched.setdefault("incident_response", []).append(
                "sensitive_incident_analysis"
            )
        elif not (
            _COMPLIANCE_ANALYSIS_RE.search(text) is not None
            and _NON_COMPLIANCE_SECURITY_SUBJECT_RE.search(text) is None
        ):
            scores["security_audit"] = scores.get("security_audit", 0.0) + 18
            matched.setdefault("security_audit", []).append(
                "sensitive_read_only_analysis"
            )

    if is_document_comparison(semantics):
        scores["research"] = scores.get("research", 0.0) + 12
        matched.setdefault("research", []).append("document_comparison")


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


def score_categories(
    prompt: str,
    rules: KnowledgeLibrary,
    *,
    semantics: PromptSemantics | None = None,
) -> tuple[str, dict[str, float], float, str, list[str], list[CategoryMatch]]:
    semantics = semantics or analyze_prompt_semantics(prompt)
    text = normalize_prompt(semantics.actionable_text)
    categories = rules.category_weights.get("categories", {})
    raw_scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}

    for name, cfg in categories.items():
        score_value, matched_terms = _score_category(text, cfg)
        raw_scores[name] = score_value
        matched[name] = matched_terms

    _apply_structural_boosts(text, raw_scores, matched, semantics)
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


def _action_danger(
    prompt: str,
    rules: KnowledgeLibrary,
    *,
    semantics: PromptSemantics | None = None,
) -> str:
    text = normalize_prompt(prompt)
    semantics = semantics or analyze_prompt_semantics(prompt)
    order = {
        "read_only_analysis": 0,
        "write_local_files": 1,
        "run_tests": 2,
        "git_operations": 3,
        "network_access": 4,
        "external_service_action": 5,
        "dependency_install": 6,
        "database_operation": 7,
        "deployment_operation": 8,
        "destructive_operation": 9,
        "secret_touching_operation": 10,
        "unknown": -1,
    }
    danger = _score_level_group(prompt, rules.action_danger_rules.get("levels", {}), order, "read_only_analysis")
    if semantics.test_intent in {"positive", "mixed"} and order.get(danger, -1) <= order["run_tests"]:
        return "run_tests"
    if is_analysis_only_request(text):
        return "read_only_analysis"
    if danger == "run_tests" and semantics.test_intent not in {"positive", "mixed"}:
        if _has_code_change_intent(text):
            return "write_local_files"
        return "read_only_analysis"
    actionable_change = _NEGATED_CODE_CHANGE_RE.sub(" ", text)
    if (
        danger == "read_only_analysis"
        and _CODE_MODIFICATION_RE.search(actionable_change) is not None
    ):
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


def _is_bounded_read_only_document_task(
    semantics: PromptSemantics,
    *,
    category: str,
    action_danger: str,
    risk_level: str,
    rules: KnowledgeLibrary,
    base_complexity: str | None = None,
    current_complexity: str | None = None,
) -> bool:
    text = semantics.actionable_text
    if not (
        1 <= semantics.explicit_file_count <= 2
        and semantics.explicit_document_count == semantics.explicit_file_count
        and action_danger == "read_only_analysis"
        and semantics.test_intent not in {"positive", "mixed"}
        and category in {"documentation", "research", "simple_text"}
        and risk_level == "low"
        and _DOCUMENT_READ_RE.search(text) is not None
        and _BOUNDED_OUTPUT_RE.search(text) is not None
    ):
        return False
    if not (
        is_document_comparison(semantics)
        or category in {"documentation", "simple_text"}
        or re.search(r"\b(?:read|review|summarize|summary|inspect)\b", text)
    ):
        return False
    if (
        _has_code_change_intent(text)
        or _EXTERNAL_RESEARCH_RE.search(text)
        or _is_sensitive_analysis(semantics, text)
        or _ARCHITECTURE_SYNTHESIS_RE.search(text)
        or _EXHAUSTIVE_SCOPE_RE.search(text)
        or _LARGE_CORPUS_RE.search(text)
        or _has_multi_tool_workflow(text)
    ):
        return False
    for level in ("medium", "high"):
        patterns = rules.complexity_rules.get(level, [])
        if isinstance(patterns, dict):
            patterns = patterns.get("signals", [])
        if any(_term_matches(str(pattern), text) for pattern in patterns):
            return False
    if current_complexity == "high":
        return False
    if (
        current_complexity == "medium"
        and base_complexity is not None
        and base_complexity != "medium"
    ):
        return False
    return True


def _complexity_for(
    prompt: str,
    category: str,
    base_complexity: str,
    rules: KnowledgeLibrary,
    *,
    semantics: PromptSemantics | None = None,
    action_danger: str = "read_only_analysis",
    risk_level: str = "low",
) -> str:
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
    if (
        semantics is not None
        and 1 <= semantics.explicit_document_count <= 2
        and (
            _is_sensitive_analysis(semantics, text)
            or _EXTERNAL_RESEARCH_RE.search(text)
            or _EXHAUSTIVE_SCOPE_RE.search(text)
            or _has_multi_tool_workflow(text)
        )
        and complexity == "low"
    ):
        complexity = "medium"
    if (
        semantics is not None
        and _is_sensitive_analysis(semantics, text)
        and complexity == "low"
    ):
        complexity = "medium"
    if semantics is not None and _is_bounded_read_only_document_task(
        semantics,
        category=category,
        action_danger=action_danger,
        risk_level=risk_level,
        rules=rules,
        base_complexity=base_complexity,
        current_complexity=complexity,
    ):
        complexity = "low"
    return complexity


def _dimensions(
    prompt: str,
    risk_level: str,
    action_danger: str,
    *,
    semantics: PromptSemantics | None = None,
) -> tuple[str, str, str, str]:
    text = normalize_prompt(prompt)
    semantics = semantics or analyze_prompt_semantics(prompt)
    repo_impact = "remote" if _contains_any(text, ["push", "pull request", "tag", "release", "publish"]) else "local" if _contains_any(text, ["commit", "branch", "repo"]) else "none"
    security_sensitivity = (
        "critical"
        if risk_level == "critical"
        else "high"
        if risk_level == "high" or _is_sensitive_analysis(semantics, text)
        else "low"
        if "auth" in text
        else "none"
    )
    destructiveness = "critical" if _contains_any(text, ["rm -rf", "delete all", "wipe", "drop table", "force push", "truncate table"]) else "hard" if action_danger in {"deployment_operation", "database_operation"} else "soft" if _contains_any(text, ["remove", "delete", "overwrite"]) else "none"
    if action_danger in {"network_access", "external_service_action", "dependency_install"}:
        execution_scope = "network"
    elif action_danger in {"deployment_operation", "database_operation", "destructive_operation"}:
        execution_scope = "system"
    elif semantics.repository_wide or repo_impact == "remote" or action_danger == "git_operations":
        execution_scope = "repo"
    elif semantics.explicit_file_count >= 2:
        execution_scope = "module"
    elif semantics.explicit_file_count == 1:
        execution_scope = "single_file"
    elif _contains_any(text, ["module", "service", "gateway"]):
        execution_scope = "module"
    else:
        execution_scope = "unknown"
    return repo_impact, security_sensitivity, destructiveness, execution_scope


def _task_subdomain(
    semantics: PromptSemantics,
    *,
    category: str,
    action_danger: str,
) -> str | None:
    if category in {"security_audit", "secret_handling", "incident_response"}:
        value = "security_audit"
    elif category == "architecture":
        value = "architecture_design"
    elif semantics.test_intent in {"positive", "mixed"}:
        value = "test_execution"
    elif is_document_comparison(semantics):
        value = "document_comparison"
    elif category in {"normal_coding", "complex_coding", "debugging", "dependency_management"}:
        code_change_text = _NEGATED_CODE_CHANGE_RE.sub(" ", semantics.actionable_text)
        if _CODE_MODIFICATION_RE.search(code_change_text):
            value = "code_modification"
        elif _CODE_GENERATION_RE.search(code_change_text):
            value = "code_generation"
        elif action_danger == "read_only_analysis":
            value = "read_only_analysis"
        else:
            return None
    elif category in {"research", "grant_work", "data_analysis"}:
        value = "general_research"
    elif action_danger == "read_only_analysis" and re.search(
        r"\b(?:analy[sz]e|audit|compare|describe|explain|inspect|read|review|summarize)\b",
        semantics.actionable_text,
    ):
        value = "read_only_analysis"
    else:
        return None
    if value not in TASK_SUBDOMAINS:
        raise ValueError("task subdomain is outside the controlled vocabulary")
    return value


def score(prompt: str, rules: KnowledgeLibrary | None = None) -> ScoreCard:
    rules = rules or load_rules()
    semantics = analyze_prompt_semantics(prompt)
    semantic_prompt = semantics.actionable_text
    text = normalize_prompt(semantic_prompt)
    override = check_hard_override(semantic_prompt, rules)
    categories = rules.category_weights.get("categories", {})

    if override is not None:
        base = categories.get(override.category, categories.get("unknown", {}))
        complexity = _complexity_for(
            semantic_prompt,
            override.category,
            str(base.get("complexity", "medium")),
            rules,
            semantics=semantics,
            action_danger=override.action_danger,
            risk_level=override.risk,
        )
        if override.group in {
            "production_changes",
            "database_ops",
            "destructive_database",
        }:
            complexity = "medium"
        if override.group == "pipe_to_shell" and ("curl" in text or "wget" in text or "| bash" in text or "| sh" in text):
            complexity = "medium"
        evidence = _score_level_group(semantic_prompt, rules.evidence_rules.get("levels", {}), {"none": 0, "light": 1, "source_required": 2, "multi_source": 3, "official_source_only": 4}, "light")
        context = _score_level_group(semantic_prompt, rules.context_rules.get("levels", {}), {"small": 0, "medium": 1, "large": 2, "unknown": 1}, "small")
        repo_impact, security_sensitivity, destructiveness, execution_scope = _dimensions(
            semantic_prompt,
            override.risk,
            override.action_danger,
            semantics=semantics,
        )
        task_subdomain = _task_subdomain(
            semantics,
            category=override.category,
            action_danger=override.action_danger,
        )
        semantic_reason_codes = list(semantics.reason_codes)
        if task_subdomain == "document_comparison":
            semantic_reason_codes.append("document_comparison_subdomain")
        if _is_bounded_read_only_document_task(
            semantics,
            category=override.category,
            action_danger=override.action_danger,
            risk_level=override.risk,
            rules=rules,
            base_complexity=str(base.get("complexity", "medium")),
            current_complexity=complexity,
        ):
            semantic_reason_codes.append("bounded_read_only_comparison")
        semantic_reason_codes = list(dict.fromkeys(semantic_reason_codes))
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
            reasons=[override.reason]
            + [f"semantic:{code}" for code in semantic_reason_codes],
            repo_impact=repo_impact,
            security_sensitivity=security_sensitivity,
            destructiveness=destructiveness,
            execution_scope=execution_scope,
            safety_constraints=list(semantics.safety_constraints),
            task_subdomain=task_subdomain,
            semantic_reason_codes=semantic_reason_codes,
        )

    category, category_scores, confidence, confidence_level, mixed, top_matches = score_categories(
        semantic_prompt,
        rules,
        semantics=semantics,
    )
    base = categories.get(category, categories.get("unknown", {}))
    base_risk = str(base.get("risk", "low"))
    base_complexity = str(base.get("complexity", "medium"))
    risk_level = _risk_for_category(category, base_risk, semantic_prompt)
    action_danger = _action_danger(semantic_prompt, rules, semantics=semantics)
    complexity_level = _complexity_for(
        semantic_prompt,
        category,
        base_complexity,
        rules,
        semantics=semantics,
        action_danger=action_danger,
        risk_level=risk_level,
    )
    evidence_requirement = _score_level_group(semantic_prompt, rules.evidence_rules.get("levels", {}), {"none": 0, "light": 1, "source_required": 2, "multi_source": 3, "official_source_only": 4}, "none")
    context_requirement = _score_level_group(semantic_prompt, rules.context_rules.get("levels", {}), {"small": 0, "medium": 1, "large": 2, "unknown": 1}, "small")
    profile = str(base.get("default_profile", "standard"))
    warnings: list[str] = []
    if semantics.safety_constraints:
        warnings.append("SAFETY_CONSTRAINTS_RECOGNIZED")

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
    reasons.extend(f"safety_constraint:{item}" for item in semantics.safety_constraints)
    if top_matches:
        reasons.append("matched:" + ",".join(top_matches[0].matched_terms[:5]))

    repo_impact, security_sensitivity, destructiveness, execution_scope = _dimensions(
        semantic_prompt,
        risk_level,
        action_danger,
        semantics=semantics,
    )
    task_subdomain = _task_subdomain(
        semantics,
        category=category,
        action_danger=action_danger,
    )
    semantic_reason_codes = list(semantics.reason_codes)
    if task_subdomain == "document_comparison":
        semantic_reason_codes.append("document_comparison_subdomain")
    if _is_bounded_read_only_document_task(
        semantics,
        category=category,
        action_danger=action_danger,
        risk_level=risk_level,
        rules=rules,
        base_complexity=base_complexity,
        current_complexity=complexity_level,
    ):
        semantic_reason_codes.append("bounded_read_only_comparison")
    semantic_reason_codes = list(dict.fromkeys(semantic_reason_codes))
    reasons.extend(f"semantic:{code}" for code in semantic_reason_codes)
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
        safety_constraints=list(semantics.safety_constraints),
        task_subdomain=task_subdomain,
        semantic_reason_codes=semantic_reason_codes,
    )
