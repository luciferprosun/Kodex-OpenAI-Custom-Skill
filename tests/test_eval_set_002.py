
"""Reference eval-set test. Codex should adapt route_prompt import to current repo API."""
import json
from pathlib import Path

from smart_codex.scorer import score
from smart_codex.knowledge import load_rules

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "rules" / "eval_set_002.jsonl"


def test_eval_set_002_routes_expected_fields():
    rules = load_rules(ROOT)
    failures = []
    for i, line in enumerate(EVAL.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        case = json.loads(line)
        result = score(case["prompt"], rules)
        actual = {
            "category": result.category,
            "profile": result.profile,
            "risk": result.risk_level,
            "complexity": result.complexity_level,
        }
        expected = {
            "category": case["expected_category"],
            "profile": case["expected_profile"],
            "risk": case["expected_risk"],
            "complexity": case["expected_complexity"],
        }
        if actual != expected:
            failures.append((i, case["prompt"], expected, actual, case.get("reason")))
    assert not failures, "Eval failures:\n" + "\n".join(map(str, failures[:20]))
