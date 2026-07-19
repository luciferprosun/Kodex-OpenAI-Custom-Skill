"""Privacy-safe shadow decisions that can never mutate the live route."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterator
import uuid

from smart_codex.runtime.telemetry.errors import TelemetryStorageError
from smart_codex.runtime.telemetry.models import canonical_json, compute_record_hash, utc_now
from smart_codex.runtime.telemetry.privacy import scan_record
from smart_codex.runtime.telemetry.storage import _write_all

from .dataset import _config, dataset_status
from .learner import ALGORITHM_VERSION, stratum_key


SHADOW_EVENT_VERSION = "1.0.0"


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _candidate_for(stratum_id: str) -> tuple[str | None, dict[str, Any] | None]:
    config = _config()
    directory = config.telemetry_root / "policy-candidates"
    for path in sorted(directory.glob("candidate-*.json"), reverse=True):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(value, dict) or value.get("authority") is not False:
            continue
        for item in value.get("affected_strata", []):
            if isinstance(item, dict) and item.get("stratum_id") == stratum_id:
                return value.get("candidate_id"), item
    return None, None


class ShadowRecorder:
    def record(self, run_shell: dict[str, Any]) -> dict[str, Any]:
        config = _config()
        stratum_id = stratum_key(run_shell)
        status = dataset_status()
        manifest = status.get("manifest") if isinstance(status, dict) else None
        candidate_id, item = _candidate_for(stratum_id) if isinstance(manifest, dict) else (None, None)
        if item is None:
            decision = (
                "INSUFFICIENT_DATA"
                if not isinstance(manifest, dict) or int(manifest.get("labeled_run_count", 0)) < 30
                else "NO_COMPARABLE_ALTERNATIVE"
            )
            candidate_model = None
            candidate_effort = None
            evidence_count = 0
        else:
            decision = "CANDIDATE_AVAILABLE"
            candidate = item.get("shadow_candidate", {})
            candidate_model = candidate.get("model") if isinstance(candidate, dict) else None
            candidate_effort = candidate.get("reasoning_effort") if isinstance(candidate, dict) else None
            metrics = candidate.get("metrics", {}) if isinstance(candidate, dict) else {}
            evidence_count = int(metrics.get("labeled_runs", 0)) if isinstance(metrics, dict) else 0
        context = {
            "run_id": run_shell.get("run_id"),
            "router_decision_id": run_shell.get("router_decision_id"),
            "stratum_id": stratum_id,
            "incumbent_model": run_shell.get("recommended_model"),
            "incumbent_effort": run_shell.get("reasoning_effort"),
        }
        event: dict[str, Any] = {
            "event_version": SHADOW_EVENT_VERSION,
            "record_type": "shadow_decision",
            "event_id": str(uuid.uuid4()),
            "recorded_at": utc_now(),
            "run_id": run_shell.get("run_id"),
            "router_decision_id": run_shell.get("router_decision_id"),
            "run_context_hash": hashlib.sha256(canonical_json(context).encode("utf-8")).hexdigest(),
            "stratum_id": stratum_id,
            "algorithm_version": ALGORITHM_VERSION,
            "dataset_manifest_hash": manifest.get("manifest_hash") if isinstance(manifest, dict) else None,
            "incumbent_model": run_shell.get("recommended_model"),
            "incumbent_effort": run_shell.get("reasoning_effort"),
            "shadow_candidate_model": candidate_model,
            "shadow_candidate_effort": candidate_effort,
            "candidate_id": candidate_id,
            "evidence_count": evidence_count,
            "decision": decision,
            "applied": False,
            "authority": False,
            "privacy_classification": "metadata_only_hmac",
            "record_hash": "",
        }
        event["record_hash"] = compute_record_hash(event)
        scan_record(event)
        payload = canonical_json(event).encode("utf-8") + b"\n"
        if len(payload) > 64 * 1024:
            raise TelemetryStorageError("SHADOW_EVENT_TOO_LARGE")
        directory = config.telemetry_root / "runtime-events"
        if directory.is_symlink() or not directory.is_dir():
            raise TelemetryStorageError("RUNTIME_EVENTS_DIRECTORY_UNSAFE")
        target = directory / "shadow-decisions.jsonl"
        lock_path = directory / ".shadow.lock"
        with _lock(lock_path):
            if target.exists() and (target.is_symlink() or not target.is_file()):
                raise TelemetryStorageError("SHADOW_TARGET_UNSAFE")
            if target.exists() and target.stat().st_size:
                with target.open("rb") as handle:
                    handle.seek(-1, os.SEEK_END)
                    if handle.read(1) != b"\n":
                        raise TelemetryStorageError("SHADOW_TRAILING_FRAGMENT")
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(target, flags, 0o600)
            try:
                _write_all(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return event
