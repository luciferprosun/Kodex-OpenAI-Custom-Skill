"""Safe turn/start extraction, Router Core classification, and field rewriting."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from smart_codex.router import RoutingDecision, route_prompt

from .policy_mapper import AppliedPolicy, PolicyError, PolicyMapper


class RoutingFailure(RuntimeError):
    """Sanitized failure raised instead of forwarding an unclassified turn."""


@dataclass(frozen=True)
class RoutedTurn:
    message: dict[str, Any]
    prompt_hash: str
    category: str
    route_class: str
    original_model: str | None
    selected_model: str
    effort: str
    sandbox_mode: str
    approval_policy: object
    reasons: tuple[str, ...]


def _safe_original_model(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 128:
        return None
    if not all(character.isalnum() or character in "._-" for character in value):
        return None
    return value


def _apply_collaboration_mode_overrides(
    params: dict[str, Any],
    *,
    model: str,
    effort: str,
) -> None:
    """Align precedence-bearing TUI settings with top-level overrides.

    The installed experimental schema says ``collaborationMode`` takes
    precedence over the top-level model and effort fields. The stock remote
    TUI supplies this object, so leaving its nested settings untouched would
    make an otherwise valid turn/start rewrite inert. Do not add the
    experimental field to clients that omitted it and do not alter the mode or
    developer instructions.
    """

    if "collaborationMode" not in params or params["collaborationMode"] is None:
        return
    collaboration_mode = params["collaborationMode"]
    if not isinstance(collaboration_mode, dict):
        raise RoutingFailure("turn/start collaboration mode is malformed")
    settings = collaboration_mode.get("settings")
    if not isinstance(settings, dict):
        raise RoutingFailure("turn/start collaboration settings are malformed")
    settings["model"] = model
    settings["reasoning_effort"] = effort


def extract_turn_input(params: object) -> tuple[str, tuple[str, ...]]:
    if not isinstance(params, dict):
        raise RoutingFailure("turn/start params are malformed")
    thread_id = params.get("threadId")
    inputs = params.get("input")
    if not isinstance(thread_id, str) or not thread_id:
        raise RoutingFailure("turn/start thread id is missing")
    if not isinstance(inputs, list) or not inputs:
        raise RoutingFailure("turn/start input is missing")

    texts: list[str] = []
    modalities: list[str] = []
    for item in inputs:
        if not isinstance(item, dict):
            raise RoutingFailure("turn/start contains a malformed input item")
        item_type = item.get("type")
        if item_type == "text":
            text = item.get("text")
            if not isinstance(text, str):
                raise RoutingFailure("turn/start contains malformed text input")
            if text.strip():
                texts.append(text)
            if "text" not in modalities:
                modalities.append("text")
        elif item_type in {"image", "localImage"}:
            if "image" not in modalities:
                modalities.append("image")
        elif item_type in {"skill", "mention"}:
            continue
        else:
            raise RoutingFailure("turn/start contains an unsupported input type")
    if not texts:
        raise RoutingFailure("turn/start contains no routable user text")
    if "text" not in modalities:
        modalities.insert(0, "text")
    return "\n\n".join(texts), tuple(modalities)


class TurnRouter:
    def __init__(self, mapper: PolicyMapper):
        self.mapper = mapper

    def route_message(self, message: object) -> RoutedTurn:
        if not isinstance(message, dict) or message.get("method") != "turn/start":
            raise RoutingFailure("only turn/start can be routed")
        request_id = message.get("id")
        if isinstance(request_id, bool) or not isinstance(request_id, (str, int)):
            raise RoutingFailure("turn/start request id is malformed")
        prompt, modalities = extract_turn_input(message.get("params"))
        try:
            decision: RoutingDecision = route_prompt(prompt, dry_run=True)
            applied: AppliedPolicy = self.mapper.apply(
                decision,
                prompt,
                required_modalities=modalities,
            )
        except (PolicyError, ValueError, RuntimeError) as exc:
            raise RoutingFailure("turn/start could not be classified safely") from exc

        routed = deepcopy(message)
        params = routed["params"]
        if params.get("permissions") is not None:
            raise RoutingFailure(
                "turn/start named permissions cannot be combined with routed sandbox policy"
            )
        original_model = _safe_original_model(params.get("model"))
        if original_model is not None and self.mapper.registry.get(original_model) is None:
            original_model = None
        sandbox_mode = applied.sandbox_mode
        sandbox_policy = deepcopy(applied.sandbox_policy)
        original_sandbox = params.get("sandboxPolicy")
        if (
            applied.sandbox_mode == "workspace-write"
            and isinstance(original_sandbox, dict)
            and original_sandbox.get("type") == "readOnly"
            and self.mapper.requirements.allows_sandbox("read-only")
        ):
            sandbox_mode = "read-only"
            sandbox_policy = {"type": "readOnly", "networkAccess": False}

        approval_policy = deepcopy(applied.approval_policy)
        original_approval = params.get("approvalPolicy")
        if (
            applied.approval_policy == "on-request"
            and original_approval == "untrusted"
            and self.mapper.requirements.allows_approval("untrusted")
        ):
            approval_policy = "untrusted"

        params["model"] = applied.model.model
        params["effort"] = applied.effort
        params["sandboxPolicy"] = sandbox_policy
        params["approvalPolicy"] = approval_policy
        params["approvalsReviewer"] = "user"
        _apply_collaboration_mode_overrides(
            params,
            model=applied.model.model,
            effort=applied.effort,
        )

        return RoutedTurn(
            message=routed,
            prompt_hash=decision.prompt_hash,
            category=decision.category,
            route_class=applied.route_class,
            original_model=original_model,
            selected_model=applied.model.model,
            effort=applied.effort,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            reasons=applied.reasons,
        )
