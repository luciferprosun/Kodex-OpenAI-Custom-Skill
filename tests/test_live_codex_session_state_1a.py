from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading

import pytest

from smart_codex.policy_version import MODEL_POLICY_VERSION
from smart_codex.session_control import (
    MARKER_SCHEMA_VERSION,
    STATE_SCHEMA_VERSION,
    SessionControlError,
    SessionControlStore,
    default_state_root,
    research_capture_enabled,
)


ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = datetime(2026, 7, 21, 1, 30, tzinfo=timezone.utc)


def store_at(tmp_path: Path) -> SessionControlStore:
    marker_ids = iter(("rm-" + "2" * 32, "rm-" + "3" * 32, "rm-" + "4" * 32))
    return SessionControlStore(
        tmp_path / "state",
        repository_root=ROOT,
        clock=lambda: FIXED_TIME,
        session_id_factory=lambda: "rt-" + "1" * 32,
        marker_id_factory=lambda: next(marker_ids),
    )


def state_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "router_enabled": False,
        "research_telemetry_enabled": False,
        "telemetry_session_id": None,
        "telemetry_started_at": None,
        "policy_version": MODEL_POLICY_VERSION,
        "last_updated_at": FIXED_TIME.isoformat(timespec="microseconds"),
        "last_updated_by": "smart-router-off",
    }
    payload.update(updates)
    return payload


def write_raw_state(store: SessionControlStore, value: object) -> None:
    store.root.mkdir(mode=0o700, parents=True)
    store.state_path.write_text(json.dumps(value), encoding="utf-8")
    os.chmod(store.state_path, 0o600)


def test_missing_state_defaults_to_both_controls_off_without_writing(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    snapshot = store.read()

    assert snapshot.status == "missing"
    assert snapshot.state.router_enabled is False
    assert snapshot.state.research_telemetry_enabled is False
    assert snapshot.state.telemetry_session_id is None
    assert not store.root.exists()


def test_state_root_uses_xdg_and_safe_local_fallback(tmp_path: Path) -> None:
    assert default_state_root(environ={"XDG_STATE_HOME": str(tmp_path / "xdg")}) == (
        tmp_path / "xdg" / "smart-codex" / "session-control"
    )
    assert default_state_root(environ={}, home=tmp_path / "user") == (
        tmp_path / "user" / ".local" / "state" / "smart-codex" / "session-control"
    )
    with pytest.raises(SessionControlError, match="MUST_BE_ABSOLUTE"):
        default_state_root(environ={"XDG_STATE_HOME": "relative-state"})


def test_valid_state_loads_deterministically(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    first = store.set_router(True)
    second = store.read()

    assert second.status == "valid"
    assert second.state == first
    assert second.state.policy_version == MODEL_POLICY_VERSION
    assert store.state_path.read_bytes() == store.state_path.read_bytes()


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "[]",
        json.dumps(state_payload(schema_version="unknown")),
        json.dumps(state_payload(router_enabled="false")),
        json.dumps(state_payload(router_enabled=1)),
        json.dumps(state_payload(router_enabled=0)),
        json.dumps(state_payload(research_telemetry_enabled="false")),
        json.dumps(state_payload(extra="not allowed")),
        '{"schema_version":"smart-codex-session-control-v1",'
        '"router_enabled":false,"router_enabled":true}',
    ],
)
def test_malformed_or_invalid_state_fails_closed(tmp_path: Path, raw: str) -> None:
    store = store_at(tmp_path)
    store.root.mkdir(mode=0o700, parents=True)
    store.state_path.write_text(raw, encoding="utf-8")
    os.chmod(store.state_path, 0o600)

    snapshot = store.read()

    assert snapshot.status == "malformed"
    assert snapshot.state.router_enabled is False
    assert snapshot.state.research_telemetry_enabled is False


def test_insecure_state_permissions_fail_closed(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    write_raw_state(store, state_payload())
    os.chmod(store.state_path, 0o644)

    snapshot = store.read()

    assert snapshot.status == "malformed"
    assert snapshot.state.router_enabled is False


class Truthy:
    def __bool__(self) -> bool:
        return True


@pytest.mark.parametrize("value", ["true", "false", 0, 1, None, [], {}, Truthy()])
def test_non_boolean_control_values_cannot_activate_state(tmp_path: Path, value: object) -> None:
    store = store_at(tmp_path)
    with pytest.raises(SessionControlError):
        store.set_router(value)  # type: ignore[arg-type]
    assert store.read().state.router_enabled is False


def test_router_and_telemetry_transitions_are_independent_and_idempotent(tmp_path: Path) -> None:
    store = store_at(tmp_path)

    router_on = store.set_router(True)
    repeated_router_on = store.set_router(True)
    telemetry_on = store.set_telemetry(True)
    router_off = store.set_router(False)
    repeated_router_off = store.set_router(False)

    assert router_on == repeated_router_on
    assert router_on.router_enabled is True
    assert router_on.research_telemetry_enabled is False
    assert telemetry_on.router_enabled is True
    assert telemetry_on.research_telemetry_enabled is True
    assert router_off.router_enabled is False
    assert router_off.research_telemetry_enabled is True
    assert router_off == repeated_router_off


def test_combined_activation_api_rejects_telemetry_with_router_off(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    with pytest.raises(SessionControlError, match="REQUIRES_ROUTER_ON"):
        store.set_router(False, enable_telemetry=True)
    assert store.read().status == "missing"


def test_telemetry_start_and_stop_write_metadata_only_markers(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    started = store.set_telemetry(True)
    repeated = store.set_telemetry(True)
    stopped = store.set_telemetry(False)

    marker_paths = sorted(store.marker_root.glob("*.json"))
    assert started == repeated
    assert started.telemetry_session_id == "rt-" + "1" * 32
    assert stopped.telemetry_session_id is None
    assert stopped.research_telemetry_enabled is False
    assert len(marker_paths) == 2
    markers = [json.loads(path.read_text(encoding="utf-8")) for path in marker_paths]
    assert {marker["transition"] for marker in markers} == {
        "capture_started",
        "capture_stopped",
    }
    assert {marker["schema_version"] for marker in markers} == {
        MARKER_SCHEMA_VERSION
    }
    encoded = json.dumps(markers).lower()
    for forbidden in ("prompt", "response", "secret", "api_key", "attachment"):
        assert forbidden not in encoded


def test_selective_research_gate_tracks_only_the_telemetry_switch(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    assert research_capture_enabled(store) is False
    store.set_router(True)
    assert research_capture_enabled(store) is False
    store.set_telemetry(True)
    assert research_capture_enabled(store) is True
    store.set_telemetry(False)
    assert research_capture_enabled(store) is False


def test_combined_activation_persists_both_controls_in_one_state(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    state = store.set_router(True, enable_telemetry=True)

    assert state.router_enabled is True
    assert state.research_telemetry_enabled is True
    assert state.last_updated_by == "smart-router-on-with-telemetry"
    on_disk = json.loads(store.state_path.read_text(encoding="utf-8"))
    assert on_disk["router_enabled"] is True
    assert on_disk["research_telemetry_enabled"] is True


def test_failed_combined_state_write_leaves_previous_state_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = store_at(tmp_path)
    before = store.set_router(False)
    before_bytes = store.state_path.read_bytes()

    def fail_write(payload: bytes) -> None:
        raise SessionControlError("SYNTHETIC_STATE_WRITE_FAILURE")

    monkeypatch.setattr(store, "_atomic_write_state", fail_write)
    with pytest.raises(SessionControlError, match="SYNTHETIC_STATE_WRITE_FAILURE"):
        store.set_router(True, enable_telemetry=True)

    assert store.state_path.read_bytes() == before_bytes
    assert SessionControlStore(store.root, repository_root=ROOT).read().state == before


def test_marker_failure_rolls_back_combined_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = store_at(tmp_path)
    before = store.set_router(False)
    before_bytes = store.state_path.read_bytes()

    def fail_marker(**kwargs: object) -> None:
        raise SessionControlError("SYNTHETIC_MARKER_FAILURE")

    monkeypatch.setattr(store, "_write_marker", fail_marker)
    with pytest.raises(SessionControlError, match="SYNTHETIC_MARKER_FAILURE"):
        store.set_router(True, enable_telemetry=True)

    assert store.state_path.read_bytes() == before_bytes
    assert SessionControlStore(store.root, repository_root=ROOT).read().state == before


def test_atomic_concurrent_updates_never_expose_invalid_json(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    errors: list[BaseException] = []

    def worker(value: bool) -> None:
        try:
            for _ in range(8):
                store.set_router(value)
                payload = json.loads(store.state_path.read_text(encoding="utf-8"))
                assert type(payload["router_enabled"]) is bool
        except BaseException as exc:  # collected and asserted in the parent thread
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index % 2 == 0,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert store.read().status == "valid"


def test_state_location_is_outside_repository_and_permissions_are_restrictive(
    tmp_path: Path,
) -> None:
    store = store_at(tmp_path)
    store.set_router(True)

    with pytest.raises(ValueError):
        store.root.resolve().relative_to(ROOT.resolve())
    assert stat_mode(store.root) == 0o700
    assert stat_mode(store.state_path) == 0o600
    assert stat_mode(store.lock_path) == 0o600


def test_state_root_inside_repository_is_rejected() -> None:
    with pytest.raises(SessionControlError, match="INSIDE_REPOSITORY"):
        SessionControlStore(ROOT / ".unsafe-state", repository_root=ROOT)


def test_persisted_control_files_contain_no_prompt_or_secret_material(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    store.set_router(True, enable_telemetry=True)
    store.set_telemetry(False)

    encoded = "\n".join(
        path.read_text(encoding="utf-8")
        for path in store.root.rglob("*")
        if path.is_file() and path.name != ".session-control.lock"
    ).lower()
    for forbidden in (
        "raw_prompt",
        "prompt_text",
        "provider_response",
        "authorization",
        "credential",
        "private key",
    ):
        assert forbidden not in encoded


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777
