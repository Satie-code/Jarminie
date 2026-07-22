"""Unit tests for security.policy_engine."""

import pytest

from config.schema import SecurityConfig
from device_control.action_engine import ActionType
from security.policy_engine import PermissionPolicyEngine, RiskLevel

_EXPECTED_DEFAULTS: dict[ActionType, RiskLevel] = {
    ActionType.LAUNCH_APPLICATION: RiskLevel.LOW,
    ActionType.WINDOW_FOCUS: RiskLevel.LOW,
    ActionType.WINDOW_MOVE: RiskLevel.LOW,
    ActionType.WINDOW_RESIZE: RiskLevel.LOW,
    ActionType.WINDOW_MINIMIZE: RiskLevel.LOW,
    ActionType.FILE_CREATE: RiskLevel.LOW,
    ActionType.FOLDER_CREATE: RiskLevel.LOW,
    ActionType.CLOSE_APPLICATION: RiskLevel.MEDIUM,
    ActionType.WINDOW_CLOSE: RiskLevel.MEDIUM,
    ActionType.FILE_MOVE: RiskLevel.MEDIUM,
    ActionType.FILE_COPY: RiskLevel.MEDIUM,
    ActionType.FILE_RENAME: RiskLevel.MEDIUM,
    ActionType.FILE_DELETE: RiskLevel.HIGH,
    ActionType.FOLDER_DELETE: RiskLevel.HIGH,
    ActionType.SYSTEM_COMMAND: RiskLevel.HIGH,
    ActionType.WORKFLOW_STEP: RiskLevel.HIGH,
}


@pytest.fixture
def engine() -> PermissionPolicyEngine:
    return PermissionPolicyEngine(SecurityConfig())


def test_every_action_type_has_a_default_risk_level_covered_by_this_test():
    """Guards against this test file itself going stale if ActionType
    ever gains a new member without a corresponding entry here."""
    assert set(_EXPECTED_DEFAULTS) == set(ActionType)


@pytest.mark.parametrize("action_type,expected_level", list(_EXPECTED_DEFAULTS.items()))
def test_classify_matches_documented_built_in_defaults(engine, action_type, expected_level):
    policy = engine.classify(action_type)
    assert policy.action_type is action_type
    assert policy.risk_level is expected_level


def test_low_risk_does_not_require_confirmation(engine):
    policy = engine.classify(ActionType.WINDOW_FOCUS)
    assert policy.risk_level is RiskLevel.LOW
    assert policy.requires_confirmation is False


@pytest.mark.parametrize("action_type", [ActionType.CLOSE_APPLICATION, ActionType.FILE_DELETE])
def test_medium_and_high_risk_require_confirmation(engine, action_type):
    policy = engine.classify(action_type)
    assert policy.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH)
    assert policy.requires_confirmation is True


def test_config_override_of_a_built_in_risk_level_takes_effect():
    config = SecurityConfig(risk_policies={"file_delete": "low"})
    engine = PermissionPolicyEngine(config)

    policy = engine.classify(ActionType.FILE_DELETE)

    assert policy.risk_level is RiskLevel.LOW
    assert policy.requires_confirmation is False


def test_config_override_can_raise_risk_level_too():
    config = SecurityConfig(risk_policies={"window_focus": "high"})
    engine = PermissionPolicyEngine(config)

    policy = engine.classify(ActionType.WINDOW_FOCUS)

    assert policy.risk_level is RiskLevel.HIGH
    assert policy.requires_confirmation is True


def test_override_for_an_unrelated_action_type_does_not_leak():
    config = SecurityConfig(risk_policies={"file_delete": "low"})
    engine = PermissionPolicyEngine(config)

    policy = engine.classify(ActionType.FOLDER_DELETE)

    assert policy.risk_level is RiskLevel.HIGH


def test_invalid_override_value_falls_back_to_default():
    config = SecurityConfig(risk_policies={"file_delete": "not_a_real_level"})
    engine = PermissionPolicyEngine(config)

    policy = engine.classify(ActionType.FILE_DELETE)

    assert policy.risk_level is RiskLevel.HIGH


def test_unmapped_action_type_falls_back_to_medium(engine):
    class _FakeActionType:
        value = "some_future_action_type"

    policy = engine.classify(_FakeActionType())

    assert policy.risk_level is RiskLevel.MEDIUM
    assert policy.requires_confirmation is True


# --- is_hard_denied() ----------------------------------------------------------


def test_is_hard_denied_true_for_a_denylisted_action_type():
    config = SecurityConfig(hard_denylist=["system_command"])
    engine = PermissionPolicyEngine(config)

    assert engine.is_hard_denied(ActionType.SYSTEM_COMMAND) is True


def test_is_hard_denied_false_for_an_unlisted_action_type(engine):
    assert engine.is_hard_denied(ActionType.SYSTEM_COMMAND) is False


def test_hard_denylist_ships_empty_by_default():
    assert SecurityConfig().hard_denylist == []
