
"""Knowledge Library loader for Codex Patch Smart Router.

Loads JSON rules from repo-root rules/. Fails closed on malformed config.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json

ALLOWED_SANDBOX = {"read-only", "workspace-write", "danger-full-access"}
ALLOWED_V0_SANDBOX = {"read-only", "workspace-write"}
ALLOWED_VERBOSITY = {"low", "medium", "high"}
ALLOWED_REASONING_EFFORT = {"minimal", "low", "medium", "high", "xhigh"}
ALLOWED_APPROVAL_POLICY = {"on-request"}  # V0 only
ALLOWED_ACTION_DANGERS = {
    "read_only_analysis",
    "write_local_files",
    "run_tests",
    "git_operations",
    "network_access",
    "dependency_install",
    "database_operation",
    "deployment_operation",
    "destructive_operation",
    "secret_touching_operation",
}

class ConfigError(RuntimeError):
    pass

@dataclass(frozen=True)
class KnowledgeLibrary:
    root: Path
    prompt_weight_dimensions: dict
    category_weights: dict
    risk_triggers: dict
    complexity_rules: dict
    action_danger_rules: dict
    evidence_rules: dict
    context_rules: dict
    profile_policy: dict
    tie_breakers: dict

REQUIRED_FILES = {
    "prompt_weight_dimensions": "prompt_weight_dimensions.json",
    "category_weights": "category_weights.json",
    "risk_triggers": "risk_triggers.json",
    "complexity_rules": "complexity_rules.json",
    "action_danger_rules": "action_danger_rules.json",
    "evidence_rules": "evidence_rules.json",
    "context_rules": "context_rules.json",
    "profile_policy": "profile_policy.json",
    "tie_breakers": "tie_breakers.json",
}


def repo_root_from_here() -> Path:
    # smart_codex/knowledge.py -> repo root is parent of package dir
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise ConfigError(f"Failed to load JSON rules file {path}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"Rules file {path} must contain a JSON object")
    return data


def _validate_profile_policy(profile_policy: dict) -> None:
    profiles = profile_policy.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ConfigError("profile_policy.json missing non-empty profiles object")
    for name, cfg in profiles.items():
        sandbox = cfg.get("sandbox_mode")
        if sandbox not in ALLOWED_SANDBOX:
            raise ConfigError(f"Profile {name} invalid sandbox_mode: {sandbox}")
        if sandbox not in ALLOWED_V0_SANDBOX:
            raise ConfigError(f"Profile {name} uses forbidden V0 sandbox_mode: {sandbox}")
        verbosity = cfg.get("model_verbosity")
        if verbosity not in ALLOWED_VERBOSITY:
            raise ConfigError(f"Profile {name} invalid model_verbosity: {verbosity}")
        effort = cfg.get("model_reasoning_effort")
        if effort not in ALLOWED_REASONING_EFFORT:
            raise ConfigError(f"Profile {name} invalid model_reasoning_effort: {effort}")
        approval = cfg.get("approval_policy")
        if approval not in ALLOWED_APPROVAL_POLICY:
            raise ConfigError(f"Profile {name} invalid V0 approval_policy: {approval}")
        model = cfg.get("model")
        if not isinstance(model, str) or not model:
            raise ConfigError(f"Profile {name} missing model placeholder")
        if "tools" in cfg:
            raise ConfigError(f"Profile {name} must not declare unverified tools")


def _validate_category_weights(category_weights: dict) -> None:
    categories = category_weights.get("categories")
    if not isinstance(categories, dict) or not categories:
        raise ConfigError("category_weights.json missing non-empty categories object")
    for name, cfg in categories.items():
        if not isinstance(cfg, dict):
            raise ConfigError(f"Category {name} must be an object")
        for key in ["default_profile", "risk", "complexity", "strong", "weak", "negative"]:
            if key not in cfg:
                raise ConfigError(f"Category {name} missing {key}")
        if cfg["risk"] not in {"low", "medium", "high", "critical"}:
            raise ConfigError(f"Category {name} invalid risk: {cfg['risk']}")
        if cfg["complexity"] not in {"low", "medium", "high"}:
            raise ConfigError(f"Category {name} invalid complexity: {cfg['complexity']}")


def _validate_risk_triggers(risk_triggers: dict) -> None:
    triggers = risk_triggers.get("triggers")
    if not isinstance(triggers, list) or not triggers:
        raise ConfigError("risk_triggers.json missing non-empty triggers list")
    for index, trigger in enumerate(triggers, start=1):
        for key in [
            "group",
            "terms",
            "risk",
            "category",
            "profile",
            "sandbox",
            "approval",
            "action_danger",
        ]:
            if key not in trigger:
                raise ConfigError(f"risk trigger {index} missing {key}")
        if trigger["risk"] not in {"high", "critical"}:
            raise ConfigError(f"risk trigger {trigger['group']} must be high or critical")
        if trigger["sandbox"] not in ALLOWED_V0_SANDBOX:
            raise ConfigError(f"risk trigger {trigger['group']} invalid sandbox")
        if trigger["approval"] != "on-request":
            raise ConfigError(f"risk trigger {trigger['group']} invalid approval")
        if trigger["action_danger"] not in ALLOWED_ACTION_DANGERS:
            raise ConfigError(
                f"risk trigger {trigger['group']} invalid action_danger: "
                f"{trigger['action_danger']}"
            )
        if not isinstance(trigger["terms"], list) or not trigger["terms"]:
            raise ConfigError(f"risk trigger {trigger['group']} has no terms")


def _validate_levels(name: str, data: dict) -> None:
    levels = data.get("levels")
    if not isinstance(levels, dict) or not levels:
        raise ConfigError(f"{name} missing non-empty levels object")


def load_rules(root: Path | None = None) -> KnowledgeLibrary:
    root = root or repo_root_from_here()
    rules_dir = root / "rules"
    if not rules_dir.exists():
        raise ConfigError(f"Missing rules directory: {rules_dir}")
    loaded = {key: load_json(rules_dir / filename) for key, filename in REQUIRED_FILES.items()}
    _validate_category_weights(loaded["category_weights"])
    _validate_risk_triggers(loaded["risk_triggers"])
    _validate_levels("action_danger_rules.json", loaded["action_danger_rules"])
    _validate_levels("evidence_rules.json", loaded["evidence_rules"])
    _validate_levels("context_rules.json", loaded["context_rules"])
    _validate_profile_policy(loaded["profile_policy"])
    return KnowledgeLibrary(root=root, **loaded)
