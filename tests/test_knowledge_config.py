import copy

import pytest

from smart_codex.knowledge import ConfigError, _validate_profile_policy, load_rules


def test_missing_rules_directory_fails_closed(tmp_path):
    with pytest.raises(ConfigError):
        load_rules(tmp_path)


def test_profile_policy_rejects_never_approval():
    rules = load_rules()
    policy = copy.deepcopy(rules.profile_policy)
    policy["profiles"]["standard"]["approval_policy"] = "never"

    with pytest.raises(ConfigError):
        _validate_profile_policy(policy)
