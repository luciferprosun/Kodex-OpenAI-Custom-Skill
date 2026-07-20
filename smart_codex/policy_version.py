"""Canonical SmartRouter policy identities and provenance validation."""

MODEL_POLICY_VERSION = "model-policy-calibration-v0.2"
LEGACY_MODEL_POLICY_VERSION = "model-policy-calibration-v0.1"
UNKNOWN_POLICY_VERSION = "unknown"
SUPPORTED_MODEL_POLICY_VERSIONS = frozenset(
    {LEGACY_MODEL_POLICY_VERSION, MODEL_POLICY_VERSION}
)


def normalize_policy_provenance(value: object) -> str:
    """Preserve only a supported policy identity supplied by its producer."""

    if isinstance(value, str) and value in SUPPORTED_MODEL_POLICY_VERSIONS:
        return value
    return UNKNOWN_POLICY_VERSION
