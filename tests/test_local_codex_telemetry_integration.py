from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time

import pytest

from smart_codex.app_server_router.protocol import decode_message, encode_message
from smart_codex.app_server_router.proxy import AppServerProxy
from smart_codex.app_server_router.websocket import WebSocketServer, connect_websocket
from smart_codex.runtime.telemetry.errors import TelemetryValidationError
from smart_codex.runtime.telemetry.models import seal_record
from smart_codex.runtime.telemetry.schema import RUN_RECORD_FIELDS, SOURCED_FIELDS
from smart_codex.runtime.telemetry.validator import validate_json_schema_document, validate_run_record

from app_server_test_helpers import turn_message, turn_router
from telemetry_test_helpers import enabled_service, records, start_basic


ROOT = Path(__file__).resolve().parents[1]


def test_app_server_proxy_collects_structured_metadata_without_changing_forwarded_turn(tmp_path) -> None:
    async def scenario() -> None:
        service, storage = enabled_service(tmp_path)
        forwarded = {}

        async def backend_handler(connection) -> None:
            raw = await connection.recv_text()
            message = decode_message(raw)
            forwarded.update(message)
            await connection.send_text(
                encode_message(
                    {
                        "id": message["id"],
                        "result": {
                            "turn": {"id": "turn-telemetry", "status": "inProgress"},
                            "model": message["params"]["model"],
                        },
                    }
                )
            )
            await connection.send_text(
                encode_message(
                    {
                        "method": "thread/tokenUsage/updated",
                        "params": {
                            "threadId": "thread-test",
                            "turnId": "turn-telemetry",
                            "tokenUsage": {
                                "last": {
                                    "inputTokens": 50,
                                    "cachedInputTokens": 10,
                                    "outputTokens": 20,
                                    "reasoningOutputTokens": 5,
                                    "totalTokens": 70,
                                },
                                "total": {
                                    "inputTokens": 50,
                                    "cachedInputTokens": 10,
                                    "outputTokens": 20,
                                    "reasoningOutputTokens": 5,
                                    "totalTokens": 70,
                                },
                                "modelContextWindow": 1000000,
                            },
                        },
                    }
                )
            )
            await connection.send_text(
                encode_message(
                    {
                        "method": "item/started",
                        "params": {
                            "threadId": "thread-test",
                            "turnId": "turn-telemetry",
                            "item": {"id": "tool-1", "type": "commandExecution"},
                        },
                    }
                )
            )
            await connection.send_text(
                encode_message(
                    {
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-test",
                            "turnId": "turn-telemetry",
                            "item": {"id": "tool-1", "type": "commandExecution"},
                        },
                    }
                )
            )
            await connection.send_text(
                encode_message(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-test",
                            "turn": {"id": "turn-telemetry", "status": "completed"},
                        },
                    }
                )
            )

        backend = WebSocketServer("127.0.0.1", 0, backend_handler)
        await backend.start()
        proxy = AppServerProxy(
            backend_url=f"ws://127.0.0.1:{backend.bound_port}",
            turn_router=turn_router(),
            telemetry=service,
        )
        await proxy.start()
        client = await connect_websocket(proxy.url)
        original = turn_message("Write a two-sentence email.", request_id=44)
        try:
            await client.send_text(encode_message(original))
            for _ in range(5):
                await client.recv_text()
            await asyncio.sleep(0)
        finally:
            await client.close()
            await proxy.close()
            await backend.close()
        stored = records(storage, "run")
        assert len(stored) == 1
        record = stored[0]
        assert record["input_tokens"] == 50
        assert record["visible_output_tokens"] == 15
        assert record["reasoning_tokens"] == 5
        assert record["tool_call_count"] == 1
        assert record["backend_model"] == forwarded["params"]["model"]
        assert record["operator_outcome"] is None
        assert "Write a two-sentence email." not in json.dumps(record)
        assert forwarded["params"]["input"] == original["params"]["input"]

    asyncio.run(scenario())


def test_slow_telemetry_start_does_not_block_app_server_forwarding(tmp_path, monkeypatch) -> None:
    async def scenario() -> None:
        service, storage = enabled_service(tmp_path)
        original_start = service.start_run

        def slow_start(**kwargs):
            time.sleep(0.2)
            return original_start(**kwargs)

        monkeypatch.setattr(service, "start_run", slow_start)
        received = asyncio.Event()

        async def backend_handler(connection) -> None:
            await connection.recv_text()
            received.set()

        backend = WebSocketServer("127.0.0.1", 0, backend_handler)
        await backend.start()
        proxy = AppServerProxy(
            backend_url=f"ws://127.0.0.1:{backend.bound_port}",
            turn_router=turn_router(),
            telemetry=service,
        )
        proxy._TELEMETRY_START_TIMEOUT_SECONDS = 0.01
        await proxy.start()
        client = await connect_websocket(proxy.url)
        try:
            await client.send_text(encode_message(turn_message("Synthetic fixture task.")))
            await asyncio.wait_for(received.wait(), timeout=0.15)
        finally:
            await client.close()
            await proxy.close()
            await backend.close()
        assert records(storage, "run") == []

    asyncio.run(scenario())


def test_schema_document_field_sets_match_runtime_contract() -> None:
    schema = json.loads((ROOT / "schemas" / "local_codex_run.schema.json").read_text(encoding="utf-8"))
    validate_json_schema_document(schema)
    assert set(schema["required"]) == RUN_RECORD_FIELDS
    assert set(schema["properties"]["measurement_sources"]["required"]) == SOURCED_FIELDS


def test_sanitized_example_is_a_valid_hash_linked_record() -> None:
    example = json.loads((ROOT / "examples" / "sanitized_telemetry_record.json").read_text(encoding="utf-8"))
    validate_run_record(example)


def test_validator_rejects_model_self_acceptance(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    assert start_basic(service).finish(status="completed").appended
    record = records(storage, "run")[0]
    record["operator_outcome"] = "accepted"
    record["operator_outcome_at"] = record["finished_at"]
    record = seal_record(record)
    with pytest.raises(TelemetryValidationError, match="SELF_ACCEPTANCE_FORBIDDEN"):
        validate_run_record(record)


def test_validator_enforces_maximum_record_size(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    assert start_basic(service).finish(status="completed").appended
    record = records(storage, "run")[0]
    record["tool_calls_by_type"] = {f"tool_{index:04d}_" + "x" * 100: 1 for index in range(1000)}
    record["tool_call_count"] = 1000
    record["measurement_sources"]["tool_call_count"] = "measured"
    record = seal_record(record)
    with pytest.raises(TelemetryValidationError, match="RECORD_TOO_LARGE"):
        validate_run_record(record)


def test_explicit_zero_retry_and_invalid_tool_counts_are_valid(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    run.consume_event({"type": "retry.count", "count": 0})
    run.consume_event({"type": "invalid_tool_call.count", "count": 0})
    assert run.finish(status="completed").appended
    record = records(storage, "run")[0]
    assert record["retry_count"] == 0
    assert record["invalid_tool_call_count"] == 0


def test_compaction_events_are_deduplicated(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    started = {
        "method": "item/started",
        "params": {
            "threadId": "thread-1",
            "turnId": "turn-1",
            "item": {"id": "compact-1", "type": "contextCompaction"},
        },
    }
    completed = {
        "method": "item/completed",
        "params": {
            "threadId": "thread-1",
            "turnId": "turn-1",
            "item": {"id": "compact-1", "type": "contextCompaction"},
        },
    }
    run.consume_event(started)
    run.consume_event(completed)
    run.consume_event(
        {
            "method": "thread/compacted",
            "params": {"threadId": "thread-1", "turnId": "turn-1"},
        }
    )
    assert run.finish(status="completed").appended
    assert records(storage, "run")[0]["compaction_count"] == 1
