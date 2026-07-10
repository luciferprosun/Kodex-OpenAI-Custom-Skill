from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = PACKAGE_ROOT / "rules"
PROFILES_DIR = PACKAGE_ROOT / "profiles"

LOG_DIR = Path.home() / ".codex-patch-smart-router"
LOG_FILE = LOG_DIR / "decisions.jsonl"

CODEX_BINARY = "codex"
