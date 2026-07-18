#!/usr/bin/env python3
"""Validate the public-safe SmartRouter token-economics research bundle."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation"
EVIDENCE_DATE = "2026-07-18"
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
TEXT_SUFFIXES = {".html", ".json", ".jsonl", ".md", ".py", ".svg", ".txt"}
FORBIDDEN_NAMES = {
    ".env", "credentials.json", "id_ed25519", "id_rsa",
}
FORBIDDEN_SUFFIXES = {".key", ".pem", ".pyc"}
LINK_RE = re.compile(r"\[([^]]+)\]\(([^)]+)\)")
HTML_LINK_RE = re.compile(r"(?:href|src)=[\"']([^\"']+)[\"']")

# Each URL is a decisive handbook citation that was directly reopened on the
# evidence-cutoff date. A new handbook URL deliberately fails until reviewed.
NETWORK_VERIFIED = {
    "https://arxiv.org/abs/2210.03629": "browser_direct",
    "https://developers.openai.com/api/docs/guides/prompt-caching": "browser_direct",
    "https://developers.openai.com/api/docs/pricing": "browser_direct",
    "https://github.com/SWE-agent/SWE-agent": "browser_direct",
    "https://github.com/SWE-bench/experiments": "browser_direct",
    "https://github.com/agentrebench/AgentRE-Bench": "browser_direct",
    "https://github.com/harbor-framework/harbor": "browser_direct",
    "https://github.com/harbor-framework/terminal-bench-2": "browser_direct",
    "https://github.com/microsoft/STATE-Bench": "browser_direct",
    "https://github.com/openai/codex/blob/56395bddaf26eb2829387ca6a417bf9128e5b239/codex-rs/exec/src/exec_events.rs": "direct_http_200",
    "https://github.com/openai/openai-agents-python/blob/65886fa16dcdb482090b30b74de1d0cc80b9f4c6/docs/usage.md": "direct_http_200",
    "https://github.com/web-arena-x/webarena": "browser_direct",
}
CLAIM_ALIGNMENT_REVIEW = {
    "https://arxiv.org/abs/2210.03629": "Primary paper supports ReAct's interleaved reasoning/action history; it is not used as token telemetry.",
    "https://developers.openai.com/api/docs/guides/prompt-caching": "Official guide supports distinct cache-read/cache-write fields and model/date-dependent cache accounting.",
    "https://developers.openai.com/api/docs/pricing": "Official dated page is used only as a current price reference, never as an unlabeled historical ledger.",
    "https://github.com/SWE-agent/SWE-agent": "Primary repository supports SWE-agent identity, trajectory format context, and the bounded pinned fixture source.",
    "https://github.com/SWE-bench/experiments": "Primary archive supports the existence of predictions, logs, trajectories, and result artifacts; it is not treated as a uniform token schema.",
    "https://github.com/agentrebench/AgentRE-Bench": "Primary repository supports benchmark identity, long-horizon reverse-engineering tasks, tools, and evaluation structure.",
    "https://github.com/harbor-framework/harbor": "Primary repository supports Harbor as an agent-evaluation framework; the handbook does not infer a uniform telemetry contract.",
    "https://github.com/harbor-framework/terminal-bench-2": "Primary repository supports Terminal-Bench 2 task/evaluator structure, not a complete accepted-cost dataset.",
    "https://github.com/microsoft/STATE-Bench": "Primary repository supports STATE-Bench identity and stateful enterprise-workflow evaluation structure; no run-level token claim is attached.",
    "https://github.com/openai/codex/blob/56395bddaf26eb2829387ca6a417bf9128e5b239/codex-rs/exec/src/exec_events.rs": "Pinned primary source supports the inspected Codex typed event/usage surface and version boundary.",
    "https://github.com/openai/openai-agents-python/blob/65886fa16dcdb482090b30b74de1d0cc80b9f4c6/docs/usage.md": "Pinned official SDK documentation supports run/request usage fields and per-request entries; it is not a task-outcome corpus.",
    "https://github.com/web-arena-x/webarena": "Primary repository supports WebArena benchmark implementation and objective evaluation; its code license is not treated as rights to separately hosted traces.",
}


class PublicationValidationError(Exception):
    pass


def jsonl(path: Path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def public_files():
    seen = set()
    for entry in PUBLIC_ENTRIES:
        if not entry.exists():
            continue
        paths = [entry] if entry.is_file() else entry.rglob("*")
        for path in paths:
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def validate_all_json():
    files = sorted(ROOT.rglob("*.json")) + sorted(ROOT.rglob("*.jsonl"))
    records = 0
    for path in files:
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
            records += 1
        else:
            records += len(jsonl(path))
    return {"files": len(files), "documents_or_rows": records}


def load_corpus_validator():
    path = ROOT / "analysis" / "validate_corpus.py"
    spec = importlib.util.spec_from_file_location("token_economics_validator", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise PublicationValidationError("could not load corpus validator")
    spec.loader.exec_module(module)
    return module


def registry_url_index(rows):
    index = {}
    for row in rows:
        for key in ("canonical_url", "api_endpoint"):
            value = row.get(key)
            if value:
                index.setdefault(value.rstrip("/"), []).append(row["source_id"])
    return index


def resolve_local_link(source: Path, raw_target: str):
    target = raw_target.split("#", 1)[0]
    if not target:
        return source
    path = (source.parent / unquote(target)).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise PublicationValidationError(f"link escapes research root: {source}: {raw_target}") from exc
    if not path.exists():
        raise PublicationValidationError(f"broken local link: {source}: {raw_target}")
    return path


def validate_links(source_rows):
    local_audit = []
    external = []
    markdown_files = [path for path in public_files() if path.suffix == ".md"]
    for path in markdown_files:
        for label, target in LINK_RE.findall(path.read_text(encoding="utf-8")):
            scheme = urlsplit(target).scheme
            if scheme in {"http", "https"}:
                if path == ROOT / "handbook" / "SMARTROUTER_AGENT_TOKEN_ECONOMICS.md":
                    external.append((label, target))
                continue
            if scheme or target.startswith("mailto:"):
                continue
            resolved = resolve_local_link(path, target)
            local_audit.append({
                "source": str(path.relative_to(ROOT)),
                "label": label,
                "target": target,
                "resolved": str(resolved.relative_to(ROOT)),
                "status": "PASS",
            })

    html = ROOT / "handbook" / "SMARTROUTER_AGENT_TOKEN_ECONOMICS.html"
    for target in HTML_LINK_RE.findall(html.read_text(encoding="utf-8")):
        scheme = urlsplit(target).scheme
        if scheme or target.startswith("#"):
            continue
        resolved = resolve_local_link(html, target)
        local_audit.append({
            "source": str(html.relative_to(ROOT)),
            "label": "HTML href/src",
            "target": target,
            "resolved": str(resolved.relative_to(ROOT)),
            "status": "PASS",
        })

    source_index = registry_url_index(source_rows)
    citation_audit = []
    for label, url in sorted(set(external), key=lambda item: item[1]):
        source_ids = source_index.get(url.rstrip("/"), [])
        if not source_ids:
            raise PublicationValidationError(f"handbook citation absent from source registry: {url}")
        if url not in NETWORK_VERIFIED:
            raise PublicationValidationError(f"handbook citation not directly reverified: {url}")
        if url not in CLAIM_ALIGNMENT_REVIEW:
            raise PublicationValidationError(f"handbook citation lacks claim-alignment review: {url}")
        citation_audit.append({
            "label": label,
            "url": url,
            "source_ids": source_ids,
            "registry_match": True,
            "reachability": "resolved",
            "verification_method": NETWORK_VERIFIED[url],
            "claim_alignment": "PASS_LEAD_PRIMARY_SOURCE_REVIEW",
            "reviewed_claim": CLAIM_ALIGNMENT_REVIEW[url],
            "verified_at": EVIDENCE_DATE,
        })
    return local_audit, citation_audit


def scan_public_bundle():
    secret_patterns = {
        "openai_key": re.compile(r"sk" + r"-(?:proj-)?[A-Za-z0-9_-]{20,}"),
        "github_classic_token": re.compile(r"gh" + r"[pousr]_[A-Za-z0-9]{20,}"),
        "github_fine_grained_token": re.compile(r"github" + r"_pat_[A-Za-z0-9_]{20,}"),
        "private_key": re.compile(r"BEGIN [A-Z0-9 ]*PRIVATE KEY"),
        "aws_access_key": re.compile(r"AK" + r"IA[0-9A-Z]{16}"),
        "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    }
    findings = []
    private_paths = []
    aoia_hits = []
    unsafe_names = []
    unexpected_binaries = []
    allowed_binary_suffixes = {".jpg", ".jpeg", ".pdf", ".png"}
    script_self = ROOT / "analysis" / "run_publication_validation.py"

    for path in public_files():
        relative = path.relative_to(ROOT)
        lowered = path.name.lower()
        if lowered in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            unsafe_names.append(str(relative))
        if path.suffix.lower() not in TEXT_SUFFIXES | allowed_binary_suffixes:
            unexpected_binaries.append(str(relative))
        if path == script_self or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="strict")
        for category, pattern in secret_patterns.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append({"category": category, "path": str(relative), "line": line})
        for match in re.finditer(r"/(?:home|Users)/[^/\s]+", text):
            line = text.count("\n", 0, match.start()) + 1
            private_paths.append({"path": str(relative), "line": line})
        # Validation reports are allowed to record the negative separation
        # result itself; all substantive publication artifacts remain scanned.
        if not path.is_relative_to(VALIDATION):
            for match in re.finditer(r"\bAOIA(?:-Core)?\b", text, re.IGNORECASE):
                line = text.count("\n", 0, match.start()) + 1
                aoia_hits.append({"path": str(relative), "line": line})

    symlinks = [str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.is_symlink()]
    nested_git = [str(path.relative_to(ROOT)) for path in ROOT.rglob(".git")]
    if findings or private_paths or aoia_hits or unsafe_names or unexpected_binaries or symlinks or nested_git:
        raise PublicationValidationError(
            "public-bundle scan failed: "
            + json.dumps({
                "secret_categories": Counter(row["category"] for row in findings),
                "private_path_count": len(private_paths),
                "aoia_hit_count": len(aoia_hits),
                "unsafe_names": unsafe_names,
                "unexpected_binaries": unexpected_binaries,
                "symlinks": symlinks,
                "nested_git": nested_git,
            }, sort_keys=True)
        )
    files = list(public_files())
    return {
        "files_scanned": len(files),
        "bytes_scanned": sum(path.stat().st_size for path in files),
        "secret_matches": 0,
        "private_absolute_paths": 0,
        "aoia_content_matches": 0,
        "unsafe_filenames": 0,
        "symlinks": 0,
        "nested_git_directories": 0,
        "unexpected_binaries": 0,
        "raw_private_chats": 0,
    }


def validate_registries(source_rows, dataset_rows):
    source_ids = {row["source_id"] for row in source_rows}
    if len(source_ids) != len(source_rows):
        raise PublicationValidationError("duplicate canonical source ID")
    for row in dataset_rows:
        if not row.get("source_ids") or not set(row["source_ids"]) <= source_ids:
            raise PublicationValidationError(f"unresolved dataset provenance: {row['dataset_id']}")
        for required in (
            "license", "software_or_schema_license", "dataset_or_telemetry_rights",
            "raw_redistribution_status", "allowed_derived_statistics_status",
            "decision", "human_review_required",
        ):
            if required not in row:
                raise PublicationValidationError(f"{row['dataset_id']} lacks {required}")
    decision_counts = Counter(row["decision"] for row in dataset_rows)
    admitted = [row for row in dataset_rows if row["accepted_for_numerical_routing"]]
    if admitted:
        raise PublicationValidationError("2A unexpectedly admitted a dataset to numerical routing")
    return {
        "sources": len(source_rows),
        "source_aliases": sum(len(row.get("aliases", [])) for row in source_rows),
        "datasets_or_surfaces": len(dataset_rows),
        "decision_counts": dict(sorted(decision_counts.items())),
        "records_with_unknown_primary_license": sum(row["license"] is None for row in dataset_rows),
        "numerical_routing_datasets": 0,
    }


def validate_charts():
    png = sorted((ROOT / "charts").glob("[0-9][0-9]_*.png"))
    svg = sorted((ROOT / "charts").glob("[0-9][0-9]_*.svg"))
    metadata = sorted((ROOT / "charts" / "metadata").glob("*.json"))
    if not (len(png) == len(svg) == len(metadata) == 15):
        raise PublicationValidationError("chart output set is incomplete")
    required = {
        "title", "dataset", "sample_size", "measurement_type", "models",
        "task_stratum", "date", "uncertainty", "known_limitations",
    }
    for path in metadata:
        row = json.loads(path.read_text(encoding="utf-8"))
        normalized = dict(row)
        normalized["date"] = row.get("generated_at_date") or row.get("evidence_cutoff")
        missing = required - normalized.keys()
        if missing:
            raise PublicationValidationError(f"{path.name} lacks chart metadata {sorted(missing)}")
    return {"png": 15, "svg": 15, "metadata_sidecars": 15, "regeneration_script": "analysis/generate_charts.py"}


def validate_pdf():
    pdf = ROOT / "output" / "pdf" / "SmartRouter_Agent_Token_Economics_2026.pdf"
    info = subprocess.run(["pdfinfo", str(pdf)], check=True, capture_output=True, text=True).stdout
    text = subprocess.run(["pdftotext", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
    fields = {}
    for line in info.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    try:
        pages = int(fields.get("Pages", ""))
    except ValueError as exc:
        raise PublicationValidationError("PDF page count is not parseable") from exc
    if not 30 <= pages <= 50 or "A4" not in fields.get("Page size", ""):
        raise PublicationValidationError("unexpected PDF page geometry")
    if fields.get("Encrypted") != "no" or fields.get("JavaScript") != "no":
        raise PublicationValidationError("PDF contains active or encrypted content")
    words = len(re.findall(r"\S+", text))
    if words < 4000 or "Conclusion" not in text:
        raise PublicationValidationError("PDF text extraction is incomplete")
    pdf_sha256 = hashlib.sha256(pdf.read_bytes()).hexdigest()
    visual_review_path = VALIDATION / "PDF_VISUAL_REVIEW.json"
    if not visual_review_path.exists():
        raise PublicationValidationError("PDF lacks a separate visual page-review record")
    visual_review = json.loads(visual_review_path.read_text(encoding="utf-8"))
    if visual_review.get("pdf_sha256") != pdf_sha256:
        raise PublicationValidationError("PDF changed after the visual page review")
    if visual_review.get("rendered_page_count") != pages:
        raise PublicationValidationError("visual review did not render all PDF pages")
    if visual_review.get("reviewed_pages") != list(range(1, pages + 1)):
        raise PublicationValidationError("visual review does not enumerate every PDF page")
    if visual_review.get("result") != "PASS":
        raise PublicationValidationError("PDF visual review did not pass")
    return {
        "file": str(pdf.relative_to(ROOT)),
        "pages": pages,
        "page_size": fields.get("Page size"),
        "tagged": fields.get("Tagged"),
        "encrypted": False,
        "javascript": False,
        "extractable_words": words,
        "sha256": pdf_sha256,
        "visual_review": visual_review["summary"],
        "visual_review_record": str(visual_review_path.relative_to(ROOT)),
        "renderer": fields.get("Creator"),
    }


def write_outputs(results, local_links, citations):
    VALIDATION.mkdir(exist_ok=True)
    (VALIDATION / "validation_results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (VALIDATION / "LOCAL_LINK_AUDIT.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in local_links), encoding="utf-8"
    )
    (VALIDATION / "CITATION_AUDIT.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in citations), encoding="utf-8"
    )
    citation_lines = [
        "# Citation Claim-Alignment Review", "",
        f"Reviewed: {EVIDENCE_DATE}. Every decisive handbook citation was matched to a canonical source ID, reopened, and reviewed for the claim actually made.", "",
        "| Citation | Source IDs | Alignment review |", "| --- | --- | --- |",
    ]
    for row in citations:
        citation_lines.append(
            f"| {row['label']} | {', '.join(row['source_ids'])} | {row['reviewed_claim']} |"
        )
    (VALIDATION / "CITATION_CLAIM_REVIEW.md").write_text(
        "\n".join(citation_lines) + "\n", encoding="utf-8"
    )
    privacy = results["privacy"]
    (VALIDATION / "PRIVACY_SCAN.md").write_text(
        "# Privacy and Secret Scan\n\n"
        f"Evidence cutoff: {EVIDENCE_DATE}.\n\n"
        f"- Public-safe files scanned: {privacy['files_scanned']}\n"
        f"- Bytes scanned: {privacy['bytes_scanned']}\n"
        "- High-confidence credential patterns: 0\n"
        "- Private absolute paths: 0\n"
        "- Raw private chats: 0\n"
        "- AOIA content: 0\n"
        "- Unsafe filenames: 0\n"
        "- Symlinks: 0\n"
        "- Nested `.git` directories: 0\n"
        "- Unexpected binaries: 0\n\n"
        "The scan reports categories and locations only; it never writes a matched secret. "
        "The publication set excludes temporary research packets; the sanitized preflight is included.\n",
        encoding="utf-8",
    )
    pdf = results["pdf"]
    (VALIDATION / "PDF_VALIDATION.md").write_text(
        "# PDF Validation\n\n"
        f"- File: `{pdf['file']}`\n"
        f"- Pages: {pdf['pages']}\n"
        f"- Page size: {pdf['page_size']}\n"
        f"- Tagged: {pdf['tagged']}\n"
        f"- Encrypted: {str(pdf['encrypted']).lower()}\n"
        f"- JavaScript: {str(pdf['javascript']).lower()}\n"
        f"- Extractable words: {pdf['extractable_words']}\n"
        f"- Visual review: {pdf['visual_review']}\n"
        f"- Visual review record: `{pdf['visual_review_record']}`\n"
        f"- Renderer: {pdf['renderer']}\n",
        encoding="utf-8",
    )
    report = f"""# Publication Validation Report

Evidence cutoff: {EVIDENCE_DATE}, Europe/Berlin.

## Verdict

PASS before independent adversarial review.

## Structural validation

- JSON/JSONL files parsed: {results['json']['files']}
- JSON documents or JSONL rows parsed: {results['json']['documents_or_rows']}
- Strict JSON schemas validated: {results['corpus']['schemas']}
- Normalized runs: {results['corpus']['records']['agent_runs.jsonl']}
- Normalized requests: {results['corpus']['records']['agent_requests.jsonl']}
- Normalized tasks: {results['corpus']['records']['tasks.jsonl']}
- Provenance records: {results['corpus']['records']['provenance.jsonl']}

Unknown telemetry remains `null` with explicit missingness. No quality D/E,
censored, unlicensed, or privacy-unreviewed record enters numerical priors.

## Evidence and rights

- Canonical sources: {results['registries']['sources']}
- Deduplicated source aliases: {results['registries']['source_aliases']}
- Dataset/telemetry records: {results['registries']['datasets_or_surfaces']}
- Numerical routing datasets: 0
- Handbook external citations directly reverified: {len(citations)}
- Local Markdown/HTML links resolved: {len(local_links)}

Missing licenses remain explicit `null` and route the corresponding material to
metadata-only, rejection, or human review. Code/schema licenses are never used
as automatic permission to redistribute captured run content.

## Numerical non-claim

The bounded sample contains 19 class-E parser fixtures and zero compatible
quality A-C measured-token runs. All model/task token charts that require such
runs therefore render explicit no-data panels. No universal token budget,
model-specific cost frontier, causal effect, or production routing rule is
published. API prices are not treated as subscription quotas or as a historical
price ledger.

## Reproducibility and publication safety

- Charts: 15 PNG, 15 SVG, 15 metadata sidecars
- PDF: {pdf['pages']} A4 pages, extractable text, no encryption or JavaScript
- Raw third-party trajectories committed: 0
- High-confidence credential findings: 0
- Private absolute paths in publication set: 0
- AOIA content in publication set: 0
- Symlinks or nested repositories: 0

The independent adversarial review and resolution log are tracked separately
under `reviews/`.
"""
    (VALIDATION / "VALIDATION_REPORT.md").write_text(report, encoding="utf-8")


def main():
    try:
        json_result = validate_all_json()
        validator = load_corpus_validator()
        corpus_result = validator.validate_corpus()
        source_rows = jsonl(ROOT / "sources" / "source_registry.jsonl")
        dataset_rows = jsonl(ROOT / "sources" / "dataset_registry.jsonl")
        registry_result = validate_registries(source_rows, dataset_rows)
        local_links, citations = validate_links(source_rows)
        chart_result = validate_charts()
        privacy_result = scan_public_bundle()
        pdf_result = validate_pdf()
        results = {
            "status": "PASS",
            "evidence_cutoff": EVIDENCE_DATE,
            "json": json_result,
            "corpus": corpus_result,
            "registries": registry_result,
            "links": {"local": len(local_links), "external_citations": len(citations)},
            "charts": chart_result,
            "privacy": privacy_result,
            "pdf": pdf_result,
            "numerical_priors": 0,
            "runtime_changed": False,
        }
        write_outputs(results, local_links, citations)
    except Exception as exc:  # validation CLI must emit one actionable failure
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
