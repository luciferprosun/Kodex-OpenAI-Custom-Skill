"""JSON-RPC message helpers and privacy-preserving routing event logs."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Protocol


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
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.touch(mode=0o600, exist_ok=True)
        os.chmod(self.path, 0o600)

    def emit(self, event: Mapping[str, object]) -> None:
        sanitized = sanitize_event(event)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(encode_message(sanitized) + "\n")


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
