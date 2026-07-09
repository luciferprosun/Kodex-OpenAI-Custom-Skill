import json
from pathlib import Path

from smart_codex.router import route_prompt


def test_eval_set_001_routes_as_expected():
    path = Path(__file__).resolve().parents[1] / "rules" / "eval_set_001.jsonl"
    failures = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        result = route_prompt(item["prompt"])
        checks = {
            "category": (result.category, item["expected_category"]),
            "profile": (result.selected_profile, item["expected_profile"]),
            "risk": (result.risk, item["expected_risk"]),
        }
        for field, (actual, expected) in checks.items():
            if actual != expected:
                failures.append(
                    f"line {line_number} {field}: expected {expected!r}, got {actual!r} for {item['prompt']!r}"
                )
    assert not failures, "\n".join(failures)

