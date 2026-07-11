from smart_codex.router import route_prompt


def test_unknown_no_risk_routes_standard_with_warning():
    result = route_prompt("make it better")

    assert result.category == "unknown"
    assert result.selected_profile == "standard"
    assert result.warning == "low confidence route"


def test_unknown_with_risk_signal_routes_security_read_only():
    result = route_prompt("update the thing with the access stuff")

    assert result.category == "security_audit"
    assert result.risk == "medium"
    assert result.selected_profile == "security"
    assert result.sandbox_mode == "read-only"
