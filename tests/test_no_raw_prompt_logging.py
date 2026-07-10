import json

from smart_codex.logging_safe import write_decision_log
from smart_codex.router import route_prompt


def test_fake_secret_prompt_never_appears_in_log(tmp_path):
    prompt = "audit this fake API key sk-test-123 and do not store it"
    decision = route_prompt(prompt)
    log_path = tmp_path / "decisions.jsonl"

    write_decision_log(decision, log_path=log_path)

    text = log_path.read_text(encoding="utf-8")
    entry = json.loads(text)
    assert "sk-test-123" not in text
    assert prompt not in text
    assert entry["prompt_hash"] == decision.prompt_hash
    assert entry["action_danger"] == decision.action_danger
