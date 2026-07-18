#!/usr/bin/env python3
"""Generate publication-safe charts, including explicit no-data panels."""

from __future__ import annotations

import html
import json
import textwrap
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from coverage_status import failure_coverage_status


ROOT = Path(__file__).resolve().parents[1]
CHARTS = ROOT / "charts"
META = CHARTS / "metadata"
WIDTH, HEIGHT = 1600, 1000
BG, INK, MUTED = "#F5F7FA", "#102A43", "#627D98"
GRID, ACCENT, ACCENT_2, WARN = "#D9E2EC", "#007F86", "#2F80ED", "#C05621"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(size, bold=False):
    path = FONT_BOLD if bold else FONT_REGULAR
    return ImageFont.truetype(path, size=size)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def wrap(draw, text, xy, width_chars, font_obj, fill=INK, spacing=8):
    lines = []
    for paragraph in str(text).splitlines() or [""]:
        lines.extend(textwrap.wrap(paragraph, width=width_chars, break_long_words=False, break_on_hyphens=False) or [""])
    draw.multiline_text(xy, "\n".join(lines), font=font_obj, fill=fill, spacing=spacing)


def base_canvas(title, subtitle):
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((42, 34, WIDTH - 42, HEIGHT - 34), radius=28, fill="#FFFFFF", outline=GRID, width=2)
    draw.rectangle((42, 34, 62, HEIGHT - 34), fill=ACCENT)
    draw.text((98, 78), title, font=font(45, True), fill=INK)
    wrap(draw, subtitle, (100, 142), 105, font(23), MUTED, 5)
    return image, draw


def footer(draw, text):
    draw.line((100, 900, 1500, 900), fill=GRID, width=2)
    wrap(draw, text, (100, 920), 140, font(18), MUTED, 3)


def write_svg(path, title, subtitle, body_lines, footer_text):
    escaped = [html.escape(str(line)) for line in body_lines]
    body = "".join(
        f'<text x="120" y="{300 + index * 54}" font-size="28" fill="#102A43">{line}</text>'
        for index, line in enumerate(escaped)
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1000" viewBox="0 0 1600 1000">
<rect width="1600" height="1000" fill="#F5F7FA"/>
<rect x="42" y="34" width="1516" height="932" rx="28" fill="#FFFFFF" stroke="#D9E2EC" stroke-width="2"/>
<rect x="42" y="34" width="20" height="932" fill="#007F86"/>
<text x="98" y="115" font-family="DejaVu Sans" font-weight="bold" font-size="45" fill="#102A43">{html.escape(title)}</text>
<text x="100" y="175" font-family="DejaVu Sans" font-size="23" fill="#627D98">{html.escape(subtitle[:120])}</text>
{body}
<line x1="100" y1="900" x2="1500" y2="900" stroke="#D9E2EC" stroke-width="2"/>
<text x="100" y="940" font-family="DejaVu Sans" font-size="17" fill="#627D98">{html.escape(footer_text[:170])}</text>
</svg>\n'''
    path.write_text(svg, encoding="utf-8")


def save_chart(stem, image, metadata, svg_title, svg_subtitle, svg_lines, footer_text):
    image.save(CHARTS / f"{stem}.png", optimize=True)
    write_svg(CHARTS / f"{stem}.svg", svg_title, svg_subtitle, svg_lines, footer_text)
    (META / f"{stem}.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def common_metadata(title, n, measurement, limitation, datasets=None):
    return {
        "title": title,
        "evidence_cutoff": "2026-07-18",
        "generated_at_date": "2026-07-18",
        "dataset": datasets or [],
        "sample_size": n,
        "measurement_type": measurement,
        "models": [],
        "task_stratum": None,
        "uncertainty": "not estimable" if n == 0 else "registry-count uncertainty is not a sampling interval",
        "known_limitations": [limitation],
        "numerical_prior_eligible": False,
    }


def no_data_chart(stem, title, requested_metric):
    subtitle = "Required analysis retained; quantitative comparison withheld because no compatible public A–C run sample passed the evidence and rights gates."
    image, draw = base_canvas(title, subtitle)
    left, top, right, bottom = 180, 300, 1420, 790
    for step in range(6):
        y = top + step * (bottom - top) / 5
        draw.line((left, y, right, y), fill=GRID, width=2)
    draw.line((left, top, left, bottom), fill=MUTED, width=3)
    draw.line((left, bottom, right, bottom), fill=MUTED, width=3)
    draw.rounded_rectangle((420, 425, 1180, 650), radius=24, fill="#FFF8F0", outline="#F6AD55", width=3)
    draw.text((534, 474), "NO COMPARABLE A–C RUNS", font=font(37, True), fill=WARN)
    wrap(draw, f"{requested_metric}: null — local telemetry 2B is required.", (510, 545), 55, font(25), INK, 5)
    foot = "Registry: 41 discovery records | admitted numerical runs: n=0 | measurement: unavailable | uncertainty: not estimable"
    footer(draw, foot)
    metadata = common_metadata(title, 0, "no compatible measured public run records", "An empty panel is intentional; it prevents aggregate, estimated, or unlicensed records from becoming numerical priors.")
    save_chart(stem, image, metadata, title, subtitle, ["NO COMPARABLE A-C RUNS", f"{requested_metric}: null", "Local telemetry 2B required"], foot)


def historical_chart(coverage):
    title = "Historical agent-trajectory coverage"
    subtitle = "Public artifacts become richer over time, but trajectory availability and token telemetry remain different things."
    image, draw = base_canvas(title, subtitle)
    eras = coverage["historical_eras"]
    colors = ["#9FB3C8", "#9FB3C8", "#F6AD55", "#F6AD55", "#D69E2E", "#2F80ED", "#007F86"]
    y = 255
    for index, era in enumerate(eras):
        draw.text((100, y), era["period"], font=font(19, True), fill=MUTED)
        draw.rounded_rectangle((360, y - 5, 1450, y + 34), radius=12, fill="#EDF2F7")
        width = 240 + index * 120
        draw.rounded_rectangle((360, y - 5, min(1450, 360 + width), y + 34), radius=12, fill=colors[index])
        label = era["era"].replace("_", " ")
        draw.text((380, y + 2), label, font=font(18, True), fill="#FFFFFF" if index > 1 else INK)
        y += 84
    foot = "n=7 historical eras | measurement: primary-source discovery map | no token totals inferred for missing eras"
    footer(draw, foot)
    metadata = common_metadata(title, 7, "historical source-discovery classification", "Bars encode evidence-era progression, not model capability or token volume.")
    save_chart("11_historical_agent_trajectory_coverage", image, metadata, title, subtitle, [f"{era['period']}: {era['run_level_token_telemetry']}" for era in eras], foot)


def missingness_heatmap(rows):
    title = "Dataset telemetry missingness heatmap"
    subtitle = "Field status across all discovery records. Presence does not imply compatible semantics, objective outcomes, or permission for numerical routing."
    image, draw = base_canvas(title, subtitle)
    columns = ["token", "cost", "timing", "tool_call", "success", "verifier", "trajectory", "failure"]
    x0, y0, cell_w, cell_h = 480, 230, 116, 15
    for col_index, column in enumerate(columns):
        draw.text((x0 + col_index * cell_w, y0 - 42), column, font=font(15, True), fill=INK)
    palette = {"present": "#007F86", "present_untyped": "#63B3ED", "absent": "#CBD5E0", "unknown": "#F6AD55", "blocked": "#C05621"}
    for row_index, row in enumerate(rows):
        y = y0 + row_index * cell_h
        draw.text((100, y - 2), row["dataset_id"][:34], font=font(11), fill=MUTED)
        statuses = [
            row["token_fields_status"], row["cost_fields_status"], row["timing_fields_status"],
            row["tool_call_fields_status"], row["success_labels_status"], row["verifiers_status"],
            row["raw_trajectory_status"],
            failure_coverage_status(row.get("failure_trajectory_coverage")),
        ]
        for col_index, status in enumerate(statuses):
            color = "#C05621" if row["raw_acquisition_status"] == "blocked" and col_index == 6 else palette.get(status, "#F6AD55")
            draw.rectangle((x0 + col_index * cell_w, y, x0 + col_index * cell_w + cell_w - 5, y + cell_h - 2), fill=color)
    legend_y = 865
    for index, (label, color) in enumerate(palette.items()):
        x = 610 + index * 180
        draw.rectangle((x, legend_y, x + 24, legend_y + 24), fill=color)
        draw.text((x + 32, legend_y + 2), label, font=font(14), fill=INK)
    foot = "n=41 registry records | measurement: field-status metadata | orange/grey cells are unknown/absent, not zero"
    footer(draw, foot)
    metadata = common_metadata(title, len(rows), "registry field-status metadata", "Field presence is not a measurement-quality score and does not establish semantic comparability.", [row["dataset_id"] for row in rows])
    save_chart("12_dataset_missingness_heatmap", image, metadata, title, subtitle, ["41 discovery records", "8 telemetry/outcome dimensions", "Presence is not comparability"], foot)


def evidence_quality_chart(rows):
    title = "Public evidence quality by source record"
    subtitle = "Preliminary run-evidence quality classes. Unknown means the candidate was not normalized to a run-quality class."
    image, draw = base_canvas(title, subtitle)
    counts = Counter(row.get("quality_class") or "unknown" for row in rows)
    labels = ["A", "B", "C", "D", "E", "unknown"]
    maximum = max(counts.values()) or 1
    for index, label in enumerate(labels):
        y = 250 + index * 100
        draw.text((170, y + 12), label, font=font(24, True), fill=INK)
        draw.rounded_rectangle((250, y, 1370, y + 56), radius=14, fill="#EDF2F7")
        bar_width = int(1120 * counts[label] / maximum)
        color = ACCENT if label in {"A", "B", "C"} else (WARN if label in {"D", "E"} else "#9FB3C8")
        if bar_width:
            draw.rounded_rectangle((250, y, 250 + bar_width, y + 56), radius=14, fill=color)
        draw.text((1390, y + 12), str(counts[label]), font=font(24, True), fill=INK)
    foot = "n=41 registry records | A–C admitted numerical runs: 0 | classes describe telemetry evidence, not model capability"
    footer(draw, foot)
    metadata = common_metadata(title, len(rows), "registry quality classification", "Unknown and D/E records are excluded from numerical priors; class is not a benchmark score.", [row["dataset_id"] for row in rows])
    metadata["counts"] = dict(counts)
    save_chart("13_public_evidence_quality", image, metadata, title, subtitle, [f"{label}: {counts[label]}" for label in labels], foot)


def escalation_frontier():
    title = "Proposed model-escalation frontier"
    subtitle = "Research objective only. The frontier cannot be calibrated until complete attempt chains and verifier outcomes are collected locally."
    image, draw = base_canvas(title, subtitle)
    left, top, right, bottom = 200, 270, 1420, 790
    draw.line((left, bottom, right, bottom), fill=INK, width=3)
    draw.line((left, top, left, bottom), fill=INK, width=3)
    draw.text((600, 820), "Expected accepted-task cost", font=font(22, True), fill=INK)
    draw.text((75, 460), "Success / risk\nconstraint", font=font(20, True), fill=INK)
    points = [(350, 700), (650, 610), (950, 455), (1260, 340)]
    for a, b in zip(points, points[1:]):
        draw.line((*a, *b), fill="#9FB3C8", width=6)
    for index, (x, y) in enumerate(points, 1):
        draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill="#FFFFFF", outline=MUTED, width=4)
        draw.text((x - 7, y - 12), str(index), font=font(17, True), fill=MUTED)
    draw.rounded_rectangle((520, 390, 1100, 570), radius=22, fill="#FFF8F0", outline="#F6AD55", width=3)
    draw.text((604, 430), "UNCALIBRATED — n=0", font=font(34, True), fill=WARN)
    wrap(draw, "Do not attach model names or prices until 2B supplies compatible route chains.", (590, 492), 45, font(22), INK, 4)
    foot = "conceptual schematic | models: none assigned | uncertainty: unbounded | runtime integration: none"
    footer(draw, foot)
    metadata = common_metadata(title, 0, "conceptual research objective", "The line is schematic and must not be read as an empirical efficiency frontier.")
    save_chart("14_proposed_model_escalation_frontier", image, metadata, title, subtitle, ["UNCALIBRATED — n=0", "No model names assigned", "Local route chains required"], foot)


def local_fields_chart(coverage):
    title = "Local telemetry fields still required"
    subtitle = "Measurements public datasets cannot jointly provide with trustworthy provenance, outcomes, and complete failure coverage."
    image, draw = base_canvas(title, subtitle)
    groups = {
        "Token accounting": ["cached / cache writes", "reasoning vs visible output", "history/tool/compaction attribution"],
        "Route economics": ["complete retry chains", "escalation transitions", "price-date-correct components"],
        "Outcome evidence": ["objective verifier", "censored status", "human review and final acceptance"],
        "Runtime state": ["context occupancy", "tool errors/repeats", "wall time and rate-limit waits"],
    }
    x_positions = [110, 485, 860, 1235]
    for (heading, fields), x in zip(groups.items(), x_positions):
        draw.rounded_rectangle((x, 270, x + 320, 760), radius=24, fill="#EDF7F7", outline="#9ED7D9", width=2)
        wrap(draw, heading, (x + 24, 305), 20, font(25, True), ACCENT, 5)
        y = 405
        for field_name in fields:
            draw.ellipse((x + 28, y + 8, x + 44, y + 24), fill=ACCENT_2)
            wrap(draw, field_name, (x + 58, y), 22, font(20), INK, 4)
            y += 105
    foot = "4 collection groups | 12 priority field families | raw prompts and hidden reasoning text are explicitly excluded"
    footer(draw, foot)
    metadata = common_metadata(title, 12, "requirements derived from public missing-data map", "The list is a collection specification, not observed local telemetry.")
    metadata["critical_missing_measurements"] = coverage["critical_missing_measurements"]
    save_chart("15_local_telemetry_fields_required", image, metadata, title, subtitle, list(groups), foot)


def write_index(stems):
    lines = [
        "# Chart Index", "",
        "All charts were generated by `analysis/generate_charts.py`. PNG is used in the handbook/PDF; SVG and JSON sidecars preserve accessible text and provenance.", "",
        "Charts 1–10 are intentional no-data panels because no compatible public A–C run records passed the numerical and rights gates. Chart 14 is explicitly schematic.", "",
        "| Chart | PNG | SVG | Metadata |", "| --- | --- | --- | --- |",
    ]
    for stem, title in stems:
        lines.append(f"| {title} | [{stem}.png]({stem}.png) | [{stem}.svg]({stem}.svg) | [JSON](metadata/{stem}.json) |")
    lines.append("")
    (CHARTS / "CHART_INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    CHARTS.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)
    rows = load_jsonl(ROOT / "sources" / "dataset_registry.jsonl")
    coverage = load_json(ROOT / "sources" / "coverage_map.json")
    no_data_specs = [
        ("01_token_usage_by_task_model", "Token usage by task class and model", "conditional token distribution"),
        ("02_p50_p90_total_tokens", "p50 / p90 total tokens", "cluster-bootstrap token quantiles"),
        ("03_tokens_per_accepted_task", "Tokens per accepted task", "complete-chain tokens per accepted task"),
        ("04_cost_per_accepted_task", "Cost per accepted task", "complete-chain accepted-task cost"),
        ("05_success_vs_token_consumption", "Success probability versus token consumption", "out-of-task/source success calibration"),
        ("06_cache_ratio_by_workload", "Cache ratio by workload", "compatible cached-input / input ratio"),
        ("07_tool_calls_vs_total_tokens", "Tool calls versus total tokens", "tool-intensity association"),
        ("08_repository_size_vs_input_tokens", "Repository size versus input tokens", "repository-size association"),
        ("09_retry_count_vs_accepted_cost", "Retry count versus accepted-task cost", "complete retry-chain economics"),
        ("10_agent_count_vs_tokens_success", "Agent count versus total tokens and success", "multi-agent amplification and outcome"),
    ]
    for stem, title, metric in no_data_specs:
        no_data_chart(stem, title, metric)
    historical_chart(coverage)
    missingness_heatmap(rows)
    evidence_quality_chart(rows)
    escalation_frontier()
    local_fields_chart(coverage)
    stems = [(stem, title) for stem, title, _ in no_data_specs] + [
        ("11_historical_agent_trajectory_coverage", "Historical agent-trajectory coverage"),
        ("12_dataset_missingness_heatmap", "Dataset telemetry missingness heatmap"),
        ("13_public_evidence_quality", "Public evidence quality by source record"),
        ("14_proposed_model_escalation_frontier", "Proposed model-escalation frontier"),
        ("15_local_telemetry_fields_required", "Local telemetry fields still required"),
    ]
    write_index(stems)
    print(json.dumps({"status": "PASS", "charts": len(stems), "png": len(stems), "svg": len(stems)}, indent=2))


if __name__ == "__main__":
    main()
