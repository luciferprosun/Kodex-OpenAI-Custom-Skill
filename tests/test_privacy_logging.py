import json

from smart_codex.logging_safe import write_decision_log
from smart_codex.router import route_prompt


def test_log_contains_hash_and_no_raw_prompt(tmp_path):
    prompt = "write an email reply with private details"
    decision = route_prompt(prompt)
    log_path = tmp_path / "decisions.jsonl"

    wrote = write_decision_log(decision, log_path=log_path, enabled=True)

    assert wrote is True
    text = log_path.read_text(encoding="utf-8")
    assert prompt not in text
    entry = json.loads(text)
    assert entry["prompt_hash"] == decision.prompt_hash
    assert entry["prompt_redacted"] is None


def test_no_log_disables_write(tmp_path):
    decision = route_prompt("write an email reply")
    log_path = tmp_path / "decisions.jsonl"

    wrote = write_decision_log(decision, log_path=log_path, enabled=False)

    assert wrote is False
    assert not log_path.exists()

