"""Offline, provider-free smoke flow for Smart Router demo closure."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

from .policy_version import MODEL_POLICY_VERSION
from .runtime.telemetry.collector import TelemetryService
from .runtime.telemetry.hook_capture import CodexHookTelemetryCapture
from .runtime.telemetry.storage import (
    LocalTelemetryStorage,
    StorageLimits,
    TelemetryPaths,
)
from .runtime.telemetry.validator import validate_run_record
from .session_cli import render_status
from .session_control import (
    WRAPPER_MODE_ENV,
    WRAPPER_MODE_VALUE,
    SessionControlStore,
)
from .session_hook_bridge import route_stop, route_user_prompt_submit


def _payload(event: str, *, prompt: str | None = None) -> dict[str, object]:
    value: dict[str, object] = {
        "session_id": "local-demo-session",
        "transcript_path": None,
        "cwd": "/local/demo/workspace",
        "hook_event_name": event,
        "model": "local-demo-model",
        "permission_mode": "default",
        "turn_id": "local-demo-turn-2",
    }
    if prompt is not None:
        value["prompt"] = prompt
    return value


def _print_step(number: int, title: str) -> None:
    print(f"\n[{number}] {title}")


def main() -> int:
    print("SMART ROUTER DEMO CLOSURE 1A")
    print("Execution mode: LOCAL MOCKED HOOK FLOW — NO MODEL OR PROVIDER CALL")
    with tempfile.TemporaryDirectory(prefix="smart-router-demo-closure-") as temporary:
        root = Path(temporary)
        store = SessionControlStore(
            root / "controls",
            repository_root=Path(__file__).resolve().parents[1],
        )
        storage = LocalTelemetryStorage(
            TelemetryPaths(root / "telemetry", root / "telemetry-salt"),
            StorageLimits(min_free_bytes=0),
            activation_reader=lambda: (
                store.read().state.research_telemetry_enabled is True
            ),
        )
        service = TelemetryService(
            storage,
            window_id="smart-router",
            router_policy_version=MODEL_POLICY_VERSION,
            codex_protocol_version="codex-cli-0.144.6",
            synthetic=True,
        )
        capture = CodexHookTelemetryCapture(
            store,
            service_factory=lambda: service,
            synthetic=True,
        )
        wrapper_environment = {WRAPPER_MODE_ENV: WRAPPER_MODE_VALUE}

        _print_step(1, "Initial status")
        print(render_status(store.read(), telemetry_backend="OFF"))

        _print_step(2, "Enable Smart Router only")
        store.set_router(True)
        print(render_status(store.read(), telemetry_backend="OFF"))

        _print_step(3, "Classify one bounded task through the live hook bridge")
        first = route_user_prompt_submit(
            _payload(
                "UserPromptSubmit",
                prompt="Summarize README.md in three bullets without modifying files.",
            ),
            store=store,
            environ=wrapper_environment,
            telemetry=capture,
        )
        context = first.get("hookSpecificOutput", {})
        summary = context.get("additionalContext") if isinstance(context, dict) else None
        if not isinstance(summary, str) or "SMART_ROUTER_DECISION" not in summary:
            raise RuntimeError("SMOKE_ROUTER_SUMMARY_MISSING")
        print(summary)

        _print_step(4, "Start telemetry while leaving Smart Router enabled")
        store.set_telemetry(True)
        print(render_status(store.read(), telemetry_backend=capture.backend_status()))

        _print_step(5, "Run a second mocked hook lifecycle")
        second_prompt = "Compare guide_a.md and guide_b.md; report three differences."
        second = route_user_prompt_submit(
            _payload("UserPromptSubmit", prompt=second_prompt),
            store=store,
            environ=wrapper_environment,
            telemetry=capture,
        )
        if "hookSpecificOutput" not in second:
            raise RuntimeError("SMOKE_SECOND_ROUTER_SUMMARY_MISSING")
        finished = route_stop(
            _payload("Stop"),
            store=store,
            environ=wrapper_environment,
            telemetry=capture,
        )
        if finished:
            raise RuntimeError("SMOKE_TELEMETRY_DEGRADED")
        records = list(storage.iter_records())
        if len(records) != 1:
            raise RuntimeError("SMOKE_TELEMETRY_RECORD_MISSING")
        validate_run_record(records[0])
        safe_record = {
            "schema_version": records[0]["schema_version"],
            "product_surface": records[0]["product_surface"],
            "collector_status": records[0]["collector_status"],
            "synthetic": records[0]["synthetic"],
            "record_count": len(records),
        }
        print(json.dumps(safe_record, indent=2, sort_keys=True))

        _print_step(6, "Stop telemetry; Smart Router remains enabled")
        store.set_telemetry(False)
        print(render_status(store.read(), telemetry_backend="OFF"))

        _print_step(7, "Disable Smart Router and show final status")
        store.set_router(False)
        print(render_status(store.read(), telemetry_backend="OFF"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
