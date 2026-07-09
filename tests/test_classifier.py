from smart_codex.classifier import classify_prompt


def test_fix_frontend_bug_classifies_as_normal_coding():
    result = classify_prompt("fix frontend bug")
    assert result.category == "normal_coding"
    assert result.confidence > 0


def test_security_prompt_classifies_as_security_audit():
    result = classify_prompt("audit repo for secrets and sandbox risks")
    assert result.category == "security_audit"
    assert "secret" in result.matched_keywords


def test_email_reply_classifies_as_email():
    result = classify_prompt("write an email reply")
    assert result.category == "email"


def test_unknown_text_has_low_confidence_warning():
    result = classify_prompt("nonsense blorple without known task")
    assert result.category == "unknown"
    assert result.confidence <= 0.30
    assert result.warning == "low confidence route"


def test_polish_debug_prompt_classifies_as_normal_coding():
    result = classify_prompt("napraw błąd frontend, bo nie działa")
    assert result.category == "normal_coding"
    assert "blad" in result.matched_keywords or "nie dziala" in result.matched_keywords


def test_polish_architecture_prompt_classifies_as_architecture():
    result = classify_prompt("zaprojektuj architekturę API i cache dla systemu")
    assert result.category == "architecture"


def test_math_symbols_classify_as_math_theory():
    result = classify_prompt("oblicz ∫ x dx i pokaż równanie")
    assert result.category == "math_theory"
    assert "math symbol" in result.matched_keywords or "rownanie" in result.matched_keywords


def test_code_review_polish_prompt_classifies_as_normal_coding():
    result = classify_prompt("sprawdź kod i oceń czy to poprawne")
    assert result.category == "normal_coding"


def test_data_analysis_prompt_maps_to_research_category():
    result = classify_prompt("analizuj CSV w pandas dataframe i zrób histogram")
    assert result.category == "research"
