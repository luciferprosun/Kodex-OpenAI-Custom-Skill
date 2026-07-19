from __future__ import annotations

import pytest

from smart_codex.runtime.telemetry.codex_events import CodexEventAccumulator

from telemetry_test_helpers import (
    app_usage_event,
    enabled_service,
    exec_usage_event,
    records,
    start_basic,
)


def _digest(namespace: str, identifier: str) -> str:
    return (namespace + identifier).encode("utf-8").hex()[:64].ljust(64, "0")


def test_valid_run_record_with_codex_exec_usage(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    assert run.consume_event(exec_usage_event(total_tokens=130)) is True
    result = run.finish(status="completed", process_exit_code=0)

    assert result.appended is True
    record = records(storage, "run")[0]
    assert record["input_tokens"] == 100
    assert record["cached_input_tokens"] == 20
    assert record["non_cached_input_tokens"] == 80
    assert record["reasoning_tokens"] == 10
    assert record["visible_output_tokens"] == 20
    assert record["total_reported_tokens"] == 130
    assert record["counter_reconciliation"] == "final_cumulative_snapshot"


def test_missing_token_fields_remain_null(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    result = start_basic(service).finish(status="completed")
    assert result.appended is True
    record = records(storage, "run")[0]
    assert record["input_tokens"] is None
    assert record["cached_input_tokens"] is None
    assert record["reasoning_tokens"] is None
    assert record["visible_output_tokens"] is None
    assert record["measurement_sources"]["input_tokens"] == "unknown"


def test_explicit_zero_token_fields_are_preserved(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    run.consume_event(
        exec_usage_event(
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_output_tokens=0,
            total_tokens=0,
        )
    )
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    for field in (
        "input_tokens",
        "cached_input_tokens",
        "non_cached_input_tokens",
        "reasoning_tokens",
        "visible_output_tokens",
        "total_reported_tokens",
    ):
        assert record[field] == 0


def test_malformed_event_is_counted_and_not_accepted(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    assert run.consume_event({"type": "turn.completed", "usage": {"input_tokens": -1}}) is False
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert record["invalid_event_count"] == 1
    assert record["collector_status"] == "completed_with_invalid_events"
    assert record["input_tokens"] is None


def test_duplicate_event_is_not_double_counted(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    event = {
        "type": "item.started",
        "item": {"id": "tool-1", "type": "command_execution", "status": "in_progress"},
    }
    assert run.consume_event(event) is True
    assert run.consume_event(event) is False
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert record["tool_call_count"] == 1
    assert record["duplicate_event_count"] == 1


def test_started_and_completed_tool_lifecycle_counts_once(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    run.consume_event({"type": "item.started", "item": {"id": "tool-1", "type": "mcp_tool_call"}})
    run.consume_event({"type": "item.completed", "item": {"id": "tool-1", "type": "mcp_tool_call"}})
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert record["tool_call_count"] == 1
    assert record["tool_calls_by_type"] == {"mcp_tool_call": 1}


def test_cumulative_app_server_snapshot_is_not_summed_repeatedly(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service, product_surface="codex_app_server")
    run.consume_event(
        app_usage_event(
            turn_id="turn-1",
            last_input=10,
            last_cached=2,
            last_output=5,
            last_reasoning=1,
            cumulative_total=15,
        )
    )
    run.consume_event(
        app_usage_event(
            turn_id="turn-1",
            last_input=20,
            last_cached=5,
            last_output=10,
            last_reasoning=2,
            cumulative_total=45,
        )
    )
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert record["input_tokens"] == 20
    assert record["total_reported_tokens"] == 30


def test_out_of_order_cumulative_event_keeps_highest_total_snapshot(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service, product_surface="codex_app_server")
    newest = app_usage_event(
        turn_id="turn-2",
        last_input=40,
        last_cached=10,
        last_output=20,
        last_reasoning=5,
        cumulative_total=100,
    )
    older = app_usage_event(
        turn_id="turn-2",
        last_input=10,
        last_cached=1,
        last_output=5,
        last_reasoning=1,
        cumulative_total=30,
    )
    run.consume_event(newest)
    run.consume_event(older)
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert record["input_tokens"] == 40
    assert record["total_reported_tokens"] == 60


def test_equal_cumulative_total_with_conflicting_last_snapshot_is_unreconciled(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service, product_surface="codex_app_server")
    run.consume_event(
        app_usage_event(
            turn_id="turn-3",
            last_input=40,
            last_cached=10,
            last_output=20,
            last_reasoning=5,
            cumulative_total=100,
        )
    )
    run.consume_event(
        app_usage_event(
            turn_id="turn-3",
            last_input=10,
            last_cached=1,
            last_output=5,
            last_reasoning=1,
            cumulative_total=100,
        )
    )
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert record["collector_status"] == "partial_unreconciled"
    assert record["input_tokens"] is None
    assert record["counter_reconciliation"] == "unknown"


def test_equal_request_usage_with_distinct_request_ids_is_not_deduplicated(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    usage = {
        "input_tokens": 10,
        "cached_input_tokens": 2,
        "output_tokens": 5,
        "reasoning_output_tokens": 1,
        "total_tokens": 15,
    }
    run.consume_event({"type": "request.completed", "request_id": "request-1", "usage": usage})
    run.consume_event({"type": "request.completed", "request_id": "request-2", "usage": usage})
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert record["request_count"] == 2
    assert record["input_tokens"] == 20
    assert record["duplicate_event_count"] == 0


def test_conflicting_request_and_final_totals_become_unknown(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    run.consume_event(
        {
            "type": "request.completed",
            "request_id": "request-1",
            "usage": {
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "output_tokens": 5,
                "reasoning_output_tokens": 1,
                "total_tokens": 15,
            },
        }
    )
    run.consume_event(exec_usage_event(input_tokens=20, cached_input_tokens=0, output_tokens=5, reasoning_output_tokens=1, total_tokens=25))
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert record["collector_status"] == "partial_unreconciled"
    assert record["input_tokens"] is None
    assert record["counter_reconciliation"] == "unknown"


def test_missing_reasoning_field_does_not_invent_visible_output(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    run.consume_event(exec_usage_event(reasoning_output_tokens=None, total_tokens=130))
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert record["reasoning_tokens"] is None
    assert record["visible_output_tokens"] is None
    assert record["total_reported_tokens"] == 130


def test_missing_cached_field_does_not_invent_non_cached_input(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service)
    run.consume_event(exec_usage_event(cached_input_tokens=None, total_tokens=130))
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert record["cached_input_tokens"] is None
    assert record["non_cached_input_tokens"] is None


def test_unknown_model_identity_and_backend_unavailable_are_valid(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(
        service,
        requested_model=None,
        launched_model=None,
        backend_model=None,
        model_identity_status="unknown",
    )
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert record["model_identity_status"] == "unknown"
    assert record["backend_model"] is None


def test_app_server_model_reroute_updates_service_identity(tmp_path) -> None:
    service, storage = enabled_service(tmp_path)
    run = start_basic(service, product_surface="codex_app_server")
    run.consume_event(
        {
            "method": "model/rerouted",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "fromModel": "gpt-5.6-luna",
                "toModel": "gpt-5.6-sol",
                "reason": "highRiskCyberActivity",
            },
        }
    )
    assert run.finish(status="completed").appended is True
    record = records(storage, "run")[0]
    assert record["backend_model"] == "gpt-5.6-sol"
    assert record["model_identity_status"] == "service_reported"
    assert record["escalation_count"] is None


@pytest.mark.parametrize("bad_event", [None, [], "not-an-event", {"usage": {}}])
def test_non_object_or_unnamed_events_are_rejected(bad_event) -> None:
    accumulator = CodexEventAccumulator(_digest)
    assert accumulator.consume(bad_event) is False
    assert accumulator.finalize().invalid_event_count == 1
