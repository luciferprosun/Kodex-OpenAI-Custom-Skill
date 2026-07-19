"""Version-aware parsing of structured Codex telemetry events."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Callable

from .schema import unknown_measurement_sources


TOOL_ITEM_TYPES = {
    "command_execution",
    "file_change",
    "mcp_tool_call",
    "dynamic_tool_call",
    "collab_agent_tool_call",
    "web_search",
    "image_view",
    "image_generation",
}
APP_TOOL_ITEM_TYPES = {
    "commandExecution",
    "fileChange",
    "mcpToolCall",
    "dynamicToolCall",
    "collabAgentToolCall",
    "webSearch",
    "imageView",
    "imageGeneration",
}


def _snake(value: str) -> str:
    value = value.replace("-", "_").replace(".", "_").replace("/", "_")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _first(mapping: dict[str, Any], *names: str) -> tuple[bool, object]:
    for name in names:
        if name in mapping:
            return True, mapping[name]
    return False, None


@dataclass(frozen=True)
class UsageSnapshot:
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    total_tokens: int | None

    @classmethod
    def parse(cls, value: object) -> "UsageSnapshot | None":
        if not isinstance(value, dict):
            return None
        present: dict[str, bool] = {}
        parsed: dict[str, int | None] = {}
        fields = {
            "input_tokens": ("input_tokens", "inputTokens"),
            "cached_input_tokens": ("cached_input_tokens", "cachedInputTokens"),
            "output_tokens": ("output_tokens", "outputTokens"),
            "reasoning_tokens": ("reasoning_output_tokens", "reasoningOutputTokens", "reasoning_tokens"),
            "total_tokens": ("total_tokens", "totalTokens"),
        }
        for field, names in fields.items():
            exists, raw = _first(value, *names)
            present[field] = exists
            parsed[field] = _integer(raw) if exists else None
            if exists and parsed[field] is None:
                return None
        if not any(present.values()):
            return None
        snapshot = cls(**parsed)
        if snapshot.cached_input_tokens is not None and snapshot.input_tokens is not None:
            if snapshot.cached_input_tokens > snapshot.input_tokens:
                return None
        if snapshot.output_tokens is not None and snapshot.reasoning_tokens is not None:
            if snapshot.reasoning_tokens > snapshot.output_tokens:
                return None
        if snapshot.total_tokens is not None and snapshot.input_tokens is not None and snapshot.output_tokens is not None:
            if snapshot.total_tokens != snapshot.input_tokens + snapshot.output_tokens:
                return None
        return snapshot

    def as_record_values(self) -> tuple[dict[str, int | None], dict[str, str]]:
        values: dict[str, int | None] = {
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "non_cached_input_tokens": None,
            "reasoning_tokens": self.reasoning_tokens,
            "visible_output_tokens": None,
            "total_reported_tokens": self.total_tokens,
        }
        sources = {field: "unknown" for field in values}
        for field in ("input_tokens", "cached_input_tokens", "reasoning_tokens", "total_reported_tokens"):
            if values[field] is not None:
                sources[field] = "provider_reported"
        if self.input_tokens is not None and self.cached_input_tokens is not None:
            values["non_cached_input_tokens"] = self.input_tokens - self.cached_input_tokens
            sources["non_cached_input_tokens"] = "reconstructed"
        if self.output_tokens is not None and self.reasoning_tokens is not None:
            values["visible_output_tokens"] = self.output_tokens - self.reasoning_tokens
            sources["visible_output_tokens"] = "reconstructed"
        return values, sources


@dataclass(frozen=True)
class EventMetrics:
    values: dict[str, Any]
    sources: dict[str, str]
    reconciliation: str
    duplicate_event_count: int
    invalid_event_count: int
    unreconciled: bool


class CodexEventAccumulator:
    """Accumulate only numeric and categorical facts from structured events."""

    def __init__(self, identifier_digest: Callable[[str, str], str]):
        self._identifier_digest = identifier_digest
        self._fingerprints: set[str] = set()
        self._tool_ids: set[str] = set()
        self._compaction_ids: set[str] = set()
        self._request_ids: set[str] = set()
        self._tool_counts: Counter[str] = Counter()
        self._final_usage: UsageSnapshot | None = None
        self._final_cumulative_total: int | None = None
        self._cumulative_conflict = False
        self._request_usages: list[UsageSnapshot] = []
        self._session_id: str | None = None
        self._backend_model: str | None = None
        self._model_identity_status: str | None = None
        self._explicit_counts: dict[str, int] = {}
        self._count_sources: dict[str, str] = {}
        self.duplicate_event_count = 0
        self.invalid_event_count = 0

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def backend_model(self) -> str | None:
        return self._backend_model

    @property
    def model_identity_status(self) -> str | None:
        return self._model_identity_status

    def set_backend_model(self, model: object, *, status: str = "service_reported") -> None:
        if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model):
            self._backend_model = model
            self._model_identity_status = status

    def bind_session(self, session_id: object) -> None:
        if isinstance(session_id, str) and session_id:
            self._session_id = self._identifier_digest("session", session_id)

    def _fingerprint(self, event: dict[str, Any], event_name: str) -> str:
        item = event.get("item")
        params = event.get("params")
        if isinstance(params, dict) and not isinstance(item, dict):
            item = params.get("item")
        identifiers: list[object] = [
            event_name,
            event.get("id"),
            event.get("request_id"),
            event.get("requestId"),
            event.get("thread_id"),
        ]
        if isinstance(params, dict):
            identifiers.extend(
                [params.get("requestId"), params.get("threadId"), params.get("turnId")]
            )
        if isinstance(item, dict):
            identifiers.extend([item.get("id"), item.get("type"), item.get("status")])
        usage = event.get("usage")
        if isinstance(params, dict) and usage is None:
            usage = params.get("tokenUsage")
        safe = json.dumps([identifiers, usage], sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(safe.encode("utf-8")).hexdigest()

    def consume(self, event: object) -> bool:
        if not isinstance(event, dict):
            self.invalid_event_count += 1
            return False
        raw_name = event.get("type") or event.get("method")
        if not isinstance(raw_name, str) or not raw_name:
            self.invalid_event_count += 1
            return False
        fingerprint = self._fingerprint(event, raw_name)
        if fingerprint in self._fingerprints:
            self.duplicate_event_count += 1
            return False
        self._fingerprints.add(fingerprint)

        params = event.get("params") if isinstance(event.get("params"), dict) else {}
        if raw_name in {"thread.started", "thread/started"}:
            self.bind_session(event.get("thread_id") or params.get("threadId"))
            return True
        if raw_name == "thread/tokenUsage/updated":
            return self._consume_app_usage(params)
        if raw_name in {"turn.completed", "turn/usage"}:
            usage = UsageSnapshot.parse(event.get("usage"))
            if usage is None:
                self.invalid_event_count += 1
                return False
            self._final_usage = usage
            return True
        if raw_name in {"request.completed", "model/request/completed"}:
            usage = UsageSnapshot.parse(event.get("usage") or params.get("usage"))
            request_id = event.get("request_id") or params.get("requestId") or event.get("id")
            if usage is None or not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
                self.invalid_event_count += 1
                return False
            safe_id = str(request_id)
            if safe_id not in self._request_ids:
                self._request_ids.add(safe_id)
                self._request_usages.append(usage)
            return True
        if raw_name in {"item.started", "item.completed", "item/started", "item/completed"}:
            item = event.get("item") if isinstance(event.get("item"), dict) else params.get("item")
            return self._consume_item(item, raw_name, params)
        if raw_name in {"thread/compacted", "context.compacted"}:
            compaction_id = f"compaction:{params.get('threadId')}:{params.get('turnId')}"
            self._record_compaction(compaction_id)
            return True
        if raw_name in {"model/rerouted", "model.rerouted"}:
            self.set_backend_model(params.get("toModel") or event.get("to_model"))
            return True
        if raw_name in {"model/escalated", "model.escalated"}:
            count = _integer(event.get("count") if "count" in event else params.get("count"))
            if count is None:
                count = 1
            self._explicit_counts["escalation_count"] = count
            self._count_sources["escalation_count"] = "provider_reported"
            self.set_backend_model(params.get("toModel") or event.get("to_model"))
            return True
        explicit = {
            "request.count": "request_count",
            "retry.count": "retry_count",
            "invalid_tool_call.count": "invalid_tool_call_count",
            "compaction.count": "compaction_count",
        }.get(raw_name)
        if explicit:
            count = _integer(event.get("count") if "count" in event else params.get("count"))
            if count is None:
                self.invalid_event_count += 1
                return False
            self._explicit_counts[explicit] = count
            self._count_sources[explicit] = "provider_reported"
            return True
        return True

    def _consume_app_usage(self, params: dict[str, Any]) -> bool:
        token_usage = params.get("tokenUsage")
        if not isinstance(token_usage, dict):
            self.invalid_event_count += 1
            return False
        last = UsageSnapshot.parse(token_usage.get("last"))
        total = UsageSnapshot.parse(token_usage.get("total"))
        if last is None or total is None or total.total_tokens is None:
            self.invalid_event_count += 1
            return False
        if self._final_cumulative_total is None or total.total_tokens > self._final_cumulative_total:
            self._final_cumulative_total = total.total_tokens
            self._final_usage = last
            self._cumulative_conflict = False
        elif total.total_tokens == self._final_cumulative_total and last != self._final_usage:
            self._cumulative_conflict = True
        return True

    def _consume_item(self, item: object, event_name: str, params: dict[str, Any]) -> bool:
        if not isinstance(item, dict):
            self.invalid_event_count += 1
            return False
        item_type = item.get("type")
        if not isinstance(item_type, str):
            self.invalid_event_count += 1
            return False
        normalized = _snake(item_type)
        item_id_raw = item.get("id")
        item_id = str(item_id_raw) if isinstance(item_id_raw, (str, int)) and not isinstance(item_id_raw, bool) else None
        if item_type == "contextCompaction" or normalized == "context_compaction":
            turn_id = params.get("turnId")
            thread_id = params.get("threadId")
            identity = (
                f"compaction:{thread_id}:{turn_id}"
                if isinstance(turn_id, str)
                else item_id or f"{event_name}:context_compaction"
            )
            self._record_compaction(identity)
            return True
        if item_type not in APP_TOOL_ITEM_TYPES and normalized not in TOOL_ITEM_TYPES:
            return True
        identity = item_id or hashlib.sha256(f"{event_name}:{normalized}".encode("utf-8")).hexdigest()
        if identity not in self._tool_ids:
            self._tool_ids.add(identity)
            self._tool_counts[normalized] += 1
        return True

    def _record_compaction(self, identity: str) -> None:
        if identity not in self._compaction_ids:
            self._compaction_ids.add(identity)

    @staticmethod
    def _sum_request_usage(values: list[UsageSnapshot]) -> UsageSnapshot | None:
        if not values:
            return None
        fields: dict[str, int | None] = {}
        for field in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"):
            components = [getattr(value, field) for value in values]
            fields[field] = sum(components) if all(component is not None for component in components) else None
        return UsageSnapshot(**fields)

    @staticmethod
    def _compatible(left: UsageSnapshot, right: UsageSnapshot) -> bool:
        for field in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"):
            first = getattr(left, field)
            second = getattr(right, field)
            if first is not None and second is not None and first != second:
                return False
        return True

    def finalize(self) -> EventMetrics:
        values: dict[str, Any] = {
            "session_id": self._session_id,
            "backend_model": self._backend_model,
            "input_tokens": None,
            "non_cached_input_tokens": None,
            "cached_input_tokens": None,
            "reasoning_tokens": None,
            "visible_output_tokens": None,
            "total_reported_tokens": None,
            "request_count": None,
            "tool_call_count": None,
            "tool_calls_by_type": None,
            "invalid_tool_call_count": None,
            "retry_count": None,
            "escalation_count": None,
            "compaction_count": None,
        }
        sources = unknown_measurement_sources()
        request_sum = self._sum_request_usage(self._request_usages)
        usage: UsageSnapshot | None = None
        unreconciled = False
        if self._cumulative_conflict:
            reconciliation = "unknown"
            unreconciled = True
        elif request_sum is not None and self._final_usage is not None:
            if self._compatible(request_sum, self._final_usage):
                usage = self._final_usage
                reconciliation = "mixed_reconciled"
            else:
                reconciliation = "unknown"
                unreconciled = True
        elif self._final_usage is not None:
            usage = self._final_usage
            reconciliation = "final_cumulative_snapshot"
        elif request_sum is not None:
            usage = request_sum
            reconciliation = "per_request_sum"
        else:
            reconciliation = "unknown"
        if usage is not None:
            token_values, token_sources = usage.as_record_values()
            values.update(token_values)
            sources.update(token_sources)
        if self._request_ids:
            values["request_count"] = len(self._request_ids)
            sources["request_count"] = "measured"
        if self._tool_counts:
            values["tool_calls_by_type"] = dict(sorted(self._tool_counts.items()))
            values["tool_call_count"] = sum(self._tool_counts.values())
            sources["tool_call_count"] = "measured"
        if self._compaction_ids:
            values["compaction_count"] = len(self._compaction_ids)
            sources["compaction_count"] = "measured"
        for field, value in self._explicit_counts.items():
            values[field] = value
            sources[field] = self._count_sources[field]
        return EventMetrics(
            values=values,
            sources=sources,
            reconciliation=reconciliation,
            duplicate_event_count=self.duplicate_event_count,
            invalid_event_count=self.invalid_event_count,
            unreconciled=unreconciled,
        )
