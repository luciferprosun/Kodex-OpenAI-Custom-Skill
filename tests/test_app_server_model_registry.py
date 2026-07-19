from __future__ import annotations

import asyncio

import pytest

from smart_codex.app_server_router.backend import discover_backend
from smart_codex.app_server_router.model_registry import ModelRegistry, RegistryError
from smart_codex.app_server_router.websocket import WebSocketServer
from smart_codex.app_server_router.protocol import decode_message, encode_message

from app_server_test_helpers import live_model_data, model, registry


def test_live_registry_records_only_sanitized_capability_metadata() -> None:
    value = registry()
    snapshot = value.snapshot()

    assert snapshot.codex_version == "codex-cli 0.144.5"
    assert len(snapshot.models) == 5
    assert value.get("gpt-5.6-sol").supported_efforts[-1] == "ultra"  # type: ignore[union-attr]
    assert value.get("gpt-5.3-codex-spark").input_modalities == ("text",)  # type: ignore[union-attr]
    assert value.get("codex-auto-review").hidden is True  # type: ignore[union-attr]
    assert value.get("codex-auto-review").routable is False  # type: ignore[union-attr]


def test_deprecated_model_records_upgrade_target() -> None:
    data = [
        model(
            "legacy-balanced",
            "Legacy Balanced",
            "Balanced model.",
            upgrade="new-balanced",
        ),
        model("new-balanced", "New Balanced", "Balanced model."),
    ]
    value = registry(data)

    deprecated = value.get("legacy-balanced")
    assert deprecated is not None
    assert deprecated.deprecated is True
    assert deprecated.upgrade_target == "new-balanced"


def test_registry_resolves_distinct_catalog_id_and_wire_model_slug() -> None:
    data = [model("catalog-luna", "Luna", "Fast model.")]
    data[0]["model"] = "wire-luna"

    value = registry(data)

    assert value.get("catalog-luna") is value.get("wire-luna")


def test_ambiguous_catalog_and_wire_identifiers_fail_closed() -> None:
    first = model("catalog-one", "One", "First model.")
    first["model"] = "shared-model"
    second = model("shared-model", "Two", "Second model.")

    with pytest.raises(RegistryError):
        registry([first, second])


def test_malformed_or_empty_live_registry_fails_closed() -> None:
    with pytest.raises(RegistryError):
        ModelRegistry.from_model_list([], codex_version="codex-cli 0.144.5")

    broken = live_model_data()
    broken[0] = {**broken[0], "supportedReasoningEfforts": []}
    with pytest.raises(RegistryError):
        ModelRegistry.from_model_list(broken, codex_version="codex-cli 0.144.5")


def test_backend_discovery_paginates_model_list_and_reads_requirements() -> None:
    async def scenario() -> None:
        seen: list[str] = []

        async def handler(connection) -> None:
            while True:
                message = decode_message(await connection.recv_text())
                method = message.get("method")
                seen.append(str(method))
                if method == "initialize":
                    await connection.send_text(
                        encode_message(
                            {
                                "id": message["id"],
                                "result": {
                                    "userAgent": "fake/0.144.5",
                                    "codexHome": "/tmp/fake",
                                    "platformFamily": "unix",
                                    "platformOs": "linux",
                                },
                            }
                        )
                    )
                elif method == "model/list":
                    cursor = message["params"].get("cursor")
                    data = live_model_data()
                    page = data[:2] if cursor is None else data[2:]
                    next_cursor = "page-2" if cursor is None else None
                    await connection.send_text(
                        encode_message(
                            {
                                "id": message["id"],
                                "result": {"data": page, "nextCursor": next_cursor},
                            }
                        )
                    )
                elif method == "configRequirements/read":
                    await connection.send_text(
                        encode_message(
                            {
                                "id": message["id"],
                                "result": {
                                    "requirements": {
                                        "allowedSandboxModes": ["read-only"],
                                        "allowedApprovalPolicies": ["on-request"],
                                    }
                                },
                            }
                        )
                    )
                    return

        server = WebSocketServer("127.0.0.1", 0, handler)
        await server.start()
        try:
            discovered = await discover_backend(
                f"ws://127.0.0.1:{server.bound_port}",
                codex_version="codex-cli 0.144.5",
                attempts=1,
            )
        finally:
            await server.close()

        assert len(discovered.registry.all()) == 5
        assert discovered.requirements.allowed_sandbox_modes == ("read-only",)
        assert seen == [
            "initialize",
            "initialized",
            "model/list",
            "model/list",
            "configRequirements/read",
        ]

    asyncio.run(scenario())
