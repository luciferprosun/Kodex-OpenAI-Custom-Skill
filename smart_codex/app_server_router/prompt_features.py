"""Deterministic task features used only for model and effort selection.

Safety classification remains owned by Router Core.  This module consumes its
risk and action outputs and adds coarse workload features; it never grants
authority or weakens a Router Core decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Iterable

from smart_codex.preprocessor import analyze_prompt_semantics


SIZE_CLASSES = ("tiny", "small", "medium", "large", "xlarge", "unknown")
EFFORT_NAMES = ("minimal", "low", "medium", "high", "xhigh", "max")


@lru_cache(maxsize=512)
def _compiled_feature_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, flags=re.IGNORECASE)


def _has(text: str, patterns: Iterable[str]) -> bool:
    return any(_compiled_feature_pattern(pattern).search(text) is not None for pattern in patterns)


def _model_preference(text: str) -> str | None:
    pattern = re.compile(
        r"\b(?:use|choose|select|prefer|route(?:\s+this)?\s+to|run\s+with|model)\s+"
        r"(?:the\s+)?(gpt[-.a-z0-9]+|sol|terra|luna|spark)\b",
        flags=re.IGNORECASE,
    )
    match = pattern.search(text)
    if match is None:
        return None
    return match.group(1).lower()


def _effort_preference(text: str) -> str | None:
    patterns = (
        r"\b(?:reasoning\s+)?effort\s*(?:=|:|to|at)?\s*"
        r"(minimal|low|medium|high|xhigh|max)\b",
        r"\buse\s+(minimal|low|medium|high|xhigh|max)\s+"
        r"(?:reasoning|effort)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match is not None:
            return match.group(1).lower()
    return None


@dataclass(frozen=True)
class TaskFeatures:
    task_domain: str
    coding: bool
    work_mode: str
    likely_files: str
    edit_size: str
    expected_tool_calls: str
    test_burden: str
    expected_duration: str
    repository: bool
    context_size: str
    required_modalities: tuple[str, ...]
    image_requirement: bool
    web_research_requirement: bool
    source_verification_requirement: bool
    external_tool_workflow: bool
    research_depth: str
    latency_sensitivity: str
    quality_sensitivity: str
    architectural_depth: str
    mathematical_depth: str
    ambiguity: str
    independent_workstreams: str
    need_for_delegation: bool
    need_for_parallel_agents: bool
    side_effect_requirement: bool
    reversible: bool
    risk: str
    action_danger: str
    explicit_model_preference: str | None
    explicit_effort_preference: str | None
    clear_transformation: bool
    simple_deterministic_task: bool
    rapid_edit: bool
    broad_refactor: bool
    hard_debugging: bool
    deep_security: bool
    final_audit: bool
    deterministic_eval: bool
    explicit_test_requirement: bool
    correctness_depends_on_tests: bool


def extract_task_features(
    prompt: str,
    decision: object,
    *,
    required_modalities: Iterable[str],
) -> TaskFeatures:
    """Return stable workload classes without retaining the prompt."""

    # Preserve identifier word boundaries before case-folding.  This lets the
    # same declarative signals recognize both prose (``button label``) and
    # common code/config identifiers (``buttonLabel``) without matching exact
    # prompts or retaining either representation.
    semantics = analyze_prompt_semantics(prompt)
    word_bounded_prompt = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])",
        " ",
        prompt,
    )
    feature_semantics = (
        semantics
        if word_bounded_prompt == prompt
        else analyze_prompt_semantics(word_bounded_prompt)
    )
    text = feature_semantics.actionable_text
    category = str(getattr(decision, "category", "unknown"))
    risk = str(getattr(decision, "risk_level", "low"))
    action_danger = str(getattr(decision, "action_danger", "read_only_analysis"))
    router_context = str(getattr(decision, "context_requirement", "unknown"))

    coding_categories = {
        "normal_coding",
        "complex_coding",
        "architecture",
        "debugging",
        "testing",
        "dependency_management",
        "repo_operations",
        "release_management",
        "prompt_engineering",
    }
    coding = category in coding_categories or semantics.test_modification_intent or _has(
        text,
        (
            r"\b(?:python|javascript|typescript|rust|java|c#|code|function|class)\b",
            r"\bgo\s+(?:code|function|module|program|package)\b|\.go\b",
            r"\b(?:unit test|pytest|repository|repo|module|api endpoint|button (?:label|text))\b",
            r"\b(?:ui|frontend|css|component|fixture|formatter|route constant|loading message|icon title)\b",
            r"\b(?:kod|moduł|modul|funkcj\w*|testy|testów|testow)\b",
            r"\b(?:docstring|list comprehension|regular expression|regex|boolean condition|constant declaration)\b",
            r"\bjson\b.*\b(?:normaliz|transform|convert)\w*\b",
            r"\bconfiguration option\b.*\bimplementation\b",
        ),
    )

    edit_intent = semantics.test_modification_intent or _has(
        text,
        (
            r"\b(?:change|edit|fix|implement|add|append|create|delete|modify|move|remove|rename|refactor|rewrite|patch|update|adjust|replace|prototype)\b",
            r"\b(?:correct|repair)\b.*\b(?:code|function|test|bug)\b",
            r"\b(?:adjustment|correction|modification)\b.*\b(?:code|ui|css|component|file|fixture)\b",
            r"\bmake\b.*\b(?:code|ui|css|component|file|button|label|spacing)\b",
            r"\b(?:dodaj|edytuj|napraw|przeredaguj|usuń|usun|zmień|zmien|zmodyfikuj)\b",
        ),
    )
    analysis_intent = _has(
        text,
        (
            r"\b(?:explain|describe|review|analy[sz]e|audit|diagnose|plan|research|summarize|compare|read|inspect)\b",
            r"\bwithout\s+(?:editing|changing|executing|running)\b",
        ),
    )
    work_mode = "editing" if edit_intent else "analysis" if analysis_intent else "transformation"
    clear_transformation = _has(
        text,
        (
            r"\b(?:correct|proofread|spellcheck|fix the grammar|fix grammar)\b.*\b(?:sentence|paragraph|text)\b",
            r"\b(?:rewrite|rephrase|shorten|translate|summarize|classify|extract|convert)\b",
            r"\b(?:grammar|spelling|capitalization|punctuation)\b",
            r"\b(?:classification|extraction|normalization)\s+(?:table|list|mapping|transformation)\b",
        ),
    )
    simple_deterministic_task = _has(
        text,
        (
            r"\b(?:small|simple|one)\s+deterministic\s+(?:python\s+|javascript\s+)?script\b",
            r"\b(?:write|add)\s+(?:one|a single|a simple|one simple)\s+unit test\b",
            r"\b(?:simple|small)\s+(?:data transformation|classification|code explanation)\b",
            r"\b(?:explain|describe)\b.*\b(?:one[- ]line|simple|small)\b.*\b(?:function|expression|condition|regex|code)\b",
            r"\b(?:draft|write)\b.*\b(?:concise|short|small)\s+docstring\b",
            r"\b(?:explain|describe)\b.*\b(?:briefly|in plain language)\b",
            r"\b(?:small|simple)\s+deterministic\s+(?:json\s+)?(?:normalization\s+)?script\b",
        ),
    )

    xlarge_context = _has(
        text,
        (
            r"\b(?:million[- ]token|multiple repositories|many repositories|dozens of services)\b",
            r"\b(?:huge|very large)\s+(?:document\s+)?(?:monorepo|corpus|context)\b",
        ),
    )
    large_context = _has(
        text,
        (
            r"\b(?:whole|entire|project[- ]wide|repo[- ]wide)\s+(?:repo|repository|codebase|project|system|router)\b",
            r"\b(?:all (?:production )?services|all modules|large repository|broad codebase)\b",
            r"\b(?:repo[- ]wide migration|large cross[- ]service patch|many modules)\b",
            r"\b(?:very large|huge)\s+(?:\w+[- ]?){0,2}context\b",
        ),
    )
    medium_context = _has(
        text,
        (
            r"\b(?:several|multiple|three|four|five)\s+(?:\w+\s+){0,2}(?:files|modules|services|tests|fixtures|handlers)\b",
            r"\bacross\s+(?:several|multiple|three|four|five)\s+(?:\w+\s+){0,2}(?:files|modules|services|tests|fixtures|handlers)\b",
            r"\b(?:medium[- ]sized|multi[- ]file|multi[- ]module|stack trace|synthetic patch)\b",
            r"\bmedium\s+(?:\w+\s+){0,2}(?:module|patch|migration|change)\b",
        ),
    ) or semantics.explicit_file_count >= 2
    tiny_context = _has(
        text,
        (
            r"\b(?:one|single)\s+(?:line|sentence|word|label|function|file)\b",
            r"\b(?:typo|spelling|grammar|button text|button label)\b",
        ),
    )
    if xlarge_context:
        context_size = "xlarge"
    elif large_context or router_context == "large":
        context_size = "large"
    elif medium_context or router_context == "medium":
        context_size = "medium"
    elif tiny_context or semantics.explicit_file_count == 1:
        context_size = "tiny"
    elif router_context == "small":
        context_size = "small"
    else:
        context_size = "unknown"

    broad_refactor = _has(
        text,
        (
            r"\b(?:large|broad|cross[- ]module|multi[- ]module|repo[- ]wide)\s+refactor\b",
            r"\brefactor\b.*\b(?:all|many)\s+(?:modules|services|files)\b",
        ),
    )
    if xlarge_context:
        likely_files = "xlarge"
    elif broad_refactor or large_context:
        likely_files = "large"
    elif medium_context:
        likely_files = "medium"
    elif tiny_context and coding:
        likely_files = "tiny"
    elif coding:
        likely_files = "small"
    else:
        likely_files = "tiny"

    if not edit_intent:
        edit_size = "tiny"
    elif broad_refactor or xlarge_context:
        edit_size = "xlarge" if xlarge_context else "large"
    elif large_context:
        edit_size = "large"
    elif medium_context:
        edit_size = "medium"
    elif tiny_context:
        edit_size = "tiny"
    else:
        edit_size = "small"

    # Execution intent is owned by the shared clause-state analyzer. Editing a
    # test or relying on test evidence is not itself an instruction to execute
    # tests, particularly when the user explicitly prohibited execution.
    explicit_test_requirement = semantics.test_execution_requested
    prototype_only = _has(
        text,
        (
            r"\b(?:prototype|mockup|spike|proof of concept)\b",
            r"\btests?\s+(?:are|is)\s+not\s+required\b",
        ),
    )
    correctness_depends_on_tests = bool(
        coding
        and edit_intent
        and not prototype_only
        and not _has(
            text,
            (
                r"\b(?:copy|label|wording|comment|typo|formatting|button text)\b",
                r"\bdeterministic\s+(?:python|javascript|typescript|rust|go|java)?\s*script\b",
            ),
        )
    )
    if _has(text, (r"\b(?:full|entire|complete)\s+(?:test )?suite\b", r"\bmany failing tests\b")):
        test_burden = "large"
    elif _has(text, (r"\b(?:several|multiple|five|six|ten)\s+(?:failing )?tests\b", r"\bintegration tests?\b")):
        test_burden = "medium"
    elif explicit_test_requirement or correctness_depends_on_tests:
        test_burden = "small"
    else:
        test_burden = "tiny"

    explicit_web_research = _has(
        text,
        (
            r"\b(?:web research|search the web|browse|online research|current landscape)\b",
            r"\b(?:latest|current)\b.*\b(?:documentation|programs|sources|information)\b",
            r"\b(?:current official guidance|current official api|current code[- ]formatting tools)\b",
        ),
    )
    bounded_local_documents = (
        1 <= semantics.explicit_file_count <= 2
        and semantics.explicit_document_count == semantics.explicit_file_count
        and not explicit_web_research
    )
    web_research = explicit_web_research or (
        category in {"research", "grant_work"} and not bounded_local_documents
    )
    source_verification = _has(
        text,
        (
            r"(?<!open-)\bsources?\b|\b(?:sourced|citation|cite|cited|verify|verification|official documentation|official guidance)\b",
            r"\bcompare eligibility\b",
        ),
    )
    web_research = web_research or source_verification
    external_tool_workflow = _has(
        text,
        (
            r"\b(?:connected|external)\s+(?:issue tracker|calendar|drive|service|tool|connector)\b",
            r"\b(?:issue tracker|calendar|drive|connector|external tool)\s+workflow\b",
            r"\b(?:query|search|inspect|update|use)\b.*\b(?:issue tracker|calendar|drive|connector)\b",
        ),
    )
    if _has(
        text,
        (
            r"\b(?:global|broad|strategic|comprehensive|multi[- ]source)\b.*\b(?:research|strategy|landscape|grant)\b",
            r"\b(?:legal|regulatory) constraints\b.*\b(?:regions|countries|global)\b",
        ),
    ):
        research_depth = "high"
    elif (
        (web_research or external_tool_workflow)
        and _has(
            text,
            (
                r"\b(?:research|compare|survey|investigate|verify|review)\b",
                r"\b(?:three|several|multiple)\s+(?:grants|programs|sources|options)\b",
                r"\b(?:repository history|compare approaches|technical question|eligibility)\b",
            ),
        )
    ) or _has(
        text,
        (
            r"\binspect repository history\b.*\bcompare\b",
            r"\bcompare\b.*\bcurrent\b.*\b(?:tools|services|libraries|approaches)\b",
        ),
    ):
        research_depth = "medium"
    else:
        research_depth = "low"

    rapid_signal = _has(
        text,
        (
            r"\b(?:targeted|isolated|one[- ]line|single[- ]file|single[- ]function|small ui)\b",
            r"\b(?:button|menu|field|label|copy|css|spacing|placeholder|icon|loading message|route constant)\b.*\b(?:change|edit|adjust|fix|rename|replace|update)\b",
            r"\b(?:change|edit|adjust|fix|rename|replace|update)\b.*\b(?:button|label|copy|css|spacing|placeholder|icon|loading message|route constant|one function|single function)\b",
            r"\brapid\s+(?:iteration|prototype|edit)\b",
            r"\b(?:one|a single)\b.*\b(?:local variable|field label|ui spacing|css token|component|fixture)\b",
        ),
    )
    rapid_edit = bool(
        coding
        and edit_intent
        and rapid_signal
        and edit_size in {"tiny", "small"}
        and context_size in {"tiny", "small", "medium"}
        and not broad_refactor
    )

    hard_debugging = _has(
        text,
        (
            r"\b(?:hard|difficult|intermittent|nondeterministic|distributed)\b(?:\s+\w+){0,4}\s+(?:bug|debugging|failure)\b",
            r"\b(?:uncertain|unknown)\s+root cause\b",
            r"\broot cause\b.*\b(?:unclear|across|several|multiple)\b",
        ),
    )
    negated_architecture_change = _has(
        text,
        (
            r"\bwithout\s+(?:changing|redesigning|altering)\s+(?:the\s+)?architecture\b",
            r"\bno\s+architecture\s+change\b",
        ),
    )
    architectural_depth = (
        "high"
        if (category == "architecture" and not negated_architecture_change) or broad_refactor or _has(
            text,
            (
                r"\barchitecture across\b",
                r"\bservice boundaries\b",
                r"\bredesign\b.*\b(?:across|several|multiple)\s+(?:services|modules|systems)\b",
                r"\b(?:novel algorithm|fault[- ]tolerant protocol|repo[- ]wide migration)\b",
                r"\bthreat model\b.*\b(?:complex|across|multiple|several)\b",
            ),
        )
        else "medium"
        if not negated_architecture_change
        and _has(text, (r"\b(?:design|architecture|module boundaries|refactor plan)\b",))
        else "low"
    )
    mathematical_depth = (
        "high"
        if category == "math_theory" and _has(text, (r"\b(?:proof|theorem|derive|difficult|novel)\b",))
        else "medium"
        if category == "math_theory" or _has(text, (r"\b(?:equation|calculate|mathematical)\b",))
        else "low"
    )
    deep_security = bool(
        _has(
            text,
            (
                r"\b(?:deep|complex|project[- ]wide|system[- ]wide)\s+(?:security|threat|audit)\b",
                r"\b(?:security architecture|threat model|exploit chain|auth(?:entication)? across)\b",
                r"\b(?:multiple|several)\s+(?:trust boundaries|services|vulnerabilities)\b",
                r"\bcomplex security implications\b",
            ),
        )
    )
    final_audit = _has(
        text,
        (
            r"\bfinal\s+(?:independent\s+)?(?:safety\s+|security\s+|engineering\s+)?(?:audit|review|assessment)\b",
            r"\bproject[- ]wide\s+(?:engineering|safety|security)\s+(?:audit|review)\b",
        ),
    )

    concrete_analysis = bool(
        analysis_intent
        and (
            coding
            or tiny_context
            or _has(
                text,
                (
                    r"\b(?:this|one|a single)\s+(?:sentence|function|expression|condition|declaration|policy)\b",
                    r"\breview this sentence\b",
                ),
            )
        )
    )
    ambiguous = (
        category == "unknown"
        and not rapid_edit
        and not clear_transformation
        and not simple_deterministic_task
        and not concrete_analysis
    ) or _has(
        text,
        (
            r"\b(?:ambiguous|unclear|mixed[- ]domain|uncertain root cause|make it better|do the thing)\b",
            r"\bseveral plausible causes\b",
        ),
    )
    ambiguity = "high" if ambiguous or hard_debugging else "medium" if category == "debugging" else "low"

    delegation = _has(
        text,
        (
            r"\bdelegat(?:e|ed|es|ing|ion)\b",
            r"\bsub[- ]?agents?\b",
            r"\bsplit\b.*\bagents?\b",
            r"\bmultiple agents\b",
            r"\bone agent per\b",
        ),
    )
    parallel_agents = _has(
        text,
        (r"\bparallel\s+(?:agents?|workstreams?)\b", r"\bone agent per\b", r"\bmultiple agents\b"),
    )
    if _has(text, (r"\b(?:four|five|six|many)\s+(?:independent )?workstreams\b", r"\blarge program\b")):
        workstreams = "large"
    elif delegation or parallel_agents or _has(text, (r"\b(?:several|multiple)\s+independent\s+(?:tasks|workstreams)\b",)):
        workstreams = "medium"
    elif _has(text, (r"\btwo\s+independent\s+(?:tasks|workstreams)\b",)):
        workstreams = "small"
    else:
        workstreams = "tiny"

    latency_sensitivity = (
        "high"
        if rapid_edit or _has(text, (r"\b(?:near[- ]instant|real[- ]time|latency dominates|interactive iteration)\b",))
        else "medium"
        if _has(text, (r"\b(?:quick|fast|rapid)\b",))
        else "low"
    )
    quality_sensitivity = (
        "high"
        if final_audit or deep_security or _has(text, (r"\b(?:high[- ]stakes|polished final|highest quality|legally constrained)\b",))
        else "medium"
        if source_verification or test_burden in {"medium", "large"} or _has(text, (r"\breview\b",))
        else "low"
    )

    if delegation and workstreams in {"medium", "large"}:
        expected_duration = "xlarge"
    elif xlarge_context or final_audit:
        expected_duration = "large"
    elif large_context or broad_refactor or source_verification:
        expected_duration = "large"
    elif medium_context or web_research or test_burden in {"medium", "large"}:
        expected_duration = "medium"
    elif coding or edit_intent:
        expected_duration = "small"
    else:
        expected_duration = "tiny"

    repository = bool(
        coding
        or _has(text, (r"\b(?:repo|repository|codebase|file|module|test)\b",))
    )
    if expected_duration in {"large", "xlarge"}:
        expected_tool_calls = "large"
    elif web_research or test_burden in {"medium", "large"} or likely_files == "medium":
        expected_tool_calls = "medium"
    elif repository:
        expected_tool_calls = "small"
    else:
        expected_tool_calls = "tiny"

    modalities = tuple(dict.fromkeys(str(item) for item in required_modalities))
    dangerous_irreversible = {
        "destructive_operation",
        "deployment_operation",
        "database_operation",
        "secret_touching_operation",
        "external_service_action",
    }
    side_effect = bool(edit_intent or action_danger not in {"read_only_analysis", "none"})
    deterministic_eval = _has(
        text,
        (r"\bdeterministic eval\b", r"\breproducib(?:le|ility)\b", r"\bbenchmark case\b", r"\beval case\b"),
    )

    return TaskFeatures(
        task_domain=category,
        coding=coding,
        work_mode=work_mode,
        likely_files=likely_files,
        edit_size=edit_size,
        expected_tool_calls=expected_tool_calls,
        test_burden=test_burden,
        expected_duration=expected_duration,
        repository=repository,
        context_size=context_size,
        required_modalities=modalities,
        image_requirement="image" in modalities,
        web_research_requirement=web_research,
        source_verification_requirement=source_verification,
        external_tool_workflow=external_tool_workflow,
        research_depth=research_depth,
        latency_sensitivity=latency_sensitivity,
        quality_sensitivity=quality_sensitivity,
        architectural_depth=architectural_depth,
        mathematical_depth=mathematical_depth,
        ambiguity=ambiguity,
        independent_workstreams=workstreams,
        need_for_delegation=delegation,
        need_for_parallel_agents=parallel_agents,
        side_effect_requirement=side_effect,
        reversible=action_danger not in dangerous_irreversible,
        risk=risk,
        action_danger=action_danger,
        explicit_model_preference=_model_preference(text),
        explicit_effort_preference=_effort_preference(text),
        clear_transformation=clear_transformation,
        simple_deterministic_task=simple_deterministic_task,
        rapid_edit=rapid_edit,
        broad_refactor=broad_refactor,
        hard_debugging=hard_debugging,
        deep_security=deep_security,
        final_audit=final_audit,
        deterministic_eval=deterministic_eval,
        explicit_test_requirement=explicit_test_requirement,
        correctness_depends_on_tests=correctness_depends_on_tests,
    )
