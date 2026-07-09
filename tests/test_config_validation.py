from smart_codex.profiles import validate_profile_data


def valid_data(**overrides):
    data = {
        "sandbox_mode": "read-only",
        "model_verbosity": "medium",
        "model_reasoning_effort": "medium",
        "approval_policy": "on-request",
    }
    data.update(overrides)
    return data


def test_rejects_isolated_sandbox():
    errors = validate_profile_data(valid_data(sandbox_mode="isolated"))
    assert errors


def test_rejects_standard_sandbox():
    errors = validate_profile_data(valid_data(sandbox_mode="standard"))
    assert errors


def test_rejects_verbose_verbosity():
    errors = validate_profile_data(valid_data(model_verbosity="verbose"))
    assert errors


def test_rejects_none_reasoning_effort():
    errors = validate_profile_data(valid_data(model_reasoning_effort="none"))
    assert errors


def test_rejects_danger_full_access_for_v0():
    errors = validate_profile_data(valid_data(sandbox_mode="danger-full-access"), v0=True)
    assert errors
    assert any("danger-full-access" in error for error in errors)

