from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path

from .config import LOG_FILE
from .router import RoutingDecision


def decision_to_log_entry(decision: RoutingDecision) -> dict[str, object]:
    data = asdict(decision)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_hash": data["prompt_hash"],
        "prompt_redacted": None,
        "category": data["category"],
        "complexity": data["complexity"],
        "risk": data["risk"],
        "selected_profile": data["selected_profile"],
        "selected_model": data["selected_model"],
        "reasoning_effort": data["reasoning_effort"],
        "sandbox_mode": data["sandbox_mode"],
        "approval_policy": data["approval_policy"],
        "confidence": data["confidence"],
        "decision_reasons": data["decision_reasons"],
        "override_used": data["override_used"],
        "dry_run": data["dry_run"],
        "warning": data["warning"],
    }


def write_decision_log(
    decision: RoutingDecision,
    *,
    log_path: Path = LOG_FILE,
    enabled: bool = True,
) -> bool:
    if not enabled:
        return False

    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = decision_to_log_entry(decision)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return True

