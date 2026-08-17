"""Unit tests for security.qt_confirmation_service.

QtConfirmationService.request_confirmation() itself is tested against a
monkeypatched ui.jarvis.confirmation_dialog.ConfirmationDialog — a real
modal QDialog.exec() cannot be driven from a synchronous unit test
without a QTimer.singleShot() trick, which is exercised directly against
the real dialog in tests/unit/ui/jarvis/test_confirmation_dialog.py
instead; this file only verifies QtConfirmationService's own outcome-
interpretation logic (and RequestedByConfirmationService's routing,
which needs no Qt object at all).
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QDialog

import ui.jarvis.confirmation_dialog as confirmation_dialog_module
from device_control.action_engine import ActionContext, ActionRequest, ActionType
from security.confirmation_service import ConfirmationOutcome, ConfirmationRequest
from security.policy_engine import RiskLevel
from security.qt_confirmation_service import QtConfirmationService, RequestedByConfirmationService


def _confirmation_request(requested_by: str = "ui") -> ConfirmationRequest:
    action_request = ActionRequest(
        action_type=ActionType.FILE_DELETE,
        parameters={"path": "C:/tmp/example.txt"},
        context=ActionContext(requested_by=requested_by),
        requested_at=datetime.now(UTC),
    )
    return ConfirmationRequest(
        action_request=action_request,
        risk_level=RiskLevel.HIGH,
        prompt_text="This will permanently delete example.txt. Should I proceed?",
    )


class _FakeDialog:
    """Stands in for ui.jarvis.confirmation_dialog.ConfirmationDialog.
    Class-level result/timed_out let each test configure the outcome
    before QtConfirmationService constructs an instance."""

    result = QDialog.DialogCode.Accepted
    is_timed_out = False
    instances: list["_FakeDialog"] = []

    def __init__(self, prompt_text: str, timeout_seconds: float, parent) -> None:
        self.prompt_text = prompt_text
        self.timeout_seconds = timeout_seconds
        self.timed_out = type(self).is_timed_out
        type(self).instances.append(self)

    def exec(self) -> QDialog.DialogCode:
        return type(self).result


@pytest.fixture(autouse=True)
def _patch_confirmation_dialog(monkeypatch):
    _FakeDialog.result = QDialog.DialogCode.Accepted
    _FakeDialog.is_timed_out = False
    _FakeDialog.instances = []
    monkeypatch.setattr(confirmation_dialog_module, "ConfirmationDialog", _FakeDialog)
    yield


def test_confirmed_when_dialog_accepted():
    _FakeDialog.result = QDialog.DialogCode.Accepted
    service = QtConfirmationService(confirmation_timeout_seconds=20.0)

    outcome = service.request_confirmation(_confirmation_request())

    assert outcome == ConfirmationOutcome.CONFIRMED
    assert len(_FakeDialog.instances) == 1
    assert _FakeDialog.instances[0].timeout_seconds == 20.0


def test_declined_when_dialog_rejected_without_timeout():
    _FakeDialog.result = QDialog.DialogCode.Rejected
    _FakeDialog.is_timed_out = False
    service = QtConfirmationService(confirmation_timeout_seconds=20.0)

    outcome = service.request_confirmation(_confirmation_request())

    assert outcome == ConfirmationOutcome.DECLINED


def test_timed_out_when_dialog_reports_a_timeout():
    _FakeDialog.result = QDialog.DialogCode.Rejected
    _FakeDialog.is_timed_out = True
    service = QtConfirmationService(confirmation_timeout_seconds=20.0)

    outcome = service.request_confirmation(_confirmation_request())

    assert outcome == ConfirmationOutcome.TIMED_OUT


def test_dialog_construction_failure_degrades_to_timed_out(monkeypatch):
    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(confirmation_dialog_module, "ConfirmationDialog", _raise)
    service = QtConfirmationService(confirmation_timeout_seconds=20.0)

    outcome = service.request_confirmation(_confirmation_request())

    assert outcome == ConfirmationOutcome.TIMED_OUT


# --- RequestedByConfirmationService -------------------------------------


def test_routes_to_the_override_for_a_matching_requested_by():
    ui_service = MagicMock()
    ui_service.request_confirmation.return_value = ConfirmationOutcome.CONFIRMED
    default_service = MagicMock()
    router = RequestedByConfirmationService(default=default_service, overrides={"ui": ui_service})

    outcome = router.request_confirmation(_confirmation_request(requested_by="ui"))

    assert outcome == ConfirmationOutcome.CONFIRMED
    ui_service.request_confirmation.assert_called_once()
    default_service.request_confirmation.assert_not_called()


def test_falls_back_to_default_for_an_unmapped_requested_by():
    ui_service = MagicMock()
    default_service = MagicMock()
    default_service.request_confirmation.return_value = ConfirmationOutcome.TIMED_OUT
    router = RequestedByConfirmationService(default=default_service, overrides={"ui": ui_service})

    outcome = router.request_confirmation(_confirmation_request(requested_by="voice"))

    assert outcome == ConfirmationOutcome.TIMED_OUT
    default_service.request_confirmation.assert_called_once()
    ui_service.request_confirmation.assert_not_called()


def test_falls_back_to_default_when_overrides_is_empty():
    default_service = MagicMock()
    default_service.request_confirmation.return_value = ConfirmationOutcome.DECLINED
    router = RequestedByConfirmationService(default=default_service, overrides={})

    outcome = router.request_confirmation(_confirmation_request(requested_by="ui"))

    assert outcome == ConfirmationOutcome.DECLINED
