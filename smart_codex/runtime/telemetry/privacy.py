"""Installation-local signatures and forbidden-content detection."""

from __future__ import annotations

import hashlib
import hmac
import fcntl
import os
from pathlib import Path
import re
import stat
import time
import unicodedata
from typing import Any

from .errors import TelemetryPrivacyError, TelemetryStorageError


SALT_BYTES = 32
SALT_LOCK_TIMEOUT_SECONDS = 0.25
SALT_LOCK_RETRY_SECONDS = 0.01
FORBIDDEN_KEYS = {
    "prompt",
    "raw_prompt",
    "response",
    "raw_response",
    "source_code",
    "code_contents",
    "tool_arguments",
    "tool_output",
    "tool_output_contents",
    "environment",
    "environment_variables",
    "authorization",
    "cookie",
    "cookies",
    "secret",
    "api_key",
    "private_key",
    "private_chat",
}
SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|sk-proj)-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[opusr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAuthorization\s*:\s*Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"\bCookie\s*:\s*\S+", re.IGNORECASE),
)
EMAIL_PATTERN = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:/|[A-Za-z]:[\\/]|\\\\)")


def normalize_task(task: str) -> str:
    normalized = unicodedata.normalize("NFKC", task).casefold()
    return " ".join(normalized.split())


def ensure_installation_salt(path: Path) -> bytes:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise TelemetryStorageError("SALT_PARENT_UNSAFE")
    os.chmod(path.parent, 0o700)
    lock_path = path.parent / ".telemetry_salt.lock"
    if lock_path.exists() and lock_path.is_symlink():
        raise TelemetryStorageError("SALT_LOCK_UNSAFE")
    lock_flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        lock_flags |= os.O_NOFOLLOW
    lock_descriptor = os.open(lock_path, lock_flags, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        deadline = time.monotonic() + SALT_LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TelemetryStorageError("SALT_LOCK_TIMEOUT")
                time.sleep(SALT_LOCK_RETRY_SECONDS)
        try:
            info = path.lstat()
        except FileNotFoundError:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(path, flags, 0o600)
            try:
                salt = os.urandom(SALT_BYTES)
                written = 0
                while written < SALT_BYTES:
                    count = os.write(descriptor, salt[written:])
                    if count <= 0:
                        raise TelemetryStorageError("SALT_PARTIAL_WRITE")
                    written += count
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return salt
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise TelemetryStorageError("SALT_PATH_UNSAFE")
        os.chmod(path, 0o600)
        salt = path.read_bytes()
        if len(salt) != SALT_BYTES:
            raise TelemetryStorageError("SALT_INVALID")
        return salt
    finally:
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)


def hmac_signature(salt: bytes, namespace: str, value: str) -> str:
    material = f"{namespace}\0{normalize_task(value)}".encode("utf-8")
    return hmac.new(salt, material, hashlib.sha256).hexdigest()


def task_signature(salt: bytes, task: str) -> str:
    return hmac_signature(salt, "task-v1", task)


def private_identifier(salt: bytes, namespace: str, identifier: str) -> str:
    return hmac_signature(salt, f"identifier:{namespace}", identifier)


def _walk(value: Any, *, key: str | None = None) -> None:
    if key is not None and key.casefold() in FORBIDDEN_KEYS:
        raise TelemetryPrivacyError("FORBIDDEN_FIELD")
    if isinstance(value, dict):
        for child_key, child in value.items():
            if not isinstance(child_key, str):
                raise TelemetryPrivacyError("NON_STRING_FIELD")
            _walk(child, key=child_key)
        return
    if isinstance(value, list):
        for child in value:
            _walk(child)
        return
    if not isinstance(value, str):
        return
    if "\n" in value or "\r" in value:
        raise TelemetryPrivacyError("MULTILINE_CONTENT")
    if len(value) > 512:
        raise TelemetryPrivacyError("OVERSIZED_TEXT")
    if EMAIL_PATTERN.search(value):
        raise TelemetryPrivacyError("PERSONAL_EMAIL")
    if ABSOLUTE_PATH_PATTERN.match(value):
        raise TelemetryPrivacyError("ABSOLUTE_PATH")
    if any(pattern.search(value) for pattern in SECRET_PATTERNS):
        raise TelemetryPrivacyError("SECRET_PATTERN")


def scan_record(record: dict[str, Any]) -> None:
    _walk(record)
