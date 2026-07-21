"""Selective Codex-hook capture into the existing telemetry schema.

The bridge persists only an unsealed metadata record between turn-scoped hook
processes. Raw prompts, tool arguments, responses, paths, and hook payloads are
never written. Routing and telemetry remain independent and non-authoritative.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Callable, Iterator
import uuid

from smart_codex.policy_version import normalize_policy_provenance
from smart_codex.session_control import SAFE_SESSION_ID, SessionControlStore

from .collector import TelemetryRun, TelemetryService
from .config import configured_storage
from .errors import TelemetryError
from .privacy import private_identifier, scan_record
from .schema import SCHEMA_VERSION


PENDING_SCHEMA_VERSION = "smart-codex-hook-telemetry-pending-v1"
PENDING_DIRECTORY = "hook-telemetry-pending"
PENDING_LOCK = ".hook-telemetry.lock"
MAX_PENDING_BYTES = 96 * 1024
MAX_SEEN_TOOL_IDS = 2048
HEX_64 = re.compile(r"^[a-f0-9]{64}$")
SAFE_HOOK_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")


@dataclass(frozen=True)
class HookCaptureResult:
    run_id: str | None = None
    appended: bool = False
    warning: str | None = None


class HookTelemetryCaptureError(RuntimeError):
    """Sanitized, non-authoritative hook telemetry failure."""


def _canonical_json(value: dict[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"unsupported JSON constant: {value}")


def _hook_identity(payload: object, event: str) -> tuple[str, str, str, str, str]:
    if not isinstance(payload, dict) or payload.get("hook_event_name") != event:
        raise HookTelemetryCaptureError("HOOK_TELEMETRY_PAYLOAD_INVALID")
    values: list[str] = []
    for field in ("session_id", "turn_id", "cwd", "model", "permission_mode"):
        value = payload.get(field)
        if not isinstance(value, str) or not value or len(value) > 4096:
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_PAYLOAD_INVALID")
        values.append(value)
    return values[0], values[1], values[2], values[3], values[4]


def _tool_bucket(value: object) -> str:
    if not isinstance(value, str) or SAFE_HOOK_TOKEN.fullmatch(value) is None:
        raise HookTelemetryCaptureError("HOOK_TELEMETRY_TOOL_INVALID")
    if value == "Bash":
        return "shell"
    if value in {"apply_patch", "Edit", "Write"}:
        return "file_edit"
    if value.startswith("mcp__"):
        return "mcp"
    return "local_tool"


class CodexHookTelemetryCapture:
    """Cross-process hook lifecycle adapter for schema-2.0.0 telemetry."""

    def __init__(
        self,
        store: SessionControlStore,
        *,
        service_factory: Callable[[], TelemetryService] | None = None,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
        synthetic: bool = False,
    ) -> None:
        if type(synthetic) is not bool:
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_SYNTHETIC_INVALID")
        self.store = store
        self.pending_root = store.root / PENDING_DIRECTORY
        self.lock_path = store.root / PENDING_LOCK
        self._service_factory = service_factory or self._default_service
        self._monotonic_ns = monotonic_ns
        self.synthetic = synthetic

    def _capture_enabled(self) -> bool:
        snapshot = self.store.read()
        return (
            snapshot.status == "valid"
            and snapshot.state.research_telemetry_enabled is True
            and snapshot.state.telemetry_session_id is not None
        )

    def _default_service(self) -> TelemetryService:
        storage = configured_storage(activation_reader=self._capture_enabled)
        return TelemetryService(
            storage,
            window_id="smart-router",
            router_policy_version=self.store.read().state.policy_version,
            codex_protocol_version="codex-cli-0.144.6",
        )

    @staticmethod
    def _pending_key(salt: bytes, session_id: str, turn_id: str) -> str:
        return private_identifier(salt, "codex-hook-turn", f"{session_id}\0{turn_id}")

    def _pending_path(self, key: str) -> Path:
        if HEX_64.fullmatch(key) is None:
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_KEY_INVALID")
        return self.pending_root / f"pending-{key}.json"

    def start_prompt(
        self,
        payload: object,
        *,
        task: str,
        decision: object,
    ) -> HookCaptureResult:
        if not self._capture_enabled():
            return HookCaptureResult()
        session_id, turn_id, cwd, model, permission_mode = _hook_identity(
            payload,
            "UserPromptSubmit",
        )
        try:
            service = self._service_factory()
            started = service.start_run(
                task=task,
                task_domain=getattr(decision, "category", "unknown"),
                task_subdomain=getattr(decision, "task_subdomain", None),
                task_difficulty=getattr(decision, "complexity_level", "unknown"),
                task_scope=getattr(decision, "execution_scope", "unknown"),
                task_risk=getattr(decision, "risk_level", "unknown"),
                verification_available=None,
                requested_model=model,
                recommended_model=getattr(decision, "selected_model", None),
                launched_model=model,
                backend_model=None,
                model_identity_status="client_requested_only",
                reasoning_effort=None,
                agent_count=None,
                sandbox="unknown",
                approval_policy=permission_mode,
                product_surface="codex_cli_hooks",
                session_id=session_id,
                window_id="smart-router",
                workspace=cwd,
                router_policy_version=normalize_policy_provenance(
                    getattr(decision, "policy_version", None)
                ),
                codex_protocol_version="codex-cli-0.144.6",
                synthetic=self.synthetic,
            )
        except (OSError, RuntimeError, ValueError):
            return HookCaptureResult(warning="TELEMETRY_OBSERVER_ERROR")
        if started.run is None:
            return HookCaptureResult(warning=started.warning)

        run = started.run
        key = self._pending_key(run.salt, session_id, turn_id)
        snapshot = self.store.read()
        capture_session = snapshot.state.telemetry_session_id
        if snapshot.status != "valid" or capture_session is None:
            return HookCaptureResult(warning="TELEMETRY_CAPTURE_STATE_CHANGED")
        envelope: dict[str, object] = {
            "schema_version": PENDING_SCHEMA_VERSION,
            "pending_key": key,
            "capture_session_id": capture_session,
            "started_monotonic_ns": self._monotonic_ns(),
            "record": run.record,
            "seen_tool_ids": [],
        }
        try:
            self._validate_envelope(envelope, expected_key=key)
            with self._locked():
                path = self._pending_path(key)
                if path.exists():
                    existing = self._read_envelope(path, expected_key=key)
                    record = existing["record"]
                    run_id = record.get("run_id") if isinstance(record, dict) else None
                    return HookCaptureResult(
                        run_id=run_id if isinstance(run_id, str) else None
                    )
                self._atomic_write(path, _canonical_json(envelope))
        except (OSError, HookTelemetryCaptureError, TelemetryError, ValueError):
            return HookCaptureResult(warning="TELEMETRY_PENDING_WRITE_FAILED")
        return HookCaptureResult(run_id=run.run_id)

    def observe_tool(self, payload: object) -> HookCaptureResult:
        if not self._capture_enabled():
            return HookCaptureResult()
        session_id, turn_id, _, _, _ = _hook_identity(payload, "PostToolUse")
        if not isinstance(payload, dict):
            return HookCaptureResult(warning="HOOK_TELEMETRY_PAYLOAD_INVALID")
        tool_use_id = payload.get("tool_use_id")
        if not isinstance(tool_use_id, str) or not tool_use_id or len(tool_use_id) > 4096:
            return HookCaptureResult(warning="HOOK_TELEMETRY_TOOL_INVALID")
        try:
            tool_bucket = _tool_bucket(payload.get("tool_name"))
            service = self._service_factory()
            salt = service._installation_salt()
            key = self._pending_key(salt, session_id, turn_id)
            tool_id = private_identifier(salt, "codex-hook-tool", tool_use_id)
            with self._locked():
                path = self._pending_path(key)
                if not path.exists():
                    return HookCaptureResult()
                envelope = self._read_envelope(path, expected_key=key)
                seen = envelope["seen_tool_ids"]
                assert isinstance(seen, list)
                if tool_id in seen:
                    record = envelope["record"]
                    run_id = record.get("run_id") if isinstance(record, dict) else None
                    return HookCaptureResult(
                        run_id=run_id if isinstance(run_id, str) else None
                    )
                if len(seen) >= MAX_SEEN_TOOL_IDS:
                    return HookCaptureResult(warning="TELEMETRY_TOOL_LIMIT_REACHED")
                seen.append(tool_id)
                record = envelope["record"]
                assert isinstance(record, dict)
                by_type = record.get("tool_calls_by_type")
                counts = dict(by_type) if isinstance(by_type, dict) else {}
                counts[tool_bucket] = int(counts.get(tool_bucket, 0)) + 1
                record["tool_calls_by_type"] = counts
                record["tool_call_count"] = sum(counts.values())
                sources = record.get("measurement_sources")
                if not isinstance(sources, dict):
                    raise HookTelemetryCaptureError("HOOK_TELEMETRY_RECORD_INVALID")
                sources["tool_call_count"] = "measured"
                self._validate_envelope(envelope, expected_key=key)
                self._atomic_write(path, _canonical_json(envelope))
                run_id = record.get("run_id")
                return HookCaptureResult(
                    run_id=run_id if isinstance(run_id, str) else None
                )
        except (OSError, RuntimeError, ValueError, HookTelemetryCaptureError, TelemetryError):
            return HookCaptureResult(warning="TELEMETRY_OBSERVER_ERROR")

    def finish_turn(self, payload: object) -> HookCaptureResult:
        if not self._capture_enabled():
            return HookCaptureResult()
        session_id, turn_id, _, _, _ = _hook_identity(payload, "Stop")
        try:
            service = self._service_factory()
            salt = service._installation_salt()
            key = self._pending_key(salt, session_id, turn_id)
            with self._locked():
                path = self._pending_path(key)
                if not path.exists():
                    return HookCaptureResult()
                envelope = self._read_envelope(path, expected_key=key)
                snapshot = self.store.read()
                if (
                    snapshot.status != "valid"
                    or snapshot.state.research_telemetry_enabled is not True
                    or envelope["capture_session_id"]
                    != snapshot.state.telemetry_session_id
                ):
                    path.unlink(missing_ok=True)
                    return HookCaptureResult(warning="TELEMETRY_CAPTURE_STATE_CHANGED")
                started_monotonic_ns = envelope["started_monotonic_ns"]
                assert isinstance(started_monotonic_ns, int)
                if started_monotonic_ns > self._monotonic_ns():
                    path.unlink(missing_ok=True)
                    return HookCaptureResult(warning="TELEMETRY_CLOCK_UNRECONCILED")
                record = envelope["record"]
                assert isinstance(record, dict)
                run = TelemetryRun(
                    record,
                    storage=service.storage,
                    salt=salt,
                    started_monotonic_ns=started_monotonic_ns,
                )
                result = run.finish(status="completed")
                path.unlink(missing_ok=True)
                return HookCaptureResult(
                    run_id=result.run_id,
                    appended=result.appended,
                    warning=result.warning,
                )
        except (OSError, RuntimeError, ValueError, HookTelemetryCaptureError, TelemetryError):
            return HookCaptureResult(warning="TELEMETRY_OBSERVER_ERROR")

    def backend_status(self) -> str:
        if not self._capture_enabled():
            return "OFF"
        try:
            warning = self._service_factory().storage.write_preflight()
        except (OSError, RuntimeError, ValueError, TelemetryError):
            return "DEGRADED_TELEMETRY_INITIALIZATION_ERROR"
        return "READY" if warning is None else f"DEGRADED_{warning}"

    def discard_pending(self) -> int:
        """Remove transient unsealed envelopes when capture is explicitly stopped."""

        if not self.pending_root.exists():
            return 0
        if self.pending_root.is_symlink() or not self.pending_root.is_dir():
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_DIRECTORY_UNSAFE")
        removed = 0
        with self._locked():
            for path in sorted(self.pending_root.glob("pending-*.json")):
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or path.is_symlink():
                    raise HookTelemetryCaptureError("HOOK_TELEMETRY_PENDING_UNSAFE")
                path.unlink()
                removed += 1
        return removed

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self._ensure_directory(self.store.root)
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.lock_path, flags, 0o600)
        try:
            os.chmod(self.lock_path, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    @staticmethod
    def _ensure_directory(path: Path) -> None:
        if path.exists() and (path.is_symlink() or not path.is_dir()):
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_DIRECTORY_UNSAFE")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink() or not path.is_dir():
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_DIRECTORY_UNSAFE")
        os.chmod(path, 0o700)

    def _atomic_write(self, path: Path, payload: bytes) -> None:
        if len(payload) > MAX_PENDING_BYTES:
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_PENDING_TOO_LARGE")
        self._ensure_directory(path.parent)
        if path.exists() and (path.is_symlink() or not path.is_file()):
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_PENDING_UNSAFE")
        temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(temporary, flags, 0o600)
            try:
                written = 0
                while written < len(payload):
                    count = os.write(descriptor, payload[written:])
                    if count <= 0:
                        raise HookTelemetryCaptureError("HOOK_TELEMETRY_PARTIAL_WRITE")
                    written += count
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporary, path)
            os.chmod(path, 0o600)
            parent = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _read_envelope(self, path: Path, *, expected_key: str) -> dict[str, object]:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) & 0o077
                or info.st_size <= 0
                or info.st_size > MAX_PENDING_BYTES
            ):
                raise HookTelemetryCaptureError("HOOK_TELEMETRY_PENDING_UNSAFE")
            payload = bytearray()
            while len(payload) <= MAX_PENDING_BYTES:
                chunk = os.read(
                    descriptor,
                    min(4096, MAX_PENDING_BYTES + 1 - len(payload)),
                )
                if not chunk:
                    break
                payload.extend(chunk)
            raw = bytes(payload)
        finally:
            os.close(descriptor)
        try:
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeError, ValueError) as exc:
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_PENDING_INVALID") from exc
        if not isinstance(value, dict):
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_PENDING_INVALID")
        self._validate_envelope(value, expected_key=expected_key)
        return value

    @staticmethod
    def _validate_envelope(value: dict[str, object], *, expected_key: str) -> None:
        if set(value) != {
            "schema_version",
            "pending_key",
            "capture_session_id",
            "started_monotonic_ns",
            "record",
            "seen_tool_ids",
        }:
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_PENDING_FIELDS_INVALID")
        if value.get("schema_version") != PENDING_SCHEMA_VERSION:
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_PENDING_SCHEMA_INVALID")
        if value.get("pending_key") != expected_key or HEX_64.fullmatch(expected_key) is None:
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_PENDING_KEY_INVALID")
        capture_session = value.get("capture_session_id")
        if not isinstance(capture_session, str) or SAFE_SESSION_ID.fullmatch(capture_session) is None:
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_CAPTURE_SESSION_INVALID")
        started = value.get("started_monotonic_ns")
        if isinstance(started, bool) or not isinstance(started, int) or started < 0:
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_MONOTONIC_INVALID")
        record = value.get("record")
        if (
            not isinstance(record, dict)
            or record.get("schema_version") != SCHEMA_VERSION
            or record.get("record_type") != "run"
            or record.get("finished_at") is not None
            or record.get("record_hash") != ""
        ):
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_RECORD_INVALID")
        scan_record(record)
        seen = value.get("seen_tool_ids")
        if (
            not isinstance(seen, list)
            or len(seen) > MAX_SEEN_TOOL_IDS
            or len(set(seen)) != len(seen)
            or any(not isinstance(item, str) or HEX_64.fullmatch(item) is None for item in seen)
        ):
            raise HookTelemetryCaptureError("HOOK_TELEMETRY_TOOL_IDS_INVALID")


def telemetry_backend_status(store: SessionControlStore) -> str:
    """Return a controlled, read-only backend health value for status output."""

    return CodexHookTelemetryCapture(store).backend_status()
