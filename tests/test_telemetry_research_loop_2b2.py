from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path

import pytest

from smart_codex import cli
from smart_codex.app_server_router import launcher as app_launcher
from smart_codex.app_server_router.backend import BackendError, SUPPORTED_CODEX_VERSION
from smart_codex.learning import dataset as dataset_module
from smart_codex.learning.dataset import build_dataset, dataset_status
from smart_codex.learning.learner import candidate_report, propose_policy, shadow_status, validate_candidate
from smart_codex.learning.shadow import ShadowRecorder
from smart_codex import research_launcher
from smart_codex.runtime.telemetry.collector import TelemetryService
from smart_codex.runtime.telemetry.config import (
    EXTERNAL_MAX_FILE_BYTES,
    EXTERNAL_MAX_TOTAL_BYTES,
    EXTERNAL_MIN_FREE_BYTES,
    ExternalTelemetryConfig,
    configure_external_storage,
    load_external_config,
    reset_external_config,
)
from smart_codex.runtime.telemetry.errors import TelemetryStorageError, TelemetryValidationError
from smart_codex.runtime.telemetry.models import seal_record, utc_now
from smart_codex.runtime.telemetry.mounts import MountedFilesystem, MountVerification, verify_mount
from smart_codex.runtime.telemetry.outcome import (
    build_outcome_record,
    latest_pending_run,
    pending_runs,
    record_outcome,
)
from smart_codex.runtime.telemetry.storage import LocalTelemetryStorage, StorageLimits, TelemetryPaths

from telemetry_test_helpers import exec_usage_event


ROOT = Path(__file__).resolve().parents[1]


def _append_process(root: str, salt: str, window_id: str, count: int, queue) -> None:
    storage = LocalTelemetryStorage(
        TelemetryPaths(root=Path(root), salt=Path(salt)),
        StorageLimits(min_free_bytes=0),
    )
    service = TelemetryService(
        storage,
        window_id=window_id,
        workspace_signature=("a" if window_id == "aoia" else "b") * 64,
        router_policy_version="policy-v1",
        codex_protocol_version="codex-cli_0.144.5",
        synthetic=True,
    )
    appended = 0
    for index in range(count):
        started = service.start_run(
            task=f"Synthetic process append {window_id} {index}",
            task_domain="normal_coding",
            task_difficulty="low",
            task_scope="single_file",
            task_risk="low",
            recommended_model="gpt-test",
            launched_model="gpt-test",
            model_identity_status="client_requested_only",
            reasoning_effort="medium",
            sandbox="read-only",
            approval_policy="on-request",
            product_surface="codex_app_server_research",
        )
        if started.run is not None and started.run.finish(status="completed").appended:
            appended += 1
    queue.put(appended)


def mounted(tmp_path: Path, **overrides) -> MountedFilesystem:
    values = {
        "device": "/dev/mmc-test1",
        "filesystem": "exfat",
        "label": "SDCARD",
        "uuid": "TEST-1234",
        "mount_point": str(tmp_path),
        "read_only": False,
        "available_bytes": 20 * 1024**3,
        "writable": True,
        "transport": "mmc",
        "hotplug": True,
        "removable": False,
    }
    values.update(overrides)
    return MountedFilesystem(**values)


def fake_config(tmp_path: Path) -> ExternalTelemetryConfig:
    root = tmp_path / "SmartRouterTelemetry"
    for name in ("raw", "derived", "manifests", "policy-candidates", "reports", "runtime-events"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return ExternalTelemetryConfig(
        telemetry_root=root,
        device_uuid="TEST-1234",
        mount_point=tmp_path,
        filesystem_type="ext4",
        configured_at="2026-07-19T00:00:00+00:00",
        limits=StorageLimits(
            max_file_bytes=EXTERNAL_MAX_FILE_BYTES,
            max_total_bytes=EXTERNAL_MAX_TOTAL_BYTES,
            min_free_bytes=0,
        ),
    )


def patch_dataset_config(monkeypatch, config: ExternalTelemetryConfig) -> None:
    monkeypatch.setattr(dataset_module, "load_external_config", lambda: config)
    monkeypatch.setattr(
        dataset_module,
        "verify_mount",
        lambda *args, **kwargs: MountVerification(True, "VERIFIED", mounted(config.mount_point)),
    )


def external_storage(config: ExternalTelemetryConfig) -> LocalTelemetryStorage:
    storage = LocalTelemetryStorage(
        TelemetryPaths(
            root=config.telemetry_root / "raw",
            salt=config.telemetry_root.parent / "internal-salt",
        ),
        config.limits,
    )
    storage.set_enabled(True)
    return storage


def add_run(
    storage: LocalTelemetryStorage,
    *,
    model: str = "gpt-test-incumbent",
    input_tokens: int | None = 100,
    outcome: str | None = None,
    window_id: str = "smart-router",
    risk: str = "low",
) -> dict:
    service = TelemetryService(
        storage,
        window_id=window_id,
        workspace_signature="a" * 64,
        router_policy_version="policy-v1",
        codex_protocol_version="codex-cli_0.144.5",
    )
    started = service.start_run(
        task=f"Synthetic metadata-only task {os.urandom(4).hex()}",
        task_domain="normal_coding",
        task_subdomain="read_only_analysis",
        task_difficulty="low",
        task_scope="single_file",
        task_risk=risk,
        verification_available=True,
        recommended_model=model,
        launched_model=model,
        backend_model=model,
        model_identity_status="provider_reported",
        reasoning_effort="medium",
        sandbox="read-only",
        approval_policy="on-request",
        product_surface="codex_app_server_research",
    )
    assert started.run is not None
    if input_tokens is not None:
        started.run.consume_event(
            exec_usage_event(
                input_tokens=input_tokens,
                cached_input_tokens=0,
                output_tokens=20,
                reasoning_output_tokens=5,
                total_tokens=input_tokens + 20,
            )
        )
    result = started.run.finish(status="completed", process_exit_code=0)
    assert result.appended
    run = next(
        value
        for value in storage.iter_records()
        if value.get("record_type") == "run" and value.get("run_id") == result.run_id
    )
    if outcome is not None:
        assert record_outcome(
            storage,
            run["run_id"],
            outcome,
            edit_magnitude="none" if outcome == "accepted" else None,
            tests_passed=1,
            tests_failed=0,
        ).appended
    return run


def test_exact_codex_version_mismatch_fails_before_backend_start(tmp_path, monkeypatch) -> None:
    async def mismatched(_: str) -> str:
        return "codex-cli 0.144.6"

    monkeypatch.setattr(app_launcher, "read_codex_version", mismatched)
    monkeypatch.setattr(
        app_launcher.BackendProcess,
        "start",
        lambda self: pytest.fail("backend must not start on a version mismatch"),
    )
    args = argparse.Namespace(
        cwd=str(tmp_path),
        codex_bin="codex",
        backend_url=None,
        backend_port=0,
        proxy_port=0,
        event_log=None,
        print_command=True,
        manager_only=False,
    )
    with pytest.raises(BackendError, match="generated protocol contract"):
        asyncio.run(app_launcher.run(args))


def test_regenerated_protocol_contract_is_exact_and_reviewed() -> None:
    manifest = json.loads(
        (ROOT / "smart_codex/app_server_router/schemas/protocol_contract_0_144_5.json").read_text(
            encoding="utf-8"
        )
    )
    assert SUPPORTED_CODEX_VERSION == "codex-cli 0.144.5"
    assert manifest["codex_version"] == SUPPORTED_CODEX_VERSION
    assert manifest["review_status"] == "reviewed"
    assert manifest["fail_closed"] is True
    assert all(len(value) == 64 for value in manifest["bundles"].values())


def test_verify_mount_accepts_exact_uuid_and_rejects_changed_or_internal(tmp_path) -> None:
    root = tmp_path / "SmartRouterTelemetry"
    root.mkdir()
    good = mounted(tmp_path)
    assert verify_mount(root, "TEST-1234", minimum_free_bytes=1, filesystems=[good]).ok
    changed = verify_mount(root, "WRONG", minimum_free_bytes=1, filesystems=[good])
    assert changed.reason == "FILESYSTEM_UUID_MISMATCH"
    internal = mounted(Path("/"), device="/dev/root", mount_point="/", uuid="TEST-1234")
    fallback = verify_mount(root, "TEST-1234", minimum_free_bytes=1, filesystems=[internal])
    assert fallback.reason == "INTERNAL_FILESYSTEM_FALLBACK"


def test_verify_mount_rejects_symlink_read_only_and_low_space(tmp_path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    root = link / "SmartRouterTelemetry"
    assert verify_mount(root, "TEST-1234", minimum_free_bytes=1, filesystems=[mounted(tmp_path)]).reason == "STORAGE_PATH_SYMLINK"
    safe_root = tmp_path / "SmartRouterTelemetry"
    safe_root.mkdir()
    read_only = mounted(tmp_path, read_only=True, writable=False)
    assert verify_mount(safe_root, "TEST-1234", minimum_free_bytes=1, filesystems=[read_only]).reason == "FILESYSTEM_NOT_WRITABLE"
    low = mounted(tmp_path, available_bytes=10)
    assert verify_mount(safe_root, "TEST-1234", minimum_free_bytes=11, filesystems=[low]).reason == "INSUFFICIENT_EXTERNAL_FREE_SPACE"


def test_configuration_is_strict_atomic_private_and_reset_preserves_data(tmp_path, monkeypatch) -> None:
    root = tmp_path / "SmartRouterTelemetry"
    target = tmp_path / "config" / "smart-codex" / "telemetry.json"
    verification = MountVerification(True, "VERIFIED", mounted(tmp_path))
    monkeypatch.setattr("smart_codex.runtime.telemetry.config.verify_mount", lambda *args, **kwargs: verification)
    config = configure_external_storage(root, "TEST-1234", path=target)
    assert config.telemetry_root == root
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.parent.stat().st_mode & 0o777 == 0o700
    assert load_external_config(target) == config
    marker = root / "raw" / "preserve"
    marker.write_text("immutable evidence", encoding="utf-8")
    assert reset_external_config(target) is True
    assert marker.read_text(encoding="utf-8") == "immutable evidence"


def test_configuration_rejects_unknown_keys_and_unsafe_permissions(tmp_path) -> None:
    target = tmp_path / "smart-codex" / "telemetry.json"
    target.parent.mkdir(mode=0o700)
    target.write_text(json.dumps({"config_version": "1.0.0", "unexpected": True}), encoding="utf-8")
    os.chmod(target, 0o600)
    with pytest.raises(TelemetryStorageError, match="CONFIG_FIELD_SET_MISMATCH"):
        load_external_config(target)
    os.chmod(target, 0o644)
    with pytest.raises(TelemetryStorageError, match="CONFIG_FILE_PERMISSIONS"):
        load_external_config(target)


def test_configuration_rejects_symlinked_parent_component(tmp_path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(TelemetryStorageError, match="CONFIG_PARENT_SYMLINK"):
        load_external_config(linked / "smart-codex" / "telemetry.json")


def test_external_storage_never_falls_back_when_mount_verification_fails(tmp_path) -> None:
    root = tmp_path / "mount" / "SmartRouterTelemetry"
    storage = LocalTelemetryStorage(
        TelemetryPaths(root=root / "raw", salt=tmp_path / "salt"),
        StorageLimits(min_free_bytes=0),
        mount_verifier=lambda: MountVerification(False, "FILESYSTEM_UUID_MISMATCH"),
        external_root=root,
    )
    with pytest.raises(TelemetryStorageError, match="FILESYSTEM_UUID_MISMATCH"):
        storage.set_enabled(True)
    assert not root.exists()


def test_one_hundred_overlapping_appends_are_complete_and_window_isolated(tmp_path) -> None:
    config = fake_config(tmp_path)
    storage = external_storage(config)
    services = {
        window: TelemetryService(
            storage,
            window_id=window,
            workspace_signature=("a" if window == "aoia" else "b") * 64,
            router_policy_version="policy-v1",
            codex_protocol_version="codex-cli_0.144.5",
        )
        for window in ("aoia", "smart-router")
    }

    def append(index: int) -> bool:
        window = "aoia" if index % 2 == 0 else "smart-router"
        start = services[window].start_run(
            task=f"Synthetic concurrent task {index}",
            task_domain="normal_coding",
            task_difficulty="low",
            task_scope="single_file",
            task_risk="low",
            recommended_model="gpt-test",
            launched_model="gpt-test",
            model_identity_status="client_requested_only",
            reasoning_effort="medium",
            sandbox="read-only",
            approval_policy="on-request",
            product_surface="codex_app_server_research",
        )
        return bool(start.run and start.run.finish(status="completed").appended)

    with ThreadPoolExecutor(max_workers=16) as pool:
        assert all(pool.map(append, range(100)))
    runs = [value for value in storage.iter_records() if value.get("record_type") == "run"]
    assert len(runs) == 100
    assert len({value["run_id"] for value in runs}) == 100
    assert sum(value["window_id"] == "aoia" for value in runs) == 50
    assert sum(value["window_id"] == "smart-router" for value in runs) == 50


def test_two_process_append_validation_has_no_loss_or_corruption(tmp_path) -> None:
    storage = LocalTelemetryStorage(
        TelemetryPaths(root=tmp_path / "raw", salt=tmp_path / "salt"),
        StorageLimits(min_free_bytes=0),
    )
    storage.set_enabled(True)
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    processes = [
        context.Process(
            target=_append_process,
            args=(str(storage.paths.root), str(storage.paths.salt), window, 25, queue),
        )
        for window in ("aoia", "smart-router")
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    assert sum(queue.get(timeout=2) for _ in processes) == 50
    runs = [value for value in storage.iter_records() if value.get("record_type") == "run"]
    assert len(runs) == 50
    assert all(value["synthetic"] is True for value in runs)


def test_two_research_launchers_keep_independent_window_context(tmp_path, monkeypatch) -> None:
    config = fake_config(tmp_path)
    storage = external_storage(config)
    observed: list[tuple[str, str]] = []

    async def exact_version(_: str) -> str:
        return SUPPORTED_CODEX_VERSION

    async def fake_routed(args, *, telemetry_service, research_banner):
        observed.append((telemetry_service.window_id, Path(args.event_log).name))
        await asyncio.sleep(0)
        assert research_banner["Storage filesystem"] == "verified"
        return 0

    monkeypatch.setattr(research_launcher, "_verify_workspace", lambda *args: None)
    monkeypatch.setattr(research_launcher, "load_external_config", lambda: config)
    monkeypatch.setattr(research_launcher, "configured_storage", lambda **kwargs: storage)
    monkeypatch.setattr(research_launcher, "read_codex_version", exact_version)
    monkeypatch.setattr(research_launcher, "run_routed_tui", fake_routed)
    monkeypatch.setattr(
        research_launcher,
        "shadow_status",
        lambda: {"decision": "ABSTAIN — INSUFFICIENT_DATA"},
    )

    async def scenario() -> None:
        values = []
        for window in ("aoia", "smart-router"):
            values.append(
                research_launcher._run(
                    argparse.Namespace(
                        window_id=window,
                        cwd=str(tmp_path),
                        codex_bin="codex",
                        print_command=True,
                        manager_only=False,
                    )
                )
            )
        assert await asyncio.gather(*values) == [0, 0]

    asyncio.run(scenario())
    assert {window for window, _ in observed} == {"aoia", "smart-router"}
    assert len({name for _, name in observed}) == 2


def test_research_launcher_refuses_when_telemetry_is_disabled(tmp_path, monkeypatch) -> None:
    config = fake_config(tmp_path)
    storage = LocalTelemetryStorage(
        TelemetryPaths(root=config.telemetry_root / "raw", salt=tmp_path / "salt"),
        config.limits,
    )
    monkeypatch.setattr(research_launcher, "_verify_workspace", lambda *args: None)
    monkeypatch.setattr(research_launcher, "load_external_config", lambda: config)
    monkeypatch.setattr(research_launcher, "configured_storage", lambda **kwargs: storage)
    args = argparse.Namespace(
        window_id="smart-router",
        cwd=str(tmp_path),
        codex_bin="codex",
        print_command=True,
        manager_only=False,
    )
    with pytest.raises(BackendError, match="not explicitly enabled"):
        asyncio.run(research_launcher._run(args))


def test_workspace_path_is_replaced_by_hmac_signature(tmp_path) -> None:
    config = fake_config(tmp_path)
    storage = external_storage(config)
    service = TelemetryService(storage, window_id="smart-router", codex_protocol_version="codex-cli_0.144.5")
    start = service.start_run(
        task="Synthetic private workspace fixture",
        task_domain="normal_coding",
        workspace=str(tmp_path / "private-project"),
        product_surface="codex_app_server_research",
    )
    assert start.run is not None
    assert start.run.finish(status="completed").appended
    raw = next((config.telemetry_root / "raw").rglob("codex_runs-*.jsonl")).read_text(encoding="utf-8")
    assert str(tmp_path) not in raw
    record = json.loads(raw)
    assert len(record["workspace_signature"]) == 64


def test_outcome_combinations_corrections_and_pending_are_enforced(tmp_path) -> None:
    config = fake_config(tmp_path)
    storage = external_storage(config)
    aoia = add_run(storage, window_id="aoia")
    smart = add_run(storage, window_id="smart-router")
    with pytest.raises(TelemetryValidationError, match="INCONSISTENT_ACCEPTED_OUTCOME"):
        build_outcome_record(aoia, "accepted", failure_category="incorrect_approach")
    with pytest.raises(TelemetryValidationError, match="REJECTED_OUTCOME_REQUIRES_FAILURE"):
        build_outcome_record(smart, "rejected", failure_category="none")
    assert latest_pending_run(storage, window_id="aoia")["run_id"] == aoia["run_id"]
    assert len(pending_runs(storage, window_id="smart-router")) == 1
    assert record_outcome(storage, aoia["run_id"], "accepted", edit_magnitude="none").appended
    assert record_outcome(
        storage,
        aoia["run_id"],
        "accepted-with-edits",
        edit_magnitude="minor",
        followup_turns=1,
    ).appended
    outcomes = [value for value in storage.iter_records() if value.get("record_type") == "outcome"]
    assert outcomes[-1]["supersedes_outcome_id"] == outcomes[-2]["outcome_id"]
    assert pending_runs(storage, window_id="aoia") == []


def test_noninteractive_process_cannot_write_operator_outcome(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli, "_interactive_operator_terminal", lambda: False)
    assert cli.main(["outcome", "00000000-0000-0000-0000-000000000000", "accepted"]) == 2
    assert "OUTCOME_REQUIRES_INTERACTIVE_OPERATOR_TTY" in capsys.readouterr().out


def test_latest_outcome_cli_selects_only_requested_window(tmp_path, monkeypatch, capsys) -> None:
    config = fake_config(tmp_path)
    storage = external_storage(config)
    aoia = add_run(storage, window_id="aoia")
    add_run(storage, window_id="smart-router")
    monkeypatch.setattr(cli, "_interactive_operator_terminal", lambda: True)
    monkeypatch.setattr(
        "smart_codex.runtime.telemetry.config.configured_storage",
        lambda *args, **kwargs: storage,
    )
    assert cli.main(
        [
            "outcome",
            "latest",
            "--window-id",
            "aoia",
            "accepted",
            "--edit-magnitude",
            "none",
        ]
    ) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["run_id"] == aoia["run_id"]
    assert len(pending_runs(storage, window_id="smart-router")) == 1


def test_dataset_is_reproducible_separates_versions_and_excludes_unknown_tokens(tmp_path, monkeypatch) -> None:
    config = fake_config(tmp_path)
    patch_dataset_config(monkeypatch, config)
    storage = external_storage(config)
    add_run(storage, input_tokens=100, outcome="accepted")
    add_run(storage, input_tokens=None)
    legacy = json.loads((ROOT / "examples/sanitized_telemetry_record.json").read_text(encoding="utf-8"))
    target = next((config.telemetry_root / "raw").rglob("codex_runs-*.jsonl"))
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(legacy, sort_keys=True) + "\n")
    first = build_dataset()
    second = build_dataset()
    assert first == second
    assert len(first["schema_protocol_groups"]) == 2
    assert first["known_token_run_count"] == 2
    assert first["record_count"] == 3
    assert dataset_status()["state"] == "CURRENT"


def test_corrupt_record_is_excluded_without_losing_valid_run(tmp_path, monkeypatch) -> None:
    config = fake_config(tmp_path)
    patch_dataset_config(monkeypatch, config)
    storage = external_storage(config)
    add_run(storage, outcome="accepted")
    target = next((config.telemetry_root / "raw").rglob("codex_runs-*.jsonl"))
    with target.open("ab") as handle:
        handle.write(b"{not-json}\n")
    manifest = build_dataset()
    assert manifest["record_count"] == 1
    assert manifest["exclusions"]["INVALID_JSON"] == 1


def test_shadow_abstains_with_empty_data_and_never_applies_route(tmp_path, monkeypatch) -> None:
    config = fake_config(tmp_path)
    patch_dataset_config(monkeypatch, config)
    storage = external_storage(config)
    empty = build_dataset()
    assert empty["record_count"] == 0
    status = shadow_status()
    assert status["decision"] == "ABSTAIN — INSUFFICIENT_DATA"
    service = TelemetryService(
        storage,
        window_id="smart-router",
        workspace_signature="a" * 64,
        router_policy_version="policy-v1",
        codex_protocol_version="codex-cli_0.144.5",
        shadow_recorder=ShadowRecorder(),
    )
    started = service.start_run(
        task="Synthetic shadow fixture",
        task_domain="normal_coding",
        task_difficulty="low",
        task_scope="single_file",
        task_risk="low",
        recommended_model="incumbent",
        launched_model="incumbent",
        model_identity_status="client_requested_only",
        reasoning_effort="medium",
        sandbox="read-only",
        approval_policy="on-request",
        product_surface="codex_app_server_research",
    )
    assert started.run is not None
    event = json.loads((config.telemetry_root / "runtime-events/shadow-decisions.jsonl").read_text(encoding="utf-8"))
    assert event["decision"] == "INSUFFICIENT_DATA"
    assert event["applied"] is False
    assert event["authority"] is False
    assert started.run.record["recommended_model"] == "incumbent"


def test_candidate_generation_requires_comparable_threshold_and_manifest_binding(tmp_path, monkeypatch) -> None:
    config = fake_config(tmp_path)
    patch_dataset_config(monkeypatch, config)
    storage = external_storage(config)
    for _ in range(31):
        add_run(storage, model="incumbent", input_tokens=100, outcome="accepted")
    for _ in range(30):
        add_run(storage, model="efficient", input_tokens=50, outcome="accepted")
    build_dataset()
    report = candidate_report()
    assert len(report["affected_strata"]) == 1
    assert report["affected_strata"][0]["shadow_candidate"]["model"] == "efficient"
    candidate = propose_policy()
    assert candidate["authority"] is False
    assert candidate["live_routing_mutation"] is False
    validation = validate_candidate(candidate["candidate_id"])
    assert validation["valid"] is True
    assert validation["manifest_bound"] is True
    assert validation["safety_fields_absent"] is True


def test_repository_contains_no_raw_telemetry_files() -> None:
    tracked_like = [
        path
        for path in ROOT.rglob("codex_runs-*.jsonl")
        if ".git" not in path.parts and ".venv" not in path.parts
    ]
    assert tracked_like == []
