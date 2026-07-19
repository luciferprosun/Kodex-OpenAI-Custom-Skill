"""Read-only removable-storage discovery and fail-closed mount verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
from typing import Any, Iterable

from .errors import TelemetryStorageError


MIN_DISCOVERY_FREE_BYTES = 10 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class MountedFilesystem:
    device: str
    filesystem: str
    label: str | None
    uuid: str
    mount_point: str
    read_only: bool
    available_bytes: int
    writable: bool
    transport: str | None = None
    hotplug: bool = False
    removable: bool = False

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MountVerification:
    ok: bool
    reason: str
    filesystem: MountedFilesystem | None = None


def _run_json(command: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        value = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise TelemetryStorageError("STORAGE_DISCOVERY_FAILED") from exc
    if not isinstance(value, dict):
        raise TelemetryStorageError("STORAGE_DISCOVERY_MALFORMED")
    return value


def _flatten_mounts(values: Iterable[object]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        result.append(value)
        children = value.get("children")
        if isinstance(children, list):
            result.extend(_flatten_mounts(children))
    return result


def _block_metadata() -> dict[str, dict[str, Any]]:
    document = _run_json(
        [
            "lsblk",
            "--json",
            "--bytes",
            "--output",
            "NAME,PATH,TYPE,RM,HOTPLUG,TRAN,MOUNTPOINTS,FSTYPE,LABEL,UUID,SIZE",
        ]
    )
    roots = document.get("blockdevices")
    if not isinstance(roots, list):
        raise TelemetryStorageError("STORAGE_DISCOVERY_MALFORMED")
    metadata: dict[str, dict[str, Any]] = {}

    def visit(node: object, inherited: dict[str, Any]) -> None:
        if not isinstance(node, dict):
            return
        combined = {
            "transport": node.get("tran") or inherited.get("transport"),
            "hotplug": bool(node.get("hotplug")) or bool(inherited.get("hotplug")),
            "removable": bool(node.get("rm")) or bool(inherited.get("removable")),
        }
        path = node.get("path")
        if isinstance(path, str):
            metadata[path] = combined
        for child in node.get("children", []) if isinstance(node.get("children"), list) else []:
            visit(child, combined)

    for root in roots:
        visit(root, {})
    return metadata


def mounted_filesystems() -> list[MountedFilesystem]:
    document = _run_json(
        [
            "findmnt",
            "--json",
            "--bytes",
            "--output",
            "SOURCE,TARGET,FSTYPE,OPTIONS,UUID,LABEL,AVAIL,SIZE",
        ]
    )
    roots = document.get("filesystems")
    if not isinstance(roots, list):
        raise TelemetryStorageError("STORAGE_DISCOVERY_MALFORMED")
    block = _block_metadata()
    result: list[MountedFilesystem] = []
    for value in _flatten_mounts(roots):
        source = value.get("source")
        target = value.get("target")
        uuid = value.get("uuid")
        filesystem = value.get("fstype")
        if not all(isinstance(item, str) and item for item in (source, target, uuid, filesystem)):
            continue
        options = str(value.get("options") or "")
        option_set = set(options.split(","))
        available = value.get("avail")
        available_bytes = available if isinstance(available, int) and available >= 0 else 0
        target_path = Path(target)
        writable = (
            "rw" in option_set
            and "ro" not in option_set
            and target_path.is_dir()
            and os.access(target_path, os.W_OK | os.X_OK)
        )
        meta = block.get(source, {})
        result.append(
            MountedFilesystem(
                device=source,
                filesystem=filesystem,
                label=value.get("label") if isinstance(value.get("label"), str) else None,
                uuid=uuid,
                mount_point=target,
                read_only="ro" in option_set or "rw" not in option_set,
                available_bytes=available_bytes,
                writable=writable,
                transport=meta.get("transport") if isinstance(meta.get("transport"), str) else None,
                hotplug=bool(meta.get("hotplug")),
                removable=bool(meta.get("removable")),
            )
        )
    return result


def mounted_filesystem_for_path(path: Path) -> MountedFilesystem | None:
    document = _run_json(
        [
            "findmnt",
            "--json",
            "--bytes",
            "--target",
            str(path),
            "--output",
            "SOURCE,TARGET,FSTYPE,OPTIONS,UUID,LABEL,AVAIL,SIZE",
        ]
    )
    roots = document.get("filesystems")
    if not isinstance(roots, list):
        raise TelemetryStorageError("STORAGE_DISCOVERY_MALFORMED")
    values = _flatten_mounts(roots)
    if not values:
        return None
    value = max(values, key=lambda item: len(str(item.get("target") or "")))
    source = value.get("source")
    target = value.get("target")
    filesystem = value.get("fstype")
    filesystem_uuid = value.get("uuid")
    if not all(
        isinstance(item, str) and item
        for item in (source, target, filesystem, filesystem_uuid)
    ):
        return None
    option_set = set(str(value.get("options") or "").split(","))
    target_path = Path(target)
    available = value.get("avail")
    return MountedFilesystem(
        device=source,
        filesystem=filesystem,
        label=value.get("label") if isinstance(value.get("label"), str) else None,
        uuid=filesystem_uuid,
        mount_point=target,
        read_only="ro" in option_set or "rw" not in option_set,
        available_bytes=available if isinstance(available, int) and available >= 0 else 0,
        writable=(
            "rw" in option_set
            and "ro" not in option_set
            and target_path.is_dir()
            and os.access(target_path, os.W_OK | os.X_OK)
        ),
    )


def discover_storage_candidates() -> tuple[list[MountedFilesystem], MountedFilesystem | None]:
    filesystems = mounted_filesystems()
    candidates = [
        item
        for item in filesystems
        if item.mount_point != "/"
        and item.writable
        and not item.read_only
        and item.available_bytes >= MIN_DISCOVERY_FREE_BYTES
        and item.device.startswith("/dev/")
        and (item.hotplug or item.removable)
    ]
    selected = candidates[0] if len(candidates) == 1 else None
    return candidates, selected


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
            raise TelemetryStorageError("STORAGE_PATH_INSPECTION_FAILED") from exc
        if stat.S_ISLNK(info.st_mode):
            raise TelemetryStorageError("STORAGE_PATH_SYMLINK")


def verify_mount(
    root: Path,
    expected_uuid: str,
    *,
    minimum_free_bytes: int,
    filesystems: list[MountedFilesystem] | None = None,
) -> MountVerification:
    if not root.is_absolute() or root.name != "SmartRouterTelemetry":
        return MountVerification(False, "INVALID_EXTERNAL_ROOT")
    try:
        _reject_symlink_components(root)
    except TelemetryStorageError as exc:
        return MountVerification(False, exc.category)
    try:
        if filesystems is None:
            direct = mounted_filesystem_for_path(root)
            entries = [direct] if direct is not None else []
        else:
            entries = filesystems
    except TelemetryStorageError as exc:
        return MountVerification(False, exc.category)
    matches: list[MountedFilesystem] = []
    root_text = os.path.normpath(str(root))
    for item in entries:
        mount_text = os.path.normpath(item.mount_point)
        try:
            common = os.path.commonpath((root_text, mount_text))
        except ValueError:
            continue
        if common == mount_text:
            matches.append(item)
    if not matches:
        return MountVerification(False, "MOUNT_NOT_FOUND")
    filesystem = max(matches, key=lambda item: len(os.path.normpath(item.mount_point)))
    if filesystem.mount_point == "/":
        return MountVerification(False, "INTERNAL_FILESYSTEM_FALLBACK")
    if filesystem.uuid.casefold() != expected_uuid.casefold():
        return MountVerification(False, "FILESYSTEM_UUID_MISMATCH", filesystem)
    if filesystem.read_only or not filesystem.writable:
        return MountVerification(False, "FILESYSTEM_NOT_WRITABLE", filesystem)
    if filesystem.available_bytes < minimum_free_bytes:
        return MountVerification(False, "INSUFFICIENT_EXTERNAL_FREE_SPACE", filesystem)
    existing = root if root.exists() else root.parent
    if not existing.is_dir() or not os.access(existing, os.W_OK | os.X_OK):
        return MountVerification(False, "EXTERNAL_ROOT_NOT_WRITABLE", filesystem)
    try:
        if root.exists() and root.stat().st_uid != os.getuid():
            return MountVerification(False, "EXTERNAL_ROOT_WRONG_OWNER", filesystem)
        free = int(shutil.disk_usage(existing).free)
    except OSError:
        return MountVerification(False, "EXTERNAL_ROOT_INSPECTION_FAILED", filesystem)
    if free < minimum_free_bytes:
        return MountVerification(False, "INSUFFICIENT_EXTERNAL_FREE_SPACE", filesystem)
    return MountVerification(True, "VERIFIED", filesystem)
