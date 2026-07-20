from __future__ import annotations

from dataclasses import fields
import json
from types import SimpleNamespace

import pytest

from smart_codex import __version__ as ROUTER_VERSION
from smart_codex.app_server_router.prompt_features import extract_task_features
from smart_codex.app_server_router.turn_router import RoutedTurn
from smart_codex.policy_version import MODEL_POLICY_VERSION
from smart_codex.preprocessor import analyze_prompt_semantics
from smart_codex.research_launcher import ROUTER_POLICY_VERSION
from smart_codex.router import RoutingDecision, route_prompt
from smart_codex.runtime.telemetry.codex_events import CodexEventAccumulator
from smart_codex.runtime.telemetry.collector import TelemetryService
from smart_codex.runtime.telemetry.dashboard import build_dashboard
from smart_codex.runtime.telemetry.schema import SCHEMA_VERSION
from smart_codex.runtime.telemetry.validator import validate_run_record
from smart_codex.scorer import ScoreCard, TASK_SUBDOMAINS, score

from telemetry_test_helpers import app_usage_event, enabled_service, records, start_basic


TARGET_COMPARISON = (
    "Read README.md and docs/TELEMETRY_RESEARCH_LOOP_2B2.md, report three "
    "differences, modify nothing, and run no tests."
)


def _digest(namespace: str, identifier: str) -> str:
    return (namespace + identifier).encode("utf-8").hex()[:64].ljust(64, "0")


def _request_completed(identifier: str) -> dict[str, object]:
    return {
        "type": "request.completed",
        "request_id": identifier,
        "usage": {
            "input_tokens": 10,
            "cached_input_tokens": 2,
            "output_tokens": 5,
            "reasoning_output_tokens": 1,
            "total_tokens": 15,
        },
    }


def test_document_comparison_has_independent_controlled_subdomain() -> None:
    decision = route_prompt(TARGET_COMPARISON)

    assert decision.category == "research"
    assert decision.task_subdomain == "document_comparison"
    assert decision.task_subdomain in TASK_SUBDOMAINS
    assert decision.action_danger == "read_only_analysis"
    assert decision.task_subdomain != decision.action_danger
    assert "document_comparison_subdomain" in decision.semantic_reason_codes


def test_positive_test_execution_has_test_subdomain() -> None:
    decision = route_prompt("Run the focused test suite.")

    assert decision.category == "testing"
    assert decision.task_subdomain == "test_execution"
    assert decision.action_danger == "run_tests"


def test_security_subdomain_does_not_inherit_action_danger() -> None:
    decision = route_prompt("Audit auth permissions without accessing credentials.")

    assert decision.category == "security_audit"
    assert decision.task_subdomain == "security_audit"
    assert decision.action_danger == "read_only_analysis"
    assert decision.task_subdomain != decision.action_danger


def test_unknown_subdomain_remains_null() -> None:
    decision = route_prompt("Hello.")

    assert decision.category == "unknown"
    assert decision.task_subdomain is None


@pytest.mark.parametrize(
    "prompt",
    [
        "Run no tests.",
        "Do not run tests.",
        "Don't run the tests.",
        "Without running tests, inspect the code.",
        "Do not execute pytest.",
    ],
)
def test_english_negated_test_actions_are_suppressed(prompt: str) -> None:
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)

    assert semantics.test_intent == "negative"
    assert "test_execution_prohibited" in semantics.safety_constraints
    assert "negated_test_action_suppressed" in decision.semantic_reason_codes
    assert decision.action_danger != "run_tests"
    assert decision.task_subdomain != "test_execution"


@pytest.mark.parametrize(
    "prompt",
    [
        "Run the tests.",
        "Execute pytest.",
        "Run the focused test suite.",
    ],
)
def test_english_positive_test_actions_remain_positive(prompt: str) -> None:
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)

    assert semantics.test_intent == "positive"
    assert decision.action_danger == "run_tests"
    assert decision.task_subdomain == "test_execution"
    assert "positive_test_action_detected" in decision.semantic_reason_codes


def test_english_mixed_test_clause_preserves_positive_integration_action() -> None:
    prompt = "Do not run unit tests, but run integration tests."
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)

    assert semantics.test_intent == "mixed"
    assert decision.action_danger == "run_tests"
    assert decision.task_subdomain == "test_execution"
    assert decision.semantic_reason_codes[:2] == [
        "negated_test_action_suppressed",
        "positive_test_action_detected",
    ]


@pytest.mark.parametrize(
    "prompt",
    [
        "Nie uruchamiaj testów.",
        "Nie wykonuj testów.",
        "Bez uruchamiania testów przeczytaj dokumentację.",
        "Nie używaj pytest.",
    ],
)
def test_polish_negated_test_actions_are_suppressed(prompt: str) -> None:
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)

    assert semantics.test_intent == "negative"
    assert decision.action_danger != "run_tests"
    assert decision.task_subdomain != "test_execution"
    assert decision.sandbox_mode == "read-only"


@pytest.mark.parametrize(
    "prompt",
    [
        "Uruchom testy.",
        "Wykonaj pytest.",
        "Uruchom pełny zestaw testów.",
    ],
)
def test_polish_positive_test_actions_remain_positive(prompt: str) -> None:
    decision = route_prompt(prompt)

    assert decision.action_danger == "run_tests"
    assert decision.task_subdomain == "test_execution"


def test_polish_mixed_test_clause_preserves_positive_integration_action() -> None:
    prompt = "Nie uruchamiaj testów jednostkowych, ale uruchom testy integracyjne."
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)

    assert semantics.test_intent == "mixed"
    assert decision.action_danger == "run_tests"
    assert decision.task_subdomain == "test_execution"


@pytest.mark.parametrize(
    "prompt",
    [
        "Do not run tests or execute pytest.",
        "Do not run unit tests or run pytest.",
        "Do not execute pytest or launch the test suite.",
        "Nie uruchamiaj testów ani nie wykonuj pytest.",
        "Nie wykonuj testów lub pytest.",
        "Bez uruchamiania testów ani pytest przeanalizuj kod.",
        "- Do not run tests.\n- Do not execute pytest.",
    ],
)
def test_coordinated_negative_test_actions_remain_non_executing(prompt: str) -> None:
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)

    assert semantics.test_intent == "negative"
    assert decision.action_danger != "run_tests"
    assert decision.task_subdomain != "test_execution"
    assert decision.sandbox_mode == "read-only"


@pytest.mark.parametrize(
    "prompt",
    [
        "Explain how to run tests without executing anything.",
        "Describe how pytest works.",
        "Document the command used to run tests.",
        "Show an example of how a developer could execute pytest, but do not execute it.",
        'What does "run the tests" mean?',
        'The documentation says "run the tests". Explain this sentence.',
        "Wyjaśnij, jak uruchamia się testy, ale ich nie uruchamiaj.",
        "Opisz działanie pytest bez jego wykonywania.",
        "Udokumentuj komendę do uruchamiania testów.",
        'Dokumentacja zawiera zdanie "uruchom testy". Wyjaśnij je.',
    ],
)
def test_descriptive_or_quoted_test_language_is_not_execution(prompt: str) -> None:
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)

    assert semantics.test_intent in {"none", "negative"}
    assert decision.action_danger != "run_tests"
    assert decision.task_subdomain != "test_execution"
    assert decision.sandbox_mode == "read-only"


@pytest.mark.parametrize(
    "prompt",
    [
        "Do not run unit tests, but run integration tests.",
        "Do not execute pytest; run the smoke test instead.",
        "Nie uruchamiaj testów jednostkowych, ale uruchom testy integracyjne.",
        "Nie wykonuj pytest, lecz wykonaj test dymny.",
    ],
)
def test_contrast_clause_preserves_genuine_positive_test_action(prompt: str) -> None:
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)

    assert semantics.test_intent == "mixed"
    assert decision.action_danger == "run_tests"
    assert decision.task_subdomain == "test_execution"


def test_negative_test_constraint_preserves_code_correctness_dependency() -> None:
    prompt = "Fix a bug in parser.py. Do not run tests."
    decision = route_prompt(prompt)
    features = extract_task_features(prompt, decision, required_modalities=("text",))

    assert decision.action_danger == "write_local_files"
    assert features.explicit_test_requirement is False
    assert features.correctness_depends_on_tests is True
    assert features.test_burden == "small"


def test_mixed_test_constraint_preserves_model_policy_test_requirement() -> None:
    prompt = "Do not run unit tests, but run integration tests."
    decision = route_prompt(prompt)
    features = extract_task_features(prompt, decision, required_modalities=("text",))

    assert features.explicit_test_requirement is True


@pytest.mark.parametrize(
    ("prompt", "execution_requested", "correctness_depends"),
    [
        (
            "Read README.md and docs/guide.md; report three differences and do not run tests.",
            False,
            False,
        ),
        ("Explain pytest; do not execute it.", False, False),
        ("Fix a bug in parser.py. Do not run tests.", False, True),
        ("Refactor parser.py without running tests.", False, True),
        ("Modify parser.py, then run the tests.", True, True),
        ("Summarize README.md briefly.", False, False),
    ],
)
def test_execution_intent_is_separate_from_correctness_dependency(
    prompt: str,
    execution_requested: bool,
    correctness_depends: bool,
) -> None:
    decision = route_prompt(prompt)
    features = extract_task_features(prompt, decision, required_modalities=("text",))

    assert features.explicit_test_requirement is execution_requested
    assert features.correctness_depends_on_tests is correctness_depends
    if correctness_depends:
        assert features.test_burden != "tiny"


@pytest.mark.parametrize(
    ("prompt", "expected_scope", "expected_count"),
    [
        ("Read `README.md` and summarize it briefly.", "single_file", 1),
        ("Compare README.md and docs/guide.md briefly.", "module", 2),
        ("Compare README.md with `README.md` and report one difference.", "single_file", 1),
        ("Review:\n- src/parser.py\n- tests/test_parser.py", "module", 2),
        ("Review `src/parser.py` without changing it.", "single_file", 1),
        ("Review this file and summarize it.", "unknown", 0),
        ("Review the entire repository and summarize its structure.", "repo", 0),
    ],
)
def test_scope_uses_distinct_explicit_file_references(
    prompt: str,
    expected_scope: str,
    expected_count: int,
) -> None:
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)

    assert semantics.explicit_file_count == expected_count
    assert decision.execution_scope == expected_scope


def test_quoting_and_punctuation_do_not_create_distinct_paths() -> None:
    semantics = analyze_prompt_semantics(
        'Review "README.md", (`README.md`), and README.md; summarize it briefly.'
    )

    assert semantics.explicit_file_count == 1


def test_case_distinct_paths_remain_distinct_on_case_sensitive_hosts() -> None:
    semantics = analyze_prompt_semantics("Compare Guide.md and guide.md briefly.")

    assert semantics.explicit_file_count == 2


@pytest.mark.parametrize(
    ("prompt", "expected_count"),
    [
        ("Compare a.json and a.jsonl.", 2),
        ("Compare a.jsonl with `a.jsonl`.", 1),
        ("Compare README.md with ./README.md.", 1),
        ("Compare README.md with docs/../README.md.", 1),
        ("Compare docs/a.md with docs/b.md.", 2),
        ("Read https://example.com/a.md.", 0),
        ("Read README.md, then docs/a.md.", 2),
        ("Review:\n- `docs/a.md`\n- `docs/b.md`", 2),
        ("Compare README and docs/guide.", 0),
    ],
)
def test_local_file_references_use_terminal_extensions_and_lexical_normalization(
    prompt: str,
    expected_count: int,
) -> None:
    semantics = analyze_prompt_semantics(prompt)

    assert semantics.explicit_file_count == expected_count


def test_bounded_one_document_summary_is_low_difficulty() -> None:
    decision = route_prompt("Read README.md and provide a short summary. Modify nothing.")

    assert decision.complexity_level == "low"
    assert decision.action_danger == "read_only_analysis"


def test_bounded_two_document_comparison_is_low_without_weakening_controls() -> None:
    decision = route_prompt(TARGET_COMPARISON)

    assert decision.complexity_level == "low"
    assert decision.risk_level == "low"
    assert decision.sandbox_mode == "read-only"
    assert decision.approval_policy == "on-request"
    assert "bounded_read_only_comparison" in decision.semantic_reason_codes


@pytest.mark.parametrize(
    "prompt",
    [
        "Browse the web and compare README.md with docs/guide.md using current sources.",
        "Synthesize an architecture design from ARCHITECTURE.md and docs/design.md.",
        "Audit auth permissions in SECURITY.md and PRIVACY.md; report three findings.",
        "Audit SECURITY.md and PRIVACY.md; report three findings.",
        "Perform a privacy audit of PRIVACY.md and README.md; report three findings.",
        "Compare README.md and docs/guide.md and exhaustively analyze every clause.",
        "Compare README.md and docs/guide.md, query the API, and report three differences.",
        "Compare README.md and docs/guide.md using jq, sed, and awk; report three differences.",
        "Modify README.md and docs/guide.md, then run tests.",
    ],
)
def test_bounded_rule_does_not_downgrade_excluded_work(prompt: str) -> None:
    decision = route_prompt(prompt)

    assert decision.complexity_level in {"medium", "high"}
    assert "bounded_read_only_comparison" not in decision.semantic_reason_codes


@pytest.mark.parametrize(
    "prompt",
    [
        "Delete README.md and docs/guide.md and report three points.",
        "Remove README.md and docs/guide.md and report three points.",
        "Move README.md and docs/guide.md and report three points.",
        "Append to README.md and docs/guide.md and report three points.",
        "Usuń README.md i docs/guide.md oraz podaj trzy punkty.",
        "Przenieś README.md i docs/guide.md oraz podaj trzy punkty.",
    ],
)
def test_document_write_actions_are_never_bounded_low(prompt: str) -> None:
    decision = route_prompt(prompt)

    assert decision.action_danger != "read_only_analysis"
    assert "bounded_read_only_comparison" not in decision.semantic_reason_codes
    assert decision.approval_policy == "on-request"


def test_sensitive_document_task_is_classified_and_not_downgraded() -> None:
    decision = route_prompt("Audit SECURITY.md and PRIVACY.md; report three findings.")

    assert decision.category == "security_audit"
    assert decision.task_subdomain == "security_audit"
    assert decision.complexity_level == "medium"
    assert decision.risk_level in {"medium", "high", "critical"}
    assert decision.action_danger == "read_only_analysis"
    assert decision.sandbox_mode == "read-only"
    assert decision.approval_policy == "on-request"


def test_supported_code_subdomains_use_controlled_vocabulary() -> None:
    generated = route_prompt("Implement a function in parser.py.")
    modified = route_prompt("Fix a bug in parser.py.")
    researched = route_prompt("Research current database libraries online.")
    architecture = route_prompt("Design a service architecture.")

    assert generated.task_subdomain == "code_generation"
    assert modified.task_subdomain == "code_modification"
    assert researched.task_subdomain == "general_research"
    assert architecture.task_subdomain == "architecture_design"
    assert {
        generated.task_subdomain,
        modified.task_subdomain,
        researched.task_subdomain,
        architecture.task_subdomain,
    } <= TASK_SUBDOMAINS


def test_unknown_counters_remain_distinct_from_explicit_zero() -> None:
    unknown = CodexEventAccumulator(_digest).finalize()
    explicit_zero = CodexEventAccumulator(_digest)
    assert explicit_zero.consume({"type": "retry.count", "count": 0}) is True

    assert unknown.values["request_count"] is None
    assert unknown.values["retry_count"] is None
    assert explicit_zero.finalize().values["retry_count"] is None
    assert explicit_zero.finalize(lifecycle_status="completed").values["retry_count"] == 0


@pytest.mark.parametrize("request_ids", [("request-1",), ("request-1", "request-2")])
def test_completed_request_ids_prove_request_count(request_ids: tuple[str, ...]) -> None:
    accumulator = CodexEventAccumulator(_digest)
    for request_id in request_ids:
        assert accumulator.consume(_request_completed(request_id)) is True

    metrics = accumulator.finalize()
    assert metrics.values["request_count"] == len(request_ids)
    assert metrics.sources["request_count"] == "measured"


def test_request_start_without_completion_does_not_prove_request_count() -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume({"type": "request.started", "request_id": "request-1"}) is True

    assert accumulator.finalize().values["request_count"] is None


def test_explicit_request_count_is_used_when_it_is_the_only_evidence() -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume({"type": "request.count", "count": 2}) is True

    metrics = accumulator.finalize()
    assert metrics.values["request_count"] == 2
    assert metrics.sources["request_count"] == "provider_reported"


def test_agreeing_request_count_sources_reconcile() -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume(_request_completed("request-1")) is True
    assert accumulator.consume(_request_completed("request-2")) is True
    assert accumulator.consume({"type": "request.count", "count": 2}) is True

    metrics = accumulator.finalize()
    assert metrics.values["request_count"] == 2
    assert metrics.sources["request_count"] == "measured"
    assert metrics.unreconciled is False


def test_conflicting_request_count_sources_fail_closed() -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume(_request_completed("request-1")) is True
    assert accumulator.consume(_request_completed("request-2")) is True
    assert accumulator.consume({"type": "request.count", "count": 1}) is True

    metrics = accumulator.finalize()
    assert metrics.values["request_count"] is None
    assert metrics.sources["request_count"] == "unknown"
    assert metrics.unreconciled is True


def test_regressing_request_count_snapshot_fails_closed() -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume({"type": "request.count", "count": 2}) is True
    assert accumulator.consume({"type": "request.count", "count": 1}) is True

    metrics = accumulator.finalize()
    assert metrics.values["request_count"] is None
    assert metrics.unreconciled is True


def test_malformed_request_count_is_rejected() -> None:
    accumulator = CodexEventAccumulator(_digest)

    assert accumulator.consume({"type": "request.count", "count": -1}) is False
    assert accumulator.consume({"type": "request.count", "count": "2"}) is False
    assert accumulator.finalize().values["request_count"] is None
    assert accumulator.invalid_event_count == 2


@pytest.mark.parametrize("retry_count", [1, 2])
def test_explicit_retry_counter_is_preserved(retry_count: int) -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume({"type": "retry.count", "count": retry_count}) is True

    metrics = accumulator.finalize()
    assert metrics.values["retry_count"] == retry_count
    assert metrics.sources["retry_count"] == "provider_reported"


def test_unsupported_retry_event_cannot_manufacture_a_positive_count() -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume({"type": "retry.started", "id": "retry-1"}) is False

    metrics = accumulator.finalize(lifecycle_status="aborted")
    assert metrics.values["retry_count"] is None
    assert metrics.sources["retry_count"] == "unknown"
    assert metrics.unreconciled is True


def test_retry_zero_requires_normal_terminal_completion() -> None:
    incomplete = CodexEventAccumulator(_digest)
    aborted = CodexEventAccumulator(_digest)
    completed = CodexEventAccumulator(_digest)
    for accumulator in (incomplete, aborted, completed):
        assert accumulator.consume({"type": "retry.count", "count": 0}) is True

    assert incomplete.finalize().values["retry_count"] is None
    assert aborted.finalize(lifecycle_status="aborted").values["retry_count"] is None
    metrics = completed.finalize(lifecycle_status="completed")
    assert metrics.values["retry_count"] == 0
    assert metrics.sources["retry_count"] == "provider_reported"


def test_regressing_retry_snapshot_fails_closed_without_lowering() -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume({"type": "retry.count", "count": 2}) is True
    assert accumulator.consume({"type": "retry.count", "count": 1}) is True

    metrics = accumulator.finalize(lifecycle_status="completed")
    assert metrics.values["retry_count"] is None
    assert metrics.unreconciled is True


def test_duplicate_retry_event_does_not_inflate_count() -> None:
    accumulator = CodexEventAccumulator(_digest)
    event = {"type": "retry.started", "id": "retry-1"}
    assert accumulator.consume(event) is False
    assert accumulator.consume(event) is False

    metrics = accumulator.finalize(lifecycle_status="completed")
    assert metrics.values["retry_count"] is None
    assert metrics.unreconciled is True
    assert metrics.duplicate_event_count == 1


def test_retry_zero_with_unsupported_observed_ids_fails_closed() -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume({"type": "retry.count", "count": 0}) is True
    assert accumulator.consume({"type": "retry.started", "id": "retry-1"}) is False

    metrics = accumulator.finalize(lifecycle_status="completed")
    assert metrics.values["retry_count"] is None
    assert metrics.sources["retry_count"] == "unknown"
    assert metrics.unreconciled is True


def test_aborted_run_does_not_persist_retry_zero(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    assert run.consume_event({"type": "retry.count", "count": 0}) is True
    assert run.finish(status="aborted").appended is True

    record = records(storage, "run")[0]
    assert record["retry_count"] is None
    assert record["measurement_sources"]["retry_count"] == "unknown"


def test_duplicate_completed_request_id_is_not_double_counted() -> None:
    accumulator = CodexEventAccumulator(_digest)
    event = _request_completed("request-1")
    assert accumulator.consume(event) is True
    assert accumulator.consume(event) is False

    metrics = accumulator.finalize()
    assert metrics.values["request_count"] == 1
    assert metrics.duplicate_event_count == 1


def test_repeated_request_id_with_changed_payload_becomes_unavailable() -> None:
    accumulator = CodexEventAccumulator(_digest)
    first = _request_completed("request-1")
    second = _request_completed("request-1")
    second["usage"] = {
        "input_tokens": 11,
        "cached_input_tokens": 2,
        "output_tokens": 5,
        "reasoning_output_tokens": 1,
        "total_tokens": 16,
    }

    assert accumulator.consume(first) is True
    assert accumulator.consume(second) is True
    metrics = accumulator.finalize()
    assert metrics.values["request_count"] is None
    assert metrics.values["total_reported_tokens"] is None
    assert metrics.unreconciled is True


def test_repeated_cumulative_count_events_use_latest_value_without_summing() -> None:
    accumulator = CodexEventAccumulator(_digest)

    assert accumulator.consume({"type": "request.count", "count": 1}) is True
    assert accumulator.consume({"type": "request.count", "count": 2}) is True
    assert accumulator.consume({"type": "request.count", "count": 2}) is False
    assert accumulator.consume({"type": "retry.count", "count": 1}) is True
    assert accumulator.consume({"type": "retry.count", "count": 2}) is True
    assert accumulator.consume({"type": "retry.count", "count": 2}) is False

    metrics = accumulator.finalize()
    assert metrics.values["request_count"] == 2
    assert metrics.values["retry_count"] == 2
    assert metrics.duplicate_event_count == 2


def test_repeated_cumulative_events_do_not_invent_request_or_retry_counts() -> None:
    accumulator = CodexEventAccumulator(_digest)
    event = app_usage_event(
        turn_id="turn-1",
        last_input=10,
        last_cached=2,
        last_output=5,
        last_reasoning=1,
        cumulative_total=15,
    )
    assert accumulator.consume(event) is True
    assert accumulator.consume(event) is False

    metrics = accumulator.finalize()
    assert metrics.values["request_count"] is None
    assert metrics.values["retry_count"] is None
    assert metrics.duplicate_event_count == 1


def test_new_decisions_and_records_use_policy_v03(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    decision = route_prompt(TARGET_COMPARISON)
    started = service.start_from_decision(task=TARGET_COMPARISON, decision=decision)
    assert started.run is not None
    assert started.run.finish(status="completed").appended is True
    record = records(storage, "run")[0]

    assert MODEL_POLICY_VERSION == "model-policy-calibration-v0.3"
    assert ROUTER_POLICY_VERSION == MODEL_POLICY_VERSION
    assert decision.policy_version == MODEL_POLICY_VERSION
    assert record["router_policy_version"] == MODEL_POLICY_VERSION
    assert record["task_subdomain"] == "document_comparison"
    assert record["task_scope"] == "module"
    assert record["task_difficulty"] == "low"
    validate_run_record(record)

    snapshot = build_dashboard(storage, limit=1)
    serialized = json.dumps(snapshot, sort_keys=True)
    assert snapshot["label_quality"]["status"] == "quarantined"
    assert "document_comparison" not in serialized


@pytest.mark.parametrize(
    "historical_policy_version",
    ["model-policy-calibration-v0.1", "model-policy-calibration-v0.2"],
)
def test_historical_policy_records_remain_valid_and_dashboard_quarantined(
    tmp_path,
    historical_policy_version: str,
) -> None:
    _, storage = enabled_service(tmp_path)
    historical_service = TelemetryService(
        storage,
        router_policy_version=historical_policy_version,
    )
    run = start_basic(
        historical_service,
        task="synthetic historical compatibility fixture",
        task_subdomain="run_tests",
    )
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    validate_run_record(record)

    snapshot = build_dashboard(storage, limit=1)
    serialized = json.dumps(snapshot, sort_keys=True)
    assert record["router_policy_version"] == historical_policy_version
    assert snapshot["label_quality"]["status"] == "quarantined"
    assert "run_tests" not in serialized


@pytest.mark.parametrize(
    ("provenance", "expected"),
    [
        ("model-policy-calibration-v0.3", "model-policy-calibration-v0.3"),
        ("model-policy-calibration-v0.2", "model-policy-calibration-v0.2"),
        ("model-policy-calibration-v0.1", "model-policy-calibration-v0.1"),
        (None, "unknown"),
        ("malformed policy value!", "unknown"),
        ("model-policy-calibration-v9.9", "unknown"),
    ],
)
def test_decision_policy_provenance_is_never_inferred_from_current_software(
    tmp_path,
    provenance: str | None,
    expected: str,
) -> None:
    _, storage = enabled_service(tmp_path)
    service = TelemetryService(
        storage,
        router_policy_version=MODEL_POLICY_VERSION,
    )
    values = {
        "category": "unknown",
        "task_subdomain": None,
        "complexity_level": "low",
        "execution_scope": "unknown",
        "risk_level": "low",
        "selected_model": None,
        "reasoning_effort": "low",
        "sandbox_mode": "read-only",
        "approval_policy": "on-request",
    }
    if provenance is not None:
        values["policy_version"] = provenance
    decision = SimpleNamespace(**values)

    started = service.start_from_decision(
        task="synthetic policy provenance fixture",
        decision=decision,
    )
    assert started.run is not None
    assert started.run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert record["router_policy_version"] == expected
    validate_run_record(record)


def test_routed_turn_preserves_historical_positional_field_order() -> None:
    historical_names = [
        "message",
        "prompt_hash",
        "category",
        "route_class",
        "original_model",
        "selected_model",
        "effort",
        "sandbox_mode",
        "approval_policy",
        "reasons",
        "candidate_scores",
        "rejected_candidates",
        "fallback_order",
        "selection_confidence",
        "switch_confidence",
        "previous_model",
        "score_margin",
        "switch_reason",
        "selection_explanation",
        "drift_warnings",
        "migration_warning",
        "task_difficulty",
        "task_scope",
        "task_risk",
        "action_danger",
        "verification_available",
    ]
    assert [item.name for item in fields(RoutedTurn)][: len(historical_names)] == historical_names
    positional_values = [
        {},
        "hash",
        "unknown",
        "standard",
        None,
        "gpt-5",
        "low",
        "read-only",
        "on-request",
        (),
        (),
        None,
        (),
        "high",
        "high",
        None,
        0.0,
        "stay",
        "legacy",
        (),
        None,
        "low",
        "single_file",
        "low",
        "read_only_analysis",
        True,
    ]
    routed = RoutedTurn(*positional_values)
    assert routed.verification_available is True
    assert routed.task_subdomain is None
    assert routed.policy_version is None


def test_score_card_preserves_historical_positional_field_order() -> None:
    historical_names = [
        "category",
        "profile",
        "risk_level",
        "complexity_level",
        "evidence_requirement",
        "context_requirement",
        "action_danger",
        "confidence",
        "confidence_level",
        "category_scores",
        "top_categories",
        "mixed_categories",
        "override",
        "warnings",
        "reasons",
        "repo_impact",
        "security_sensitivity",
        "destructiveness",
        "execution_scope",
        "safety_constraints",
        "source",
    ]
    assert [item.name for item in fields(ScoreCard)][: len(historical_names)] == historical_names
    positional_values = [
        "unknown",
        "standard",
        "low",
        "medium",
        "none",
        "small",
        "read_only_analysis",
        0.0,
        "low",
        {},
        [],
        [],
        None,
        [],
        [],
        "none",
        "none",
        "none",
        "unknown",
        [],
        "legacy_source",
    ]
    card = ScoreCard(*positional_values)
    assert card.source == "legacy_source"
    assert card.task_subdomain is None


def test_schema_version_and_security_authority_boundaries_are_unchanged() -> None:
    decision = route_prompt("Audit auth permissions without accessing credentials.")

    assert ROUTER_VERSION == "0.1.0"
    assert SCHEMA_VERSION == "2.0.0"
    assert decision.risk_level == "high"
    assert decision.action_danger == "read_only_analysis"
    assert decision.sandbox_mode == "read-only"
    assert decision.approval_policy == "on-request"


@pytest.mark.parametrize(
    "prompt",
    [
        "Review whether to run tests.",
        "Should I run tests?",
        "REVIEW WHETHER TO RUN TESTS!",
        "Can you run pytest?",
        'Review the statement "run tests".',
        'The documentation says "run pytest".',
        "Describe how to run pytest.",
    ],
)
def test_review_questions_and_mentions_never_become_execution(prompt: str) -> None:
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)
    features = extract_task_features(prompt, decision, required_modalities=("text",))

    assert semantics.test_execution_requested is False
    assert semantics.test_intent in {"none", "negative"}
    assert features.explicit_test_requirement is False
    assert decision.action_danger == "read_only_analysis"
    assert decision.task_subdomain != "test_execution"
    assert decision.sandbox_mode == "read-only"


@pytest.mark.parametrize(
    "prompt",
    [
        "Run pytest.",
        "Uruchom pytest.",
        "Without delay, run tests.",
        "Bez zwłoki uruchom testy.",
        'Run "pytest".',
        "Run `pytest`.",
        "RUN PYTEST!",
    ],
)
def test_imperative_and_quoted_targets_remain_executable(prompt: str) -> None:
    original = prompt
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)
    features = extract_task_features(prompt, decision, required_modalities=("text",))

    assert prompt == original
    assert semantics.test_execution_requested is True
    assert semantics.test_intent == "positive"
    assert features.explicit_test_requirement is True
    assert decision.action_danger == "run_tests"
    assert decision.task_subdomain == "test_execution"


@pytest.mark.parametrize(
    "prompt",
    [
        "Explain how pytest works, then run tests.",
        "Describe the test command, and then execute it.",
        "Najpierw wyjaśnij pytest, a następnie uruchom testy.",
        "Explain pytest. After that, run tests.",
        "Describe pytest; next execute the tests.",
        "Opisz pytest; potem uruchom testy.",
        "Explain pytest; subsequently execute it.",
        "- Explain how pytest works.\n- Run tests.",
    ],
)
def test_independent_later_clause_establishes_execution(prompt: str) -> None:
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)

    assert semantics.test_execution_requested is True
    assert decision.action_danger == "run_tests"
    assert decision.task_subdomain == "test_execution"


@pytest.mark.parametrize(
    "prompt",
    [
        "Do not not run tests.",
        "Do not, under any circumstances, run tests.",
        "Do not, for now, execute pytest.",
    ],
)
def test_ambiguous_or_long_test_prohibitions_fail_closed(prompt: str) -> None:
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)

    assert semantics.test_execution_requested is False
    assert semantics.test_execution_prohibited is True
    assert decision.action_danger != "run_tests"


def test_markdown_clause_boundary_preserves_later_genuine_execution() -> None:
    prompt = "- Do not run unit tests.\n- Run integration tests."
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)

    assert semantics.test_intent == "mixed"
    assert decision.action_danger == "run_tests"


@pytest.mark.parametrize(
    "prompt",
    [
        "Fix unit tests in tests/test_parser.py; do not run tests.",
        "Napraw testy jednostkowe w tests/test_parser.py; nie uruchamiaj testów.",
    ],
)
def test_test_editing_prohibition_keeps_correctness_dependency(prompt: str) -> None:
    semantics = analyze_prompt_semantics(prompt)
    decision = route_prompt(prompt)
    features = extract_task_features(prompt, decision, required_modalities=("text",))

    assert semantics.test_execution_prohibited is True
    assert semantics.test_execution_requested is False
    assert semantics.test_modification_intent is True
    assert features.explicit_test_requirement is False
    assert features.correctness_depends_on_tests is True
    assert features.test_burden != "tiny"
    assert decision.action_danger == "write_local_files"
    assert decision.sandbox_mode == "workspace-write"
    assert decision.approval_policy == "on-request"


@pytest.mark.parametrize(
    "prompt",
    [
        "Audit and compare privacy controls in SECURITY.md and PRIVACY.md; report three differences.",
        "Compare SECURITY.md and PRIVACY.md; report three differences.",
        "Audit security controls in SECURITY.md; report three findings.",
        "Review privacy protections in PRIVACY.md; give a short summary.",
        "Compare authentication and authorization rules in auth_a.md and auth_b.md; report three differences.",
        "Perform a compliance review of COMPLIANCE.md and summarize three findings.",
        "Investigate an incident report in INCIDENT.md; summarize three findings.",
        "Przeprowadź audyt bezpieczeństwa pliku SECURITY.md; podaj trzy wnioski.",
        "Porównaj zasady prywatności w SECURITY.md i PRIVACY.md; podaj trzy różnice.",
    ],
)
def test_sensitive_document_work_never_receives_bounded_low(prompt: str) -> None:
    decision = route_prompt(prompt)

    assert decision.category in {"security_audit", "incident_response", "legal_admin"}
    if decision.category in {"security_audit", "incident_response"}:
        assert decision.task_subdomain == "security_audit"
    assert decision.complexity_level in {"medium", "high"}
    assert decision.risk_level in {"medium", "high", "critical"}
    assert decision.action_danger == "read_only_analysis"
    assert decision.sandbox_mode == "read-only"
    assert decision.approval_policy == "on-request"
    assert "bounded_read_only_comparison" not in decision.semantic_reason_codes


@pytest.mark.parametrize(
    "prompt",
    [
        "Delete README.md and guide.md; report three points.",
        "Rename README.md and guide.md; report three points.",
        "Overwrite README.md and guide.md; report three points.",
        "Edit README.md and guide.md; report three points.",
        "Refactor parser.py and tests/test_parser.py; report three changes.",
    ],
)
def test_every_write_capable_document_task_is_excluded_from_bounded_low(
    prompt: str,
) -> None:
    decision = route_prompt(prompt)

    assert decision.action_danger != "read_only_analysis"
    assert "bounded_read_only_comparison" not in decision.semantic_reason_codes


def test_completed_clean_explicit_retry_zero_is_trusted() -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume({"type": "retry.count", "count": 0}) is True

    metrics = accumulator.finalize(lifecycle_status="completed")
    assert metrics.values["retry_count"] == 0
    assert metrics.sources["retry_count"] == "provider_reported"
    assert metrics.unreconciled is False


@pytest.mark.parametrize("lifecycle_status", [None, "aborted", "process_error", "collector_interrupted"])
def test_retry_zero_requires_normal_completion(lifecycle_status: str | None) -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume({"type": "retry.count", "count": 0}) is True

    metrics = accumulator.finalize(lifecycle_status=lifecycle_status)
    assert metrics.values["retry_count"] is None
    assert metrics.sources["retry_count"] == "unknown"


@pytest.mark.parametrize(
    "event",
    [
        {"type": "retry.started", "id": "retry-1"},
        {"type": "retry.completed", "id": "retry-1"},
        {"type": "model/request/retry", "retry_count": 1},
        {"type": "model/request/retried", "count": 1},
    ],
)
def test_unsupported_retry_like_evidence_blocks_trusted_zero(
    event: dict[str, object],
) -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume({"type": "retry.count", "count": 0}) is True
    assert accumulator.consume(event) is False

    metrics = accumulator.finalize(lifecycle_status="completed")
    assert metrics.values["retry_count"] is None
    assert metrics.sources["retry_count"] == "unknown"
    assert metrics.unreconciled is True


def test_zero_then_supported_positive_retry_snapshot_stays_positive() -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume({"type": "retry.count", "count": 0}) is True
    assert accumulator.consume({"type": "retry.count", "count": 2}) is True

    metrics = accumulator.finalize(lifecycle_status="completed")
    assert metrics.values["retry_count"] == 2
    assert metrics.sources["retry_count"] == "provider_reported"


def test_positive_then_zero_retry_snapshot_never_becomes_zero() -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume({"type": "retry.count", "count": 2}) is True
    assert accumulator.consume({"type": "retry.count", "count": 0}) is True

    metrics = accumulator.finalize(lifecycle_status="completed")
    assert metrics.values["retry_count"] is None
    assert metrics.unreconciled is True


@pytest.mark.parametrize("malformed", ["0", "one", -1, None, True])
def test_malformed_retry_snapshot_keeps_state_unknown(malformed: object) -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume({"type": "retry.count", "count": malformed}) is False

    metrics = accumulator.finalize(lifecycle_status="completed")
    assert metrics.values["retry_count"] is None
    assert metrics.sources["retry_count"] == "unknown"
    assert metrics.unreconciled is True


def test_absent_retry_evidence_does_not_fabricate_completed_zero() -> None:
    metrics = CodexEventAccumulator(_digest).finalize(lifecycle_status="completed")

    assert metrics.values["retry_count"] is None
    assert metrics.sources["retry_count"] == "unknown"


def test_routing_decision_preserves_legacy_positionals_without_provenance() -> None:
    historical_names = [
        "prompt_hash",
        "category",
        "complexity",
        "risk",
        "selected_profile",
        "selected_model",
        "sandbox_mode",
        "approval_policy",
        "reasoning_effort",
        "model_verbosity",
        "confidence",
        "decision_reasons",
        "override_used",
        "dry_run",
        "warning",
        "risk_level",
        "complexity_level",
        "action_danger",
        "evidence_requirement",
        "context_requirement",
        "repo_impact",
        "security_sensitivity",
        "destructiveness",
        "execution_scope",
        "safety_constraints",
        "score_source",
    ]
    assert [item.name for item in fields(RoutingDecision)][: len(historical_names)] == historical_names
    decision = RoutingDecision(
        "hash",
        "unknown",
        "medium",
        "low",
        "standard",
        None,
        "read-only",
        "on-request",
        "low",
        "low",
        0.0,
        [],
        False,
        True,
        None,
        "low",
        "medium",
        "read_only_analysis",
        "none",
        "small",
        "none",
        "none",
        "none",
        "unknown",
        [],
        "legacy_source",
    )

    assert decision.score_source == "legacy_source"
    assert decision.task_subdomain is None
    assert decision.policy_version is None


def test_score_card_has_no_implicit_policy_provenance_field() -> None:
    assert "policy_version" not in {item.name for item in fields(ScoreCard)}


def test_canonical_router_assigns_current_policy_explicitly() -> None:
    decision = route_prompt("Summarize README.md in five sentences.")

    assert decision.policy_version == MODEL_POLICY_VERSION
