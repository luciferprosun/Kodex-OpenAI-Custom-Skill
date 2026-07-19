"""Bounded, append-only local JSONL storage."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import threading
import time
from typing import Any, Callable, Iterator
import uuid

from .errors import TelemetryError, TelemetryStorageError
from .models import canonical_json, utc_now
from .schema import MAX_RECORD_BYTES, SCHEMA_VERSION


DEFAULT_MAX_FILE_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 50 * 1024 * 1024
DEFAULT_MIN_FREE_BYTES = 1024 * 1024 * 1024
FILE_PATTERN = re.compile(r"^codex_runs-(\d{4})\.jsonl$")
OUTCOME_FILE_PATTERN = re.compile(r"^codex_outcomes-(\d{4})\.jsonl$")
_THREAD_APPEND_LOCK = threading.Lock()
LOCK_TIMEOUT_SECONDS = 5.0
LOCK_RETRY_SECONDS = 0.01


def _write_all(descriptor: int, payload: bytes) -> None:
    """Write every byte or leave a detectable trailing fragment."""

    written = 0
    while written < len(payload):
        count = os.write(descriptor, payload[written:])
        if count <= 0:
            raise TelemetryStorageError("PARTIAL_APPEND")
        written += count


@dataclass(frozen=True)
class StorageLimits:
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES
    max_record_bytes: int = MAX_RECORD_BYTES


@dataclass(frozen=True)
class TelemetryPaths:
    root: Path
    salt: Path
    outcomes_root: Path | None = None

    @classmethod
    def default(cls) -> "TelemetryPaths":
        state_root = Path.home() / ".local" / "state" / "smart-codex"
        return cls(root=state_root / "telemetry", salt=state_root / "telemetry_salt")

    @property
    def state_file(self) -> Path:
        return self.root / "state.json"

    @property
    def lock_file(self) -> Path:
        return self.root / ".append.lock"


@dataclass(frozen=True)
class AppendResult:
    appended: bool
    warning: str | None = None
    file_name: str | None = None


class LocalTelemetryStorage:
    def __init__(
        self,
        paths: TelemetryPaths | None = None,
        limits: StorageLimits | None = None,
        *,
        mount_verifier: Callable[[], object] | None = None,
        external_root: Path | None = None,
    ):
        self.paths = paths or TelemetryPaths.default()
        self.limits = limits or StorageLimits()
        self.mount_verifier = mount_verifier
        self.external_root = external_root

    @property
    def external(self) -> bool:
        return self.external_root is not None

    def verify_mount(self) -> str | None:
        if self.mount_verifier is None:
            return None
        try:
            result = self.mount_verifier()
        except (OSError, TelemetryStorageError):
            return "MOUNT_VERIFICATION_FAILED"
        if not bool(getattr(result, "ok", False)):
            reason = getattr(result, "reason", "MOUNT_VERIFICATION_FAILED")
            return str(reason) if isinstance(reason, str) else "MOUNT_VERIFICATION_FAILED"
        return None

    def _ensure_root(self) -> None:
        mount_warning = self.verify_mount()
        if mount_warning is not None:
            raise TelemetryStorageError(mount_warning)
        self.paths.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.paths.root.is_symlink():
            raise TelemetryStorageError("STORAGE_ROOT_SYMLINK")
        os.chmod(self.paths.root, 0o700)
        if self.paths.outcomes_root is not None:
            if self.paths.outcomes_root.exists() and self.paths.outcomes_root.is_symlink():
                raise TelemetryStorageError("OUTCOMES_DIRECTORY_SYMLINK")
            self.paths.outcomes_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(self.paths.outcomes_root, 0o700)
        if not self.external:
            summaries = self.paths.root / "summaries"
            if summaries.exists() and summaries.is_symlink():
                raise TelemetryStorageError("SUMMARIES_DIRECTORY_SYMLINK")
            summaries.mkdir(mode=0o700, exist_ok=True)
            os.chmod(summaries, 0o700)

    def enabled(self) -> bool:
        if self.verify_mount() is not None:
            return False
        path = self.paths.state_file
        if not path.exists():
            return False
        if path.is_symlink() or not path.is_file():
            return False
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return state.get("schema_version") == SCHEMA_VERSION and state.get("enabled") is True

    def set_enabled(self, enabled: bool) -> None:
        self._ensure_root()
        if self.paths.state_file.is_symlink():
            raise TelemetryStorageError("STATE_FILE_SYMLINK")
        state = {
            "schema_version": SCHEMA_VERSION,
            "enabled": bool(enabled),
            "updated_at": utc_now(),
        }
        temporary = self.paths.root / f".state-{uuid.uuid4()}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            payload = canonical_json(state).encode("utf-8") + b"\n"
            _write_all(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, self.paths.state_file)
        os.chmod(self.paths.state_file, 0o600)

    def free_bytes(self) -> int:
        probe = self.paths.root if self.paths.root.exists() else self.paths.root.parent
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        return int(shutil.disk_usage(probe).free)

    def storage_size(self) -> int:
        total = 0
        locations = [(self.paths.root, "codex_runs-*.jsonl")]
        if self.paths.outcomes_root is not None:
            locations.append((self.paths.outcomes_root, "codex_outcomes-*.jsonl"))
        for root, pattern in locations:
            if not root.exists():
                continue
            for path in root.rglob(pattern):
                try:
                    info = path.lstat()
                except OSError:
                    continue
                if stat.S_ISREG(info.st_mode):
                    total += info.st_size
        return total

    def write_preflight(self) -> str | None:
        mount_warning = self.verify_mount()
        if mount_warning is not None:
            return f"TELEMETRY_DISABLED_{mount_warning}"
        if not self.enabled():
            return "TELEMETRY_DISABLED"
        if self.free_bytes() < self.limits.min_free_bytes:
            return "TELEMETRY_DISABLED_LOW_DISK"
        if self.storage_size() >= self.limits.max_total_bytes:
            return "TELEMETRY_DISABLED_TOTAL_CAP"
        return None

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self._ensure_root()
        if self.paths.lock_file.exists() and self.paths.lock_file.is_symlink():
            raise TelemetryStorageError("LOCK_FILE_SYMLINK")
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.paths.lock_file, flags, 0o600)
        try:
            os.chmod(self.paths.lock_file, 0o600)
            deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
            remaining = max(0.0, deadline - time.monotonic())
            if not _THREAD_APPEND_LOCK.acquire(timeout=remaining):
                raise TelemetryStorageError("LOCK_TIMEOUT")
            try:
                while True:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise TelemetryStorageError("LOCK_TIMEOUT")
                        time.sleep(LOCK_RETRY_SECONDS)
                try:
                    yield
                finally:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                _THREAD_APPEND_LOCK.release()
        finally:
            os.close(descriptor)

    def _target_file(self, record: dict[str, Any], line_size: int) -> Path:
        timestamp = record.get("finished_at") or record.get("operator_outcome_at")
        if not isinstance(timestamp, str):
            raise TelemetryStorageError("MISSING_RECORD_TIMESTAMP")
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise TelemetryStorageError("INVALID_RECORD_TIMESTAMP") from exc
        separate_outcome = record.get("record_type") == "outcome" and self.paths.outcomes_root is not None
        base = self.paths.outcomes_root if separate_outcome else self.paths.root
        assert base is not None
        pattern = OUTCOME_FILE_PATTERN if separate_outcome else FILE_PATTERN
        prefix = "codex_outcomes" if separate_outcome else "codex_runs"
        directory = base / f"{parsed.year:04d}" / f"{parsed.month:02d}"
        year_directory = directory.parent
        if year_directory.exists() and year_directory.is_symlink():
            raise TelemetryStorageError("YEAR_DIRECTORY_SYMLINK")
        if directory.exists() and directory.is_symlink():
            raise TelemetryStorageError("MONTH_DIRECTORY_SYMLINK")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(year_directory, 0o700)
        os.chmod(directory, 0o700)
        candidates: list[tuple[int, Path]] = []
        for path in directory.glob(f"{prefix}-*.jsonl"):
            match = pattern.fullmatch(path.name)
            if match and path.is_file() and not path.is_symlink():
                candidates.append((int(match.group(1)), path))
        if candidates:
            number, current = max(candidates)
            if current.stat().st_size + line_size <= self.limits.max_file_bytes:
                return current
            number += 1
        else:
            number = 1
        return directory / f"{prefix}-{number:04d}.jsonl"

    def append(self, record: dict[str, Any]) -> AppendResult:
        try:
            from .validator import validate_outcome_record, validate_run_record

            record_type = record.get("record_type") if isinstance(record, dict) else None
            if record_type == "run":
                validate_run_record(record)
            elif record_type == "outcome":
                validate_outcome_record(record)
            else:
                return AppendResult(False, "TELEMETRY_REJECTED_UNKNOWN_RECORD_TYPE")
            encoded = canonical_json(record).encode("utf-8") + b"\n"
        except TelemetryError as exc:
            return AppendResult(False, f"TELEMETRY_REJECTED_{exc.category}")
        except (TypeError, ValueError, OverflowError):
            return AppendResult(False, "TELEMETRY_REJECTED_NON_JSON_VALUE")
        if len(encoded) > self.limits.max_record_bytes:
            return AppendResult(False, "TELEMETRY_REJECTED_RECORD_TOO_LARGE")
        if len(encoded) > self.limits.max_file_bytes:
            return AppendResult(False, "TELEMETRY_REJECTED_FILE_LIMIT")
        try:
            with self._locked():
                mount_warning = self.verify_mount()
                if mount_warning is not None:
                    return AppendResult(False, f"TELEMETRY_DISABLED_{mount_warning}")
                if not self.enabled():
                    return AppendResult(False, "TELEMETRY_DISABLED")
                if self.free_bytes() < self.limits.min_free_bytes:
                    return AppendResult(False, "TELEMETRY_DISABLED_LOW_DISK")
                current_total = self.storage_size()
                if current_total + len(encoded) > self.limits.max_total_bytes:
                    return AppendResult(False, "TELEMETRY_DISABLED_TOTAL_CAP")
                target = self._target_file(record, len(encoded))
                if target.exists() and (target.is_symlink() or not target.is_file()):
                    return AppendResult(False, "TELEMETRY_REJECTED_UNSAFE_TARGET")
                if target.exists() and target.stat().st_size:
                    read_flags = os.O_RDONLY
                    if hasattr(os, "O_NOFOLLOW"):
                        read_flags |= os.O_NOFOLLOW
                    read_descriptor = os.open(target, read_flags)
                    try:
                        os.lseek(read_descriptor, -1, os.SEEK_END)
                        if os.read(read_descriptor, 1) != b"\n":
                            return AppendResult(False, "TELEMETRY_DISABLED_TRAILING_FRAGMENT")
                    finally:
                        os.close(read_descriptor)
                flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                descriptor = os.open(target, flags, 0o600)
                try:
                    _write_all(descriptor, encoded)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.chmod(target, 0o600)
                return AppendResult(True, file_name=target.name)
        except TelemetryStorageError as exc:
            return AppendResult(False, f"TELEMETRY_DISABLED_{exc.category}")
        except OSError:
            return AppendResult(False, "TELEMETRY_DISABLED_STORAGE_ERROR")

    def iter_records(self) -> Iterator[dict[str, Any]]:
        if self.verify_mount() is not None:
            return
        locations = [(self.paths.root, "codex_runs-*.jsonl")]
        if self.paths.outcomes_root is not None:
            locations.append((self.paths.outcomes_root, "codex_outcomes-*.jsonl"))
        paths = sorted(
            path
            for root, pattern in locations
            if root.exists()
            for path in root.rglob(pattern)
        )
        for path in paths:
            try:
                info = path.lstat()
            except OSError:
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            try:
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        if len(line.encode("utf-8")) > self.limits.max_record_bytes:
                            continue
                        try:
                            value = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(value, dict):
                            yield value
            except OSError:
                continue
