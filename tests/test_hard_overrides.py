
from smart_codex.scorer import check_hard_override, score
from smart_codex.knowledge import load_rules


def test_secret_override_beats_benign_category():
    prompt = "Please write a nice email and include this API key check"
    result = score(prompt, load_rules())
    assert result.profile == "security"
    assert result.risk_level in {"high", "critical"}
    assert result.override is not None


def test_rm_rf_override_is_critical_security():
    result = score("run rm -rf on the build directory", load_rules())
    assert result.profile == "security"
    assert result.risk_level == "critical"
    assert "REQUIRES_CONFIRMATION" in result.warnings
