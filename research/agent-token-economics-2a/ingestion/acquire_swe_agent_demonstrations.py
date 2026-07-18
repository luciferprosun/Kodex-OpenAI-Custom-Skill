#!/usr/bin/env python3
"""Bounded, resumable acquisition of the pinned SWE-agent demo tree.

The default mode writes metadata only. Raw payload download requires --download
and an output directory outside this research repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path


OWNER_REPO = "SWE-agent/SWE-agent"
REVISION = "3ea751c087f32b16e039a2233dd6eefecef325d5"
PREFIX = "trajectories/demonstrations/"
EXPECTED_FILES = 19
EXPECTED_BYTES = 1_503_861
DEFAULT_LIMIT = 2 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]


def request(url, headers=None):
    merged = {"User-Agent": "SmartRouter-token-economics-2a", "Accept": "application/vnd.github+json"}
    merged.update(headers or {})
    return urllib.request.urlopen(urllib.request.Request(url, headers=merged), timeout=60)


def git_blob_sha1(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def inventory():
    url = f"https://api.github.com/repos/{OWNER_REPO}/git/trees/{REVISION}?recursive=1"
    with request(url) as response:
        tree = json.load(response)["tree"]
    rows = sorted(
        ({"path": item["path"], "size_bytes": item["size"], "git_blob_sha1": item["sha"]} for item in tree
         if item.get("type") == "blob" and item["path"].startswith(PREFIX) and item["path"].endswith(".traj")),
        key=lambda row: row["path"],
    )
    if len(rows) != EXPECTED_FILES or sum(row["size_bytes"] for row in rows) != EXPECTED_BYTES:
        raise RuntimeError("pinned tree count/size differs from audited inventory")
    return rows


def download_one(row, output_dir):
    destination = output_dir / row["path"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        data = destination.read_bytes()
        if len(data) == row["size_bytes"] and git_blob_sha1(data) == row["git_blob_sha1"]:
            return data, True
    part = destination.with_suffix(destination.suffix + ".part")
    existing = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={existing}-"} if existing else {}
    url = f"https://raw.githubusercontent.com/{OWNER_REPO}/{REVISION}/{row['path']}"
    with request(url, headers) as response:
        append = existing > 0 and response.status == 206
        mode = "ab" if append else "wb"
        with part.open(mode) as handle:
            while True:
                block = response.read(64 * 1024)
                if not block:
                    break
                handle.write(block)
    data = part.read_bytes()
    if len(data) != row["size_bytes"] or git_blob_sha1(data) != row["git_blob_sha1"]:
        raise RuntimeError(f"size/blob checksum mismatch for {row['path']}")
    os.replace(part, destination)
    return data, False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir == ROOT or ROOT in output_dir.parents:
        raise SystemExit("raw output must remain outside the research repository")
    rows = inventory()
    total = sum(row["size_bytes"] for row in rows)
    if total > args.max_bytes:
        raise SystemExit(f"audited payload {total} exceeds byte ceiling {args.max_bytes}")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_rows = []
    for row in rows:
        item = dict(row)
        item.update({"revision": REVISION, "downloaded": False, "resumed_or_reused": False, "sha256": None})
        if args.download:
            data, reused = download_one(row, output_dir)
            item.update({"downloaded": True, "resumed_or_reused": reused, "sha256": hashlib.sha256(data).hexdigest()})
        out_rows.append(item)
    (output_dir / "inventory.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in out_rows), encoding="utf-8")
    print(json.dumps({
        "status": "PASS", "mode": "download" if args.download else "metadata_only",
        "revision": REVISION, "files": len(rows), "bytes": total,
        "license_signal": "MIT repository license; raw content still requires privacy/reasoning review",
        "raw_repository_output": str(output_dir),
    }, indent=2))


if __name__ == "__main__":
    sys.exit(main())
