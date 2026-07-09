from __future__ import annotations

from dataclasses import dataclass
import re


HIGH_RISK_PATTERNS = [
    (r"\bsecrets?\b", "secret material"),
    (r"\btokens?\b", "token material"),
    (r"\bauth\b", "auth material"),
    (r"\bpasswords?\b", "password material"),
    (r"\bapi\s+keys?\b", "api key material"),
    (r"\bmalware\b", "malware"),
    (r"\bexploit\b", "exploit"),
    (r"\bsandbox\b", "sandbox change or audit"),
    (r"\bpermissions?\b", "permission change or audit"),
    (r"\bdelete\b", "destructive delete request"),
    (r"\bremove\b", "destructive remove request"),
    (r"\bwipe\b", "destructive wipe request"),
    (r"\brm\s+-rf\b", "destructive rm -rf request"),
    (r"\bsudo\b", "privileged command"),
    (r"\bchmod\b", "permission command"),
    (r"\bchown\b", "ownership command"),
    (r"\bssh\s+keys?\b", "ssh key material"),
    (r"\bprivate\s+keys?\b", "private key material"),
    (r"(?<!\w)\.env(?!\w)", ".env material"),
    (r"\bcredentials?\b", "credential material"),
]

COMPLEXITY_HIGH_PATTERNS = [
    (r"\bmulti[-\s]?file\b", "multi-file work"),
    (r"\brefactor\b", "refactor"),
    (r"\barchitecture\b", "architecture"),
    (r"\bmigration\b", "migration"),
    (r"\bproof\b", "proof"),
    (r"\bneutrino\b", "neutrino"),
    (r"\bderivation\b", "derivation"),
]


@dataclass(frozen=True)
class RiskAssessment:
    risk: str
    complexity: str
    reasons: list[str]


def assess_risk(prompt: str, category: str) -> RiskAssessment:
    text = re.sub(r"\s+", " ", prompt.lower()).strip()
    reasons: list[str] = []

    risk = "low"
    for pattern, reason in HIGH_RISK_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            risk = "high"
            reasons.append(reason)

    if category == "security_audit":
        risk = "high"
        reasons.append("security audit category")
    elif category == "repo_operations" and risk != "high":
        risk = "medium"
        reasons.append("repo operation category")

    words = [word for word in re.split(r"\s+", text) if word]
    complexity = "low"
    if len(words) > 80:
        complexity = "medium"
        reasons.append("prompt longer than 80 words")

    for pattern, reason in COMPLEXITY_HIGH_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            complexity = "high"
            reasons.append(reason)

    if category in {"complex_coding", "architecture", "math_theory"}:
        complexity = "high"
        reasons.append(f"{category} category")
    elif category in {"research", "grant_work"} and complexity == "low":
        complexity = "medium"
        reasons.append(f"{category} category")

    if not reasons:
        reasons.append("no high-risk or high-complexity signals")

    return RiskAssessment(risk=risk, complexity=complexity, reasons=dedupe(reasons))


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

