
"""Prompt preprocessing for Codex Patch Smart Router.

V0 rule: preprocessing must not execute, inspect files, or mutate state.
"""
from __future__ import annotations
import re

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RE = re.compile(r"\s+")


def normalize_prompt(prompt: str) -> str:
    """Return a normalized prompt for scoring.

    Keeps content as text only. Does not split prompt into shell tokens.
    """
    if not isinstance(prompt, str):
        prompt = str(prompt)
    prompt = _CONTROL_RE.sub(" ", prompt)
    prompt = prompt.strip().lower()
    prompt = _WS_RE.sub(" ", prompt)
    return prompt


def prompt_has_injection_markers(prompt: str) -> bool:
    text = normalize_prompt(prompt)
    markers = ["ignore previous", "system prompt", "developer message", "jailbreak", "bypass policy"]
    return any(m in text for m in markers)
