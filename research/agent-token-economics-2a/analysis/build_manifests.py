#!/usr/bin/env python3
"""Create acquisition, transformation, and exclusion manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "manifests"
REGISTRY = ROOT / "sources" / "dataset_registry.jsonl"
INDEX = ROOT / "data" / "raw-index" / "swe_agent_demonstration_index.jsonl"
SAMPLE = ROOT / "data" / "samples" / "swe_agent_demonstration_field_sample.jsonl"


def load_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def main():
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    datasets = load_jsonl(REGISTRY)
    sample_index = load_jsonl(INDEX)
    downloaded_bytes = sum(row.get("downloaded_bytes") or 0 for row in sample_index)
    downloaded_files = sum(bool(row.get("downloaded")) for row in sample_index)

    acquisition = []
    exclusions = []
    for row in datasets:
        is_demo = row["dataset_id"] == "ds_sweagent_demonstrations"
        payload_downloaded = is_demo and downloaded_files > 0
        acquisition.append({
            "manifest_version": "2a.1",
            "dataset_id": row["dataset_id"],
            "source_ids": row["source_ids"],
            "inspection_date": "2026-07-18",
            "raw_acquisition_status": row["raw_acquisition_status"],
            "acquisition_mode": "bounded_temporary_parser_inspection" if payload_downloaded else "metadata_only",
            "payload_downloaded": payload_downloaded,
            "downloaded_files": downloaded_files if is_demo else 0,
            "downloaded_bytes": downloaded_bytes if is_demo else 0,
            "raw_files_committed": False,
            "resume_supported": is_demo,
            "structured_size": row["structured_size"],
            "license_signal": row["license"],
            "dataset_or_telemetry_rights": row["dataset_or_telemetry_rights"],
            "notes": "Temporary raw payload excluded; public repository stores source metadata and derived allowlisted fields only." if payload_downloaded else "No payload downloaded.",
        })
        if not payload_downloaded:
            exclusions.append({
                "manifest_version": "2a.1",
                "dataset_id": row["dataset_id"],
                "excluded_payload": True,
                "reason": row["rejection_reason"] or row["raw_acquisition_status"],
                "raw_redistribution_status": row["raw_redistribution_status"],
                "human_review_required": row["human_review_required"],
                "numerical_prior_excluded": not row["accepted_for_numerical_routing"],
            })

    transformations = []
    if INDEX.exists() and SAMPLE.exists():
        transformations.append({
            "manifest_version": "2a.1",
            "dataset_id": "ds_sweagent_demonstrations",
            "input_index": str(INDEX.relative_to(ROOT)),
            "input_index_sha256": digest(INDEX),
            "output_sample": str(SAMPLE.relative_to(ROOT)),
            "output_sample_sha256": digest(SAMPLE),
            "transformations": [
                "discard raw message text and thought/reasoning content",
                "retain immutable source locator, hashes, sizes, structural field names, counts, and telemetry-field presence",
                "set numerical-prior permission false",
            ],
            "raw_content_committed": False,
            "hidden_reasoning_removed": True,
            "privacy_review": "allowlist_only",
        })

    write_jsonl(MANIFESTS / "ACQUISITION_MANIFEST.jsonl", acquisition)
    write_jsonl(MANIFESTS / "TRANSFORMATION_MANIFEST.jsonl", transformations)
    write_jsonl(MANIFESTS / "EXCLUSION_MANIFEST.jsonl", exclusions)
    print(json.dumps({
        "status": "PASS",
        "datasets": len(datasets),
        "payload_datasets": sum(row["payload_downloaded"] for row in acquisition),
        "downloaded_files": downloaded_files,
        "downloaded_bytes": downloaded_bytes,
        "transformations": len(transformations),
        "exclusions": len(exclusions),
        "raw_data_committed": False,
    }, indent=2))


if __name__ == "__main__":
    main()
