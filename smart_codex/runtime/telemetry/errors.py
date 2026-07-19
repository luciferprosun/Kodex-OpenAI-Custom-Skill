"""Sanitized telemetry error categories."""

from __future__ import annotations


class TelemetryError(RuntimeError):
    """Base error that must never contain rejected record contents."""

    category = "TELEMETRY_ERROR"

    def __init__(self, category: str | None = None):
        self.category = category or self.category
        super().__init__(self.category)


class TelemetryValidationError(TelemetryError):
    category = "VALIDATION_FAILED"


class TelemetryStorageError(TelemetryError):
    category = "STORAGE_FAILED"


class TelemetryPrivacyError(TelemetryValidationError):
    category = "PRIVACY_REJECTED"
