from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from smart_codex import outcome_helper
from smart_codex.app_server_router.backend import SUPPORTED_CODEX_VERSION
from smart_codex.runtime.telemetry.collector import TelemetryService
from smart_codex.runtime.telemetry.storage import LocalTelemetryStorage, StorageLimits, TelemetryPaths
from smart_codex.runtime.telemetry.validator import validate_outcome_record


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_WRAPPER = ROOT / "scripts" / "start-smart-router-research"
OUTCOME_WRAPPER = ROOT / "scripts" / "rate-latest-smart-router-run"
EXPECTED_REMOTE = "https://github.com/luciferprosun/Kodex-OpenAI-Custom-Skill.git"


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _wrapper_fixture(
    tmp_path: Path,
    *,
    preflight: dict[str, object],
    preflight_exit: int = 0,
    codex_version: str = SUPPORTED_CODEX_VERSION,
) -> tuple[Path, dict[str, str], Path]:
    repository = tmp_path / "fixture-repository"
    scripts = repository / "scripts"
    binaries = tmp_path / "bin"
    scripts.mkdir(parents=True)
    binaries.mkdir()
    shutil.copy2(RESEARCH_WRAPPER, scripts / RESEARCH_WRAPPER.name)
    (scripts / RESEARCH_WRAPPER.name).chmod(0o755)
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "remote", "add", "origin", EXPECTED_REMOTE],
        check=True,
    )

    preflight_payload = json.dumps(preflight, sort_keys=True)
    _write_executable(
        scripts / "smart-codex",
        "#!/usr/bin/env bash\n"
        "[[ \"$*\" == \"telemetry preflight\" ]] || exit 90\n"
        f"printf '%s\\n' '{preflight_payload}'\n"
        "printf '%s\\n' 'PRIVATE-PREFLIGHT-STDERR' >&2\n"
        f"exit {preflight_exit}\n",
    )
    capture = tmp_path / "launcher-arguments.json"
    _write_executable(
        scripts / "start-routed-codex-research",
        "#!/usr/bin/env bash\n"
        "python3 -c 'import json, os, sys; "
        "open(os.environ[\"CAPTURE_PATH\"], \"w\", encoding=\"utf-8\").write(json.dumps(sys.argv[1:]))' "
        "\"$@\"\n",
    )
    _write_executable(
        binaries / "codex",
        "#!/usr/bin/env bash\n"
        "[[ \"$*\" == \"--version\" ]] || exit 91\n"
        f"printf '%s\\n' '{codex_version}'\n",
    )
    environment = dict(os.environ)
    environment["PATH"] = f"{binaries}:{environment['PATH']}"
    environment["CAPTURE_PATH"] = str(capture)
    return repository, environment, capture


def _ready_preflight() -> dict[str, object]:
    return {
        "ok": True,
        "preflight": "READY",
        "storage_mode": "external",
        "enabled": True,
        "mount_verification": "VERIFIED",
    }


def test_research_wrapper_refuses_when_preflight_is_not_ready(tmp_path) -> None:
    preflight = {
        "ok": False,
        "preflight": "TELEMETRY_DISABLED_FILESYSTEM_NOT_WRITABLE",
        "storage_mode": "external",
        "enabled": False,
        "mount_verification": "FILESYSTEM_NOT_WRITABLE",
        "device_uuid": "PRIVATE-DEVICE-IDENTITY",
        "mount_point": "/private/telemetry/location",
    }
    repository, environment, capture = _wrapper_fixture(
        tmp_path,
        preflight=preflight,
        preflight_exit=2,
    )

    result = subprocess.run(
        [str(repository / "scripts" / RESEARCH_WRAPPER.name)],
        cwd=tmp_path,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 2
    assert "TELEMETRY_PREFLIGHT_NOT_READY" in result.stderr
    assert "PRIVATE-DEVICE-IDENTITY" not in result.stdout + result.stderr
    assert "/private/telemetry/location" not in result.stdout + result.stderr
    assert "PRIVATE-PREFLIGHT-STDERR" not in result.stdout + result.stderr
    assert not capture.exists()


def test_research_wrapper_uses_exact_root_window_and_no_prompt_argv(tmp_path) -> None:
    repository, environment, capture = _wrapper_fixture(
        tmp_path,
        preflight=_ready_preflight(),
    )

    result = subprocess.run(
        [str(repository / "scripts" / RESEARCH_WRAPPER.name)],
        cwd=tmp_path,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(capture.read_text(encoding="utf-8")) == [
        "--window-id",
        "smart-router",
        "--cwd",
        str(repository.resolve()),
    ]


def test_research_wrapper_verifies_exact_reviewed_codex_version(tmp_path) -> None:
    repository, environment, capture = _wrapper_fixture(
        tmp_path,
        preflight=_ready_preflight(),
        codex_version="codex-cli 0.144.5",
    )

    result = subprocess.run(
        [str(repository / "scripts" / RESEARCH_WRAPPER.name)],
        cwd=tmp_path,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 2
    assert "CODEX_VERSION_MISMATCH" in result.stderr
    assert not capture.exists()
    source = RESEARCH_WRAPPER.read_text(encoding="utf-8")
    assert f'REVIEWED_CODEX_VERSION="{SUPPORTED_CODEX_VERSION}"' in source


def test_research_wrapper_never_accepts_internal_storage(tmp_path) -> None:
    preflight = _ready_preflight()
    preflight["storage_mode"] = "internal"
    repository, environment, capture = _wrapper_fixture(tmp_path, preflight=preflight)

    result = subprocess.run(
        [str(repository / "scripts" / RESEARCH_WRAPPER.name)],
        cwd=tmp_path,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 2
    assert "TELEMETRY_PREFLIGHT_NOT_READY" in result.stderr
    assert not capture.exists()


def test_research_wrapper_verifies_smart_router_repository_identity(tmp_path) -> None:
    repository, environment, capture = _wrapper_fixture(
        tmp_path,
        preflight=_ready_preflight(),
    )
    subprocess.run(
        ["git", "-C", str(repository), "remote", "set-url", "origin", "https://example.invalid/other.git"],
        check=True,
    )

    result = subprocess.run(
        [str(repository / "scripts" / RESEARCH_WRAPPER.name)],
        cwd=tmp_path,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 2
    assert "SMART_ROUTER_REPOSITORY_IDENTITY_MISMATCH" in result.stderr
    assert "example.invalid" not in result.stderr
    assert not capture.exists()


def test_research_wrapper_does_not_modify_or_replace_ordinary_codex() -> None:
    source = RESEARCH_WRAPPER.read_text(encoding="utf-8")
    assert '"${CODEX_BIN}" --version' in source
    assert '"$@"' not in source
    assert "alias codex" not in source
    assert "function codex" not in source
    assert "telemetry preflight" in source
    assert "telemetry enable" not in source
    assert "~/.local/state" not in source


def test_desktop_entries_call_only_the_tracked_wrappers_and_contain_no_storage_identity() -> None:
    expected = {
        "SmartRouter Research.desktop": (
            "SmartRouter Research",
            "/home/l/Kodex-OpenAI-Custom-Skill/scripts/start-smart-router-research",
        ),
        "Rate SmartRouter Result.desktop": (
            "Rate SmartRouter Result",
            "/home/l/Kodex-OpenAI-Custom-Skill/scripts/rate-latest-smart-router-run",
        ),
    }
    forbidden = {
        "device_uuid",
        "filesystem uuid",
        "$mount",
        "smart-router-telemetry-salt",
        "authorization:",
        "credential=",
        "environment=",
        "prompt=",
    }
    for file_name, (name, executable) in expected.items():
        source = (ROOT / "desktop" / file_name).read_text(encoding="utf-8")
        values = dict(
            line.split("=", 1)
            for line in source.splitlines()
            if line and not line.startswith("[") and "=" in line
        )
        assert values["Name"] == name
        assert values["Terminal"] == "true"
        assert values["Exec"] == executable
        assert not forbidden.intersection(source.casefold().splitlines())
        for marker in forbidden:
            assert marker not in source.casefold()


def test_first_live_task_is_bounded_read_only_and_not_submitted_automatically() -> None:
    source = (ROOT / "docs/handoffs/FIRST_LIVE_SMARTROUTER_TELEMETRY_TASK.md").read_text(
        encoding="utf-8"
    )
    allowed_files = {
        "docs/TELEMETRY_RESEARCH_LOOP_2B2.md",
        "smart_codex/research_launcher.py",
        "smart_codex/app_server_router/turn_router.py",
        "smart_codex/runtime/telemetry/collector.py",
        "smart_codex/runtime/telemetry/storage.py",
    }
    listed_files = {
        line.removeprefix("- `").removesuffix("`")
        for line in source.splitlines()
        if line.startswith("- `")
    }
    assert listed_files == allowed_files
    for requirement in (
        "current routing authority",
        "no learning engine is connected",
        "five safety guarantees",
        "three limitations",
        "no file, Git state, or configuration was modified",
        "Do not write files",
        "write to Git",
        "change configuration",
        "create an outcome",
        "TICE/STIE",
        "paid API calls",
        "do not submit",
    ):
        assert requirement.casefold() in source.casefold()


def _storage(tmp_path: Path) -> LocalTelemetryStorage:
    external_root = tmp_path / "SmartRouterTelemetry"
    storage = LocalTelemetryStorage(
        TelemetryPaths(
            root=external_root / "raw",
            salt=tmp_path / "installation-salt",
            outcomes_root=external_root / "outcomes",
        ),
        StorageLimits(min_free_bytes=0),
        external_root=external_root,
    )
    storage.set_enabled(True)
    return storage


def _add_run(
    storage: LocalTelemetryStorage,
    *,
    window_id: str = "smart-router",
    synthetic: bool = False,
    backend_model: str | None = "gpt-fixture",
    reasoning_effort: str | None = "medium",
) -> dict[str, object]:
    service = TelemetryService(
        storage,
        window_id=window_id,
        workspace_signature=("a" if window_id == "smart-router" else "b") * 64,
        router_policy_version="fixture-policy",
        codex_protocol_version="codex-cli_0.144.6",
        synthetic=synthetic,
    )
    started = service.start_run(
        task="bounded-test-fixture",
        task_domain="normal_coding",
        task_subdomain="read_only_analysis",
        task_difficulty="low",
        task_scope="single_file",
        task_risk="low",
        verification_available=True,
        recommended_model="gpt-fixture",
        launched_model="gpt-fixture",
        backend_model=backend_model,
        model_identity_status="provider_reported",
        reasoning_effort=reasoning_effort,
        sandbox="read-only",
        approval_policy="on-request",
        product_surface="codex_app_server_research",
    )
    assert started.run is not None
    result = started.run.finish(status="completed", process_exit_code=0)
    assert result.appended
    return next(
        record
        for record in storage.iter_records()
        if record.get("record_type") == "run" and record.get("run_id") == result.run_id
    )


def _allow_operator(monkeypatch: pytest.MonkeyPatch, storage: LocalTelemetryStorage) -> None:
    monkeypatch.setattr(outcome_helper, "foreground_interactive_tty", lambda: True)
    monkeypatch.setattr(outcome_helper, "has_codex_ancestor", lambda: False)
    monkeypatch.setattr(outcome_helper, "configured_storage", lambda **_: storage)


def test_outcome_helper_requires_foreground_interactive_tty(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(outcome_helper, "foreground_interactive_tty", lambda: False)
    monkeypatch.setattr(
        outcome_helper,
        "configured_storage",
        lambda **_: pytest.fail("storage must not be opened without an operator TTY"),
    )
    error = io.StringIO()

    assert outcome_helper.main(output=io.StringIO(), error=error) == 2
    assert "INTERACTIVE_FOREGROUND_TTY_REQUIRED" in error.getvalue()


def test_outcome_helper_refuses_execution_beneath_codex(monkeypatch) -> None:
    monkeypatch.setattr(outcome_helper, "foreground_interactive_tty", lambda: True)
    monkeypatch.setattr(outcome_helper, "has_codex_ancestor", lambda: True)
    monkeypatch.setattr(
        outcome_helper,
        "configured_storage",
        lambda **_: pytest.fail("storage must not be opened beneath Codex"),
    )
    error = io.StringIO()

    assert outcome_helper.main(output=io.StringIO(), error=error) == 2
    assert "CODEX_ANCESTOR_DETECTED" in error.getvalue()


def test_outcome_helper_excludes_synthetic_and_non_smart_router_runs(monkeypatch, tmp_path) -> None:
    storage = _storage(tmp_path)
    selected = _add_run(storage, window_id="smart-router")
    aoia = _add_run(storage, window_id="aoia")
    synthetic = _add_run(storage, window_id="smart-router", synthetic=True)
    _allow_operator(monkeypatch, storage)
    output = io.StringIO()

    assert outcome_helper.main(input_fn=lambda _: "5", output=output, error=io.StringIO()) == 0

    displayed = output.getvalue()
    assert str(selected["run_id"]) in displayed
    assert str(aoia["run_id"]) not in displayed
    assert str(synthetic["run_id"]) not in displayed
    outcomes = [record for record in storage.iter_records() if record.get("record_type") == "outcome"]
    assert len(outcomes) == 1
    assert outcomes[0]["run_id"] == selected["run_id"]
    assert outcomes[0]["operator_outcome"] == "aborted"


def test_outcome_helper_never_selects_an_outcome_automatically(monkeypatch, tmp_path) -> None:
    storage = _storage(tmp_path)
    _add_run(storage)
    _allow_operator(monkeypatch, storage)

    def end_of_input(_: str) -> str:
        raise EOFError

    assert outcome_helper.main(
        input_fn=end_of_input,
        output=io.StringIO(),
        error=io.StringIO(),
    ) == 2
    assert not [record for record in storage.iter_records() if record.get("record_type") == "outcome"]


def test_outcome_helper_displays_only_allowed_metadata_and_preserves_run(monkeypatch, tmp_path) -> None:
    storage = _storage(tmp_path)
    run = _add_run(storage)
    _allow_operator(monkeypatch, storage)
    run_file = next(storage.paths.root.rglob("codex_runs-*.jsonl"))
    original_run_bytes = run_file.read_bytes()
    output = io.StringIO()

    assert outcome_helper.main(input_fn=lambda _: "1", output=output, error=io.StringIO()) == 0

    displayed = output.getvalue()
    assert str(run["run_id"]) in displayed
    assert str(run["window_id"]) in displayed
    assert str(run["finished_at"]) in displayed
    assert str(run["backend_model"]) in displayed
    assert str(run["reasoning_effort"]) in displayed
    assert str(run["collector_status"]) in displayed
    assert str(run["task_signature"]) not in displayed
    assert str(run["workspace_signature"]) not in displayed
    assert str(tmp_path) not in displayed
    assert "raw telemetry" not in displayed.casefold()
    assert run_file.read_bytes() == original_run_bytes

    outcomes = [record for record in storage.iter_records() if record.get("record_type") == "outcome"]
    assert len(outcomes) == 1
    validate_outcome_record(outcomes[0])
    assert outcomes[0]["original_record_hash"] == run["record_hash"]
    assert outcomes[0]["operator_outcome"] == "accepted"
    assert outcomes[0]["edit_magnitude"] == "none"


def test_outcome_helper_asks_failure_category_only_for_rejection(monkeypatch, tmp_path) -> None:
    accepted_storage = _storage(tmp_path / "accepted")
    _add_run(accepted_storage)
    _allow_operator(monkeypatch, accepted_storage)
    accepted_prompts: list[str] = []

    def accept(prompt: str) -> str:
        accepted_prompts.append(prompt)
        return "2"

    assert outcome_helper.main(input_fn=accept, output=io.StringIO(), error=io.StringIO()) == 0
    assert len(accepted_prompts) == 1

    rejected_storage = _storage(tmp_path / "rejected")
    _add_run(rejected_storage)
    _allow_operator(monkeypatch, rejected_storage)
    answers = iter(("4", "3"))
    rejected_prompts: list[str] = []

    def reject(prompt: str) -> str:
        rejected_prompts.append(prompt)
        return next(answers)

    assert outcome_helper.main(input_fn=reject, output=io.StringIO(), error=io.StringIO()) == 0
    assert len(rejected_prompts) == 2
    outcome = next(
        record for record in rejected_storage.iter_records() if record.get("record_type") == "outcome"
    )
    assert outcome["operator_outcome"] == "rejected"
    assert outcome["failure_category"] == "test_failure"


def test_outcome_wrapper_has_no_user_supplied_outcome_arguments() -> None:
    source = OUTCOME_WRAPPER.read_text(encoding="utf-8")
    assert "smart_codex.outcome_helper" in source
    assert '"$@"' not in source
    assert "--outcome" not in source
