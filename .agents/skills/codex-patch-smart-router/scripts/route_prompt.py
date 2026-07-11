#!/usr/bin/env python3
"""Return an advisory Smart Router decision for one prompt read from stdin."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable


SCHEMA_VERSION = "0.1.0"
SOURCE = "codex-patch-smart-router-core"
CONFIRMATION_RISKS = {"high", "critical"}
CONFIRMATION_ACTIONS = {
    "destructive_operation",
    "secret_touching_operation",
    "deployment_operation",
    "database_operation",
}


class AdapterConfigurationError(RuntimeError):
    """Raised when the repository or Router Core cannot be loaded safely."""


def _find_repository_root(script_path: Path) -> Path:
    start = script_path.resolve().parent
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "smart_codex"
        ).is_dir():
            return candidate
    raise AdapterConfigurationError


def _load_router() -> tuple[Callable[..., Any], type[Exception]]:
    repository_root = _find_repository_root(Path(__file__))
    root_text = str(repository_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    try:
        from smart_codex.knowledge import ConfigError
        from smart_codex.router import route_prompt
    except Exception:
        raise AdapterConfigurationError from None

    return route_prompt, ConfigError


def _warnings(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def _requires_confirmation(
    risk_level: str,
    action_danger: str,
    warnings: list[str],
) -> bool:
    return (
        risk_level in CONFIRMATION_RISKS
        or action_danger in CONFIRMATION_ACTIONS
        or any("REQUIRES_CONFIRMATION" in warning.upper() for warning in warnings)
    )


def _success_payload(decision: object, prompt: str) -> dict[str, object]:
    risk_level = str(getattr(decision, "risk_level"))
    action_danger = str(getattr(decision, "action_danger"))
    warnings = _warnings(getattr(decision, "warning"))
    prompt_hash = getattr(decision, "prompt_hash", None)
    if not isinstance(prompt_hash, str) or not prompt_hash:
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "source": SOURCE,
        "prompt_hash": prompt_hash,
        "category": str(getattr(decision, "category")),
        "risk_level": risk_level,
        "complexity_level": str(getattr(decision, "complexity_level")),
        "action_danger": action_danger,
        "recommended_profile": str(getattr(decision, "selected_profile")),
        "recommended_sandbox": str(getattr(decision, "sandbox_mode")),
        "recommended_approval": str(getattr(decision, "approval_policy")),
        "evidence_requirement": str(getattr(decision, "evidence_requirement")),
        "context_requirement": str(getattr(decision, "context_requirement")),
        "confidence": float(getattr(decision, "confidence")),
        "mixed_categories": [],
        "requires_confirmation": _requires_confirmation(
            risk_level,
            action_danger,
            warnings,
        ),
        "warnings": warnings,
    }


def _error_payload(
    status: str,
    error_code: str,
    message: str,
    *,
    requires_confirmation: bool,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "error_code": error_code,
        "message": message,
        "requires_confirmation": requires_confirmation,
    }


def _write(payload: dict[str, object], *, pretty: bool) -> None:
    if pretty:
        output = json.dumps(payload, indent=2, ensure_ascii=True)
    else:
        output = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    sys.stdout.write(output + "\n")


def _parse_options(argv: list[str]) -> bool:
    if argv.count("--stdin") != 1:
        raise ValueError
    if argv.count("--pretty") > 1:
        raise ValueError
    if any(argument not in {"--stdin", "--pretty"} for argument in argv):
        raise ValueError
    return "--pretty" in argv


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        pretty = _parse_options(arguments)
    except ValueError:
        _write(
            _error_payload(
                "input_error",
                "INVALID_ARGUMENTS",
                "Use --stdin to provide one prompt through standard input.",
                requires_confirmation=False,
            ),
            pretty=False,
        )
        return 2

    try:
        prompt = sys.stdin.read()
    except UnicodeError:
        _write(
            _error_payload(
                "input_error",
                "INVALID_UTF8",
                "The prompt must be valid UTF-8 text.",
                requires_confirmation=False,
            ),
            pretty=pretty,
        )
        return 2

    if not prompt.strip():
        _write(
            _error_payload(
                "input_error",
                "EMPTY_PROMPT",
                "No prompt was provided.",
                requires_confirmation=False,
            ),
            pretty=pretty,
        )
        return 2

    try:
        router, config_error = _load_router()
    except AdapterConfigurationError:
        _write(
            _error_payload(
                "config_error",
                "KNOWLEDGE_LIBRARY_ERROR",
                "The Smart Router Knowledge Library could not be loaded.",
                requires_confirmation=True,
            ),
            pretty=pretty,
        )
        return 2

    try:
        decision = router(prompt, dry_run=True)
    except Exception as error:
        if isinstance(error, (config_error, OSError, ValueError)):
            _write(
                _error_payload(
                    "config_error",
                    "KNOWLEDGE_LIBRARY_ERROR",
                    "The Smart Router Knowledge Library could not be loaded.",
                    requires_confirmation=True,
                ),
                pretty=pretty,
            )
            return 2
        _write(
            _error_payload(
                "internal_error",
                "ROUTER_INTERNAL_ERROR",
                "The Smart Router could not produce a decision.",
                requires_confirmation=True,
            ),
            pretty=pretty,
        )
        return 3

    try:
        payload = _success_payload(decision, prompt)
    except Exception:
        _write(
            _error_payload(
                "internal_error",
                "ROUTER_INTERNAL_ERROR",
                "The Smart Router could not produce a decision.",
                requires_confirmation=True,
            ),
            pretty=pretty,
        )
        return 3

    _write(payload, pretty=pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
