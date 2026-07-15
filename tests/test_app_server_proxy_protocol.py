from __future__ import annotations

import asyncio
import copy
import json

from smart_codex.app_server_router.protocol import (
    MemoryEventSink,
    ROUTING_ERROR_CODE,
    decode_message,
    encode_message,
)
from smart_codex.app_server_router.proxy import AppServerProxy
from smart_codex.app_server_router.websocket import (
    WebSocketClosed,
    WebSocketServer,
    connect_websocket,
)

from app_server_test_helpers import turn_message, turn_router


def test_initialize_notifications_errors_and_ids_are_transparent() -> None:
    async def scenario() -> None:
        received: list[str] = []
        initialized_notice = '{"method":"fake/initialized","params":{"sequence":1}}'
        preserved_error = '{"id":"error-request","error":{"code":-32601,"message":"missing"}}'

        async def backend_handler(connection) -> None:
            while True:
                raw = await connection.recv_text()
                received.append(raw)
                message = decode_message(raw)
                if message.get("method") == "initialize":
                    await connection.send_text(
                        encode_message(
                            {
                                "id": message["id"],
                                "result": {
                                    "userAgent": "fake/0.144.4",
                                    "codexHome": "/tmp/fake",
                                    "platformFamily": "unix",
                                    "platformOs": "linux",
                                },
                            }
                        )
                    )
                elif message.get("method") == "initialized":
                    await connection.send_text(initialized_notice)
                elif message.get("method") == "fake/error":
                    await connection.send_text(preserved_error)
                elif message.get("method") == "thread/start":
                    await connection.send_text(
                        encode_message(
                            {
                                "id": message["id"],
                                "result": {
                                    "thread": {"id": "thread-transparent"},
                                    "model": "gpt-5.6-sol",
                                    "reasoningEffort": "max",
                                },
                            }
                        )
                    )
                elif message.get("method") == "turn/steer":
                    await connection.send_text(
                        encode_message({"id": message["id"], "result": {"turnId": "turn-1"}})
                    )

        backend = WebSocketServer("127.0.0.1", 0, backend_handler)
        await backend.start()
        proxy = AppServerProxy(
            backend_url=f"ws://127.0.0.1:{backend.bound_port}",
            turn_router=turn_router(),
        )
        await proxy.start()
        client = await connect_websocket(proxy.url)
        try:
            initialize_raw = json.dumps(
                {
                    "method": "initialize",
                    "id": "init-preserved",
                    "params": {
                        "clientInfo": {"name": "test", "title": "Test", "version": "1"},
                        "capabilities": None,
                    },
                },
                indent=2,
            )
            await client.send_text(initialize_raw)
            initialize_response = decode_message(await client.recv_text())
            assert initialize_response["id"] == "init-preserved"
            assert received[0] == initialize_raw

            initialized_raw = '{"method":"initialized"}'
            await client.send_text(initialized_raw)
            assert await client.recv_text() == initialized_notice
            assert received[1] == initialized_raw

            error_request = '{"method":"fake/error","id":"error-request","params":{}}'
            await client.send_text(error_request)
            assert await client.recv_text() == preserved_error
            assert received[2] == error_request

            thread_raw = '{"method":"thread/start","id":73,"params":{"model":"gpt-5.6-sol"}}'
            await client.send_text(thread_raw)
            thread_response = decode_message(await client.recv_text())
            assert thread_response["id"] == 73
            assert received[3] == thread_raw

            steer_raw = (
                '{"method":"turn/steer","id":74,"params":{"threadId":"thread-transparent",'
                '"input":[{"type":"text","text":"keep exact","text_elements":[]}],'
                '"expectedTurnId":"turn-1"}}'
            )
            await client.send_text(steer_raw)
            steer_response = decode_message(await client.recv_text())
            assert steer_response["id"] == 74
            assert received[4] == steer_raw
        finally:
            await client.close()
            await proxy.close()
            await backend.close()

    asyncio.run(scenario())


def test_turn_modification_stream_order_and_approval_round_trip() -> None:
    async def scenario() -> None:
        received: list[str] = []
        approval_received = asyncio.Event()
        events = MemoryEventSink()
        approval_request = (
            '{"method":"item/commandExecution/requestApproval","id":"approval-1",'
            '"params":{"threadId":"thread-test","turnId":"turn-1","itemId":"item-1",'
            '"reason":"test approval","command":["true"],"cwd":"/tmp"}}'
        )
        notifications = [
            '{"method":"turn/started","params":{"threadId":"thread-test","turn":{"id":"turn-1"}}}',
            '{"method":"item/started","params":{"threadId":"thread-test","turnId":"turn-1","item":{"id":"item-1"}}}',
        ]
        completed = (
            '{"method":"turn/completed","params":{"threadId":"thread-test",'
            '"turn":{"id":"turn-1","status":"completed"}}}'
        )

        async def backend_handler(connection) -> None:
            while True:
                raw = await connection.recv_text()
                received.append(raw)
                message = decode_message(raw)
                if message.get("method") == "turn/start":
                    await connection.send_text(
                        encode_message(
                            {
                                "id": message["id"],
                                "result": {"turn": {"id": "turn-1", "status": "inProgress"}},
                            }
                        )
                    )
                    for notification in notifications:
                        await connection.send_text(notification)
                    await connection.send_text(
                        encode_message(
                            {
                                "method": "thread/settings/updated",
                                "params": {
                                    "threadId": "thread-test",
                                    "threadSettings": {
                                        "model": message["params"]["model"],
                                        "effort": message["params"]["effort"],
                                    },
                                },
                            }
                        )
                    )
                    await connection.send_text(approval_request)
                elif message.get("id") == "approval-1":
                    approval_received.set()
                    await connection.send_text(completed)
                    return

        backend = WebSocketServer("127.0.0.1", 0, backend_handler)
        await backend.start()
        proxy = AppServerProxy(
            backend_url=f"ws://127.0.0.1:{backend.bound_port}",
            turn_router=turn_router(),
            events=events,
        )
        await proxy.start()
        client = await connect_websocket(proxy.url)
        original = turn_message("Write a two-sentence email.", request_id=91)
        original["params"]["collaborationMode"] = {
            "mode": "default",
            "settings": {
                "model": "gpt-5.6-sol",
                "reasoning_effort": "max",
                "developer_instructions": None,
            },
        }
        before = copy.deepcopy(original)
        try:
            await client.send_text(encode_message(original))
            response = decode_message(await client.recv_text())
            assert response["id"] == 91
            assert [await client.recv_text(), await client.recv_text()] == notifications
            active_settings = decode_message(await client.recv_text())
            assert active_settings["method"] == "thread/settings/updated"
            assert await client.recv_text() == approval_request
            assert approval_received.is_set() is False

            approval_response = (
                '{"id":"approval-1","result":{"decision":"acceptForSession"}}'
            )
            await client.send_text(approval_response)
            assert await client.recv_text() == completed
            await asyncio.wait_for(approval_received.wait(), timeout=1)

            forwarded = decode_message(received[0])
            assert original == before
            assert forwarded["id"] == before["id"]
            assert forwarded["params"]["input"] == before["params"]["input"]
            assert forwarded["params"]["cwd"] == before["params"]["cwd"]
            assert forwarded["params"]["outputSchema"] == before["params"]["outputSchema"]
            assert forwarded["params"]["model"] == "gpt-5.6-luna"
            assert forwarded["params"]["effort"] == "low"
            assert forwarded["params"]["collaborationMode"] == {
                "mode": "default",
                "settings": {
                    "model": "gpt-5.6-luna",
                    "reasoning_effort": "low",
                    "developer_instructions": None,
                },
            }
            assert forwarded["params"]["sandboxPolicy"]["type"] == "readOnly"
            assert forwarded["params"]["approvalPolicy"] == "on-request"
            assert forwarded["params"]["approvalsReviewer"] == "user"
            assert received[1] == approval_response

            route_events = [event for event in events.events if event.get("event") == "route"]
            assert [event["status"] for event in route_events] == ["forwarded", "accepted"]
            assert route_events[0]["original_model"] == "gpt-5.6-sol"
            assert route_events[0]["forwarded_model"] == "gpt-5.6-luna"
            active = [event for event in events.events if event.get("event") == "active_settings"]
            assert active[0]["active_model"] == "gpt-5.6-luna"
            assert active[0]["active_effort"] == "low"
        finally:
            await client.close()
            await proxy.close()
            await backend.close()

    asyncio.run(scenario())


def test_auth_refresh_frames_transit_byte_for_byte_without_router_events() -> None:
    async def scenario() -> None:
        events = MemoryEventSink()
        received: list[str] = []
        refresh_request = (
            '{"method":"account/chatgptAuthTokens/refresh","id":"auth-refresh-1",'
            '"params":{"reason":"test"}}'
        )
        refresh_response = (
            '{"id":"auth-refresh-1","result":{"accessToken":"fake-access-value",'
            '"idToken":"fake-id-value"}}'
        )
        acknowledgement = '{"method":"fake/authRefreshAccepted","params":{}}'

        async def backend_handler(connection) -> None:
            await connection.send_text(refresh_request)
            received.append(await connection.recv_text())
            await connection.send_text(acknowledgement)

        backend = WebSocketServer("127.0.0.1", 0, backend_handler)
        await backend.start()
        proxy = AppServerProxy(
            backend_url=f"ws://127.0.0.1:{backend.bound_port}",
            turn_router=turn_router(),
            events=events,
        )
        await proxy.start()
        client = await connect_websocket(proxy.url)
        try:
            assert await client.recv_text() == refresh_request
            await client.send_text(refresh_response)
            assert await client.recv_text() == acknowledgement
            assert received == [refresh_response]
            assert events.events == []
        finally:
            await client.close()
            await proxy.close()
            await backend.close()

    asyncio.run(scenario())


def test_routing_failure_returns_sanitized_error_and_does_not_forward() -> None:
    async def scenario() -> None:
        received: list[str] = []
        events = MemoryEventSink()

        async def backend_handler(connection) -> None:
            try:
                received.append(await connection.recv_text())
            except WebSocketClosed:
                return

        backend = WebSocketServer("127.0.0.1", 0, backend_handler)
        await backend.start()
        proxy = AppServerProxy(
            backend_url=f"ws://127.0.0.1:{backend.bound_port}",
            turn_router=turn_router(),
            events=events,
        )
        await proxy.start()
        client = await connect_websocket(proxy.url)
        try:
            malformed = {
                "method": "turn/start",
                "id": "bad-turn",
                "params": {
                    "threadId": "thread-test",
                    "input": [{"type": "image", "url": "https://example.invalid/x.png"}],
                },
            }
            await client.send_text(encode_message(malformed))
            response = decode_message(await client.recv_text())
            assert response["id"] == "bad-turn"
            assert response["error"]["code"] == ROUTING_ERROR_CODE
            assert "ordinary Codex" in response["error"]["message"]
            await asyncio.sleep(0.05)
            assert received == []
            assert events.events[0]["status"] == "routing_error"
        finally:
            await client.close()
            await proxy.close()
            await backend.close()

    asyncio.run(scenario())
