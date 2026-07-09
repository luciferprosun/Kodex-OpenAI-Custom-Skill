from __future__ import annotations

import argparse
import json
import shlex
import sys

from .launcher import build_codex_command, run_codex_command
from .logging_safe import write_decision_log
from .model_audit import audit_models
from .router import route_prompt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smart-codex",
        description="Safe local Codex prompt router.",
    )
    parser.add_argument("--execute", action="store_true", help="execute Codex instead of dry-run")
    parser.add_argument("--dry-run", action="store_true", help="force dry-run behavior")
    parser.add_argument("--profile", help="manual profile override")
    parser.add_argument("--model", help="manual model override")
    parser.add_argument("--sandbox", help="manual sandbox override")
    parser.add_argument("--cd", help="working directory for Codex")
    parser.add_argument("--config", action="append", default=[], help="Codex config override key=value")
    parser.add_argument("--ask-for-approval", help="Codex approval policy override")
    parser.add_argument("--explain", action="store_true", help="print routing explanation")
    parser.add_argument("--no-log", action="store_true", help="disable privacy-safe decision log")
    parser.add_argument("prompt", nargs="+", help="prompt text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == "audit-models":
        return audit_models_command()

    parser = build_parser()
    args = parser.parse_args(args_list)
    prompt = " ".join(args.prompt)
    dry_run = args.dry_run or not args.execute

    try:
        decision = route_prompt(
            prompt,
            dry_run=dry_run,
            profile_override=args.profile,
            model_override=args.model,
            sandbox_override=args.sandbox,
            approval_override=args.ask_for_approval,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2

    command = build_codex_command(
        prompt,
        profile=decision.selected_profile,
        model=args.model,
        sandbox=decision.sandbox_mode,
        cd=args.cd,
        configs=args.config,
        approval_policy=decision.approval_policy,
        execute=args.execute and not args.dry_run,
    )

    if not args.no_log:
        write_decision_log(decision, enabled=True)

    print_decision(decision, command.argv, explain=args.explain)

    if command.execute:
        completed = run_codex_command(command)
        return completed.returncode
    return 0


def audit_models_command() -> int:
    result = audit_models()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


def print_decision(decision, argv: list[str], *, explain: bool) -> None:
    print(f"category: {decision.category}")
    print(f"risk: {decision.risk}")
    print(f"complexity: {decision.complexity}")
    print(f"selected_profile: {decision.selected_profile}")
    print(f"selected_model: {decision.selected_model}")
    print(f"sandbox_mode: {decision.sandbox_mode}")
    print(f"approval_policy: {decision.approval_policy}")
    print(f"confidence: {decision.confidence:.2f}")
    print(f"dry_run: {decision.dry_run}")
    if decision.warning:
        print(f"warning: {decision.warning}")
    print(f"planned_command: {shlex.join(argv)}")
    if explain:
        print("decision_reasons:")
        for reason in decision.decision_reasons:
            print(f"- {reason}")


if __name__ == "__main__":
    raise SystemExit(main())

