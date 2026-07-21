#!/usr/bin/env python3
"""Project-local UserPromptSubmit command hook."""
from __future__ import annotations

import json
from pathlib import Path
import sys


FALLBACK = {
    "decision": "block",
    "reason": "SMART_ROUTER_FAIL_CLOSED: the prompt could not be classified safely.",
}


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "smart_codex"
        ).is_dir():
            return candidate
    raise RuntimeError


def main() -> int:
    try:
        root = str(_repository_root())
        if root not in sys.path:
            sys.path.insert(0, root)
        from smart_codex.session_hook_bridge import route_user_prompt_submit

        raw_input = sys.stdin.read()
        try:
            payload = json.loads(raw_input)
        except (json.JSONDecodeError, UnicodeError):
            payload = {}
        response = route_user_prompt_submit(payload)
        output = json.dumps(response, ensure_ascii=True, separators=(",", ":"))
    except Exception:
        output = json.dumps(FALLBACK, ensure_ascii=True, separators=(",", ":"))
    sys.stdout.write(output + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
