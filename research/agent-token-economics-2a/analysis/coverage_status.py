#!/usr/bin/env python3
"""Dependency-free normalization for registry coverage-status values."""

from __future__ import annotations


def failure_coverage_status(value):
    """Map heterogeneous discovery metadata without treating uncertainty as truth."""
    if value is True:
        return "present"
    if value is False:
        return "absent"
    if value is None:
        return "unknown"
    normalized = str(value).strip().lower()
    if normalized in {"complete", "full", "yes", "true"}:
        return "present"
    if normalized in {"absent", "none", "no", "false"}:
        return "absent"
    return "unknown"
