import subprocess

from smart_codex.model_audit import audit_models, extract_json_from_text, normalize_models


def test_parse_clean_json_object():
    data = extract_json_from_text('{"models":[{"id":"gpt-test","provider":"openai"}]}')
    models = normalize_models(data)
    assert models[0]["id"] == "gpt-test"


def test_parse_clean_json_list():
    data = extract_json_from_text('[{"id":"gpt-test"}]')
    models = normalize_models(data)
    assert models[0]["id"] == "gpt-test"


def test_parse_json_embedded_in_noisy_text():
    data = extract_json_from_text('before\n{"models":[{"id":"gpt-test"}]}\nafter')
    models = normalize_models(data)
    assert models[0]["id"] == "gpt-test"


def test_parse_codex_slug_display_name_schema():
    data = extract_json_from_text(
        '{"models":[{"slug":"gpt-test","display_name":"GPT Test","visibility":"list",'
        '"supported_reasoning_levels":[{"effort":"low"},{"effort":"high"}]}]}'
    )
    models = normalize_models(data)
    assert models[0]["id"] == "gpt-test"
    assert models[0]["name"] == "GPT Test"
    assert models[0]["visible"] is True
    assert models[0]["supported_reasoning_effort"] == ["low", "high"]


def test_handles_empty_output(tmp_path):
    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    result = audit_models(output_path=tmp_path / "models.json", runner=runner)
    assert result["ok"] is False
    assert "empty" in result["error"] or "parseable" in result["error"]


def test_handles_command_not_found(tmp_path):
    def runner(*args, **kwargs):
        raise FileNotFoundError()

    result = audit_models(output_path=tmp_path / "models.json", runner=runner)
    assert result["ok"] is False
    assert result["error"] == "codex command not found"


def test_handles_nonzero_return_code(tmp_path):
    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 2, stdout="", stderr="failed")

    result = audit_models(output_path=tmp_path / "models.json", runner=runner)
    assert result["ok"] is False
    assert "return code" in result["error"]


def test_writes_parseable_catalog(tmp_path):
    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0],
            0,
            stdout='{"models":[{"id":"gpt-test","name":"Test","provider":"openai"}]}',
            stderr="",
        )

    output = tmp_path / "model_catalog.json"
    result = audit_models(output_path=output, runner=runner)
    assert result["ok"] is True
    assert output.exists()
