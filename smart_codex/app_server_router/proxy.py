"""Transparent localhost JSON-RPC proxy with turn/start-only routing."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from .protocol import (
    EventSink,
    NullEventSink,
    ProtocolError,
    decode_message,
    encode_message,
    routing_error,
)
from .turn_router import RoutedTurn, RoutingFailure, TurnRouter
from .websocket import (
    WebSocketConnection,
    WebSocketError,
    WebSocketServer,
    connect_websocket,
)


@dataclass
class _SessionState:
    pending_threads: dict[object, str]
    pending_turns: dict[object, RoutedTurn]
    thread_models: dict[str, tuple[str | None, str | None]]


class AppServerProxy:
    def __init__(
        self,
        *,
        backend_url: str,
        turn_router: TurnRouter,
        host: str = "127.0.0.1",
        port: int = 0,
        events: EventSink | None = None,
    ):
        if host != "127.0.0.1":
            raise ValueError("Smart Router proxy must bind exactly to 127.0.0.1")
        self.backend_url = backend_url
        self.turn_router = turn_router
        self.events = events or NullEventSink()
        self.server = WebSocketServer(host, port, self._handle_client)

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.server.bound_port}"

    async def start(self) -> None:
        await self.server.start()

    async def close(self) -> None:
        await self.server.close()

    async def _handle_client(self, frontend: WebSocketConnection) -> None:
        try:
            backend = await connect_websocket(self.backend_url)
        except (OSError, WebSocketError):
            await frontend.close(code=1011, reason="backend unavailable")
            return
        state = _SessionState({}, {}, {})
        upstream = asyncio.create_task(self._client_to_backend(frontend, backend, state))
        downstream = asyncio.create_task(self._backend_to_client(backend, frontend, state))
        done, pending = await asyncio.wait(
            {upstream, downstream},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await asyncio.gather(*done, return_exceptions=True)
        await backend.close()

    async def _client_to_backend(
        self,
        frontend: WebSocketConnection,
        backend: WebSocketConnection,
        state: _SessionState,
    ) -> None:
        while True:
            raw = await frontend.recv_text()
            try:
                message = decode_message(raw)
            except ProtocolError:
                await backend.send_text(raw)
                continue
            method = message.get("method")
            if method == "turn/start":
                try:
                    routed = self.turn_router.route_message(message)
                except RoutingFailure:
                    await frontend.send_text(encode_message(routing_error(message.get("id"))))
                    self.events.emit(
                        {
                            "event": "route",
                            "status": "routing_error",
                            "request_id": message.get("id"),
                        }
                    )
                    continue
                request_id = message.get("id")
                state.pending_turns[request_id] = routed
                params = message.get("params")
                thread_id = params.get("threadId") if isinstance(params, dict) else None
                original_model = routed.original_model
                if original_model is None and isinstance(thread_id, str):
                    original_model = state.thread_models.get(thread_id, (None, None))[0]
                self.events.emit(
                    {
                        "event": "route",
                        "status": "forwarded",
                        "request_id": request_id,
                        "thread_id": thread_id,
                        "prompt_hash": routed.prompt_hash,
                        "category": routed.category,
                        "route_class": routed.route_class,
                        "original_model": original_model,
                        "selected_model": routed.selected_model,
                        "forwarded_model": routed.message["params"]["model"],
                        "effort": routed.effort,
                        "sandbox": routed.sandbox_mode,
                        "approval": routed.approval_policy,
                    }
                )
                await backend.send_text(encode_message(routed.message))
                continue
            if method in {"thread/start", "thread/resume"}:
                request_id = message.get("id")
                if isinstance(request_id, (str, int)) and not isinstance(request_id, bool):
                    state.pending_threads[request_id] = str(method)
            await backend.send_text(raw)

    async def _backend_to_client(
        self,
        backend: WebSocketConnection,
        frontend: WebSocketConnection,
        state: _SessionState,
    ) -> None:
        while True:
            raw = await backend.recv_text()
            await frontend.send_text(raw)
            try:
                message = decode_message(raw)
            except ProtocolError:
                continue
            self._observe_backend(message, state)

    def _observe_backend(self, message: dict[str, Any], state: _SessionState) -> None:
        response_id = message.get("id")
        valid_id = isinstance(response_id, (str, int)) and not isinstance(response_id, bool)
        if valid_id and response_id in state.pending_threads:
            state.pending_threads.pop(response_id, None)
            result = message.get("result")
            if isinstance(result, dict):
                thread = result.get("thread")
                thread_id = thread.get("id") if isinstance(thread, dict) else None
                model = result.get("model") if isinstance(result.get("model"), str) else None
                effort = result.get("reasoningEffort") if isinstance(result.get("reasoningEffort"), str) else None
                if isinstance(thread_id, str):
                    state.thread_models[thread_id] = (model, effort)
                    self.events.emit(
                        {
                            "event": "thread",
                            "status": "initialized",
                            "request_id": response_id,
                            "thread_id": thread_id,
                            "original_model": model,
                            "effort": effort,
                        }
                    )
        routed = state.pending_turns.pop(response_id, None) if valid_id else None
        if routed is not None:
            error = message.get("error")
            error_code = error.get("code") if isinstance(error, dict) else None
            self.events.emit(
                {
                    "event": "route",
                    "status": "backend_error" if error is not None else "accepted",
                    "request_id": response_id,
                    "prompt_hash": routed.prompt_hash,
                    "category": routed.category,
                    "selected_model": routed.selected_model,
                    "forwarded_model": routed.selected_model,
                    "effort": routed.effort,
                    "error_code": error_code,
                }
            )

        method = message.get("method")
        params = message.get("params")
        if method == "thread/settings/updated" and isinstance(params, dict):
            settings = params.get("threadSettings")
            if isinstance(settings, dict):
                thread_id = params.get("threadId")
                model = settings.get("model")
                effort = settings.get("effort")
                if isinstance(thread_id, str) and isinstance(model, str):
                    state.thread_models[thread_id] = (
                        model,
                        effort if isinstance(effort, str) else None,
                    )
                    self.events.emit(
                        {
                            "event": "active_settings",
                            "status": "observed",
                            "thread_id": thread_id,
                            "active_model": model,
                            "active_effort": effort,
                        }
                    )
        elif method == "model/rerouted" and isinstance(params, dict):
            to_model = params.get("toModel")
            if isinstance(to_model, str):
                self.events.emit(
                    {
                        "event": "model_rerouted",
                        "status": "observed",
                        "thread_id": params.get("threadId"),
                        "active_model": to_model,
                    }
                )
