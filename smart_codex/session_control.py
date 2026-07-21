"""Local, fail-closed session controls for the official Codex wrapper.

This module owns only control-plane state and metadata-only capture markers. It
does not route prompts, call providers, select models, or write SmartRouter run
telemetry.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
from typing import Callable, Iterator, Mapping
import uuid

from .policy_version import MODEL_POLICY_VERSION


STATE_SCHEMA_VERSION = "smart-codex-session-control-v1"
MARKER_SCHEMA_VERSION = "smart-codex-research-marker-v1"
INTEGRATION_VERSION = "live-codex-session-control-1a"
INTEGRATION_MODE = "official_codex_wrapper_session_control"
WRAPPER_MODE_ENV = "SMART_CODEX_INTEGRATION_MODE"
WRAPPER_MODE_VALUE = STATE_SCHEMA_VERSION

STATE_FILENAME = "session-control.json"
LOCK_FILENAME = ".session-control.lock"
MARKER_DIRECTORY = "research-markers"
MAX_STATE_BYTES = 16 * 1024
LOCK_TIMEOUT_SECONDS = 2.0
LOCK_RETRY_SECONDS = 0.01

STATE_FIELDS = frozenset(
    {
        "schema_version",
        "router_enabled",
        "research_telemetry_enabled",
        "telemetry_session_id",
        "telemetry_started_at",
        "policy_version",
        "last_updated_at",
        "last_updated_by",
    }
)
UPDATE_ACTORS = frozenset(
    {
        "smart-router-on",
        "smart-router-off",
        "smart-router-on-with-telemetry",
        "telemetry-start",
        "telemetry-stop",
        "session-reset",
    }
)
SAFE_SESSION_ID = re.compile(r"^rt-[0-9a-f]{32}$")
SAFE_MARKER_ID = re.compile(r"^rm-[0-9a-f]{32}$")
_THREAD_LOCK = threading.RLock()


class SessionControlError(RuntimeError):
    """Sanitized local session-control failure."""


class SessionStateValidationError(SessionControlError):
    """Persisted state does not satisfy the exact versioned contract."""


@dataclass(frozen=True)
class SessionControlState:
    schema_version: str
    router_enabled: bool
    research_telemetry_enabled: bool
    telemetry_session_id: str | None
    telemetry_started_at: str | None
    policy_version: str
    last_updated_at: str | None
    last_updated_by: str

    @classmethod
    def safe_default(cls) -> "SessionControlState":
        return cls(
            schema_version=STATE_SCHEMA_VERSION,
            router_enabled=False,
            research_telemetry_enabled=False,
            telemetry_session_id=None,
            telemetry_started_at=None,
            policy_version=MODEL_POLICY_VERSION,
            last_updated_at=None,
            last_updated_by="none",
        )

    def public_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class StateSnapshot:
    state: SessionControlState
    status: str


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"unsupported JSON constant: {value}")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _canonical_json(value: Mapping[str, object]) -> bytes:
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


def _utc_timestamp(clock: Callable[[], datetime]) -> str:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise SessionControlError("SESSION_CONTROL_CLOCK_INVALID")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _within(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True


def _source_repository_root() -> Path | None:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists() and (candidate / "pyproject.toml").is_file():
            return candidate
    return None


def default_state_root(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    values = os.environ if environ is None else environ
    configured = values.get("XDG_STATE_HOME")
    if configured is not None:
        if not configured or any(ord(character) < 32 for character in configured):
            raise SessionControlError("XDG_STATE_HOME_INVALID")
        base = Path(configured)
        if not base.is_absolute():
            raise SessionControlError("XDG_STATE_HOME_MUST_BE_ABSOLUTE")
    else:
        base = (Path.home() if home is None else home) / ".local" / "state"
    return base / "smart-codex" / "session-control"


def wrapper_mode_active(environ: Mapping[str, str] | None = None) -> bool:
    values = os.environ if environ is None else environ
    return values.get(WRAPPER_MODE_ENV) == WRAPPER_MODE_VALUE


class SessionControlStore:
    """Versioned local state with atomic, locked transitions."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        repository_root: Path | None = None,
        clock: Callable[[], datetime] | None = None,
        session_id_factory: Callable[[], str] | None = None,
        marker_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.root = default_state_root() if root is None else Path(root)
        if not self.root.is_absolute():
            raise SessionControlError("SESSION_STATE_ROOT_MUST_BE_ABSOLUTE")
        source_root = _source_repository_root() if repository_root is None else repository_root
        if source_root is not None and _within(self.root, Path(source_root)):
            raise SessionControlError("SESSION_STATE_ROOT_INSIDE_REPOSITORY")
        self.state_path = self.root / STATE_FILENAME
        self.lock_path = self.root / LOCK_FILENAME
        self.marker_root = self.root / MARKER_DIRECTORY
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._session_id_factory = session_id_factory or (
            lambda: f"rt-{uuid.uuid4().hex}"
        )
        self._marker_id_factory = marker_id_factory or (
            lambda: f"rm-{uuid.uuid4().hex}"
        )

    def read(self) -> StateSnapshot:
        return self._read_unlocked()

    def _read_unlocked(self) -> StateSnapshot:
        path = self.state_path
        try:
            raw = self._read_regular_file(path, require_private=True)
        except FileNotFoundError:
            return StateSnapshot(SessionControlState.safe_default(), "missing")
        except (OSError, SessionControlError):
            return StateSnapshot(SessionControlState.safe_default(), "malformed")
        try:
            payload = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
            state = self._validate_payload(payload)
        except (OSError, UnicodeError, ValueError, TypeError, SessionStateValidationError):
            return StateSnapshot(SessionControlState.safe_default(), "malformed")
        return StateSnapshot(state, "valid")

    @staticmethod
    def _validate_payload(payload: object) -> SessionControlState:
        if not isinstance(payload, dict) or set(payload) != STATE_FIELDS:
            raise SessionStateValidationError("SESSION_STATE_FIELDS_INVALID")
        if payload.get("schema_version") != STATE_SCHEMA_VERSION:
            raise SessionStateValidationError("SESSION_STATE_SCHEMA_INVALID")
        if type(payload.get("router_enabled")) is not bool:
            raise SessionStateValidationError("ROUTER_STATE_BOOLEAN_INVALID")
        if type(payload.get("research_telemetry_enabled")) is not bool:
            raise SessionStateValidationError("TELEMETRY_STATE_BOOLEAN_INVALID")
        if payload.get("policy_version") != MODEL_POLICY_VERSION:
            raise SessionStateValidationError("SESSION_POLICY_VERSION_INVALID")
        if not _valid_timestamp(payload.get("last_updated_at")):
            raise SessionStateValidationError("SESSION_UPDATED_AT_INVALID")
        actor = payload.get("last_updated_by")
        if not isinstance(actor, str) or actor not in UPDATE_ACTORS:
            raise SessionStateValidationError("SESSION_UPDATE_ACTOR_INVALID")

        telemetry_enabled = payload["research_telemetry_enabled"]
        session_id = payload.get("telemetry_session_id")
        started_at = payload.get("telemetry_started_at")
        if telemetry_enabled:
            if not isinstance(session_id, str) or SAFE_SESSION_ID.fullmatch(session_id) is None:
                raise SessionStateValidationError("TELEMETRY_SESSION_ID_INVALID")
            if not _valid_timestamp(started_at):
                raise SessionStateValidationError("TELEMETRY_STARTED_AT_INVALID")
        elif session_id is not None or started_at is not None:
            raise SessionStateValidationError("INACTIVE_TELEMETRY_STATE_INVALID")

        return SessionControlState(
            schema_version=STATE_SCHEMA_VERSION,
            router_enabled=payload["router_enabled"],
            research_telemetry_enabled=telemetry_enabled,
            telemetry_session_id=session_id,
            telemetry_started_at=started_at,
            policy_version=MODEL_POLICY_VERSION,
            last_updated_at=payload["last_updated_at"],
            last_updated_by=actor,
        )

    def set_router(
        self,
        enabled: bool,
        *,
        enable_telemetry: bool = False,
    ) -> SessionControlState:
        if type(enabled) is not bool or type(enable_telemetry) is not bool:
            raise SessionControlError("SESSION_CONTROL_BOOLEAN_INVALID")
        if enable_telemetry and not enabled:
            raise SessionControlError("COMBINED_ACTIVATION_REQUIRES_ROUTER_ON")
        actor = (
            "smart-router-on-with-telemetry"
            if enabled and enable_telemetry
            else "smart-router-on"
            if enabled
            else "smart-router-off"
        )
        return self._transition(
            router_enabled=enabled,
            telemetry_enabled=True if enable_telemetry else None,
            actor=actor,
        )

    def set_telemetry(self, enabled: bool) -> SessionControlState:
        if type(enabled) is not bool:
            raise SessionControlError("SESSION_CONTROL_BOOLEAN_INVALID")
        return self._transition(
            router_enabled=None,
            telemetry_enabled=enabled,
            actor="telemetry-start" if enabled else "telemetry-stop",
        )

    def reset(self) -> SessionControlState:
        return self._transition(
            router_enabled=False,
            telemetry_enabled=False,
            actor="session-reset",
        )

    def _transition(
        self,
        *,
        router_enabled: bool | None,
        telemetry_enabled: bool | None,
        actor: str,
    ) -> SessionControlState:
        if router_enabled is not None and type(router_enabled) is not bool:
            raise SessionControlError("ROUTER_STATE_BOOLEAN_INVALID")
        if telemetry_enabled is not None and type(telemetry_enabled) is not bool:
            raise SessionControlError("TELEMETRY_STATE_BOOLEAN_INVALID")
        if actor not in UPDATE_ACTORS:
            raise SessionControlError("SESSION_UPDATE_ACTOR_INVALID")

        with self._locked():
            snapshot = self._read_unlocked()
            previous = snapshot.state
            desired_router = (
                previous.router_enabled if router_enabled is None else router_enabled
            )
            desired_telemetry = (
                previous.research_telemetry_enabled
                if telemetry_enabled is None
                else telemetry_enabled
            )
            if (
                snapshot.status == "valid"
                and desired_router == previous.router_enabled
                and desired_telemetry == previous.research_telemetry_enabled
            ):
                return previous

            now = _utc_timestamp(self._clock)
            session_id = previous.telemetry_session_id
            started_at = previous.telemetry_started_at
            transition: str | None = None
            marker_session_id: str | None = None
            if desired_telemetry and not previous.research_telemetry_enabled:
                session_id = self._session_id_factory()
                if not isinstance(session_id, str) or SAFE_SESSION_ID.fullmatch(session_id) is None:
                    raise SessionControlError("TELEMETRY_SESSION_ID_INVALID")
                started_at = now
                transition = "capture_started"
                marker_session_id = session_id
            elif not desired_telemetry and previous.research_telemetry_enabled:
                transition = "capture_stopped"
                marker_session_id = previous.telemetry_session_id
                session_id = None
                started_at = None
            elif not desired_telemetry:
                session_id = None
                started_at = None

            next_state = replace(
                previous,
                router_enabled=desired_router,
                research_telemetry_enabled=desired_telemetry,
                telemetry_session_id=session_id,
                telemetry_started_at=started_at,
                policy_version=MODEL_POLICY_VERSION,
                last_updated_at=now,
                last_updated_by=actor,
            )
            validated = self._validate_payload(next_state.public_dict())
            prior = self._capture_prior_state_file()
            self._atomic_write_state(_canonical_json(validated.public_dict()))
            if transition is not None:
                try:
                    self._write_marker(
                        transition=transition,
                        telemetry_session_id=marker_session_id,
                        timestamp=now,
                        router_enabled=desired_router,
                    )
                except BaseException:
                    self._restore_prior_state_file(prior)
                    raise
            return validated

    def _capture_prior_state_file(self) -> tuple[bool, bytes | None]:
        try:
            payload = self._read_regular_file(self.state_path, require_private=False)
        except FileNotFoundError:
            return False, None
        except OSError as exc:
            raise SessionControlError("SESSION_STATE_READ_FAILED") from exc
        return True, payload

    @staticmethod
    def _read_regular_file(path: Path, *, require_private: bool) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(path, flags)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise SessionControlError("SESSION_STATE_PATH_UNSAFE")
            if require_private and stat.S_IMODE(info.st_mode) & 0o077:
                raise SessionControlError("SESSION_STATE_PERMISSIONS_UNSAFE")
            if info.st_size <= 0 or info.st_size > MAX_STATE_BYTES:
                raise SessionControlError("SESSION_STATE_SIZE_INVALID")
            payload = bytearray()
            while len(payload) <= MAX_STATE_BYTES:
                chunk = os.read(descriptor, min(4096, MAX_STATE_BYTES + 1 - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
            if not payload or len(payload) > MAX_STATE_BYTES:
                raise SessionControlError("SESSION_STATE_SIZE_INVALID")
            return bytes(payload)
        finally:
            os.close(descriptor)

    def _restore_prior_state_file(self, prior: tuple[bool, bytes | None]) -> None:
        existed, payload = prior
        try:
            if existed:
                assert payload is not None
                self._atomic_write_state(payload)
            else:
                self.state_path.unlink(missing_ok=True)
                self._fsync_directory(self.root)
        except OSError as exc:
            raise SessionControlError("SESSION_STATE_ROLLBACK_FAILED") from exc

    def _ensure_directory(self, path: Path) -> None:
        try:
            if path.exists() and (path.is_symlink() or not path.is_dir()):
                raise SessionControlError("SESSION_STATE_DIRECTORY_UNSAFE")
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            if path.is_symlink() or not path.is_dir():
                raise SessionControlError("SESSION_STATE_DIRECTORY_UNSAFE")
            os.chmod(path, 0o700)
        except OSError as exc:
            raise SessionControlError("SESSION_STATE_DIRECTORY_FAILED") from exc

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self._ensure_directory(self.root)
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.lock_path, flags, 0o600)
        except OSError as exc:
            raise SessionControlError("SESSION_STATE_LOCK_FAILED") from exc
        try:
            os.chmod(self.lock_path, 0o600)
            with _THREAD_LOCK:
                deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
                while True:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise SessionControlError("SESSION_STATE_LOCK_TIMEOUT")
                        time.sleep(LOCK_RETRY_SECONDS)
                try:
                    yield
                finally:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def _atomic_write_state(self, payload: bytes) -> None:
        self._atomic_write(self.state_path, payload)

    def _atomic_write(self, target: Path, payload: bytes) -> None:
        self._ensure_directory(target.parent)
        temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor: int | None = None
        try:
            descriptor = os.open(temporary, flags, 0o600)
            view = memoryview(payload)
            written = 0
            while written < len(view):
                count = os.write(descriptor, view[written:])
                if count <= 0:
                    raise SessionControlError("SESSION_STATE_PARTIAL_WRITE")
                written += count
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            os.replace(temporary, target)
            os.chmod(target, 0o600)
            self._fsync_directory(target.parent)
        except OSError as exc:
            raise SessionControlError("SESSION_STATE_WRITE_FAILED") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _write_marker(
        self,
        *,
        transition: str,
        telemetry_session_id: str | None,
        timestamp: str,
        router_enabled: bool,
    ) -> None:
        if transition not in {"capture_started", "capture_stopped"}:
            raise SessionControlError("RESEARCH_MARKER_TRANSITION_INVALID")
        if (
            not isinstance(telemetry_session_id, str)
            or SAFE_SESSION_ID.fullmatch(telemetry_session_id) is None
        ):
            raise SessionControlError("TELEMETRY_SESSION_ID_INVALID")
        marker_id = self._marker_id_factory()
        if not isinstance(marker_id, str) or SAFE_MARKER_ID.fullmatch(marker_id) is None:
            raise SessionControlError("RESEARCH_MARKER_ID_INVALID")
        marker = {
            "schema_version": MARKER_SCHEMA_VERSION,
            "marker_id": marker_id,
            "telemetry_session_id": telemetry_session_id,
            "transition": transition,
            "timestamp": timestamp,
            "policy_version": MODEL_POLICY_VERSION,
            "router_enabled": router_enabled,
            "integration_version": INTEGRATION_VERSION,
        }
        self._ensure_directory(self.marker_root)
        marker_path = self.marker_root / f"{marker_id}.json"
        if marker_path.exists() or marker_path.is_symlink():
            raise SessionControlError("RESEARCH_MARKER_ID_CONFLICT")
        self._atomic_write(marker_path, _canonical_json(marker))

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def research_capture_enabled(store: SessionControlStore | None = None) -> bool:
    """Return the selective research-capture gate without writing anything."""

    selected = SessionControlStore() if store is None else store
    return selected.read().state.research_telemetry_enabled is True
