import os
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = PACKAGE_ROOT / "rules"
PROFILES_DIR = PACKAGE_ROOT / "profiles"

LOG_DIR = Path.home() / ".codex-patch-smart-router"
LOG_FILE = LOG_DIR / "decisions.jsonl"

DEFAULT_CODEX_REAL_BINARY = Path.home() / ".local" / "bin" / "codex-real"
CODEX_BINARY = os.environ.get("CODEX_REAL_BINARY", str(DEFAULT_CODEX_REAL_BINARY))
