from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Callable

from .config import CODEX_BINARY, RULES_DIR


Runner = Callable[..., subprocess.CompletedProcess[str]]


def audit_models(
    *,
    output_path: Path | None = None,
    runner: Runner | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    output = output_path or (RULES_DIR / "model_catalog.json")
    run = runner or subprocess.run

    try:
        completed = run(
            [CODEX_BINARY, "debug", "models"],
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "codex command not found", "models": [], "output_path": str(output)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "codex debug models timed out", "models": [], "output_path": str(output)}

    combined = "\n".join(
        item for item in [completed.stdout, completed.stderr] if item
    )
    parsed = extract_json_from_text(combined)
    if parsed is None:
        error = "no parseable model JSON found"
        if completed.returncode != 0:
            error = f"codex debug models failed with return code {completed.returncode}"
        return {"ok": False, "error": error, "models": [], "output_path": str(output)}

    models = normalize_models(parsed)
    if not models:
        return {"ok": False, "error": "empty or unknown model list", "models": [], "output_path": str(output)}

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"models": models}
    with output.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")

    return {
        "ok": completed.returncode == 0,
        "error": None if completed.returncode == 0 else f"codex debug models returned {completed.returncode}",
        "models": models,
        "output_path": str(output),
    }


def extract_json_from_text(text: str) -> Any | None:
    cleaned = text.strip()
    if not cleaned:
        return None

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    candidates: list[str] = []
    object_start = cleaned.find("{")
    object_end = cleaned.rfind("}")
    if object_start != -1 and object_end != -1 and object_end > object_start:
        candidates.append(cleaned[object_start : object_end + 1])

    list_start = cleaned.find("[")
    list_end = cleaned.rfind("]")
    if list_start != -1 and list_end != -1 and list_end > list_start:
        candidates.append(cleaned[list_start : list_end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def normalize_models(data: Any) -> list[dict[str, Any]]:
    raw_models: Any
    if isinstance(data, list):
        raw_models = data
    elif isinstance(data, dict):
        if isinstance(data.get("models"), list):
            raw_models = data["models"]
        elif isinstance(data.get("data"), list):
            raw_models = data["data"]
        elif data.get("id") or data.get("name"):
            raw_models = [data]
        else:
            raw_models = []
    else:
        raw_models = []

    models: list[dict[str, Any]] = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id") or item.get("model") or item.get("slug") or item.get("name") or item.get("display_name")
        if not model_id:
            continue
        visibility = item.get("visibility")
        visible = item.get("visible")
        if visible is None and visibility is not None:
            visible = visibility in {"list", "visible", "public"}
        hidden = item.get("hidden")
        if hidden is None and visibility is not None:
            hidden = visibility in {"hidden", "internal"}
        models.append(
            {
                "id": model_id,
                "name": item.get("name") or item.get("display_name"),
                "provider": item.get("provider"),
                "visible": visible,
                "hidden": hidden,
                "status": item.get("status"),
                "default": item.get("default"),
                "supported_reasoning_effort": item.get("supported_reasoning_effort")
                or item.get("reasoning_efforts")
                or extract_reasoning_efforts(item.get("supported_reasoning_levels")),
                "reasoning_summary_support": item.get("reasoning_summary_support")
                or item.get("reasoning_summary"),
            }
        )
    return models


def extract_reasoning_efforts(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    efforts: list[str] = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("effort"), str):
            efforts.append(item["effort"])
        elif isinstance(item, str):
            efforts.append(item)
    return efforts or None
