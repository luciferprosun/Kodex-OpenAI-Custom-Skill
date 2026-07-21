"""Thin ``codex-smart`` launcher for the unmodified official Codex CLI."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
from typing import Callable, Mapping, Sequence

from .session_control import (
    WRAPPER_MODE_ENV,
    WRAPPER_MODE_VALUE,
    SessionControlError,
    SessionControlStore,
    default_state_root,
)


class CodexSmartLaunchError(RuntimeError):
    """Sanitized wrapper-resolution or launch failure."""


def _same_executable(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except (FileNotFoundError, OSError):
        return left.resolve(strict=False) == right.resolve(strict=False)


def resolve_official_codex(
    *,
    search_path: str | None = None,
    wrapper_executable: Path | None = None,
) -> Path:
    resolved = shutil.which("codex", path=search_path)
    if resolved is None:
        raise CodexSmartLaunchError("OFFICIAL_CODEX_NOT_FOUND")
    candidate = Path(resolved)
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise CodexSmartLaunchError("OFFICIAL_CODEX_NOT_EXECUTABLE")

    wrapper_candidates: list[Path] = []
    if wrapper_executable is not None:
        wrapper_candidates.append(Path(wrapper_executable))
    elif sys.argv and sys.argv[0]:
        wrapper_candidates.append(Path(sys.argv[0]))
    installed_wrapper = shutil.which("codex-smart", path=search_path)
    if installed_wrapper is not None:
        wrapper_candidates.append(Path(installed_wrapper))
    if any(_same_executable(candidate, wrapper) for wrapper in wrapper_candidates):
        raise CodexSmartLaunchError("RECURSIVE_CODEX_WRAPPER_RESOLUTION")
    return candidate.resolve(strict=True)


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    execve: Callable[[str, list[str], dict[str, str]], object] = os.execve,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    environment = dict(os.environ if environ is None else environ)
    if WRAPPER_MODE_ENV in environment:
        print(
            "codex-smart failed safely: RECURSIVE_CODEX_WRAPPER_INVOCATION",
            file=sys.stderr,
        )
        return 2
    try:
        # Loading validates the local control location. Missing or malformed
        # state itself remains a safe OFF/OFF snapshot.
        SessionControlStore(default_state_root(environ=environment)).read()
        official = resolve_official_codex(
            search_path=environment.get("PATH"),
            wrapper_executable=Path(sys.argv[0]) if sys.argv and sys.argv[0] else None,
        )
    except (CodexSmartLaunchError, SessionControlError, OSError) as exc:
        detail = str(exc) if str(exc) else "CODEX_SMART_LAUNCH_FAILED"
        print(f"codex-smart failed safely: {detail}", file=sys.stderr)
        return 2

    environment[WRAPPER_MODE_ENV] = WRAPPER_MODE_VALUE
    try:
        execve(str(official), [str(official), *arguments], environment)
    except OSError:
        print("codex-smart failed safely: OFFICIAL_CODEX_EXEC_FAILED", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
