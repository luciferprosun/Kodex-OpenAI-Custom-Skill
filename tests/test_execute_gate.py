from smart_codex.launcher import build_codex_command


def test_execute_false_by_default_and_prompt_is_one_arg():
    prompt = "fix bug; rm -rf /"
    command = build_codex_command(prompt, profile="security", sandbox="read-only")

    assert command.execute is False
    assert command.argv[-1] == prompt
    assert command.argv.count(prompt) == 1


def test_execute_true_only_when_explicitly_requested():
    command = build_codex_command(
        "fix frontend bug",
        profile="standard",
        sandbox="workspace-write",
        execute=True,
    )

    assert command.execute is True
