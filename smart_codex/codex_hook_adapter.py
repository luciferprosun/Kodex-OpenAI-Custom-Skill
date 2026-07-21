"""Privacy-preserving Codex lifecycle adapters for the Smart Router.

The executable routing policy remains in ``smart_codex.router`` and the root
Knowledge Library. This module only validates hook payloads, translates tool
input into one in-memory routing string, and emits documented hook responses.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any

from .knowledge import (
    ALLOWED_ACTION_DANGERS,
    ALLOWED_APPROVAL_POLICY,
    ALLOWED_V0_SANDBOX,
)
from .profiles import AVAILABLE_PROFILES
from .router import SAFETY_ACTION_DANGERS, route_prompt


SCHEMA_VERSION = "0.1.0"
PERMISSION_MODES = {
    "default",
    "acceptEdits",
    "plan",
    "dontAsk",
    "bypassPermissions",
}
COMMAND_TOOL_NAMES = {"Bash", "apply_patch", "Edit", "Write"}
RISK_LEVELS = {"low", "medium", "high", "critical"}
COMPLEXITY_LEVELS = {"low", "medium", "high"}
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

USER_PROMPT_FAILURE = {
    "decision": "block",
    "reason": "SMART_ROUTER_FAIL_CLOSED: the prompt could not be classified safely.",
}
PRE_TOOL_FAILURE = {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            "SMART_ROUTER_DENY: the proposed action is blocked by the central "
            "safety policy."
        ),
    }
}
PERMISSION_FAILURE = {
    "hookSpecificOutput": {
        "hookEventName": "PermissionRequest",
        "decision": {
            "behavior": "deny",
            "message": (
                "SMART_ROUTER_DENY: this permission request is high or critical risk."
            ),
        },
    }
}


class HookPayloadError(ValueError):
    """Raised internally when a hook payload cannot be classified safely."""


@dataclass(frozen=True)
class NormalizedDecision:
    category: str
    risk: str
    complexity: str
    action_danger: str
    profile: str
    sandbox: str
    approval: str
    evidence: str
    context: str
    confidence: float
    requires_confirmation: bool


def _static_copy(value: dict[str, Any]) -> dict[str, Any]:
    """Return a detached copy of a static JSON response."""
    return json.loads(json.dumps(value))


def _require_nonempty_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise HookPayloadError
    return value


def _validate_common(payload: object, expected_event: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HookPayloadError

    if payload.get("hook_event_name") != expected_event:
        raise HookPayloadError

    for field in ("session_id", "cwd", "model", "turn_id"):
        _require_nonempty_string(payload, field)

    permission_mode = _require_nonempty_string(payload, "permission_mode")
    if permission_mode not in PERMISSION_MODES:
        raise HookPayloadError

    transcript_path = payload.get("transcript_path")
    if transcript_path is not None and not isinstance(transcript_path, str):
        raise HookPayloadError

    return payload


def _safe_token(value: object) -> str:
    if not isinstance(value, str) or SAFE_TOKEN.fullmatch(value) is None:
        raise HookPayloadError
    return value


def _normalize_decision(decision: object) -> NormalizedDecision:
    category = _safe_token(getattr(decision, "category", None))
    risk = _safe_token(getattr(decision, "risk_level", None))
    complexity = _safe_token(getattr(decision, "complexity_level", None))
    action_danger = _safe_token(getattr(decision, "action_danger", None))
    profile = _safe_token(getattr(decision, "selected_profile", None))
    sandbox = _safe_token(getattr(decision, "sandbox_mode", None))
    approval = _safe_token(getattr(decision, "approval_policy", None))
    evidence = _safe_token(getattr(decision, "evidence_requirement", None))
    context = _safe_token(getattr(decision, "context_requirement", None))
    confidence = getattr(decision, "confidence", None)

    if risk not in RISK_LEVELS or complexity not in COMPLEXITY_LEVELS:
        raise HookPayloadError
    if action_danger not in ALLOWED_ACTION_DANGERS:
        raise HookPayloadError
    if profile not in AVAILABLE_PROFILES:
        raise HookPayloadError
    if sandbox not in ALLOWED_V0_SANDBOX:
        raise HookPayloadError
    if approval not in ALLOWED_APPROVAL_POLICY:
        raise HookPayloadError
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(float(confidence))
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise HookPayloadError

    requires_confirmation = (
        risk in {"high", "critical"} or action_danger in SAFETY_ACTION_DANGERS
    )
    return NormalizedDecision(
        category=category,
        risk=risk,
        complexity=complexity,
        action_danger=action_danger,
        profile=profile,
        sandbox=sandbox,
        approval=approval,
        evidence=evidence,
        context=context,
        confidence=float(confidence),
        requires_confirmation=requires_confirmation,
    )


def _additional_context(decision: NormalizedDecision) -> str:
    confirmation = "true" if decision.requires_confirmation else "false"
    context = (
        f"SMART_ROUTER_DECISION schema={SCHEMA_VERSION} "
        f"category={decision.category} risk={decision.risk} "
        f"complexity={decision.complexity} "
        f"action_danger={decision.action_danger} "
        f"recommended_profile={decision.profile} "
        f"recommended_sandbox={decision.sandbox} "
        f"recommended_approval={decision.approval} "
        f"evidence_requirement={decision.evidence} "
        f"context_requirement={decision.context} "
        f"confidence={decision.confidence:.3f} "
        f"requires_confirmation={confirmation}. "
        "Recommendations are advisory and have not been applied."
    )
    if decision.risk in {"high", "critical"} and (
        decision.action_danger == "read_only_analysis"
    ):
        context += (
            " Analysis-only warning: no operation has been executed; do not execute "
            "side-effecting operations without explicit human approval. PreToolUse "
            "and PermissionRequest policies remain active."
        )
    return context


def classify_user_prompt(payload: object) -> tuple[str, object, NormalizedDecision]:
    """Return one validated prompt classification for hook consumers.

    The raw prompt is returned only to the in-process caller. Persistence and
    hook output remain the responsibility of the privacy-bounded consumers.
    """

    data = _validate_common(payload, "UserPromptSubmit")
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise HookPayloadError
    decision = route_prompt(prompt, dry_run=True)
    return prompt, decision, _normalize_decision(decision)


def render_user_prompt_context(decision: NormalizedDecision) -> dict[str, Any]:
    """Render the existing advisory hook response from a normalized decision."""

    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": _additional_context(decision),
        }
    }


def _tool_action(payload: dict[str, Any], *, require_tool_use_id: bool) -> str:
    tool_name = _require_nonempty_string(payload, "tool_name")
    if require_tool_use_id:
        _require_nonempty_string(payload, "tool_use_id")

    tool_input = payload.get("tool_input")
    if tool_name in COMMAND_TOOL_NAMES:
        if not isinstance(tool_input, dict):
            raise HookPayloadError
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            raise HookPayloadError
        return command

    if not tool_name.startswith("mcp__") or not isinstance(tool_input, dict):
        raise HookPayloadError

    try:
        arguments = json.dumps(
            tool_input,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        raise HookPayloadError from None
    return f"MCP tool {tool_name} arguments {arguments}"


def _must_deny(decision: NormalizedDecision) -> bool:
    if decision.risk == "critical":
        return True
    if decision.action_danger in SAFETY_ACTION_DANGERS:
        return True
    return decision.risk == "high" and decision.action_danger != "read_only_analysis"


def handle_user_prompt_submit(payload: object) -> dict[str, Any]:
    """Classify one full prompt and return sanitized developer context."""
    try:
        _, _, decision = classify_user_prompt(payload)
        return render_user_prompt_context(decision)
    except Exception:
        return _static_copy(USER_PROMPT_FAILURE)


def handle_pre_tool_use(payload: object) -> dict[str, Any]:
    """Deny centrally classified unsafe supported tool calls; never auto-allow."""
    try:
        data = _validate_common(payload, "PreToolUse")
        action = _tool_action(data, require_tool_use_id=True)
        decision = _normalize_decision(route_prompt(action, dry_run=True))
        if _must_deny(decision):
            return _static_copy(PRE_TOOL_FAILURE)
        return {}
    except Exception:
        return _static_copy(PRE_TOOL_FAILURE)


def handle_permission_request(payload: object) -> dict[str, Any]:
    """Deny unsafe approvals or defer to the human; never auto-allow."""
    try:
        data = _validate_common(payload, "PermissionRequest")
        action = _tool_action(data, require_tool_use_id=False)
        decision = _normalize_decision(route_prompt(action, dry_run=True))
        if _must_deny(decision):
            return _static_copy(PERMISSION_FAILURE)
        return {}
    except Exception:
        return _static_copy(PERMISSION_FAILURE)
