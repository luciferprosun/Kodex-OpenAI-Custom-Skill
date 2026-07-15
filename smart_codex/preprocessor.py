
"""Prompt preprocessing for Codex Patch Smart Router.

V0 rule: preprocessing must not execute, inspect files, or mutate state.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RE = re.compile(r"\s+")

_SENSITIVE_OBJECT = (
    r"(?:passwords?|credentials?|secrets?|tokens?|access\s+tokens?|"
    r"refresh\s+tokens?|jwt\s+tokens?|api\s+keys?|private\s+keys?|"
    r"ssh\s+keys?|(?:saved\s+)?(?:browser\s+)?cookies?|"
    r"(?:auth(?:entication)?|login|credential)\s+(?:files?|data|stores?)|"
    r"auth(?:entication)?\.json|(?<!\w)\.env(?!\w)|"
    r"(?:~?/)?\.codex/auth\.json|"
    r"(?:~?/)?\.ssh/id_(?:rsa|ed25519|ecdsa|dsa))"
)
_SENSITIVE_OBJECT_LIST = (
    rf"{_SENSITIVE_OBJECT}"
    rf"(?:\s*,\s*(?:(?:and|or)\s+)?{_SENSITIVE_OBJECT}"
    rf"|\s+(?:and|or)\s+{_SENSITIVE_OBJECT})*"
)
_PROHIBITED_ACTION = (
    r"(?:access(?:ing)?|read(?:ing)?|inspect(?:ing)?|open(?:ing)?|"
    r"expos(?:e|ing)|log(?:ging)?|print(?:ing)?|show(?:ing)?|"
    r"export(?:ing)?|retriev(?:e|ing)|copy(?:ing)?|upload(?:ing)?|"
    r"touch(?:ing)?|view(?:ing)?|reveal(?:ing)?|disclos(?:e|ing)|"
    r"extract(?:ing)?|obtain(?:ing)?|use|using|store|storing)"
)
_NEGATED_SENSITIVE_PATTERNS = (
    re.compile(
        rf"\b(?:do\s+not|don't|never|must\s+not|should\s+not)\s+"
        rf"(?:ever\s+)?{_PROHIBITED_ACTION}\s+"
        rf"(?:(?:any|the|my|your|saved)\s+)?{_SENSITIVE_OBJECT_LIST}",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"\bwithout\s+(?:ever\s+)?(?:{_PROHIBITED_ACTION}\s+)?"
        rf"(?:(?:any|the|my|your|saved)\s+)?{_SENSITIVE_OBJECT_LIST}",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"\b{_SENSITIVE_OBJECT_LIST}\s+(?:must|should)\s+not\s+be\s+"
        r"(?:accessed|read|inspected|opened|exposed|logged|printed|shown|"
        r"exported|retrieved|copied|uploaded|stored|revealed|disclosed)",
        flags=re.IGNORECASE,
    ),
)

_CONSTRAINT_LABELS = (
    (re.compile(r"\bcredentials?\b|\bcredential\s+stores?\b", re.IGNORECASE), "credential_access_prohibited"),
    (re.compile(r"\bpasswords?\b", re.IGNORECASE), "password_access_prohibited"),
    (re.compile(r"\btokens?\b", re.IGNORECASE), "token_access_prohibited"),
    (re.compile(r"\bauth|\blogin\s+data\b|\.codex/auth\.json", re.IGNORECASE), "auth_data_access_prohibited"),
    (re.compile(r"\bcookies?\b", re.IGNORECASE), "cookie_access_prohibited"),
    (re.compile(r"(?<!\w)\.env(?!\w)", re.IGNORECASE), "environment_secret_access_prohibited"),
    (re.compile(r"\b(?:private|ssh)\s+keys?\b|\.ssh/id_", re.IGNORECASE), "private_key_access_prohibited"),
    (re.compile(r"\bsecrets?\b|\bapi\s+keys?\b", re.IGNORECASE), "secret_access_prohibited"),
)


@dataclass(frozen=True)
class PromptSemantics:
    """Two in-memory views of a prompt plus sanitized safety constraints."""

    normalized_text: str
    actionable_text: str
    safety_constraints: tuple[str, ...]


def normalize_prompt(prompt: str) -> str:
    """Return a normalized prompt for scoring.

    Keeps content as text only. Does not split prompt into shell tokens.
    """
    if not isinstance(prompt, str):
        prompt = str(prompt)
    prompt = _CONTROL_RE.sub(" ", prompt)
    prompt = prompt.strip().lower()
    prompt = _WS_RE.sub(" ", prompt)
    return prompt


def analyze_prompt_semantics(prompt: str) -> PromptSemantics:
    """Separate prohibited secret access from the action being requested.

    The actionable view is used only for deterministic classification. The
    original prompt remains untouched for forwarding to Codex, and only
    canonical constraint labels are retained by routing decisions.
    """
    normalized = normalize_prompt(prompt)
    labels: list[str] = []

    def remove_constraint(match: re.Match[str]) -> str:
        matched = match.group(0)
        if "sensitive_data_access_prohibited" not in labels:
            labels.append("sensitive_data_access_prohibited")
        for pattern, label in _CONSTRAINT_LABELS:
            if pattern.search(matched) and label not in labels:
                labels.append(label)
        return " "

    actionable = normalized
    for pattern in _NEGATED_SENSITIVE_PATTERNS:
        actionable = pattern.sub(remove_constraint, actionable)

    actionable = _WS_RE.sub(" ", actionable)
    actionable = re.sub(r"\s+([,.;!?])", r"\1", actionable)
    actionable = actionable.strip(" \t\r\n,;:.!?-")
    actionable = re.sub(r"(?:[,;:]\s*)?\b(?:but|and)\b\s*$", "", actionable)
    actionable = actionable.strip(" \t\r\n,;:.!?-")
    return PromptSemantics(
        normalized_text=normalized,
        actionable_text=actionable,
        safety_constraints=tuple(labels),
    )


def prompt_has_injection_markers(prompt: str) -> bool:
    text = normalize_prompt(prompt)
    markers = ["ignore previous", "system prompt", "developer message", "jailbreak", "bypass policy"]
    return any(m in text for m in markers)
