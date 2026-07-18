#!/usr/bin/env python3
"""Render the Markdown handbook as print-ready HTML."""

from __future__ import annotations

import json
from pathlib import Path

import markdown


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "handbook" / "SMARTROUTER_AGENT_TOKEN_ECONOMICS.md"
OUTPUT = ROOT / "handbook" / "SMARTROUTER_AGENT_TOKEN_ECONOMICS.html"

CSS = r"""
@page { size: A4; margin: 17mm 15mm 20mm; }
* { box-sizing: border-box; }
html { color: #102a43; background: #eef2f6; font-family: Inter, "DejaVu Sans", Arial, sans-serif; }
body { margin: 0 auto; max-width: 1120px; background: white; font-size: 10.4pt; line-height: 1.5; }
.cover { min-height: 255mm; padding: 30mm 18mm 20mm; display: flex; flex-direction: column; justify-content: space-between; break-after: page; background: linear-gradient(145deg, #102a43 0%, #164e63 62%, #007f86 100%); color: white; }
.cover .eyebrow { color: #99f6e4; font-size: 12pt; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
.cover h1 { color: white; font-size: 34pt; line-height: 1.08; margin: 10mm 0 5mm; border: 0; }
.cover h2 { color: #d9f5f2; font-size: 17pt; line-height: 1.35; margin: 0; border: 0; break-before: auto; }
.cover .meta { border-top: 1px solid rgba(255,255,255,.35); padding-top: 7mm; font-size: 10pt; color: #d9e2ec; }
nav.toc { break-after: page; padding: 8mm 5mm 0; }
nav.toc h2 { break-before: auto; margin-top: 0; }
nav.toc ul { columns: 2; column-gap: 12mm; padding-left: 6mm; }
nav.toc li { break-inside: avoid; margin: 1.5mm 0; }
nav.toc a { color: #0f6170; text-decoration: none; }
h2 { color: #0f6170; font-size: 20pt; line-height: 1.2; margin: 0 0 5mm; padding-top: 2mm; break-before: page; border-bottom: 2px solid #9ed7d9; padding-bottom: 2.5mm; }
h3 { color: #164e63; font-size: 13.5pt; margin: 7mm 0 2.5mm; break-after: avoid; }
h4 { color: #334e68; font-size: 11.5pt; margin: 5mm 0 2mm; break-after: avoid; }
p, ul, ol { margin-top: 0; margin-bottom: 3.6mm; }
ul, ol { padding-left: 6mm; }
li { margin-bottom: 1.2mm; }
blockquote { margin: 5mm 0; padding: 4mm 5mm; border-left: 4px solid #00a6a6; background: #edf7f7; font-size: 12pt; color: #164e63; break-inside: avoid; }
code { background: #eef2f6; border-radius: 3px; padding: .4mm 1mm; font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; overflow-wrap: anywhere; }
pre { background: #102a43; color: #f0f4f8; border-radius: 7px; padding: 4mm; white-space: pre-wrap; break-inside: avoid; }
pre code { background: transparent; color: inherit; padding: 0; }
table { width: 100%; border-collapse: collapse; margin: 4mm 0 5mm; font-size: 8.4pt; break-inside: avoid-page; }
th { background: #164e63; color: white; text-align: left; }
th, td { border: 1px solid #bcccdc; padding: 2mm 2.2mm; vertical-align: top; }
tr:nth-child(even) td { background: #f5f7fa; }
img { display: block; width: 100%; max-height: 172mm; object-fit: contain; margin: 5mm auto 6mm; border: 1px solid #d9e2ec; border-radius: 5px; break-inside: avoid; }
a { color: #006d77; overflow-wrap: anywhere; }
.chapter-body { padding: 0 5mm; }
p, li { orphans: 3; widows: 3; }
@media screen { body { padding: 0 18mm 20mm; box-shadow: 0 0 40px rgba(16,42,67,.12); } .cover { margin: 0 -18mm; } }
@media print { html, body { background: white; } body { max-width: none; } .cover { margin: -17mm -15mm -20mm; min-height: 297mm; padding: 42mm 30mm 28mm; } }
"""


def main():
    source = SOURCE.read_text(encoding="utf-8")
    body_markdown = source[source.index("## Executive Summary"):]
    engine = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        extension_configs={"toc": {"permalink": False}},
    )
    body = engine.convert(body_markdown)
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>SmartRouter Agent Token Economics 2026</title><style>{CSS}</style></head>
<body>
<section class="cover"><div><div class="eyebrow">SmartRouter Research 2A</div><h1>Agent Token Economics 2026</h1><h2>Public trajectory corpus, task-cost model, and telemetry handbook</h2></div><div class="meta"><strong>Version 2A</strong><br>Evidence cutoff: 2026-07-18 · Europe/Berlin<br><br>Independent community research. Not an official OpenAI publication. No production routing behavior changed.</div></section>
<nav class="toc"><h2>Contents</h2>{engine.toc}</nav>
<main class="chapter-body">{body}</main>
</body></html>"""
    OUTPUT.write_text(document, encoding="utf-8")
    print(json.dumps({"status": "PASS", "html": str(OUTPUT), "bytes": OUTPUT.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
