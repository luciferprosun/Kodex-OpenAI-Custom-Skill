from smart_codex.risk import assess_risk


def test_delete_all_files_is_high_risk():
    result = assess_risk("delete all files", "unknown")
    assert result.risk == "high"


def test_audit_repo_secrets_is_high_risk():
    result = assess_risk("audit repo secrets", "security_audit")
    assert result.risk == "high"


def test_normal_coding_is_low_or_medium_risk():
    result = assess_risk("fix frontend bug", "normal_coding")
    assert result.risk in {"low", "medium"}


def test_repo_operation_is_medium_risk():
    result = assess_risk("commit these changes on a branch", "repo_operations")
    assert result.risk == "medium"

