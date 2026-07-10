from smart_codex.scorer import score


def test_math_signals_beat_normal_text_and_refactor_terms():
    result = score("summarize this equation and also refactor the neutrino module")

    assert result.category == "math_theory"
    assert result.profile == "math"


def test_grant_signals_beat_simple_text():
    result = score("quick grant note: also double check the budget numbers add up")

    assert result.category == "grant_work"
    assert result.profile == "research"


def test_repo_signals_beat_writing_tasks():
    result = score("write a short story, then commit it to the repo")

    assert result.category == "repo_operations"
    assert result.profile == "repo"
