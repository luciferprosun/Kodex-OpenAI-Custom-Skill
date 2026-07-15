"""Schema validation and metric aggregation for curated routing evaluations."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable


class EvaluationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvalCase:
    id: str
    group: str
    prompt: str
    acceptable_profiles: tuple[str, ...]
    acceptable_efforts: tuple[str, ...]
    fixture: str
    critical_underroute: bool


@dataclass(frozen=True)
class EvalOutcome:
    case_id: str
    profile: str
    effort: str
    model: str
    effort_supported: bool
    model_available: bool
    delegation_reason: str | None


@dataclass(frozen=True)
class EvaluationMetrics:
    total: int
    acceptable: int
    overall_accuracy: float
    trivial_deescalation: float
    spark_eligible_accuracy: float
    terra_professional_accuracy: float
    sol_architecture_accuracy: float
    critical_under_routing: int
    unsupported_efforts: int
    unavailable_selections: int
    ultra_without_delegation_reason: int


def load_eval_cases(path: Path) -> tuple[EvalCase, ...]:
    cases: list[EvalCase] = []
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvaluationError("cannot read model selection evaluation dataset") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationError(f"invalid evaluation JSONL line {line_number}") from exc
        if not isinstance(raw, dict):
            raise EvaluationError("evaluation case must be an object")
        case_id = raw.get("id")
        group = raw.get("group")
        prompt = raw.get("prompt")
        fixture = raw.get("fixture", "default")
        critical = raw.get("critical_underroute", False)
        if not all(isinstance(item, str) and item for item in (case_id, group, prompt, fixture)):
            raise EvaluationError("evaluation case identity is malformed")
        if case_id in seen:
            raise EvaluationError("evaluation case ids must be unique")
        if not isinstance(critical, bool):
            raise EvaluationError("evaluation critical flag is malformed")
        profiles = _string_tuple(raw.get("acceptable_profiles"), "acceptable_profiles")
        efforts = _string_tuple(raw.get("acceptable_efforts"), "acceptable_efforts")
        seen.add(case_id)
        cases.append(
            EvalCase(
                id=case_id,
                group=group,
                prompt=prompt,
                acceptable_profiles=profiles,
                acceptable_efforts=efforts,
                fixture=fixture,
                critical_underroute=critical,
            )
        )
    if not cases:
        raise EvaluationError("model selection evaluation dataset is empty")
    return tuple(cases)


def summarize_evaluation(
    cases: Iterable[EvalCase],
    outcomes: Iterable[EvalOutcome],
) -> EvaluationMetrics:
    case_values = tuple(cases)
    outcome_values = tuple(outcomes)
    by_id = {outcome.case_id: outcome for outcome in outcome_values}
    if len(by_id) != len(outcome_values) or set(by_id) != {case.id for case in case_values}:
        raise EvaluationError("evaluation outcomes do not match cases")

    acceptable = 0
    critical_under = 0
    unsupported = 0
    unavailable = 0
    ultra_without_reason = 0
    group_results: dict[str, list[bool]] = {}
    for case in case_values:
        outcome = by_id[case.id]
        passed = (
            outcome.profile in case.acceptable_profiles
            and outcome.effort in case.acceptable_efforts
        )
        acceptable += int(passed)
        group_results.setdefault(case.group, []).append(passed)
        if case.critical_underroute and outcome.profile != "sol":
            critical_under += 1
        unsupported += int(not outcome.effort_supported)
        unavailable += int(not outcome.model_available)
        if outcome.effort == "ultra" and outcome.delegation_reason is None:
            ultra_without_reason += 1

    def percentage(groups: tuple[str, ...]) -> float:
        values = [item for group in groups for item in group_results.get(group, [])]
        return round(100.0 * sum(values) / len(values), 2) if values else 0.0

    total = len(case_values)
    return EvaluationMetrics(
        total=total,
        acceptable=acceptable,
        overall_accuracy=round(100.0 * acceptable / total, 2),
        trivial_deescalation=percentage(("trivial_writing", "luna_simple")),
        spark_eligible_accuracy=percentage(("spark_targeted",)),
        terra_professional_accuracy=percentage(("terra_coding", "terra_research")),
        sol_architecture_accuracy=percentage(("sol_frontier",)),
        critical_under_routing=critical_under,
        unsupported_efforts=unsupported,
        unavailable_selections=unavailable,
        ultra_without_delegation_reason=ultra_without_reason,
    )


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise EvaluationError(f"evaluation {field} is malformed")
    return tuple(value)
