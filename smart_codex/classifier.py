from __future__ import annotations

from dataclasses import dataclass
import re

from .preprocessor import analyze_prompt_semantics


CATEGORIES = [
    "email",
    "simple_text",
    "literary",
    "normal_coding",
    "complex_coding",
    "architecture",
    "math_theory",
    "security_audit",
    "repo_operations",
    "research",
    "grant_work",
    "unknown",
]


CATEGORY_ORDER = [
    "security_audit",
    "repo_operations",
    "math_theory",
    "architecture",
    "complex_coding",
    "normal_coding",
    "grant_work",
    "research",
    "email",
    "simple_text",
    "literary",
]


KEYWORD_RULES: dict[str, list[tuple[str, float, str]]] = {
    "security_audit": [
        (r"\bsecrets?\b", 10, "secret"),
        (r"\btokens?\b", 10, "token"),
        (r"\bauth\b", 8, "auth"),
        (r"\bpasswords?\b", 10, "password"),
        (r"\bapi\s+keys?\b", 10, "api key"),
        (r"\bmalware\b", 10, "malware"),
        (r"\bexploit\b", 10, "exploit"),
        (r"\bsandbox\b", 8, "sandbox"),
        (r"\bpermissions?\b", 7, "permission"),
        (r"\bprivate\s+keys?\b", 10, "private key"),
        (r"(?<!\w)\.env(?!\w)", 10, ".env"),
        (r"\bcredentials?\b", 10, "credential"),
        (r"\bsecurity\b", 8, "security"),
        (r"\bbezpiecze[nń]stwo\b", 8, "bezpieczenstwo"),
        (r"\bvulnerabilit\w*\b", 10, "vulnerability"),
        (r"\binjection\b", 8, "injection"),
        (r"\bxss\b", 10, "XSS"),
        (r"\bcsrf\b", 10, "CSRF"),
        (r"\bsql\s+injection\b", 12, "SQL injection"),
        (r"\bauth\s+bypass\b", 12, "auth bypass"),
        (r"\bencrypt\w*\b", 6, "encrypt"),
        (r"\bhash\b", 6, "hash"),
        (r"\bpenetration\b", 8, "penetration"),
        (r"\bsandbox\s+escape\b", 12, "sandbox escape"),
        (r"\bprompt\s+injection\b", 12, "prompt injection"),
        (r"\bcve-\d{4}-\d+\b", 12, "CVE"),
    ],
    "repo_operations": [
        (r"\bgit\b", 7, "git"),
        (r"\bbranch\b", 6, "branch"),
        (r"\bcommit\b", 7, "commit"),
        (r"\bmerge\b", 7, "merge"),
        (r"\brebase\b", 7, "rebase"),
        (r"\brelease\b", 6, "release"),
        (r"\btag\b", 5, "tag"),
        (r"\bpull\s+request\b", 6, "pull request"),
        (r"\bpush\b", 6, "push"),
    ],
    "normal_coding": [
        (r"\bbug\b", 7, "bug"),
        (r"\bfix\b", 6, "fix"),
        (r"\bnapraw\b", 6, "napraw"),
        (r"\bfrontend\b", 7, "frontend"),
        (r"\bbackend\b", 7, "backend"),
        (r"\bapi\b", 5, "api"),
        (r"\bimplement\b", 6, "implement"),
        (r"\bzaimplementuj\b", 6, "zaimplementuj"),
        (r"\btests?\b", 5, "test"),
        (r"\bfunctions?\b", 4, "function"),
        (r"\bfunkcj\w*\b", 4, "funkcja"),
        (r"\bcomponent\b", 5, "component"),
        (r"\bnapisz\b", 4, "napisz"),
        (r"\bwrite\b", 4, "write"),
        (r"\bcreate\b", 4, "create"),
        (r"\bgeneruj\s+kod\b", 7, "generuj kod"),
        (r"\bkod\b", 5, "kod"),
        (r"\bscript\b", 5, "script"),
        (r"\bprogram\b", 5, "program"),
        (r"\bdef\b", 4, "def"),
        (r"\bclass\b", 4, "class"),
        (r"\bconst\b", 4, "const"),
        (r"\blet\b", 4, "let"),
        (r"\bvar\b", 4, "var"),
        (r"\bnie\s+dzia[lł]a\b", 8, "nie dziala"),
        (r"\bb[lł][aą]d\b", 8, "blad"),
        (r"\berror\b", 8, "error"),
        (r"\bdebug\b", 7, "debug"),
        (r"\btraceback\b", 9, "traceback"),
        (r"\bexception\b", 9, "exception"),
        (r"\bcrash\w*\b", 8, "crash"),
        (r"\bdlaczego\b", 4, "dlaczego"),
        (r"\bwhy\s+does\b", 5, "why does"),
        (r"\bwhat'?s\s+wrong\b", 5, "what's wrong"),
        (r"\bbroken\b", 6, "broken"),
        (r"\bfailed\b", 6, "failed"),
        (r"\bcode\s+review\b", 7, "code review"),
        (r"\bsprawd[zź]\s+kod\b", 7, "sprawdz kod"),
        (r"\bprzegl[aą]d\s+kodu\b", 7, "przeglad kodu"),
        (r"\boce[nń]\s+kod\b", 6, "ocen kod"),
    ],
    "complex_coding": [
        (r"\brefactor\b", 8, "refactor"),
        (r"\bmulti[-\s]?file\b", 10, "multi-file"),
        (r"\bmigration\b", 8, "migration"),
        (r"\barchitecture\b", 8, "architecture"),
        (r"\bredesign\b", 7, "redesign"),
        (r"\bmodules?\b", 5, "module"),
        (r"\bdependency\b", 5, "dependency"),
        (r"\bintegration\b", 6, "integration"),
    ],
    "architecture": [
        (r"\barchitecture\b", 10, "architecture"),
        (r"\barchitektur\w*\b", 10, "architektura"),
        (r"\bsystem\s+design\b", 10, "system design"),
        (r"\bboundaries\b", 7, "boundaries"),
        (r"\bdesign\s+plan\b", 7, "design plan"),
        (r"\broadmap\b", 5, "roadmap"),
        (r"\bmicroservice\w*\b", 8, "microservice"),
        (r"\bdatabase\s+schema\b", 7, "database schema"),
        (r"\bapi\s+design\b", 7, "API design"),
        (r"\bwzorzec\b", 5, "wzorzec"),
        (r"\bpattern\b", 5, "pattern"),
        (r"\binfrastruktur\w*\b", 6, "infrastruktura"),
        (r"\bdeployment\b", 6, "deployment"),
        (r"\bscal\w*\b", 5, "scale"),
        (r"\bcache\b", 5, "cache"),
        (r"\bqueue\b", 5, "queue"),
        (r"\bzaprojektuj\s+(system|architektur\w*|api)\b", 10, "zaprojektuj system"),
    ],
    "math_theory": [
        (r"\bproof\b", 10, "proof"),
        (r"\bdow[oó]d\b", 10, "dowod"),
        (r"\btheorem\b", 10, "theorem"),
        (r"\btwierdzenie\b", 10, "twierdzenie"),
        (r"\bequations?\b", 8, "equation"),
        (r"\br[oó]wnan\w*\b", 8, "rownanie"),
        (r"\blemma\b", 8, "lemma"),
        (r"\bneutrino\b", 10, "neutrino"),
        (r"\blsc\b", 10, "LSC"),
        (r"\btensor\b", 7, "tensor"),
        (r"\bderivation\b", 8, "derivation"),
        (r"\bca[lł]k\w*\b", 8, "calka"),
        (r"\bintegral\b", 8, "integral"),
        (r"\bmacierz\b", 7, "macierz"),
        (r"\bmatrix\b", 7, "matrix"),
        (r"\boptimization\b", 7, "optimization"),
        (r"\boptymalizacja\b", 7, "optymalizacja"),
        (r"\blagrange\b", 7, "Lagrange"),
        (r"\bfourier\b", 7, "Fourier"),
        (r"\br[oó][zż]niczkow\w*\b", 8, "rozniczkowe"),
        (r"\bdifferential\b", 8, "differential"),
        (r"\bprobabil\w*\b", 6, "probability"),
        (r"\bstatysty\w*\b", 6, "statystyka"),
        (r"[∫∂∇∑∏∈∉∪∩⊆⊇√∞±×÷]", 12, "math symbol"),
        (r"\\[a-zA-Z]+\{", 10, "latex command"),
    ],
    "research": [
        (r"\bresearch\b", 8, "research"),
        (r"\banali[sz]\w*\b", 7, "analiza"),
        (r"\banalysis\b", 7, "analysis"),
        (r"\bcompare\b", 6, "compare"),
        (r"\binvestigate\b", 7, "investigate"),
        (r"\bsources?\b", 6, "sources"),
        (r"\baudit\s+project\b", 8, "audit project"),
        (r"\bliterature\b", 6, "literature"),
        (r"\bdataset\b", 7, "dataset"),
        (r"\bpandas\b", 7, "pandas"),
        (r"\bdataframe\b", 7, "dataframe"),
        (r"\bcorrelation\b", 6, "correlation"),
        (r"\bregression\b", 6, "regression"),
        (r"\bcsv\b", 6, "CSV"),
        (r"\bjson\s+data\b", 6, "JSON data"),
        (r"\bplot\b", 5, "plot"),
        (r"\bmatplotlib\b", 6, "matplotlib"),
        (r"\bchart\b", 5, "chart"),
        (r"\bhistogram\b", 5, "histogram"),
        (r"\bcluster\b", 5, "cluster"),
    ],
    "grant_work": [
        (r"\bgrant\b", 10, "grant"),
        (r"\bfunding\b", 9, "funding"),
        (r"\bapplication\b", 7, "application"),
        (r"\bproposal\b", 8, "proposal"),
        (r"\bcall\s+for\s+proposals\b", 10, "call for proposals"),
    ],
    "email": [
        (r"\bemail\b", 10, "email"),
        (r"\breply\b", 7, "reply"),
        (r"\bdraft\s+email\b", 10, "draft email"),
        (r"\bmail\b", 8, "mail"),
        (r"\bmaila\b", 8, "mail"),
        (r"\bwiadomo[sś][cć]\b", 6, "wiadomosc"),
        (r"\bodpisz\b", 8, "odpisz"),
    ],
    "simple_text": [
        (r"\bsummarize\b", 7, "summarize"),
        (r"\bstre[sś][cć]\b", 7, "stresc"),
        (r"\bexplain\s+simply\b", 8, "explain simply"),
        (r"\bwyt[lł]umacz\s+prosto\b", 8, "wytlumacz prosto"),
        (r"\bshorten\b", 6, "shorten"),
        (r"\bskr[oó][cć]\b", 6, "skroc"),
        (r"\brewrite\s+short\b", 6, "rewrite short"),
        (r"\bsimple\s+summary\b", 6, "simple summary"),
    ],
    "literary": [
        (r"\bpoem\b", 10, "poem"),
        (r"\bstory\b", 8, "story"),
        (r"\bstyle\b", 6, "style"),
        (r"\btone\b", 6, "tone"),
        (r"\bcaption\b", 7, "caption"),
        (r"\bsocial\s+post\b", 8, "social post"),
        (r"\bwiersz\b", 10, "wiersz"),
        (r"\bhistori\w*\b", 8, "historia"),
        (r"\bpost\s+spo[lł]eczno[sś]ciowy\b", 8, "post spolecznosciowy"),
    ],
}


HARD_SECURITY_LABELS = {
    "secret",
    "token",
    "auth",
    "password",
    "api key",
    "malware",
    "exploit",
    "sandbox",
    "permission",
    "private key",
    ".env",
    "credential",
}


@dataclass(frozen=True)
class Classification:
    category: str
    confidence: float
    matched_keywords: list[str]
    scores: dict[str, float]
    warning: str | None


def normalize_text(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt.lower()).strip()


def classify_prompt(prompt: str) -> Classification:
    semantics = analyze_prompt_semantics(prompt)
    text = normalize_text(semantics.actionable_text)
    scores = {category: 0 for category in CATEGORIES}
    matched_by_category: dict[str, list[str]] = {category: [] for category in CATEGORIES}

    for category, rules in KEYWORD_RULES.items():
        for pattern, weight, label in rules:
            if re.search(pattern, text, flags=re.IGNORECASE):
                scores[category] += weight
                matched_by_category[category].append(label)

    apply_structural_heuristics(semantics.actionable_text, scores, matched_by_category)

    total_score = sum(scores.values())
    if total_score == 0:
        return Classification(
            category="unknown",
            confidence=0.0,
            matched_keywords=[],
            scores=scores,
            warning="low confidence route",
        )

    hard_security_matches = [
        label
        for label in matched_by_category["security_audit"]
        if label in HARD_SECURITY_LABELS
    ]
    if hard_security_matches:
        category = "security_audit"
    else:
        category = max(CATEGORY_ORDER, key=lambda item: (scores[item], -CATEGORY_ORDER.index(item)))

    confidence = scores[category] / total_score if total_score else 0.0
    warning = "low confidence route" if confidence <= 0.30 else None

    matched_keywords = matched_by_category[category]
    return Classification(
        category=category,
        confidence=round(confidence, 4),
        matched_keywords=matched_keywords,
        scores=scores,
        warning=warning,
    )


def apply_structural_heuristics(
    prompt: str,
    scores: dict[str, float],
    matched_by_category: dict[str, list[str]],
) -> None:
    if has_code_blocks(prompt):
        scores["normal_coding"] += 2.0
        scores["complex_coding"] += 1.0
        matched_by_category["normal_coding"].append("code block")

    if has_math_notation(prompt):
        scores["math_theory"] += 10.0
        matched_by_category["math_theory"].append("math notation")

    question_count = prompt.count("?")
    if question_count > 2:
        scores["research"] += 1.0
        matched_by_category["research"].append("multi-question prompt")

    lowered = normalize_text(prompt)
    if re.search(r"\b(multi[-\s]?file|source\s+file|code\s+file|plik|plikiem|plikach)\b", lowered):
        scores["complex_coding"] += 0.5
        matched_by_category["complex_coding"].append("file context")


def has_code_blocks(prompt: str) -> bool:
    return "```" in prompt or prompt.count("\n") > 10


def has_math_notation(prompt: str) -> bool:
    math_symbols = set("∫∂∇∑∏∈∉∪∩⊆⊇√∞±×÷")
    if any(character in prompt for character in math_symbols):
        return True
    return bool(re.search(r"\\[a-zA-Z]+\{", prompt))


def classify_prompt_weighted(prompt: str) -> Classification:
    from .knowledge import load_rules
    from .scorer import score_categories

    rules = load_rules()
    category, scores, confidence, _confidence_level, _mixed, top_categories = score_categories(prompt, rules)
    matched_keywords = top_categories[0].matched_terms if top_categories else []
    warning = "low confidence route" if category == "unknown" or confidence <= 0.30 else None
    return Classification(
        category=category,
        confidence=round(confidence, 4),
        matched_keywords=matched_keywords,
        scores=scores,
        warning=warning,
    )
