from pathlib import Path
import tomllib

from smart_codex.config import LOG_DIR


def test_project_identity_metadata():
    root = Path(__file__).resolve().parents[1]
    with (root / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)

    assert pyproject["project"]["name"] == "codex-patch-smart-router"
    assert "Codex Patch Smart Router" in (root / "README.md").read_text(encoding="utf-8")
    assert LOG_DIR.name == ".codex-patch-smart-router"
