"""Non-authoritative router and telemetry gates for ``codex-smart`` sessions."""
from __future__ import annotations

from typing import Any, Mapping

from .codex_hook_adapter import (
    classify_user_prompt,
    handle_permission_request,
    handle_pre_tool_use,
    handle_user_prompt_submit,
    render_user_prompt_context,
)
from .runtime.telemetry.hook_capture import (
    CodexHookTelemetryCapture,
    HookCaptureResult,
)
from .session_control import (
    SessionControlError,
    SessionControlStore,
    StateSnapshot,
    wrapper_mode_active,
)


def _integration_snapshot(
    *,
    store: SessionControlStore | None = None,
    environ: Mapping[str, str] | None = None,
) -> StateSnapshot | None:
    if not wrapper_mode_active(environ):
        return None
    try:
        snapshot = (SessionControlStore() if store is None else store).read()
    except (OSError, SessionControlError):
        return None
    return snapshot if snapshot.status == "valid" else None


def _router_gate_open(
    *,
    store: SessionControlStore | None = None,
    environ: Mapping[str, str] | None = None,
) -> bool:
    snapshot = _integration_snapshot(store=store, environ=environ)
    return snapshot is not None and snapshot.state.router_enabled is True


def _capture_bridge(
    store: SessionControlStore | None,
    telemetry: CodexHookTelemetryCapture | None,
) -> CodexHookTelemetryCapture:
    if telemetry is not None:
        return telemetry
    return CodexHookTelemetryCapture(SessionControlStore() if store is None else store)


def _with_telemetry_warning(
    response: dict[str, Any],
    result: HookCaptureResult,
) -> dict[str, Any]:
    warning = result.warning
    if not isinstance(warning, str) or not warning:
        return response
    enriched = dict(response)
    enriched["systemMessage"] = f"SMART_CODEX_TELEMETRY_DEGRADED:{warning}"
    return enriched


def route_user_prompt_submit(
    payload: object,
    *,
    store: SessionControlStore | None = None,
    environ: Mapping[str, str] | None = None,
    telemetry: CodexHookTelemetryCapture | None = None,
) -> dict[str, Any]:
    snapshot = _integration_snapshot(store=store, environ=environ)
    if snapshot is None:
        return {}
    router_enabled = snapshot.state.router_enabled is True
    telemetry_enabled = snapshot.state.research_telemetry_enabled is True
    if not router_enabled and not telemetry_enabled:
        return {}
    try:
        prompt, decision, normalized = classify_user_prompt(payload)
    except Exception:
        response = handle_user_prompt_submit(payload) if router_enabled else {}
        if telemetry_enabled:
            return _with_telemetry_warning(
                response,
                HookCaptureResult(warning="TELEMETRY_CLASSIFICATION_FAILED"),
            )
        return response
    response = render_user_prompt_context(normalized) if router_enabled else {}
    if not telemetry_enabled:
        return response
    try:
        result = _capture_bridge(store, telemetry).start_prompt(
            payload,
            task=prompt,
            decision=decision,
        )
    except Exception:
        result = HookCaptureResult(warning="TELEMETRY_OBSERVER_ERROR")
    return _with_telemetry_warning(response, result)


def route_pre_tool_use(
    payload: object,
    *,
    store: SessionControlStore | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not _router_gate_open(store=store, environ=environ):
        return {}
    return handle_pre_tool_use(payload)


def route_permission_request(
    payload: object,
    *,
    store: SessionControlStore | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not _router_gate_open(store=store, environ=environ):
        return {}
    return handle_permission_request(payload)


def route_post_tool_use(
    payload: object,
    *,
    store: SessionControlStore | None = None,
    environ: Mapping[str, str] | None = None,
    telemetry: CodexHookTelemetryCapture | None = None,
) -> dict[str, Any]:
    snapshot = _integration_snapshot(store=store, environ=environ)
    if snapshot is None or snapshot.state.research_telemetry_enabled is not True:
        return {}
    try:
        result = _capture_bridge(store, telemetry).observe_tool(payload)
    except Exception:
        result = HookCaptureResult(warning="TELEMETRY_OBSERVER_ERROR")
    return _with_telemetry_warning({}, result)


def route_stop(
    payload: object,
    *,
    store: SessionControlStore | None = None,
    environ: Mapping[str, str] | None = None,
    telemetry: CodexHookTelemetryCapture | None = None,
) -> dict[str, Any]:
    snapshot = _integration_snapshot(store=store, environ=environ)
    if snapshot is None or snapshot.state.research_telemetry_enabled is not True:
        return {}
    try:
        result = _capture_bridge(store, telemetry).finish_turn(payload)
    except Exception:
        result = HookCaptureResult(warning="TELEMETRY_OBSERVER_ERROR")
    return _with_telemetry_warning({}, result)
