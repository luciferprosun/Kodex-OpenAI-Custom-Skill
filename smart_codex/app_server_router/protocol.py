"""JSON-RPC message helpers and privacy-preserving routing event logs."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable, Mapping, Protocol


ROUTING_ERROR_CODE = -32090
ROUTING_ERROR_MESSAGE = (
    "Smart Router could not safely route this turn. Retry with ordinary Codex "
    "(routing off)."
)
SAFE_LOG_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}$")
LOG_FIELDS = {
    "event",
    "status",
    "request_id",
    "thread_id",
    "prompt_hash",
    "category",
    "route_class",
    "original_model",
    "previous_model",
    "new_model",
    "selected_model",
    "forwarded_model",
    "active_model",
    "effort",
    "active_effort",
    "sandbox",
    "approval",
    "error_code",
    "score_margin",
    "switch_reason",
    "selection_confidence",
    "switch_confidence",
    "selection_explanation",
    "fallback_model",
    "drift_warning",
    "migration_warning",
}


class ProtocolError(RuntimeError):
    pass


def decode_message(raw: str) -> dict[str, Any]:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError("invalid JSON message") from exc
    if not isinstance(message, dict):
        raise ProtocolError("JSON-RPC message must be an object")
    return message


def encode_message(message: Mapping[str, Any]) -> str:
    return json.dumps(message, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


def routing_error(request_id: object) -> dict[str, Any]:
    safe_id: str | int | None
    if isinstance(request_id, bool) or not isinstance(request_id, (str, int)):
        safe_id = None
    else:
        safe_id = request_id
    return {
        "id": safe_id,
        "error": {"code": ROUTING_ERROR_CODE, "message": ROUTING_ERROR_MESSAGE},
    }


class EventSink(Protocol):
    def emit(self, event: Mapping[str, object]) -> None: ...


class NullEventSink:
    def emit(self, event: Mapping[str, object]) -> None:
        del event


class MemoryEventSink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def emit(self, event: Mapping[str, object]) -> None:
        self.events.append(sanitize_event(event))


class JsonlEventSink:
    def __init__(
        self,
        path: Path,
        *,
        preflight: Callable[[], str | None] | None = None,
        max_file_bytes: int = 16 * 1024 * 1024,
    ):
        self.path = path
        self.preflight = preflight
        self.max_file_bytes = max_file_bytes
        warning = self._preflight_warning()
        if warning is not None:
            raise ProtocolError(f"event storage preflight failed: {warning}")
        _reject_symlink_components(self.path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _reject_symlink_components(self.path)
        if self.path.exists() and (self.path.is_symlink() or not self.path.is_file()):
            raise ProtocolError("event log path is unsafe")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.path, flags, 0o600)
        os.close(descriptor)
        os.chmod(self.path.parent, 0o700)
        os.chmod(self.path, 0o600)

    def _preflight_warning(self) -> str | None:
        if self.preflight is None:
            return None
        try:
            warning = self.preflight()
        except Exception:
            return "EVENT_STORAGE_PREFLIGHT_ERROR"
        return warning if isinstance(warning, str) and warning else None

    def emit(self, event: Mapping[str, object]) -> None:
        if self._preflight_warning() is not None:
            return
        sanitized = sanitize_event(event)
        payload = (encode_message(sanitized) + "\n").encode("utf-8")
        try:
            _reject_symlink_components(self.path)
            if self.path.exists():
                info = self.path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_size + len(payload) > self.max_file_bytes:
                    return
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self.path, flags, 0o600)
            try:
                written = 0
                while written < len(payload):
                    count = os.write(descriptor, payload[written:])
                    if count <= 0:
                        return
                    written += count
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.chmod(self.path, 0o600)
        except (OSError, ProtocolError):
            return


def _reject_symlink_components(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ProtocolError("event log path inspection failed") from exc
        if stat.S_ISLNK(info.st_mode):
            raise ProtocolError("event log path contains a symlink")


def sanitize_event(event: Mapping[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    for key in LOG_FIELDS:
        value = event.get(key)
        if value is None:
            continue
        if key == "request_id":
            if isinstance(value, int) and not isinstance(value, bool):
                sanitized[key] = value
            elif isinstance(value, str):
                sanitized[key] = hashlib.sha256(value.encode("utf-8")).hexdigest()
            continue
        if key == "thread_id":
            if isinstance(value, str):
                sanitized[key] = hashlib.sha256(value.encode("utf-8")).hexdigest()
            continue
        if key == "error_code" and isinstance(value, int) and not isinstance(value, bool):
            sanitized[key] = value
            continue
        if not isinstance(value, str):
            value = "granular" if key == "approval" and isinstance(value, dict) else str(value)
        value = " ".join(value.split())[:160]
        if key == "prompt_hash":
            if re.fullmatch(r"[a-f0-9]{64}", value):
                sanitized[key] = value
        elif SAFE_LOG_VALUE.fullmatch(value):
            sanitized[key] = value
    return sanitized
