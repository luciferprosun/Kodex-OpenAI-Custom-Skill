from __future__ import annotations

from pathlib import Path
from typing import Any

from smart_codex.runtime.telemetry.collector import TelemetryService
from smart_codex.runtime.telemetry.storage import (
    LocalTelemetryStorage,
    StorageLimits,
    TelemetryPaths,
)


def telemetry_storage(
    tmp_path: Path,
    *,
    max_file_bytes: int = 5 * 1024 * 1024,
    max_total_bytes: int = 50 * 1024 * 1024,
    min_free_bytes: int = 0,
) -> LocalTelemetryStorage:
    state = tmp_path / "state"
    return LocalTelemetryStorage(
        TelemetryPaths(root=state / "telemetry", salt=state / "telemetry_salt"),
        StorageLimits(
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
            min_free_bytes=min_free_bytes,
        ),
    )


def enabled_service(tmp_path: Path, **limits: int) -> tuple[TelemetryService, LocalTelemetryStorage]:
    storage = telemetry_storage(tmp_path, **limits)
    storage.set_enabled(True)
    return TelemetryService(storage), storage


def start_basic(service: TelemetryService, **overrides: Any):
    values = {
        "task": "Synthetic targeted fixture task.",
        "task_domain": "normal_coding",
        "task_subdomain": "read_only_analysis",
        "task_difficulty": "low",
        "task_scope": "single_file",
        "task_risk": "low",
        "verification_available": None,
        "requested_model": "gpt-5.6-luna",
        "recommended_model": "gpt-5.6-luna",
        "launched_model": "gpt-5.6-luna",
        "backend_model": None,
        "model_identity_status": "client_requested_only",
        "reasoning_effort": "medium",
        "agent_count": None,
        "sandbox": "read-only",
        "approval_policy": "on-request",
        "product_surface": "synthetic_fixture",
    }
    values.update(overrides)
    result = service.start_run(**values)
    assert result.warning is None
    assert result.run is not None
    return result.run


def exec_usage_event(
    *,
    input_tokens: int = 100,
    cached_input_tokens: int | None = 20,
    output_tokens: int = 30,
    reasoning_output_tokens: int | None = 10,
    total_tokens: int | None = None,
) -> dict[str, Any]:
    usage: dict[str, int] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if cached_input_tokens is not None:
        usage["cached_input_tokens"] = cached_input_tokens
    if reasoning_output_tokens is not None:
        usage["reasoning_output_tokens"] = reasoning_output_tokens
    if total_tokens is not None:
        usage["total_tokens"] = total_tokens
    return {"type": "turn.completed", "usage": usage}


def app_usage_event(
    *,
    turn_id: str,
    last_input: int,
    last_cached: int,
    last_output: int,
    last_reasoning: int,
    cumulative_total: int,
) -> dict[str, Any]:
    last_total = last_input + last_output
    return {
        "method": "thread/tokenUsage/updated",
        "params": {
            "threadId": "thread-fixture",
            "turnId": turn_id,
            "tokenUsage": {
                "last": {
                    "inputTokens": last_input,
                    "cachedInputTokens": last_cached,
                    "outputTokens": last_output,
                    "reasoningOutputTokens": last_reasoning,
                    "totalTokens": last_total,
                },
                "total": {
                    "inputTokens": cumulative_total,
                    "cachedInputTokens": 0,
                    "outputTokens": 0,
                    "reasoningOutputTokens": 0,
                    "totalTokens": cumulative_total,
                },
                "modelContextWindow": 1000000,
            },
        },
    }


def records(storage: LocalTelemetryStorage, record_type: str | None = None) -> list[dict[str, Any]]:
    values = list(storage.iter_records())
    return [value for value in values if record_type is None or value.get("record_type") == record_type]
