import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research" / "agent-token-economics-2a"
VALIDATOR_PATH = RESEARCH / "analysis" / "validate_corpus.py"
REGISTRY_BUILDER_PATH = RESEARCH / "analysis" / "build_registries.py"
STATISTICS_PATH = RESEARCH / "analysis" / "compute_statistics.py"
BASELINES_PATH = RESEARCH / "analysis" / "fit_baselines.py"
COVERAGE_STATUS_PATH = RESEARCH / "analysis" / "coverage_status.py"


def quality_components(*enabled):
    names = {
        "exact_model_identity",
        "exact_agent_identity",
        "exact_task_identity",
        "provider_reported_tokens",
        "complete_request_breakdown",
        "complete_public_safe_trajectory",
        "objective_verifier",
        "timestamped_price_table",
        "repeatable_acquisition",
        "license_clarity",
    }
    return {name: name in enabled for name in names}


def load_validator():
    spec = importlib.util.spec_from_file_location("token_economics_validator", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_registry_builder():
    spec = importlib.util.spec_from_file_location("token_economics_registry", REGISTRY_BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_research_schemas_are_strict_and_resolvable():
    validator = load_validator()
    schemas = sorted((RESEARCH / "schemas").glob("*.schema.json"))
    assert len(schemas) == 4
    for schema_path in schemas:
        validator.validate_schema_document(schema_path)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert schema["additionalProperties"] is False


def test_null_token_fields_require_explicit_missingness():
    validator = load_validator()
    record = {
        "prompt_tokens": None,
        "measurement_method": {"prompt_tokens": "unknown", "normalized_cost": "unknown"},
        "missing_fields": ["prompt_tokens", "normalized_cost"],
        "normalized_cost": None,
        "price_table_date": None,
    }
    validator.validate_missingness(record, Path("fixture.jsonl"), 1)


def test_observed_token_fields_require_non_unknown_method():
    validator = load_validator()
    record = {
        "prompt_tokens": 100,
        "measurement_method": {"prompt_tokens": "provider_reported", "normalized_cost": "unknown"},
        "missing_fields": ["normalized_cost"],
        "normalized_cost": None,
        "price_table_date": None,
    }
    validator.validate_missingness(record, Path("fixture.jsonl"), 1)


def test_censored_run_cannot_be_encoded_as_failure():
    validator = load_validator()
    record = {
        "measurement_method": {},
        "missing_fields": [],
        "censored": True,
        "censor_reason": "budget exhausted",
        "task_success": False,
    }
    try:
        validator.validate_missingness(record, Path("fixture.jsonl"), 1)
    except validator.ValidationError as exc:
        assert "ordinary success/failure" in str(exc)
    else:
        raise AssertionError("censored failure was accepted")


def test_low_quality_run_cannot_enter_numerical_priors():
    validator = load_validator()
    record = {
        "measurement_method": {},
        "missing_fields": [],
        "included_in_numerical_priors": True,
        "quality_class": "D",
        "quality_score": 30,
        "quality_components": quality_components(
            "exact_agent_identity", "exact_task_identity", "repeatable_acquisition"
        ),
        "censored": False,
        "censor_reason": None,
    }
    try:
        validator.validate_missingness(record, Path("fixture.jsonl"), 1)
    except validator.ValidationError as exc:
        assert "only A-C" in str(exc)
    else:
        raise AssertionError("class D record was accepted for numerical priors")


def test_quality_class_must_agree_with_quality_score():
    validator = load_validator()
    record = {
        "measurement_method": {},
        "missing_fields": [],
        "included_in_numerical_priors": False,
        "quality_class": "A",
        "quality_score": 0,
        "quality_components": quality_components(),
        "censored": False,
        "censor_reason": None,
    }
    try:
        validator.validate_missingness(record, Path("fixture.jsonl"), 1)
    except validator.ValidationError as exc:
        assert "quality class A disagrees" in str(exc)
    else:
        raise AssertionError("class A with score zero was accepted")


def test_quality_score_must_equal_persisted_component_sum():
    validator = load_validator()
    record = {
        "measurement_method": {},
        "missing_fields": [],
        "included_in_numerical_priors": False,
        "quality_class": "E",
        "quality_score": 20,
        "quality_components": quality_components("exact_model_identity"),
        "censored": False,
        "censor_reason": None,
    }
    try:
        validator.validate_missingness(record, Path("fixture.jsonl"), 1)
    except validator.ValidationError as exc:
        assert "does not equal component score" in str(exc)
    else:
        raise AssertionError("quality score/component mismatch was accepted")


def test_numerical_admission_requires_identity_tokens_outcome_and_verifier():
    validator = load_validator()
    record = {
        "measurement_method": {},
        "missing_fields": [],
        "included_in_numerical_priors": True,
        "quality_class": "A",
        "quality_score": 100,
        "quality_components": quality_components(
            "exact_model_identity", "exact_agent_identity", "exact_task_identity",
            "provider_reported_tokens", "complete_request_breakdown",
            "complete_public_safe_trajectory", "objective_verifier",
            "timestamped_price_table", "repeatable_acquisition", "license_clarity",
        ),
        "measurement_confidence": "high",
        "censored": False,
        "censor_reason": None,
        "license": "MIT",
        "provenance": {
            "derived_statistics_status": "allowed",
            "privacy_review": "passed",
            "license": "MIT",
        },
    }
    try:
        validator.validate_missingness(record, Path("fixture.jsonl"), 1)
    except validator.ValidationError as exc:
        assert "lacks required evidence fields" in str(exc)
    else:
        raise AssertionError("identity-free and outcome-free run entered numerical priors")


def test_censoring_analysis_requires_a_censored_a_to_c_record():
    validator = load_validator()
    record = {
        "measurement_method": {},
        "missing_fields": [],
        "included_in_numerical_priors": False,
        "included_in_censoring_analysis": True,
        "quality_class": "A",
        "quality_score": 100,
        "quality_components": quality_components(
            "exact_model_identity", "exact_agent_identity", "exact_task_identity",
            "provider_reported_tokens", "complete_request_breakdown",
            "complete_public_safe_trajectory", "objective_verifier",
            "timestamped_price_table", "repeatable_acquisition", "license_clarity",
        ),
        "measurement_confidence": "high",
        "censored": False,
        "censor_reason": None,
        "provenance": {
            "derived_statistics_status": "allowed",
            "privacy_review": "passed",
        },
    }
    try:
        validator.validate_missingness(record, Path("fixture.jsonl"), 1)
    except validator.ValidationError as exc:
        assert "censoring cohort contains an uncensored run" in str(exc)
    else:
        raise AssertionError("uncensored run entered the censoring cohort")


def test_dataset_registry_must_explicitly_permit_numerical_admission():
    validator = load_validator()
    dataset_id = "ds_sweagent_demonstrations"
    run = {
        "dataset_id": dataset_id,
        "run_id": "fixture-run",
        "task_id": "fixture-task",
        "source_id": "SE-SRC-004",
        "task_domain": "SE",
        "included_in_numerical_priors": True,
    }
    task = {
        "dataset_id": dataset_id,
        "task_id": "fixture-task",
        "source_id": "SE-SRC-004",
        "task_domain": "SE",
        "success_criterion": "tests pass",
        "verifier_profile": "pytest",
    }
    try:
        validator.validate_relations({
            "agent_runs.jsonl": [run],
            "agent_requests.jsonl": [],
            "tasks.jsonl": [task],
            "provenance.jsonl": [],
        })
    except validator.ValidationError as exc:
        assert "dataset registry does not permit numerical analysis" in str(exc)
    else:
        raise AssertionError("rights-blocked dataset entered numerical priors")


def test_registry_has_stable_provenance_and_typed_availability():
    builder = load_registry_builder()
    sources, aliases = builder.build_sources()
    datasets = builder.build_datasets({row["source_id"] for row in sources}, aliases)
    builder.validate_output(sources, datasets)
    source_ids = {row["source_id"] for row in sources}
    assert "OA-OFFICIAL-001" in source_ids
    responses = next(row for row in datasets if row["dataset_id"] == "OA-TELEM-RESPONSES-RUN")
    assert "OA-OFFICIAL-001" in responses["source_ids"]
    for row in datasets:
        for field in (
            "token_fields_available",
            "cost_fields_available",
            "timing_fields_available",
            "tool_call_fields_available",
        ):
            assert all(isinstance(item, str) for item in row[field])


def test_blocked_trajectory_sources_do_not_gain_numerical_permission():
    builder = load_registry_builder()
    sources, aliases = builder.build_sources()
    datasets = builder.build_datasets({row["source_id"] for row in sources}, aliases)
    by_id = {row["dataset_id"]: row for row in datasets}
    for dataset_id in (
        "ds_swebench_experiments",
        "ds_nebius_sweagent_trajectories",
        "hwm_visualwebarena_agent_trajectories",
    ):
        assert by_id[dataset_id]["raw_acquisition_status"] == "blocked"
        assert by_id[dataset_id]["accepted_for_numerical_routing"] is False


def test_bounded_fixture_preserves_unknown_usage_and_stays_out_of_priors():
    runs = [
        json.loads(line)
        for line in (RESEARCH / "data" / "normalized" / "agent_runs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len(runs) == 19
    for run in runs:
        assert run["quality_class"] == "E"
        assert run["included_in_numerical_priors"] is False
        assert run["included_in_censoring_analysis"] is False
        assert run["prompt_tokens"] is None
        assert run["visible_output_tokens"] is None
        assert run["total_reported_tokens"] is None
        assert run["provenance"]["raw_content_committed"] is False
        assert run["provenance"]["hidden_reasoning_removed"] is True


def test_machine_readable_priors_are_empty_and_runtime_disabled():
    empirical = json.loads(
        (RESEARCH / "knowledge" / "token-economics" / "empirical_priors.json")
        .read_text(encoding="utf-8")
    )
    escalation = json.loads(
        (RESEARCH / "knowledge" / "token-economics" / "escalation_priors.json")
        .read_text(encoding="utf-8")
    )
    assert empirical["admitted_run_count"] == 0
    assert empirical["priors"] == []
    assert escalation["priors"] == []
    assert escalation["runtime_enabled"] is False
    baselines = json.loads(
        (RESEARCH / "knowledge" / "token-economics" / "token_prediction_baselines.json")
        .read_text(encoding="utf-8")
    )
    assert all(
        result["publication_ready"] is False
        for result in baselines["regularized_baselines"].values()
    )


def test_required_chart_set_has_metadata_and_no_fake_numerical_sample():
    metadata_paths = sorted((RESEARCH / "charts" / "metadata").glob("*.json"))
    assert len(metadata_paths) == 15
    for path in metadata_paths:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        assert "known_limitations" in metadata
        assert "measurement_type" in metadata
        assert "sample_size" in metadata
    for path in metadata_paths[:10] + [metadata_paths[13]]:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        assert metadata["sample_size"] == 0
        assert metadata["numerical_prior_eligible"] is False


def _cost_chain():
    common = {
        "dataset_id": "allowed-dataset",
        "task_id": "task-1",
        "attempt_chain_id": "chain-1",
        "attempt_chain_complete": True,
        "normalized_cost": 1.0,
        "tool_cost": 0.0,
        "verification_cost": 0.1,
        "human_review_cost": 0.0,
        "failure_penalty_cost": 0.0,
        "normalized_cost_scope": "run",
        "cost_currency": "USD",
        "price_table_id": "prices-2026-07-18",
        "price_table_date": "2026-07-18",
    }
    first = dict(common, run_id="run-1", attempt_sequence=1, route_final_accepted=False, task_success=False)
    final = dict(common, run_id="run-2", attempt_sequence=2, route_final_accepted=True, task_success=True)
    return [first, final]


def test_accepted_cost_requires_last_attempt_run_scope_and_one_price_basis():
    statistics_module = load_module("token_economics_statistics", STATISTICS_PATH)
    valid = _cost_chain()
    accepted = statistics_module.accepted_chain_records(valid)
    assert len(accepted) == 1
    assert accepted[0]["accepted_task_cost"] == 2.2

    accepted_first = [dict(valid[0], route_final_accepted=True, task_success=True), dict(valid[1], route_final_accepted=False)]
    assert statistics_module.accepted_chain_records(accepted_first) == []

    chain_scoped = [dict(record, normalized_cost_scope="attempt_chain") for record in valid]
    assert statistics_module.accepted_chain_records(chain_scoped) == []

    mixed_dates = [dict(valid[0]), dict(valid[1], price_table_date="2026-07-19")]
    assert statistics_module.accepted_chain_records(mixed_dates) == []


def test_success_interval_requires_five_independent_task_clusters():
    statistics_module = load_module("token_economics_statistics_intervals", STATISTICS_PATH)
    successes = [
        {"dataset_id": "dataset", "task_id": f"task-{index}"}
        for index in range(4)
    ]
    summary = statistics_module.task_cluster_success_summary(successes, [])
    assert summary["task_cluster_bootstrap_95ci"] is None
    successes.append({"dataset_id": "dataset", "task_id": "task-4"})
    summary = statistics_module.task_cluster_success_summary(successes, [])
    assert summary["task_cluster_bootstrap_95ci"] is not None


def test_success_summary_weights_tasks_not_repeated_runs():
    statistics_module = load_module("token_economics_statistics_cluster_weight", STATISTICS_PATH)
    successes = [
        {"dataset_id": "dataset", "task_id": "task-success"}
        for _ in range(100)
    ]
    failures = [{"dataset_id": "dataset", "task_id": "task-failure"}]
    summary = statistics_module.task_cluster_success_summary(successes, failures)
    assert summary["rate"] == 0.5
    assert summary["task_clusters"] == 2


def test_statistical_and_lookup_strata_separate_surface_scope_currency_and_price_table():
    statistics_module = load_module("token_economics_statistics_strata", STATISTICS_PATH)
    baselines_module = load_module("token_economics_baselines_strata", BASELINES_PATH)
    base = {
        "dataset_id": "dataset",
        "model_id": "model",
        "product_surface": "api",
        "prompt_tokens_scope": "per_run_cumulative",
        "total_reported_tokens_scope": "per_run_cumulative",
        "normalized_cost_scope": "run",
        "cost_currency": "USD",
        "price_table_id": "prices-a",
        "price_table_date": "2026-07-18",
        "measurement_profile": (("prompt_tokens", "provider_reported"),),
    }
    variants = [
        dict(base, product_surface="codex_subscription"),
        dict(base, prompt_tokens_scope="per_request"),
        dict(base, cost_currency="EUR"),
        dict(base, price_table_id="prices-b"),
    ]
    for variant in variants:
        assert statistics_module.group_key(base) != statistics_module.group_key(variant)
        assert baselines_module.lookup_key(base) != baselines_module.lookup_key(variant)


def test_failure_coverage_uncertainty_is_not_rendered_as_present():
    coverage_module = load_module("token_economics_coverage_status", COVERAGE_STATUS_PATH)
    assert coverage_module.failure_coverage_status("complete") == "present"
    assert coverage_module.failure_coverage_status(False) == "absent"
    assert coverage_module.failure_coverage_status("not uniformly available") == "unknown"
    assert coverage_module.failure_coverage_status(None) == "unknown"
