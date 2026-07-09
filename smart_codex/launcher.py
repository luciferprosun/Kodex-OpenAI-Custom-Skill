from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from .config import CODEX_BINARY


@dataclass(frozen=True)
class CodexCommand:
    argv: list[str]
    execute: bool


def build_codex_command(
    prompt: str,
    *,
    profile: str,
    model: str | None = None,
    sandbox: str | None = None,
    cd: str | Path | None = None,
    configs: list[str] | None = None,
    approval_policy: str | None = None,
    execute: bool = False,
) -> CodexCommand:
    argv = [CODEX_BINARY, "--profile", profile]

    if model:
        argv.extend(["--model", model])
    if sandbox:
        argv.extend(["--sandbox", sandbox])
    if cd:
        argv.extend(["--cd", str(cd)])
    if approval_policy:
        argv.extend(["--ask-for-approval", approval_policy])
    for item in configs or []:
        argv.extend(["--config", item])

    argv.append(prompt)
    return CodexCommand(argv=argv, execute=execute)


def run_codex_command(command: CodexCommand) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command.argv,
        shell=False,
        check=False,
        text=True,
    )

