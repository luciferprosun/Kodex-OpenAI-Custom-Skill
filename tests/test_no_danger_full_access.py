
import copy
import pytest
from smart_codex.knowledge import load_rules, _validate_profile_policy, ConfigError


def test_profile_policy_rejects_danger_full_access():
    rules = load_rules()
    policy = copy.deepcopy(rules.profile_policy)
    policy["profiles"]["security"]["sandbox_mode"] = "danger-full-access"
    with pytest.raises(ConfigError):
        _validate_profile_policy(policy)
