#!/usr/bin/env python3
"""Repository-local deterministic entrypoint for the smart-router skill."""
from __future__ import annotations

from pathlib import Path
import sys


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "smart_codex").is_dir():
            return candidate
    raise RuntimeError("SMART_ROUTER_CONTROL_ROOT_NOT_FOUND")


def main() -> int:
    root = str(_repository_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    from smart_codex.session_cli import main as control_main

    return control_main(["smart-router", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
