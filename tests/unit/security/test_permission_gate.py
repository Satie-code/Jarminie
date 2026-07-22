"""Unit tests for security.permission_gate.

Sprint 4.7 rewrite: every test from Sprint 4.1's always-ALLOW stub era
is gone, replaced with tests against the real risk-classification +
confirmation flow — see this sprint's own Testing Checklist ("every
Sprint 4.1-4.6 test that exercised PermissionGate's old always-ALLOW
stub is revisited"). Uses a real PermissionPolicyEngine throughout
(fast, pure, no reason to fake it) and a small local stub
ConfirmationService (a real VoiceConfirmationService needs a live voice
session, out of scope for these fast unit tests — covered separately
in test_confirmation_service.py).
"""

from datetime import UTC, datetime

import pytest

from config.schema import DeviceControlConfig, SecurityConfig
from decision.authority import AuthorityEvaluator
from device_control.action_engine import ActionContext, ActionRequest, ActionType
from security.confirmation_service import ConfirmationOutcome, ConfirmationRequest
from security.permission_gate import PermissionDecision, PermissionGate
from security.policy_engine import PermissionPolicyEngine


class _StubConfirmationService:
    def __init__(self, outcome: ConfirmationOutcome) -> None:
        self._outcome = outcome
        self.requests: list[ConfirmationRequest] = []

    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationOutcome:
        self.requests.append(request)
        return self._outcome


class _RaisingConfirmationService:
    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationOutcome:
        raise RuntimeError("confirmation service exploded")


def make_request(action_type: ActionType, **parameters) -> ActionRequest:
    return ActionRequest(
        action_type=action_type,
        parameters=parameters,
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
    )


def make_gate(
    *,
    security_config: SecurityConfig | None = None,
    device_control_config: DeviceControlConfig | None = None,
    confirmation_service=None,
) -> tuple[PermissionGate, _StubConfirmationService]:
    if confirmation_service is None:
        confirmation_service = _StubConfirmationService(ConfirmationOutcome.CONFIRMED)
    gate = PermissionGate(
        AuthorityEvaluator(),
        PermissionPolicyEngine(security_config or SecurityConfig()),
        confirmation_service,
        device_control_config or DeviceControlConfig(),
    )
    return gate, confirmation_service


# --- hard_denylist ---------------------------------------------------------------


def test_hard_denylist_denies_unconditionally_with_no_confirmation_offered():
    gate, confirmation_service = make_gate(
        security_config=SecurityConfig(hard_denylist=["system_command"])
    )

    result = gate.check(make_request(ActionType.SYSTEM_COMMAND, command=["cmd"]))

    assert result is PermissionDecision.DENY
    assert confirmation_service.requests == []


def test_hard_denylist_takes_priority_over_a_permissive_allowlist():
    gate, _ = make_gate(
        security_config=SecurityConfig(hard_denylist=["launch_application"]),
        device_control_config=DeviceControlConfig(application_allowlist=None),
    )

    result = gate.check(make_request(ActionType.LAUNCH_APPLICATION, executable_path="notepad.exe"))

    assert result is PermissionDecision.DENY


# --- LOW risk never calls ConfirmationService -------------------------------------


def test_low_risk_action_allows_without_calling_confirmation_service():
    gate, confirmation_service = make_gate()

    result = gate.check(make_request(ActionType.WINDOW_FOCUS))

    assert result is PermissionDecision.ALLOW
    assert confirmation_service.requests == []


# --- MEDIUM/HIGH risk calls ConfirmationService and maps every outcome ------------


@pytest.mark.parametrize(
    "outcome,expected_decision",
    [
        (ConfirmationOutcome.CONFIRMED, PermissionDecision.ALLOW),
        (ConfirmationOutcome.DECLINED, PermissionDecision.DENY),
        (ConfirmationOutcome.TIMED_OUT, PermissionDecision.DENY),
    ],
)
def test_high_risk_action_maps_every_confirmation_outcome(outcome, expected_decision):
    gate, confirmation_service = make_gate(confirmation_service=_StubConfirmationService(outcome))

    result = gate.check(make_request(ActionType.FILE_DELETE, path="a.txt"))

    assert result is expected_decision
    assert len(confirmation_service.requests) == 1


def test_medium_risk_action_calls_confirmation_service():
    gate, confirmation_service = make_gate()

    gate.check(make_request(ActionType.CLOSE_APPLICATION, process_id=123))

    assert len(confirmation_service.requests) == 1
    assert confirmation_service.requests[0].risk_level.value == "medium"


def test_confirmation_request_carries_a_real_prompt_text():
    gate, confirmation_service = make_gate()

    gate.check(make_request(ActionType.FILE_DELETE, path="a.txt"))

    assert "a.txt" in confirmation_service.requests[0].prompt_text


# --- application_allowlist enforcement ---------------------------------------------


def test_unlisted_application_is_denied_before_confirmation_is_offered():
    gate, confirmation_service = make_gate(
        device_control_config=DeviceControlConfig(application_allowlist=["notepad.exe"])
    )

    result = gate.check(make_request(ActionType.LAUNCH_APPLICATION, executable_path="cmd.exe"))

    assert result is PermissionDecision.DENY
    assert confirmation_service.requests == []


def test_listed_application_proceeds_to_risk_classification():
    gate, _ = make_gate(
        device_control_config=DeviceControlConfig(application_allowlist=["notepad.exe"])
    )

    result = gate.check(
        make_request(ActionType.LAUNCH_APPLICATION, executable_path="C:/Windows/notepad.exe")
    )

    assert result is PermissionDecision.ALLOW


def test_application_allowlist_none_means_no_restriction():
    gate, _ = make_gate(device_control_config=DeviceControlConfig(application_allowlist=None))

    result = gate.check(make_request(ActionType.LAUNCH_APPLICATION, executable_path="anything.exe"))

    assert result is PermissionDecision.ALLOW


def test_application_allowlist_matches_case_insensitively_by_basename():
    gate, _ = make_gate(
        device_control_config=DeviceControlConfig(application_allowlist=["Notepad.EXE"])
    )

    result = gate.check(
        make_request(ActionType.LAUNCH_APPLICATION, executable_path="C:/Windows/notepad.exe")
    )

    assert result is PermissionDecision.ALLOW


# --- approved_commands enforcement --------------------------------------------------


def test_approved_commands_ships_empty_so_every_command_is_denied_by_default():
    gate, confirmation_service = make_gate()

    result = gate.check(make_request(ActionType.SYSTEM_COMMAND, command=["ping", "localhost"]))

    assert result is PermissionDecision.DENY
    assert confirmation_service.requests == []


def test_approved_command_proceeds_to_risk_classification_and_confirmation():
    gate, confirmation_service = make_gate(
        device_control_config=DeviceControlConfig(approved_commands=["ping"])
    )

    result = gate.check(make_request(ActionType.SYSTEM_COMMAND, command=["ping", "localhost"]))

    assert result is PermissionDecision.ALLOW
    assert len(confirmation_service.requests) == 1


def test_unapproved_command_is_denied_before_confirmation_is_offered():
    gate, confirmation_service = make_gate(
        device_control_config=DeviceControlConfig(approved_commands=["ping"])
    )

    result = gate.check(make_request(ActionType.SYSTEM_COMMAND, command=["del", "/f", "*"]))

    assert result is PermissionDecision.DENY
    assert confirmation_service.requests == []


# --- unrelated action types are unaffected by either allowlist ---------------------


def test_file_delete_is_unaffected_by_application_or_command_allowlists():
    gate, _ = make_gate(
        device_control_config=DeviceControlConfig(
            application_allowlist=["notepad.exe"], approved_commands=[]
        ),
        confirmation_service=_StubConfirmationService(ConfirmationOutcome.CONFIRMED),
    )

    result = gate.check(make_request(ActionType.FILE_DELETE, path="a.txt"))

    assert result is PermissionDecision.ALLOW


# --- Fail Gracefully: a crashing ConfirmationService still resolves cleanly --------


def test_confirmation_service_exception_propagates_for_dispatch_to_catch():
    """PermissionGate.check() itself doesn't add a redundant try/except
    around confirmation_service — ActionRegistry.dispatch() already
    wraps the whole check() call and degrades to FAILED, which is
    DENY-equivalent in effect. This test documents that check() lets
    the exception through rather than silently swallowing it."""
    gate, _ = make_gate(confirmation_service=_RaisingConfirmationService())

    with pytest.raises(RuntimeError):
        gate.check(make_request(ActionType.FILE_DELETE, path="a.txt"))


# --- constructed with real collaborators, not mocked -------------------------------


def test_constructed_with_real_authority_evaluator_and_policy_engine():
    evaluator = AuthorityEvaluator()
    policy_engine = PermissionPolicyEngine(SecurityConfig())
    gate = PermissionGate(
        evaluator,
        policy_engine,
        _StubConfirmationService(ConfirmationOutcome.CONFIRMED),
        DeviceControlConfig(),
    )

    assert gate._authority_evaluator is evaluator
    assert gate._policy_engine is policy_engine
