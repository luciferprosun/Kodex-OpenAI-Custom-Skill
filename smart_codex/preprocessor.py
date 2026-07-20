
"""Prompt preprocessing for Codex Patch Smart Router.

V0 rule: preprocessing must not execute, inspect files, or mutate state.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RE = re.compile(r"\s+")

_EN_TEST_TARGET = (
    r"(?:pytest|(?:(?:a|an|the|my|our|your|their|its|this|that|all|any|focused|full|complete|existing|unit|integration|"
    r"regression|smoke|e2e|end[- ]to[- ]end)\s+)*(?:tests?|test\s+suites?))"
)
_PL_TEST_TARGET = (
    r"(?:pytest|(?:pełny|pelny)\s+zestaw\s+testów|zestaw\s+testów|"
    r"testy\s+(?:jednostkowe|integracyjne)|"
    r"testów\s+(?:jednostkowych|integracyjnych)|test\s+dymny|testy|testów)"
)
_NEGATED_TEST_PATTERNS = (
    re.compile(
        rf"\b(?:do\s+not|don['’]t|never)\s+(?:run|execute|use)\s+{_EN_TEST_TARGET}",
        flags=re.IGNORECASE,
    ),
    re.compile(r"\brun\s+no\s+(?:tests?|test\s+suites?)\b", flags=re.IGNORECASE),
    re.compile(
        rf"\bwithout\s+(?:running|executing|using)\s+{_EN_TEST_TARGET}",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:do\s+not|don['’]t|never)\s+not\s+"
        rf"(?:run|execute|launch|use)\s+{_EN_TEST_TARGET}",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:do\s+not|don['’]t|never)\s*,?\s*"
        rf"(?:under\s+(?:any|no)\s+circumstances|for\s+now|yet|ever)\s*,?\s*"
        rf"(?:run|execute|launch|use)\s+{_EN_TEST_TARGET}",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"\bnie\s+(?:uruchamiaj|uruchom|wykonuj|wykonaj|używaj|uzywaj)\s+"
        rf"{_PL_TEST_TARGET}",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"\bbez\s+(?:uruchamiania|wykonywania|używania|uzywania)\s+"
        rf"{_PL_TEST_TARGET}",
        flags=re.IGNORECASE,
    ),
)
_POSITIVE_TEST_PATTERNS = (
    re.compile(rf"\b(?:run|execute|launch)\s+{_EN_TEST_TARGET}", flags=re.IGNORECASE),
    re.compile(
        rf"\b(?:uruchom(?:cie)?|wykonaj(?:cie)?)\s+{_PL_TEST_TARGET}",
        flags=re.IGNORECASE,
    ),
)

_TEST_CONTEXT_RE = re.compile(
    rf"{_EN_TEST_TARGET}|{_PL_TEST_TARGET}",
    flags=re.IGNORECASE,
)
_GENERIC_TEST_PROHIBITION_RE = re.compile(
    r"\b(?:do\s+not|don['’]t|never)\s+(?:run|execute|launch|use)\s+"
    r"(?:it|them|anything)\b|"
    r"\bwithout\s+(?:running|executing|launching|using)\s+(?:it|them|anything)\b|"
    r"\b(?:ich|go)\s+nie\s+(?:uruchamiaj|uruchom|wykonuj|wykonaj)\b|"
    r"\bbez\s+(?:jego|ich)\s+(?:uruchamiania|wykonywania)\b",
    flags=re.IGNORECASE,
)
_QUOTED_TEXT_RE = re.compile(
    r'"[^"\n]*"|“[^”\n]*”|„[^”\n]*”|`[^`\n]*`',
)

_CLAUSE_BOUNDARY_RE = re.compile(
    r"[;!?]|\.(?=\s|$)|\b(?:and\s+then|a\s+następnie|a\s+nastepnie|after\s+that|"
    r"subsequently|zamiast\s+tego|then|next|potem|następnie|nastepnie|"
    r"po\s+tym|but|instead|ale|lecz)\b",
    flags=re.IGNORECASE,
)
_EXPLANATORY_TEST_FRAME_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:please\s+)?(?:explain|wyjaśnij|wyjasnij)\b",
    flags=re.IGNORECASE,
)
_DESCRIPTIVE_TEST_FRAME_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:please\s+)?(?:describe|document|show\s+(?:an\s+)?"
    r"example|opisz|udokumentuj)\b|"
    r"^\s*(?:[-*]\s*)?(?:the\s+)?documentation\s+(?:says?|contains?)\b|"
    r"^\s*(?:[-*]\s*)?dokumentacja\s+(?:zawiera|mówi|mowi)\b",
    flags=re.IGNORECASE,
)
_REVIEW_OR_DECISION_TEST_FRAME_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:please\s+)?(?:review|assess|evaluate|decide|check)\b"
    r"[^.;!?]{0,80}\b(?:whether|if|statement|sentence|command)\b|"
    r"^\s*(?:[-*]\s*)?(?:przejrzyj|oceń|ocen|zdecyduj|sprawdź|sprawdz)\b"
    r"[^.;!?]{0,80}\b(?:czy|zdanie|komend)\w*\b",
    flags=re.IGNORECASE,
)
_INTERROGATIVE_TEST_FRAME_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:should|shall|can|could|would|may|might|must|"
    r"what|why|when|where|how|whether|czy)\b",
    flags=re.IGNORECASE,
)
_GENERIC_POSITIVE_TEST_ACTION_RE = re.compile(
    r"\b(?:run|execute|launch|use)\s+(?:it|them)\b|"
    r"\b(?:uruchom(?:cie)?|wykonaj(?:cie)?)\s+(?:go|je)\b",
    flags=re.IGNORECASE,
)
_TEST_MODIFICATION_RE = re.compile(
    r"\b(?:add|change|delete|edit|fix|modify|patch|refactor|remove|repair|"
    r"replace|rewrite|update|write)\b[^.;!?]{0,80}\b(?:pytest|tests?|"
    r"test\s+suites?)\b|"
    r"\b(?:dodaj|edytuj|napraw|przeredaguj|usuń|usun|zmień|zmien|"
    r"zmodyfikuj)\b[^.;!?]{0,80}\b(?:pytest|testy|testów)\b",
    flags=re.IGNORECASE,
)
_NEGATED_TEST_MODIFICATION_RE = re.compile(
    r"\b(?:do\s+not|don['’]t|never)\s+(?:add|change|delete|edit|fix|modify|"
    r"patch|refactor|remove|repair|replace|rewrite|update|write)\b|"
    r"\bnie\s+(?:dodawaj|edytuj|naprawiaj|przeredagowuj|usuwaj|zmieniaj|"
    r"modyfikuj)\b",
    flags=re.IGNORECASE,
)

_FILE_REFERENCE_RE = re.compile(
    r"(?<![A-Za-z0-9_@])"
    r"(?P<path>(?:\.{1,2}[\\/]+)?(?:[A-Za-z0-9_.-]+[\\/]+)*"
    r"[A-Za-z0-9_][A-Za-z0-9_.-]*\."
    r"(?P<extension>markdown|jsonl|tsx|jsx|scss|bash|yaml|toml|lock|html|"
    r"json|yml|rst|txt|pdf|ini|cfg|xml|csv|css|sql|py|md|js|ts|sh))"
    r"(?!(?:[A-Za-z0-9_-]|\.[A-Za-z0-9_]))",
    flags=re.IGNORECASE,
)
_DOCUMENT_EXTENSIONS = {"md", "markdown", "rst", "txt", "pdf"}
_SENSITIVE_DOCUMENT_NAMES = {
    "authorization.md",
    "compliance.md",
    "incident.md",
    "privacy.md",
    "security.md",
}
_REPOSITORY_WIDE_RE = re.compile(
    r"\b(?:(?:whole|entire)\s+(?:repo|repository|codebase|project)|"
    r"(?:repo|repository|project)[- ]wide|across\s+(?:the\s+)?"
    r"(?:repo|repository|codebase)|all\s+files)\b",
    flags=re.IGNORECASE,
)
_DOCUMENT_COMPARISON_RE = re.compile(
    r"\b(?:compare|comparison|differences?|different\s+between)\b",
    flags=re.IGNORECASE,
)

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
    test_intent: str = "none"
    explicit_file_count: int = 0
    explicit_document_count: int = 0
    repository_wide: bool = False
    reason_codes: tuple[str, ...] = ()
    test_execution_requested: bool = False
    test_execution_prohibited: bool = False
    test_discussion_only: bool = False
    test_modification_intent: bool = False
    sensitive_document_reference: bool = False


@dataclass(frozen=True)
class _IntentClause:
    """Bounded internal state for one test-related prompt clause."""

    start: int
    end: int
    text: str
    executable_request: bool
    execution_prohibition: bool
    descriptive_statement: bool
    explanatory_statement: bool
    review_or_decision_request: bool
    interrogative: bool
    quoted_or_mentioned_command: bool
    test_context: bool
    test_modification_intent: bool
    suppressed_spans: tuple[tuple[int, int], ...]
    negative_spans: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class _TestIntentAnalysis:
    actionable_text: str
    execution_requested: bool
    execution_prohibited: bool
    discussion_only: bool
    test_modification_intent: bool
    clauses: tuple[_IntentClause, ...]


def _normalize_local_reference(value: str) -> str | None:
    """Lexically normalize a relative path without touching the filesystem."""

    normalized = value.replace("\\", "/")
    if normalized.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", normalized):
        return None
    parts: list[str] = []
    for part in normalized.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        return None
    return "/".join(parts)


def _explicit_file_counts(text: str) -> tuple[int, int, bool]:
    """Count normalized local-looking file references without retaining paths."""

    references: dict[str, str] = {}
    sensitive_document_reference = False
    for match in _FILE_REFERENCE_RE.finditer(text):
        prefix_match = re.search(r"\S*$", text[: match.start()])
        token_prefix = prefix_match.group(0) if prefix_match is not None else ""
        if "://" in token_prefix or (
            match.start() > 0 and text[match.start() - 1] in "/\\"
        ):
            continue
        normalized = _normalize_local_reference(match.group("path"))
        if normalized is None:
            continue
        references[normalized] = match.group("extension").casefold()
        if normalized.rsplit("/", 1)[-1].casefold() in _SENSITIVE_DOCUMENT_NAMES:
            sensitive_document_reference = True
    document_count = sum(
        extension in _DOCUMENT_EXTENSIONS for extension in references.values()
    )
    return len(references), document_count, sensitive_document_reference


def is_document_comparison(semantics: PromptSemantics) -> bool:
    """Return a content-free, deterministic document-comparison signal."""

    return (
        semantics.explicit_document_count >= 2
        and _DOCUMENT_COMPARISON_RE.search(semantics.actionable_text) is not None
    )


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


def _blank_spans(text: str, spans: list[tuple[int, int]]) -> str:
    characters = list(text)
    for start, end in spans:
        characters[start:end] = " " * (end - start)
    return "".join(characters)


def _semantic_working_text(prompt: str) -> str:
    """Normalize semantic text while retaining explicit line boundaries."""

    if not isinstance(prompt, str):
        prompt = str(prompt)
    prompt = _CONTROL_RE.sub(" ", prompt)
    prompt = prompt.replace("\r\n", "\n").replace("\r", "\n")
    prompt = re.sub(r"\n\s*(?:[-*]\s+)?", "; ", prompt)
    return _WS_RE.sub(" ", prompt.strip().lower())


def _position_in_spans(position: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def _quote_delimiters_blank(text: str, spans: list[tuple[int, int]]) -> str:
    """Make quote delimiters ignorable without hiding a quoted test target."""

    characters = list(text)
    for start, end in spans:
        characters[start] = " "
        characters[end - 1] = " "
    return "".join(characters)


def _clause_ranges(
    text: str,
    quote_spans: list[tuple[int, int]],
) -> list[tuple[int, int, bool]]:
    """Return independent clause ranges without splitting quoted commands."""

    ranges: list[tuple[int, int, bool]] = []
    start = 0
    for boundary in _CLAUSE_BOUNDARY_RE.finditer(text):
        if _position_in_spans(boundary.start(), quote_spans):
            continue
        if text[start : boundary.start()].strip(" \t,;:-"):
            ranges.append((start, boundary.start(), boundary.group(0) == "?"))
        start = boundary.end()
    if text[start:].strip(" \t,;:-"):
        ranges.append((start, len(text), False))
    return ranges


def _relative_spans(
    spans: list[tuple[int, int]],
    start: int,
    end: int,
) -> list[tuple[int, int]]:
    return [
        (span_start - start, span_end - start)
        for span_start, span_end in spans
        if start <= span_start and span_end <= end
    ]


def _find_matches(
    patterns: tuple[re.Pattern[str], ...],
    text: str,
) -> list[tuple[int, int]]:
    return sorted(
        {match.span() for pattern in patterns for match in pattern.finditer(text)}
    )


def _analyze_test_intent(text: str) -> _TestIntentAnalysis:
    """Analyze test execution clause-by-clause using explicit local state."""

    quote_spans = [match.span() for match in _QUOTED_TEXT_RE.finditer(text)]
    recognition_text = _quote_delimiters_blank(text, quote_spans)
    clauses: list[_IntentClause] = []
    blanked_spans: list[tuple[int, int]] = []
    prior_test_context = False

    for start, end, punctuation_question in _clause_ranges(text, quote_spans):
        clause = text[start:end]
        recognition_clause = recognition_text[start:end]
        local_quotes = _relative_spans(quote_spans, start, end)
        test_context = _TEST_CONTEXT_RE.search(recognition_clause) is not None
        explanatory = _EXPLANATORY_TEST_FRAME_RE.search(clause) is not None
        descriptive = _DESCRIPTIVE_TEST_FRAME_RE.search(clause) is not None
        review_or_decision = _REVIEW_OR_DECISION_TEST_FRAME_RE.search(clause) is not None
        interrogative = (
            punctuation_question
            or _INTERROGATIVE_TEST_FRAME_RE.search(clause) is not None
        )
        meta_language = explanatory or descriptive or review_or_decision or interrogative

        negative_spans = _find_matches(_NEGATED_TEST_PATTERNS, recognition_clause)
        generic_negative_spans = [
            match.span()
            for match in _GENERIC_TEST_PROHIBITION_RE.finditer(recognition_clause)
            if test_context or prior_test_context
        ]
        negative_spans = sorted({*negative_spans, *generic_negative_spans})

        positive_spans = _find_matches(_POSITIVE_TEST_PATTERNS, recognition_clause)
        if test_context or prior_test_context:
            positive_spans.extend(
                match.span()
                for match in _GENERIC_POSITIVE_TEST_ACTION_RE.finditer(recognition_clause)
            )
        positive_spans = sorted(set(positive_spans))

        active_positive_spans: list[tuple[int, int]] = []
        suppressed_spans: list[tuple[int, int]] = []
        quoted_or_mentioned = False
        for positive_span in positive_spans:
            positive_start = positive_span[0]
            verb_is_quoted = _position_in_spans(positive_start, local_quotes)
            prohibited_here = any(
                negative_start <= positive_start
                for negative_start, _ in negative_spans
            )
            if verb_is_quoted:
                quoted_or_mentioned = True
                suppressed_spans.append(positive_span)
            elif meta_language or prohibited_here:
                suppressed_spans.append(positive_span)
            else:
                active_positive_spans.append(positive_span)

        quoted_test_spans = [
            span
            for span in local_quotes
            if _TEST_CONTEXT_RE.search(clause[span[0] : span[1]]) is not None
        ]
        if quoted_test_spans and not active_positive_spans:
            quoted_or_mentioned = True
            suppressed_spans.extend(quoted_test_spans)

        candidate_modification = _TEST_MODIFICATION_RE.search(clause) is not None
        modification_negated = _NEGATED_TEST_MODIFICATION_RE.search(clause) is not None
        test_modification = bool(
            candidate_modification and not modification_negated and not meta_language
        )

        local_blank_spans = sorted({*suppressed_spans, *negative_spans})
        blanked_spans.extend(
            (start + span_start, start + span_end)
            for span_start, span_end in local_blank_spans
        )
        clauses.append(
            _IntentClause(
                start=start,
                end=end,
                text=clause,
                executable_request=bool(active_positive_spans),
                execution_prohibition=bool(negative_spans),
                descriptive_statement=descriptive,
                explanatory_statement=explanatory,
                review_or_decision_request=review_or_decision,
                interrogative=interrogative,
                quoted_or_mentioned_command=quoted_or_mentioned,
                test_context=test_context,
                test_modification_intent=test_modification,
                suppressed_spans=tuple(suppressed_spans),
                negative_spans=tuple(negative_spans),
            )
        )
        prior_test_context = prior_test_context or test_context

    execution_requested = any(clause.executable_request for clause in clauses)
    execution_prohibited = any(clause.execution_prohibition for clause in clauses)
    discussion_only = bool(
        not execution_requested
        and any(
            clause.test_context
            and (
                clause.descriptive_statement
                or clause.explanatory_statement
                or clause.review_or_decision_request
                or clause.interrogative
                or clause.quoted_or_mentioned_command
            )
            for clause in clauses
        )
    )
    return _TestIntentAnalysis(
        actionable_text=_blank_spans(text, blanked_spans),
        execution_requested=execution_requested,
        execution_prohibited=execution_prohibited,
        discussion_only=discussion_only,
        test_modification_intent=any(
            clause.test_modification_intent for clause in clauses
        ),
        clauses=tuple(clauses),
    )


def analyze_prompt_semantics(prompt: str) -> PromptSemantics:
    """Separate prohibited secret access from the action being requested.

    The actionable view is used only for deterministic classification. The
    original prompt remains untouched for forwarding to Codex, and only
    canonical constraint labels are retained by routing decisions.
    """
    normalized = normalize_prompt(prompt)
    labels: list[str] = []
    reason_codes: list[str] = []

    def remove_constraint(match: re.Match[str]) -> str:
        matched = match.group(0)
        if "sensitive_data_access_prohibited" not in labels:
            labels.append("sensitive_data_access_prohibited")
        for pattern, label in _CONSTRAINT_LABELS:
            if pattern.search(matched) and label not in labels:
                labels.append(label)
        return " "

    actionable = _semantic_working_text(prompt)
    for pattern in _NEGATED_SENSITIVE_PATTERNS:
        actionable = pattern.sub(remove_constraint, actionable)

    intent = _analyze_test_intent(actionable)
    actionable = intent.actionable_text
    negated_test_action = intent.execution_prohibited
    positive_test_action = intent.execution_requested
    descriptive_test_action = intent.discussion_only

    if negated_test_action:
        if "test_execution_prohibited" not in labels:
            labels.append("test_execution_prohibited")
        reason_codes.append("negated_test_action_suppressed")
    if descriptive_test_action:
        reason_codes.append("descriptive_test_action_suppressed")

    actionable = _WS_RE.sub(" ", actionable)
    actionable = re.sub(r"\s+([,.;!?])", r"\1", actionable)
    actionable = actionable.strip(" \t\r\n,;:.!?-")
    actionable = re.sub(r"(?:[,;:]\s*)?\b(?:but|and)\b\s*$", "", actionable)
    actionable = actionable.strip(" \t\r\n,;:.!?-")
    actionable = re.sub(r"^(?:but|ale)\b\s*", "", actionable)
    if positive_test_action:
        reason_codes.append("positive_test_action_detected")
    if negated_test_action and positive_test_action:
        test_intent = "mixed"
    elif negated_test_action:
        test_intent = "negative"
    elif positive_test_action:
        test_intent = "positive"
    else:
        test_intent = "none"

    # Preserve path case while counting because the router runs on platforms
    # where differently cased paths can identify distinct files. Counts only
    # leave this helper; the paths themselves are never attached to decisions.
    (
        explicit_file_count,
        explicit_document_count,
        sensitive_document_reference,
    ) = _explicit_file_counts(prompt)
    repository_wide = _REPOSITORY_WIDE_RE.search(normalized) is not None
    if explicit_file_count >= 2:
        reason_codes.append("explicit_multi_file_scope")
    return PromptSemantics(
        normalized_text=normalized,
        actionable_text=actionable,
        safety_constraints=tuple(labels),
        test_intent=test_intent,
        explicit_file_count=explicit_file_count,
        explicit_document_count=explicit_document_count,
        repository_wide=repository_wide,
        reason_codes=tuple(reason_codes),
        test_execution_requested=positive_test_action,
        test_execution_prohibited=negated_test_action,
        test_discussion_only=descriptive_test_action,
        test_modification_intent=intent.test_modification_intent,
        sensitive_document_reference=sensitive_document_reference,
    )


def prompt_has_injection_markers(prompt: str) -> bool:
    text = normalize_prompt(prompt)
    markers = ["ignore previous", "system prompt", "developer message", "jailbreak", "bypass policy"]
    return any(m in text for m in markers)
