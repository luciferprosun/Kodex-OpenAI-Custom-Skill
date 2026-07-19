"""Run lifecycle integration for classic and App Server SmartRouter launches."""

from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Any

from .codex_events import CodexEventAccumulator
from .errors import TelemetryError
from .models import RunMetadata, new_run_record, seal_record, utc_now
from .privacy import ensure_installation_salt, private_identifier, task_signature
from .storage import AppendResult, LocalTelemetryStorage
from .validator import validate_run_record


@dataclass(frozen=True)
class StartResult:
    run: "TelemetryRun | None"
    warning: str | None = None


@dataclass(frozen=True)
class FinishResult:
    run_id: str | None
    appended: bool
    warning: str | None = None
    record_hash: str | None = None


@dataclass(frozen=True)
class PendingFinish:
    """A detached run that may be persisted outside an async event loop."""

    run: "TelemetryRun"
    status: str
    process_exit_code: int | None = None


def _safe_category(value: object, fallback: str = "unknown") -> str:
    text = str(value) if value is not None else fallback
    return text if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,159}", text) else fallback


def _approval_value(value: object) -> str:
    if isinstance(value, str):
        return _safe_category(value)
    if isinstance(value, dict):
        return "granular"
    return "unknown"


class TelemetryRun:
    def __init__(
        self,
        record: dict[str, Any],
        *,
        storage: LocalTelemetryStorage,
        salt: bytes,
    ):
        self.record = record
        self.storage = storage
        self.salt = salt
        self._started_monotonic = time.monotonic_ns()
        self._finished = False
        self._result: FinishResult | None = None
        self.events = CodexEventAccumulator(
            lambda namespace, identifier: private_identifier(salt, namespace, identifier)
        )

    @property
    def run_id(self) -> str:
        return str(self.record["run_id"])

    def consume_event(self, event: object) -> bool:
        if self._finished:
            return False
        return self.events.consume(event)

    def bind_session(self, session_id: object) -> None:
        if not self._finished:
            self.events.bind_session(session_id)

    def set_backend_model(self, model: object, *, status: str = "service_reported") -> None:
        if not self._finished:
            self.events.set_backend_model(model, status=status)

    def finish(self, *, status: str, process_exit_code: int | None = None) -> FinishResult:
        if self._finished:
            return self._result or FinishResult(self.run_id, False, "TELEMETRY_ALREADY_FINISHED")
        self._finished = True
        metrics = self.events.finalize()
        record = dict(self.record)
        for field, value in metrics.values.items():
            if value is not None:
                record[field] = value
        record["finished_at"] = utc_now()
        record["wall_time_ms"] = max(0, (time.monotonic_ns() - self._started_monotonic) // 1_000_000)
        for field, source in metrics.sources.items():
            if source != "unknown":
                record["measurement_sources"][field] = source
        record["measurement_sources"]["wall_time_ms"] = "measured"
        if metrics.values.get("backend_model") is not None:
            record["model_identity_status"] = self.events.model_identity_status or "service_reported"
            record["measurement_sources"]["backend_model"] = "provider_reported"
        record["counter_reconciliation"] = metrics.reconciliation
        record["duplicate_event_count"] = metrics.duplicate_event_count
        record["invalid_event_count"] = metrics.invalid_event_count
        if metrics.unreconciled:
            record["collector_status"] = "partial_unreconciled"
        elif metrics.invalid_event_count and status == "completed":
            record["collector_status"] = "completed_with_invalid_events"
        else:
            record["collector_status"] = status
        record["process_exit_code"] = process_exit_code
        sealed = seal_record(record)
        try:
            validate_run_record(sealed)
            appended: AppendResult = self.storage.append(sealed)
        except TelemetryError as exc:
            result = FinishResult(self.run_id, False, f"TELEMETRY_REJECTED_{exc.category}")
        except Exception:
            result = FinishResult(self.run_id, False, "TELEMETRY_REJECTED_INTERNAL_ERROR")
        else:
            result = FinishResult(
                self.run_id,
                appended.appended,
                appended.warning,
                sealed["record_hash"] if appended.appended else None,
            )
        self._result = result
        return result


class TelemetryService:
    def __init__(self, storage: LocalTelemetryStorage | None = None):
        self.storage = storage or LocalTelemetryStorage()

    @classmethod
    def from_default(cls) -> "TelemetryService":
        return cls(LocalTelemetryStorage())

    def start_run(
        self,
        *,
        task: str,
        task_domain: object,
        task_subdomain: object = None,
        task_difficulty: object = "unknown",
        task_scope: object = "unknown",
        task_risk: object = "unknown",
        verification_available: bool | None = None,
        requested_model: object = None,
        recommended_model: object = None,
        launched_model: object = None,
        backend_model: object = None,
        model_identity_status: str = "unknown",
        reasoning_effort: object = None,
        agent_count: int | None = None,
        sandbox: object = "unknown",
        approval_policy: object = "unknown",
        product_surface: str = "smart_codex_cli",
        session_id: object = None,
    ) -> StartResult:
        if not self.storage.enabled():
            return StartResult(None)
        warning = self.storage.write_preflight()
        if warning is not None:
            return StartResult(None, warning)
        try:
            salt = ensure_installation_salt(self.storage.paths.salt)
        except TelemetryError as exc:
            return StartResult(None, f"TELEMETRY_DISABLED_{exc.category}")
        except OSError:
            return StartResult(None, "TELEMETRY_DISABLED_SALT_ERROR")
        safe_session = (
            private_identifier(salt, "session", str(session_id))
            if isinstance(session_id, str) and session_id
            else None
        )
        metadata = RunMetadata(
            task_signature=task_signature(salt, task),
            task_domain=_safe_category(task_domain),
            task_subdomain=_safe_category(task_subdomain) if task_subdomain is not None else None,
            task_difficulty=_safe_category(task_difficulty),
            task_scope=_safe_category(task_scope),
            task_risk=_safe_category(task_risk),
            verification_available=verification_available,
            requested_model=_safe_category(requested_model) if requested_model is not None else None,
            recommended_model=_safe_category(recommended_model) if recommended_model is not None else None,
            launched_model=_safe_category(launched_model) if launched_model is not None else None,
            backend_model=_safe_category(backend_model) if backend_model is not None else None,
            model_identity_status=model_identity_status,
            reasoning_effort=_safe_category(reasoning_effort) if reasoning_effort is not None else None,
            agent_count=agent_count,
            sandbox=_safe_category(sandbox),
            approval_policy=_approval_value(approval_policy),
            product_surface=_safe_category(product_surface),
            session_id=safe_session,
        )
        record = new_run_record(metadata, started_at=utc_now())
        return StartResult(TelemetryRun(record, storage=self.storage, salt=salt))

    def start_from_decision(
        self,
        *,
        task: str,
        decision: object,
        requested_model: object = None,
        launched_model: object = None,
        product_surface: str = "smart_codex_cli",
        session_id: object = None,
        agent_count: int | None = None,
    ) -> StartResult:
        return self.start_run(
            task=task,
            task_domain=getattr(decision, "category", "unknown"),
            task_subdomain=getattr(decision, "action_danger", None),
            task_difficulty=getattr(decision, "complexity_level", "unknown"),
            task_scope=getattr(decision, "execution_scope", "unknown"),
            task_risk=getattr(decision, "risk_level", "unknown"),
            verification_available=None,
            requested_model=requested_model,
            recommended_model=getattr(decision, "selected_model", None),
            launched_model=launched_model,
            model_identity_status=("client_requested_only" if launched_model is not None else "unknown"),
            reasoning_effort=getattr(decision, "reasoning_effort", None),
            agent_count=agent_count,
            sandbox=getattr(decision, "sandbox_mode", "unknown"),
            approval_policy=getattr(decision, "approval_policy", "unknown"),
            product_surface=product_surface,
            session_id=session_id,
        )


class AppServerTelemetryBridge:
    """Per-proxy connection mapping from App Server turns to telemetry runs."""

    def __init__(self, service: TelemetryService | None):
        self.service = service
        self.pending: dict[object, TelemetryRun] = {}
        self.by_thread: dict[str, TelemetryRun] = {}
        self.by_turn: dict[str, TelemetryRun] = {}

    def create(self, *, thread_id: object, prompt: str, routed: object) -> StartResult:
        """Create a run shell without mutating event-loop-owned mappings."""

        if self.service is None or not isinstance(thread_id, str):
            return StartResult(None)
        return self.service.start_run(
            task=prompt,
            task_domain=getattr(routed, "category", "unknown"),
            task_subdomain=getattr(routed, "action_danger", None),
            task_difficulty=getattr(routed, "task_difficulty", "unknown"),
            task_scope=getattr(routed, "task_scope", "unknown"),
            task_risk=getattr(routed, "task_risk", "unknown"),
            verification_available=getattr(routed, "verification_available", None),
            requested_model=getattr(routed, "original_model", None),
            recommended_model=getattr(routed, "selected_model", None),
            launched_model=getattr(routed, "selected_model", None),
            model_identity_status="client_requested_only",
            reasoning_effort=getattr(routed, "effort", None),
            agent_count=None,
            sandbox=getattr(routed, "sandbox_mode", "unknown"),
            approval_policy=getattr(routed, "approval_policy", "unknown"),
            product_surface="codex_app_server",
            session_id=thread_id,
        )

    def register(self, *, request_id: object, thread_id: object, run: TelemetryRun) -> None:
        """Register a completed run shell from the async owner thread."""

        if not isinstance(thread_id, str):
            return
        self.pending[request_id] = run
        self.by_thread[thread_id] = run

    def observe_response(self, message: dict[str, Any]) -> PendingFinish | None:
        request_id = message.get("id")
        run = self.pending.pop(request_id, None)
        if run is None:
            return None
        if message.get("error") is not None:
            self._remove(run)
            return PendingFinish(run, "process_error")
        result = message.get("result")
        if isinstance(result, dict):
            turn = result.get("turn")
            turn_id = turn.get("id") if isinstance(turn, dict) else result.get("turnId")
            if isinstance(turn_id, str):
                self.by_turn[turn_id] = run
            run.set_backend_model(result.get("model"))
        return None

    def observe_notification(self, message: dict[str, Any]) -> PendingFinish | None:
        params = message.get("params")
        if not isinstance(params, dict):
            return None
        turn_id = params.get("turnId")
        thread_id = params.get("threadId")
        run = self.by_turn.get(turn_id) if isinstance(turn_id, str) else None
        if run is None and isinstance(thread_id, str):
            run = self.by_thread.get(thread_id)
        if run is None:
            return None
        method = message.get("method")
        if method == "thread/settings/updated":
            settings = params.get("threadSettings")
            if isinstance(settings, dict):
                run.set_backend_model(settings.get("model"))
        run.consume_event(message)
        if method == "turn/completed":
            turn = params.get("turn")
            turn_status = turn.get("status") if isinstance(turn, dict) else None
            status = {
                "completed": "completed",
                "failed": "process_error",
                "interrupted": "aborted",
                "cancelled": "aborted",
            }.get(turn_status, "collector_interrupted")
            self._remove(run)
            return PendingFinish(run, status)
        return None

    def detach_all(self) -> list[PendingFinish]:
        """Detach interrupted runs without performing filesystem I/O."""

        unique = {id(run): run for run in [*self.pending.values(), *self.by_thread.values(), *self.by_turn.values()]}
        self.pending.clear()
        self.by_thread.clear()
        self.by_turn.clear()
        return [PendingFinish(run, "collector_interrupted") for run in unique.values()]

    def _remove(self, run: TelemetryRun) -> None:
        self.pending = {key: value for key, value in self.pending.items() if value is not run}
        self.by_thread = {key: value for key, value in self.by_thread.items() if value is not run}
        self.by_turn = {key: value for key, value in self.by_turn.items() if value is not run}
