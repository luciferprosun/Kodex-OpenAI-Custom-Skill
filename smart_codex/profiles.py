from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib

from .config import PROFILES_DIR


ALLOWED_SANDBOX = {"read-only", "workspace-write", "danger-full-access"}
ALLOWED_V0_SANDBOX = {"read-only", "workspace-write"}
ALLOWED_VERBOSITY = {"low", "medium", "high"}
ALLOWED_REASONING_EFFORT = {"minimal", "low", "medium", "high", "xhigh"}
ALLOWED_APPROVAL_POLICY = {"untrusted", "on-request", "never"}

AVAILABLE_PROFILES = {
    "fast",
    "standard",
    "deep",
    "math",
    "security",
    "literary",
    "research",
    "repo",
}


@dataclass(frozen=True)
class ProfileConfig:
    name: str
    model: str
    sandbox_mode: str
    model_verbosity: str
    model_reasoning_effort: str
    approval_policy: str


def load_profile(profile_name: str, profiles_dir: Path = PROFILES_DIR) -> ProfileConfig:
    if profile_name not in AVAILABLE_PROFILES:
        raise ValueError(f"unknown profile: {profile_name}")

    path = profiles_dir / f"{profile_name}.config.toml"
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    profile = ProfileConfig(
        name=profile_name,
        model=str(data.get("model", "")),
        sandbox_mode=str(data.get("sandbox_mode", "")),
        model_verbosity=str(data.get("model_verbosity", "")),
        model_reasoning_effort=str(data.get("model_reasoning_effort", "")),
        approval_policy=str(data.get("approval_policy", "")),
    )
    validate_profile(profile, v0=True)
    return profile


def validate_profile(profile: ProfileConfig, v0: bool = True) -> None:
    errors = validate_profile_data(
        {
            "sandbox_mode": profile.sandbox_mode,
            "model_verbosity": profile.model_verbosity,
            "model_reasoning_effort": profile.model_reasoning_effort,
            "approval_policy": profile.approval_policy,
        },
        v0=v0,
    )
    if errors:
        raise ValueError("; ".join(errors))


def validate_profile_data(data: dict[str, str], v0: bool = True) -> list[str]:
    errors: list[str] = []
    sandbox = data.get("sandbox_mode")
    verbosity = data.get("model_verbosity")
    effort = data.get("model_reasoning_effort")
    approval = data.get("approval_policy")

    if sandbox not in ALLOWED_SANDBOX:
        errors.append(f"invalid sandbox_mode: {sandbox}")
    elif v0 and sandbox not in ALLOWED_V0_SANDBOX:
        errors.append("danger-full-access is rejected for V0")

    if verbosity not in ALLOWED_VERBOSITY:
        errors.append(f"invalid model_verbosity: {verbosity}")

    if effort not in ALLOWED_REASONING_EFFORT:
        errors.append(f"invalid model_reasoning_effort: {effort}")

    if approval not in ALLOWED_APPROVAL_POLICY:
        errors.append(f"invalid approval_policy: {approval}")

    return errors


def validate_sandbox_override(sandbox_mode: str) -> None:
    if sandbox_mode not in ALLOWED_SANDBOX:
        raise ValueError(f"invalid sandbox override: {sandbox_mode}")
    if sandbox_mode not in ALLOWED_V0_SANDBOX:
        raise ValueError("danger-full-access is rejected for V0")


def validate_profile_override(profile_name: str) -> None:
    if profile_name not in AVAILABLE_PROFILES:
        raise ValueError(f"unknown profile override: {profile_name}")


def validate_approval_override(approval_policy: str) -> None:
    if approval_policy not in ALLOWED_APPROVAL_POLICY:
        raise ValueError(f"invalid approval policy: {approval_policy}")

