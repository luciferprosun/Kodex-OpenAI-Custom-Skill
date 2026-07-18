#!/usr/bin/env python3
"""Create the public-safe file manifest for Build Week publication."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
OUTPUT = ROOT / "manifests" / "PUBLICATION_FILE_MANIFEST.jsonl"
PUBLIC_ENTRIES = [
    ROOT / "README.md",
    ROOT / "PREFLIGHT.md",
    ROOT / "analysis",
    ROOT / "charts",
    ROOT / "data",
    ROOT / "handbook",
    ROOT / "ingestion",
    ROOT / "knowledge",
    ROOT / "manifests",
    ROOT / "methods",
    ROOT / "output",
    ROOT / "reviews",
    ROOT / "schemas",
    ROOT / "sources",
    ROOT / "taxonomy",
    ROOT / "validation",
]


def files():
    seen = set()
    for entry in PUBLIC_ENTRIES:
        if not entry.exists():
            continue
        paths = [entry] if entry.is_file() else entry.rglob("*")
        for path in paths:
            if not path.is_file() or path == OUTPUT or "__pycache__" in path.parts:
                continue
            publication_path = path.relative_to(ROOT)
            if publication_path in seen:
                continue
            seen.add(publication_path)
            yield path, publication_path
    test = REPOSITORY / "tests" / "test_agent_token_economics_2a.py"
    yield test, Path("tests/test_agent_token_economics_2a.py")


def category(path: Path):
    relative = path.relative_to(REPOSITORY)
    if "data" in relative.parts:
        return "privacy_minimized_derived_metadata"
    if path.suffix.lower() in {".png", ".svg", ".html", ".pdf"}:
        return "generated_research_output"
    return "original_research_artifact"


def main():
    rows = []
    for source, destination in sorted(files(), key=lambda item: str(item[1])):
        if source.is_symlink():
            raise SystemExit(f"refusing symlink: {source}")
        payload = source.read_bytes()
        rows.append({
            "record_version": "2a.1",
            "source_path": str(source.relative_to(REPOSITORY)),
            "publication_path": str(destination),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
            "content_class": category(source),
            "raw_third_party_content": False,
            "public_safe_review_required": True,
        })
    OUTPUT.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "PASS",
        "files": len(rows),
        "bytes": sum(row["size_bytes"] for row in rows),
        "manifest": str(OUTPUT.relative_to(ROOT)),
        "manifest_self_included": False,
    }, indent=2))


if __name__ == "__main__":
    main()
