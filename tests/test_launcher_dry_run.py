from smart_codex.config import CODEX_BINARY
from smart_codex.launcher import CodexCommand, build_codex_command


def test_dry_run_builds_argv_but_does_not_execute():
    command = build_codex_command(
        "fix frontend bug",
        profile="standard",
        sandbox="workspace-write",
        execute=False,
    )
    assert isinstance(command, CodexCommand)
    assert command.execute is False
    assert command.argv[:3] == [CODEX_BINARY, "--profile", "standard"]


def test_argv_uses_list_args_not_shell_string():
    command = build_codex_command("fix frontend bug", profile="standard")
    assert isinstance(command.argv, list)
    assert all(isinstance(item, str) for item in command.argv)


def test_prompt_with_shell_metacharacters_is_one_arg():
    prompt = "fix bug; rm -rf /"
    command = build_codex_command(prompt, profile="security", sandbox="read-only")
    assert command.argv[-1] == prompt
    assert command.argv.count(prompt) == 1
