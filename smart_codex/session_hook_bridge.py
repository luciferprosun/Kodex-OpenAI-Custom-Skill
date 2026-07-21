"""Non-authoritative hook gate for ``codex-smart`` sessions."""
from __future__ import annotations

from typing import Any, Mapping

from .codex_hook_adapter import (
    handle_permission_request,
    handle_pre_tool_use,
    handle_user_prompt_submit,
)
from .session_control import SessionControlError, SessionControlStore, wrapper_mode_active


def _router_gate_open(
    *,
    store: SessionControlStore | None = None,
    environ: Mapping[str, str] | None = None,
) -> bool:
    if not wrapper_mode_active(environ):
        return False
    try:
        snapshot = (SessionControlStore() if store is None else store).read()
    except (OSError, SessionControlError):
        return False
    return snapshot.state.router_enabled is True


def route_user_prompt_submit(
    payload: object,
    *,
    store: SessionControlStore | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not _router_gate_open(store=store, environ=environ):
        return {}
    return handle_user_prompt_submit(payload)


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
