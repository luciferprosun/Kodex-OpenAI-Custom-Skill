from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path

import pytest

from smart_codex.runtime.telemetry.collector import TelemetryService
from smart_codex.runtime.telemetry.errors import TelemetryPrivacyError, TelemetryValidationError
from smart_codex.runtime.telemetry.models import compute_record_hash, seal_record, verify_record_hash
from smart_codex.runtime.telemetry.outcome import build_outcome_record, record_outcome
from smart_codex.runtime.telemetry.privacy import scan_record
from smart_codex.runtime.telemetry.summary import inspect_run, summarize
from smart_codex.runtime.telemetry.validator import validate_run_record

from telemetry_test_helpers import enabled_service, exec_usage_event, records, start_basic, telemetry_storage


def test_telemetry_is_disabled_by_default(tmp_path) -> None:
    storage = telemetry_storage(tmp_path)
    service = TelemetryService(storage)
    result = service.start_run(task="Synthetic task", task_domain="unknown")
    assert storage.enabled() is False
    assert result.run is None
    assert result.warning is None
    assert list(storage.iter_records()) == []


def test_enable_and_disable_state_is_explicit(tmp_path) -> None:
    storage = telemetry_storage(tmp_path)
    storage.set_enabled(True)
    assert storage.enabled() is True
    storage.set_enabled(False)
    assert storage.enabled() is False
    state = json.loads(storage.paths.state_file.read_text(encoding="utf-8"))
    assert state["enabled"] is False
    assert storage.paths.state_file.stat().st_mode & 0o777 == 0o600


def test_installation_salt_is_outside_telemetry_tree_and_mode_0600(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    assert storage.paths.salt.exists()
    assert storage.paths.salt.parent == storage.paths.root.parent
    assert storage.paths.salt not in storage.paths.root.parents
    assert storage.paths.salt.stat().st_mode & 0o777 == 0o600
    assert run.finish(status="completed").appended is True


def test_parallel_runs_have_unique_ids_and_no_counter_leakage(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    first = start_basic(service, task="Synthetic fixture one")
    second = start_basic(service, task="Synthetic fixture two")
    first.consume_event(exec_usage_event(input_tokens=10, cached_input_tokens=0, output_tokens=5, reasoning_output_tokens=1, total_tokens=15))
    second.consume_event(exec_usage_event(input_tokens=100, cached_input_tokens=20, output_tokens=30, reasoning_output_tokens=10, total_tokens=130))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda run: run.finish(status="completed"), (first, second)))
    assert all(result.appended for result in results)
    stored = sorted(records(storage, "run"), key=lambda value: value["input_tokens"])
    assert len({value["run_id"] for value in stored}) == 2
    assert [value["input_tokens"] for value in stored] == [10, 100]


def test_crashed_run_records_process_error_without_touching_prior_records(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    first = start_basic(service)
    assert first.finish(status="completed", process_exit_code=0).appended is True
    original = records(storage, "run")[0]
    second = start_basic(service, task="Synthetic process failure")
    assert second.finish(status="process_error", process_exit_code=7).appended is True
    stored = records(storage, "run")
    assert stored[0] == original
    assert stored[1]["collector_status"] == "process_error"
    assert stored[1]["process_exit_code"] == 7


def test_invalid_timestamp_is_rejected(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    record["finished_at"] = "2000-01-01T00:00:00+00:00"
    record = seal_record(record)
    with pytest.raises(TelemetryValidationError, match="NON_MONOTONIC_TIME"):
        validate_run_record(record)


def test_negative_token_count_is_rejected(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    record["input_tokens"] = -1
    record["measurement_sources"]["input_tokens"] = "provider_reported"
    record = seal_record(record)
    with pytest.raises(TelemetryValidationError, match="INVALID_INPUT_TOKENS"):
        validate_run_record(record)


def test_token_total_mismatch_is_rejected(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    run.consume_event(exec_usage_event(total_tokens=130))
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    record["total_reported_tokens"] = 999
    record = seal_record(record)
    with pytest.raises(TelemetryValidationError, match="TOTAL_TOKEN_MISMATCH"):
        validate_run_record(record)


def test_record_hash_detects_mutation(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    assert start_basic(service).finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert verify_record_hash(record) is True
    record["task_risk"] = "high"
    assert verify_record_hash(record) is False


def test_outcome_is_separate_and_original_record_is_immutable(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    assert start_basic(service).finish(status="completed").appended is True
    original = records(storage, "run")[0]
    original_bytes = json.dumps(original, sort_keys=True)
    result = record_outcome(storage, original["run_id"], "accepted", tests_passed=3, tests_failed=0)
    assert result.appended is True
    after = records(storage, "run")[0]
    outcome = records(storage, "outcome")[0]
    assert json.dumps(after, sort_keys=True) == original_bytes
    assert after["operator_outcome"] is None
    assert outcome["original_record_hash"] == original["record_hash"]
    assert outcome["operator_outcome"] == "accepted"


@pytest.mark.parametrize("outcome", ["accepted", "accepted-with-edits", "rejected", "aborted"])
def test_all_operator_outcomes_are_supported(tmp_path, outcome: str) -> None:
    service, storage = enabled_service(tmp_path)
    assert start_basic(service, task=f"Synthetic {outcome} fixture").finish(status="completed").appended
    run_id = records(storage, "run")[0]["run_id"]
    failure_category = "other" if outcome == "rejected" else None
    assert record_outcome(
        storage,
        run_id,
        outcome,
        failure_category=failure_category,
    ).appended is True


def test_outcome_cannot_target_missing_or_invalid_run(tmp_path) -> None:
    _, storage = enabled_service(tmp_path)
    result = record_outcome(storage, "00000000-0000-0000-0000-000000000000", "accepted")
    assert result.appended is False
    assert result.warning == "RUN_NOT_FOUND_OR_INVALID"


def test_outcome_requires_complete_and_nonconflicting_verifier_evidence(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    assert start_basic(service).finish(status="completed").appended is True
    run = records(storage, "run")[0]
    with pytest.raises(TelemetryValidationError, match="INCOMPLETE_TEST_COUNTS"):
        build_outcome_record(run, "accepted", tests_passed=3)
    with pytest.raises(TelemetryValidationError, match="CONFLICTING_VERIFICATION_EVIDENCE"):
        build_outcome_record(
            run,
            "accepted",
            tests_passed=3,
            tests_failed=0,
            verification_unavailable=True,
        )


def test_outcome_validator_enforces_verifier_result_matrix(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    assert start_basic(service).finish(status="completed").appended is True
    run = records(storage, "run")[0]
    outcome = build_outcome_record(run, "accepted", tests_passed=3, tests_failed=0)
    outcome["verifier_result"] = "failed"
    outcome["record_hash"] = compute_record_hash(outcome)
    with pytest.raises(TelemetryValidationError, match="VERIFIER_RESULT_MISMATCH"):
        from smart_codex.runtime.telemetry.validator import validate_outcome_record

        validate_outcome_record(outcome)


def test_append_only_outcome_adds_line_instead_of_rewriting(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    assert start_basic(service).finish(status="completed").appended is True
    target = next(storage.paths.root.rglob("codex_runs-*.jsonl"))
    before = target.read_bytes()
    run_id = records(storage, "run")[0]["run_id"]
    assert record_outcome(
        storage,
        run_id,
        "rejected",
        verification_unavailable=True,
        failure_category="other",
    ).appended
    after = target.read_bytes()
    assert after.startswith(before)
    assert after.count(b"\n") == before.count(b"\n") + 1


def test_storage_rotation_never_overwrites_prior_file(tmp_path) -> None:
    service, storage = enabled_service(tmp_path, max_file_bytes=4200)
    assert start_basic(service, task="Synthetic rotation one").finish(status="completed").appended
    first_path = next(storage.paths.root.rglob("codex_runs-0001.jsonl"))
    first_bytes = first_path.read_bytes()
    assert start_basic(service, task="Synthetic rotation two").finish(status="completed").appended
    files = sorted(storage.paths.root.rglob("codex_runs-*.jsonl"))
    assert len(files) == 2
    assert files[0].read_bytes() == first_bytes
    assert files[1].name == "codex_runs-0002.jsonl"


def test_total_cap_uses_mocked_small_limit_without_deletion(tmp_path) -> None:
    service, storage = enabled_service(tmp_path, max_total_bytes=1)
    run = start_basic(service)
    result = run.finish(status="completed")
    assert result.appended is False
    assert result.warning == "TELEMETRY_DISABLED_TOTAL_CAP"
    assert records(storage) == []


def test_low_disk_fail_safe_prevents_new_run(tmp_path, monkeypatch) -> None:
    service, storage = enabled_service(tmp_path, min_free_bytes=1024)
    monkeypatch.setattr(storage, "free_bytes", lambda: 0)
    result = service.start_run(task="Synthetic low disk", task_domain="unknown")
    assert result.run is None
    assert result.warning == "TELEMETRY_DISABLED_LOW_DISK"
    assert records(storage) == []


def test_salt_symlink_is_rejected_without_following_it(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    target = tmp_path / "outside-salt-target"
    target.write_bytes(b"x" * 32)
    storage.paths.salt.symlink_to(target)
    result = service.start_run(task="Synthetic symlink fixture", task_domain="unknown")
    assert result.run is None
    assert result.warning == "TELEMETRY_DISABLED_SALT_PATH_UNSAFE"
    assert target.read_bytes() == b"x" * 32


def test_salt_lock_timeout_disables_only_telemetry(tmp_path, monkeypatch) -> None:
    import smart_codex.runtime.telemetry.privacy as privacy_module

    service, storage = enabled_service(tmp_path)
    storage.paths.salt.unlink(missing_ok=True)
    lock_path = storage.paths.salt.parent / ".telemetry_salt.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    monkeypatch.setattr(privacy_module, "SALT_LOCK_TIMEOUT_SECONDS", 0.01)
    try:
        result = service.start_run(task="Synthetic salt lock fixture", task_domain="unknown")
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    assert result.run is None
    assert result.warning == "TELEMETRY_DISABLED_SALT_LOCK_TIMEOUT"


def test_jsonl_symlink_target_is_rejected(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    now = datetime.now(timezone.utc)
    directory = storage.paths.root / f"{now.year:04d}" / f"{now.month:02d}"
    directory.mkdir(parents=True)
    outside = tmp_path / "outside-record-target"
    outside.write_text("preserve", encoding="utf-8")
    (directory / "codex_runs-0001.jsonl").symlink_to(outside)
    result = run.finish(status="completed")
    assert result.appended is False
    assert result.warning == "TELEMETRY_REJECTED_UNSAFE_TARGET"
    assert outside.read_text(encoding="utf-8") == "preserve"


def test_single_record_cannot_exceed_mocked_file_limit(tmp_path) -> None:
    service, storage = enabled_service(tmp_path, max_file_bytes=128)
    run = start_basic(service)
    result = run.finish(status="completed")
    assert result.appended is False
    assert result.warning == "TELEMETRY_REJECTED_FILE_LIMIT"
    assert records(storage) == []


def test_storage_sink_revalidates_record_before_persisting(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    assert start_basic(service).finish(status="completed").appended is True
    unsafe = records(storage, "run")[0]
    unsafe["task_domain"] = "sk-proj-" + "A" * 24
    unsafe = seal_record(unsafe)
    before = storage.storage_size()
    result = storage.append(unsafe)
    assert result.appended is False
    assert result.warning == "TELEMETRY_REJECTED_SECRET_PATTERN"
    assert storage.storage_size() == before


def test_short_os_write_is_completed_as_one_valid_jsonl_record(tmp_path, monkeypatch) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    real_write = os.write

    def short_write(descriptor: int, payload: bytes) -> int:
        return real_write(descriptor, payload[: max(1, len(payload) // 2)])

    monkeypatch.setattr("smart_codex.runtime.telemetry.storage.os.write", short_write)
    assert run.finish(status="completed").appended is True
    stored = records(storage, "run")
    assert len(stored) == 1
    validate_run_record(stored[0])


def test_trailing_fragment_stops_future_appends_without_overwrite(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    assert start_basic(service).finish(status="completed").appended is True
    target = next(storage.paths.root.rglob("codex_runs-*.jsonl"))
    with target.open("ab") as handle:
        handle.write(b"{")
    before = target.read_bytes()
    result = start_basic(service, task="Synthetic second record").finish(status="completed")
    assert result.appended is False
    assert result.warning == "TELEMETRY_DISABLED_TRAILING_FRAGMENT"
    assert target.read_bytes() == before


def test_append_lock_timeout_is_bounded_and_nonfatal(tmp_path, monkeypatch) -> None:
    import smart_codex.runtime.telemetry.storage as storage_module

    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    monkeypatch.setattr(storage_module, "LOCK_TIMEOUT_SECONDS", 0.01)
    storage_module._THREAD_APPEND_LOCK.acquire()
    try:
        result = run.finish(status="completed")
    finally:
        storage_module._THREAD_APPEND_LOCK.release()
    assert result.appended is False
    assert result.warning == "TELEMETRY_DISABLED_LOCK_TIMEOUT"


def test_raw_prompt_field_is_rejected() -> None:
    with pytest.raises(TelemetryPrivacyError, match="FORBIDDEN_FIELD"):
        scan_record({"raw_prompt": "private task text"})


def test_secret_pattern_is_rejected_without_echoing_secret() -> None:
    synthetic = "sk-" + "proj-" + "A" * 24
    with pytest.raises(TelemetryPrivacyError, match="SECRET_PATTERN") as exc:
        scan_record({"model": synthetic})
    assert "AAAAAAAA" not in str(exc.value)


def test_multiline_source_like_content_is_rejected() -> None:
    with pytest.raises(TelemetryPrivacyError, match="MULTILINE_CONTENT"):
        scan_record({"category": "def hidden():\n    return 1"})


def test_inspect_hides_task_signature_unless_explicit(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    assert start_basic(service).finish(status="completed").appended
    run_id = records(storage, "run")[0]["run_id"]
    hidden = inspect_run(storage, run_id)
    visible = inspect_run(storage, run_id, show_signature=True)
    assert hidden is not None and hidden["task_signature"] == "<hidden>"
    assert visible is not None and len(visible["task_signature"]) == 64


def test_summary_requires_five_measured_samples_for_median(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    for index in range(4):
        run = start_basic(service, task=f"Synthetic summary {index}")
        run.consume_event(exec_usage_event(total_tokens=130))
        assert run.finish(status="completed").appended
    summary = summarize(storage)["summary"]
    assert summary["known_token_run_count"] == 4
    assert summary["median_total_tokens"] == "INSUFFICIENT_DATA"


def test_summary_reports_median_at_five_measured_samples(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    for index, input_tokens in enumerate((10, 20, 30, 40, 50)):
        run = start_basic(service, task=f"Synthetic measured summary {index}")
        run.consume_event(
            exec_usage_event(
                input_tokens=input_tokens,
                cached_input_tokens=0,
                output_tokens=10,
                reasoning_output_tokens=2,
                total_tokens=input_tokens + 10,
            )
        )
        assert run.finish(status="completed").appended
    summary = summarize(storage)["summary"]
    assert summary["median_total_tokens"] == 40
    assert summary["p90_total_tokens"] == 60


def test_no_telemetry_module_imports_network_clients() -> None:
    root = Path(__file__).resolve().parents[1] / "smart_codex" / "runtime" / "telemetry"
    forbidden = ("import socket", "import requests", "import urllib", "import http.client", "urlopen(")
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert not any(marker in source for marker in forbidden)


def test_storage_files_are_private_regular_files(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    assert start_basic(service).finish(status="completed").appended
    target = next(storage.paths.root.rglob("codex_runs-*.jsonl"))
    assert target.is_file() and not target.is_symlink()
    assert target.stat().st_mode & 0o777 == 0o600
    assert os.path.getsize(target) > 0
    assert storage.paths.root.stat().st_mode & 0o777 == 0o700
    assert target.parent.stat().st_mode & 0o777 == 0o700
    assert target.parent.parent.stat().st_mode & 0o777 == 0o700
    assert (storage.paths.root / "summaries").stat().st_mode & 0o777 == 0o700
