"""Strict, local-only configuration for optional external telemetry storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import stat
from typing import Any
import uuid

from .errors import TelemetryStorageError
from .models import canonical_json, utc_now
from .mounts import MountVerification, verify_mount
from .storage import LocalTelemetryStorage, StorageLimits, TelemetryPaths, _write_all


CONFIG_VERSION = "1.0.0"
EXTERNAL_MAX_FILE_BYTES = 16 * 1024 * 1024
EXTERNAL_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
EXTERNAL_MIN_FREE_BYTES = 1024 * 1024 * 1024
CONFIG_FIELDS = {
    "config_version",
    "storage_mode",
    "telemetry_root",
    "device_uuid",
    "mount_point",
    "filesystem_type",
    "configured_at",
    "limits",
}
LIMIT_FIELDS = {"max_file_bytes", "max_total_bytes", "min_free_bytes", "max_record_bytes"}
LAYOUT_DIRECTORIES = (
    "raw",
    "derived",
    "manifests",
    "policy-candidates",
    "reports",
    "runtime-events",
)


def config_path() -> Path:
    return Path.home() / ".config" / "smart-codex" / "telemetry.json"


def _reject_parent_symlinks(path: Path) -> None:
    parent = path.parent
    current = Path(parent.anchor)
    for part in parent.parts[1:]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise TelemetryStorageError("CONFIG_PARENT_SYMLINK")


def _safe_parent(path: Path) -> None:
    _reject_parent_symlinks(path)
    parent = path.parent
    if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
        raise TelemetryStorageError("CONFIG_PARENT_UNSAFE")
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(parent, 0o700)
    if stat.S_IMODE(parent.stat().st_mode) != 0o700:
        raise TelemetryStorageError("CONFIG_PARENT_PERMISSIONS")


@dataclass(frozen=True)
class ExternalTelemetryConfig:
    telemetry_root: Path
    device_uuid: str
    mount_point: Path
    filesystem_type: str
    configured_at: str
    limits: StorageLimits

    def to_record(self) -> dict[str, Any]:
        return {
            "config_version": CONFIG_VERSION,
            "storage_mode": "external",
            "telemetry_root": str(self.telemetry_root),
            "device_uuid": self.device_uuid,
            "mount_point": str(self.mount_point),
            "filesystem_type": self.filesystem_type,
            "configured_at": self.configured_at,
            "limits": {
                "max_file_bytes": self.limits.max_file_bytes,
                "max_total_bytes": self.limits.max_total_bytes,
                "min_free_bytes": self.limits.min_free_bytes,
                "max_record_bytes": self.limits.max_record_bytes,
            },
        }


def _parse_config(value: object) -> ExternalTelemetryConfig:
    if not isinstance(value, dict) or set(value) != CONFIG_FIELDS:
        raise TelemetryStorageError("CONFIG_FIELD_SET_MISMATCH")
    if value.get("config_version") != CONFIG_VERSION or value.get("storage_mode") != "external":
        raise TelemetryStorageError("CONFIG_VERSION_MISMATCH")
    limits = value.get("limits")
    if not isinstance(limits, dict) or set(limits) != LIMIT_FIELDS:
        raise TelemetryStorageError("CONFIG_LIMIT_FIELD_SET_MISMATCH")
    numbers: dict[str, int] = {}
    for field in LIMIT_FIELDS:
        number = limits.get(field)
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise TelemetryStorageError("CONFIG_LIMIT_INVALID")
        numbers[field] = number
    if not (
        numbers["max_record_bytes"] <= numbers["max_file_bytes"]
        <= numbers["max_total_bytes"]
    ):
        raise TelemetryStorageError("CONFIG_LIMIT_RELATION_INVALID")
    root = value.get("telemetry_root")
    mount = value.get("mount_point")
    device_uuid = value.get("device_uuid")
    filesystem = value.get("filesystem_type")
    configured_at = value.get("configured_at")
    if not all(isinstance(item, str) and item for item in (root, mount, device_uuid, filesystem, configured_at)):
        raise TelemetryStorageError("CONFIG_VALUE_INVALID")
    if len(device_uuid) > 128 or not all(character.isalnum() or character in "-_" for character in device_uuid):
        raise TelemetryStorageError("CONFIG_UUID_INVALID")
    if len(filesystem) > 32 or not all(character.isalnum() or character in "._+-" for character in filesystem):
        raise TelemetryStorageError("CONFIG_FILESYSTEM_INVALID")
    try:
        parsed_time = datetime.fromisoformat(configured_at)
    except ValueError as exc:
        raise TelemetryStorageError("CONFIG_TIMESTAMP_INVALID") from exc
    if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
        raise TelemetryStorageError("CONFIG_TIMESTAMP_INVALID")
    root_path = Path(root)
    mount_path = Path(mount)
    if not root_path.is_absolute() or not mount_path.is_absolute() or root_path.name != "SmartRouterTelemetry":
        raise TelemetryStorageError("CONFIG_PATH_INVALID")
    try:
        if os.path.commonpath((str(root_path), str(mount_path))) != os.path.normpath(str(mount_path)):
            raise TelemetryStorageError("CONFIG_ROOT_OUTSIDE_MOUNT")
    except ValueError as exc:
        raise TelemetryStorageError("CONFIG_ROOT_OUTSIDE_MOUNT") from exc
    return ExternalTelemetryConfig(
        telemetry_root=root_path,
        device_uuid=device_uuid,
        mount_point=mount_path,
        filesystem_type=filesystem,
        configured_at=configured_at,
        limits=StorageLimits(**numbers),
    )


def load_external_config(path: Path | None = None) -> ExternalTelemetryConfig | None:
    target = path or config_path()
    _reject_parent_symlinks(target)
    if not target.exists():
        return None
    info = target.lstat()
    if not stat.S_ISREG(info.st_mode) or target.is_symlink():
        raise TelemetryStorageError("CONFIG_FILE_UNSAFE")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise TelemetryStorageError("CONFIG_FILE_PERMISSIONS")
    if stat.S_IMODE(target.parent.stat().st_mode) != 0o700:
        raise TelemetryStorageError("CONFIG_PARENT_PERMISSIONS")
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TelemetryStorageError("CONFIG_PARSE_FAILED") from exc
    return _parse_config(value)


def _atomic_write_config(config: ExternalTelemetryConfig, target: Path) -> None:
    _safe_parent(target)
    if target.exists() and (target.is_symlink() or not target.is_file()):
        raise TelemetryStorageError("CONFIG_FILE_UNSAFE")
    temporary = target.parent / f".telemetry-{uuid.uuid4()}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        try:
            _write_all(descriptor, canonical_json(config.to_record()).encode("utf-8") + b"\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)
    os.chmod(target, 0o600)
    directory = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def configure_external_storage(
    root: Path,
    device_uuid: str,
    *,
    path: Path | None = None,
) -> ExternalTelemetryConfig:
    root = root.expanduser().absolute()
    verification = verify_mount(root, device_uuid, minimum_free_bytes=EXTERNAL_MIN_FREE_BYTES)
    if not verification.ok or verification.filesystem is None:
        raise TelemetryStorageError(verification.reason)
    filesystem = verification.filesystem
    config = ExternalTelemetryConfig(
        telemetry_root=root,
        device_uuid=device_uuid,
        mount_point=Path(filesystem.mount_point),
        filesystem_type=filesystem.filesystem,
        configured_at=utc_now(),
        limits=StorageLimits(
            max_file_bytes=EXTERNAL_MAX_FILE_BYTES,
            max_total_bytes=EXTERNAL_MAX_TOTAL_BYTES,
            min_free_bytes=EXTERNAL_MIN_FREE_BYTES,
        ),
    )
    root.mkdir(mode=0o700, parents=False, exist_ok=True)
    if root.is_symlink() or root.stat().st_uid != os.getuid():
        raise TelemetryStorageError("EXTERNAL_ROOT_UNSAFE")
    for name in LAYOUT_DIRECTORIES:
        directory = root / name
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise TelemetryStorageError("EXTERNAL_LAYOUT_UNSAFE")
        directory.mkdir(mode=0o700, exist_ok=True)
    _atomic_write_config(config, path or config_path())
    return config


def reset_external_config(path: Path | None = None) -> bool:
    target = path or config_path()
    _reject_parent_symlinks(target)
    if not target.exists():
        return False
    if target.is_symlink() or not target.is_file():
        raise TelemetryStorageError("CONFIG_FILE_UNSAFE")
    target.unlink()
    return True


class ConfiguredMountVerifier:
    def __init__(self, config: ExternalTelemetryConfig):
        self.config = config

    def __call__(self) -> MountVerification:
        result = verify_mount(
            self.config.telemetry_root,
            self.config.device_uuid,
            minimum_free_bytes=self.config.limits.min_free_bytes,
        )
        if not result.ok or result.filesystem is None:
            return result
        if Path(result.filesystem.mount_point) != self.config.mount_point:
            return MountVerification(False, "MOUNT_IDENTITY_MISMATCH", result.filesystem)
        if result.filesystem.filesystem != self.config.filesystem_type:
            return MountVerification(False, "FILESYSTEM_TYPE_MISMATCH", result.filesystem)
        return result


def configured_storage(*, require_external: bool = False) -> LocalTelemetryStorage:
    config = load_external_config()
    if config is None:
        if require_external:
            raise TelemetryStorageError("EXTERNAL_STORAGE_NOT_CONFIGURED")
        return LocalTelemetryStorage()
    salt = Path.home() / ".local" / "state" / "smart-codex" / "telemetry_salt"
    return LocalTelemetryStorage(
        TelemetryPaths(root=config.telemetry_root / "raw", salt=salt),
        config.limits,
        mount_verifier=ConfiguredMountVerifier(config),
        external_root=config.telemetry_root,
    )
