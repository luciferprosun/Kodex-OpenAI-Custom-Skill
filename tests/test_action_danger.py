
from smart_codex.scorer import score
from smart_codex.knowledge import load_rules


def test_explain_rm_rf_not_same_as_run_rm_rf():
    rules = load_rules()
    explain = score("explain what rm -rf does without running it", rules)
    run = score("run rm -rf on the build directory", rules)
    assert explain.profile == "security"  # still security/audit context
    assert run.risk_level == "critical"
    assert run.override is not None
