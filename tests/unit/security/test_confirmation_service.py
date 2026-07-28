"""Unit tests for security.confirmation_service.

Local, narrowly-scoped fakes for VoiceSessionManager/PersonaManager
(not the shared tests/unit/voice/conftest.py FakeVoiceSessionManager,
which is shaped for a different scenario) — matching this project's
established "local double for one narrow scenario" pattern.
"""

from datetime import UTC, datetime

import pytest

from device_control.action_engine import ActionContext, ActionRequest, ActionType
from security.confirmation_service import (
    ConfirmationOutcome,
    ConfirmationRequest,
    VoiceConfirmationService,
    build_prompt_text,
)
from security.policy_engine import RiskLevel
from voice.errors import SessionError


class _FakeSessionManager:
    def __init__(self, active: bool = True) -> None:
        self._active = active
        self.speak_reply_calls: list[tuple[str, str]] = []
        self.capture_timeout_seconds: float | None = None
        self.reply_to_return: str | None = "yes"
        self.raise_on_speak: Exception | None = None
        self.raise_on_capture: Exception | None = None

    def is_active(self) -> bool:
        return self._active

    def speak_reply(self, text: str, voice_id: str) -> None:
        if self.raise_on_speak is not None:
            raise self.raise_on_speak
        self.speak_reply_calls.append((text, voice_id))

    def capture_and_transcribe_reply(self, timeout_seconds: float) -> str | None:
        if self.raise_on_capture is not None:
            raise self.raise_on_capture
        self.capture_timeout_seconds = timeout_seconds
        return self.reply_to_return


class _FakePersona:
    voice_id = "p340"


class _FakePersonaManager:
    def __init__(self) -> None:
        self._persona = _FakePersona()

    def active_persona(self):
        return self._persona


def make_action_request(action_type: ActionType, **parameters) -> ActionRequest:
    return ActionRequest(
        action_type=action_type,
        parameters=parameters,
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
    )


# --- build_prompt_text() --------------------------------------------------------


def test_build_prompt_text_for_high_risk_file_delete_matches_spec_example():
    request = make_action_request(ActionType.FILE_DELETE, path="example.txt")

    text = build_prompt_text(request, RiskLevel.HIGH)

    assert text == "This will permanently delete the file example.txt. Should I proceed?"


def test_build_prompt_text_joins_a_command_list():
    request = make_action_request(ActionType.SYSTEM_COMMAND, command=["ping", "-n", "1", "host"])

    text = build_prompt_text(request, RiskLevel.HIGH)

    assert "ping -n 1 host" in text


def test_build_prompt_text_falls_back_gracefully_for_missing_parameters():
    request = make_action_request(ActionType.FILE_DELETE)

    text = build_prompt_text(request, RiskLevel.HIGH)

    assert "{path}" not in text
    assert text.endswith("Should I proceed?")


def test_build_prompt_text_falls_back_for_unmapped_action_type():
    request = make_action_request(ActionType.WORKFLOW_STEP)

    text = build_prompt_text(request, RiskLevel.HIGH)

    assert "run a workflow step" in text


# --- VoiceConfirmationService.request_confirmation() ----------------------------


def test_no_active_session_times_out_immediately_without_speaking_or_listening():
    session_manager = _FakeSessionManager(active=False)
    service = VoiceConfirmationService(session_manager, _FakePersonaManager(), 20.0)
    request = ConfirmationRequest(
        action_request=make_action_request(ActionType.FILE_DELETE, path="a.txt"),
        risk_level=RiskLevel.HIGH,
        prompt_text="irrelevant",
    )

    outcome = service.request_confirmation(request)

    assert outcome is ConfirmationOutcome.TIMED_OUT
    assert session_manager.speak_reply_calls == []


def test_speaks_via_active_persona_voice_and_uses_configured_timeout():
    session_manager = _FakeSessionManager(active=True)
    session_manager.reply_to_return = "yes"
    service = VoiceConfirmationService(session_manager, _FakePersonaManager(), 15.0)
    request = ConfirmationRequest(
        action_request=make_action_request(ActionType.FILE_DELETE, path="a.txt"),
        risk_level=RiskLevel.HIGH,
        prompt_text="irrelevant — VoiceConfirmationService rebuilds its own",
    )

    service.request_confirmation(request)

    assert len(session_manager.speak_reply_calls) == 1
    spoken_text, voice_id = session_manager.speak_reply_calls[0]
    assert "permanently delete the file a.txt" in spoken_text
    assert voice_id == "p340"
    assert session_manager.capture_timeout_seconds == 15.0


def test_has_custom_prompt_true_speaks_prompt_text_verbatim():
    """Sprint 4.13 (Technical Debt Resolution) — closes
    backlog/technical_debt.md item 25: a caller that built prompt_text
    from richer context than a single ActionRequest can carry (e.g.
    WorkflowExecutor's own whole-workflow prompt) gets it spoken
    verbatim, not rebuilt from build_prompt_text()."""
    session_manager = _FakeSessionManager(active=True)
    session_manager.reply_to_return = "yes"
    service = VoiceConfirmationService(session_manager, _FakePersonaManager(), 15.0)
    request = ConfirmationRequest(
        action_request=make_action_request(ActionType.WORKFLOW_STEP),
        risk_level=RiskLevel.HIGH,
        prompt_text="This workflow 'Cleanup' will run 3 actions, including 1 higher-risk steps.",
        has_custom_prompt=True,
    )

    service.request_confirmation(request)

    spoken_text, _ = session_manager.speak_reply_calls[0]
    assert spoken_text == (
        "This workflow 'Cleanup' will run 3 actions, including 1 higher-risk steps."
    )


def test_has_custom_prompt_false_still_rebuilds_a_generic_description():
    """Default behavior (every PermissionGate.check()-originated request)
    is unchanged by item 25's fix — has_custom_prompt defaults False."""
    session_manager = _FakeSessionManager(active=True)
    session_manager.reply_to_return = "yes"
    service = VoiceConfirmationService(session_manager, _FakePersonaManager(), 15.0)
    request = ConfirmationRequest(
        action_request=make_action_request(ActionType.WORKFLOW_STEP),
        risk_level=RiskLevel.HIGH,
        prompt_text="This is completely ignored when has_custom_prompt is False.",
    )

    service.request_confirmation(request)

    spoken_text, _ = session_manager.speak_reply_calls[0]
    assert spoken_text == "This will run a workflow step. Should I proceed?"


@pytest.mark.parametrize(
    "reply_text,expected_outcome",
    [
        ("yes", ConfirmationOutcome.CONFIRMED),
        ("yeah go ahead", ConfirmationOutcome.CONFIRMED),
        ("sure", ConfirmationOutcome.CONFIRMED),
        ("no", ConfirmationOutcome.DECLINED),
        ("no don't do that", ConfirmationOutcome.DECLINED),
        ("cancel that", ConfirmationOutcome.DECLINED),
        ("you know what, never mind", ConfirmationOutcome.DECLINED),
        ("banana", ConfirmationOutcome.DECLINED),
    ],
)
def test_interprets_spoken_reply_correctly(reply_text, expected_outcome):
    session_manager = _FakeSessionManager(active=True)
    session_manager.reply_to_return = reply_text
    service = VoiceConfirmationService(session_manager, _FakePersonaManager(), 20.0)
    request = ConfirmationRequest(
        action_request=make_action_request(ActionType.FILE_DELETE, path="a.txt"),
        risk_level=RiskLevel.HIGH,
        prompt_text="x",
    )

    outcome = service.request_confirmation(request)

    assert outcome is expected_outcome


def test_no_reply_within_timeout_is_timed_out():
    session_manager = _FakeSessionManager(active=True)
    session_manager.reply_to_return = None
    service = VoiceConfirmationService(session_manager, _FakePersonaManager(), 20.0)
    request = ConfirmationRequest(
        action_request=make_action_request(ActionType.FILE_DELETE, path="a.txt"),
        risk_level=RiskLevel.HIGH,
        prompt_text="x",
    )

    outcome = service.request_confirmation(request)

    assert outcome is ConfirmationOutcome.TIMED_OUT


# --- Sprint 4.12 hardening (scenario e): VoiceSessionManager failure mid-request ----


def test_speak_reply_raising_degrades_to_timed_out_not_an_exception():
    """A real induced VoiceSessionManager failure — is_active() was True
    when checked, but the session errors (e.g. a real SessionError from
    a race where the session ends) once speak_reply() actually runs —
    distinct from the already-tested "no active session at all" case."""
    session_manager = _FakeSessionManager(active=True)
    session_manager.raise_on_speak = SessionError("session ended mid-request")
    service = VoiceConfirmationService(session_manager, _FakePersonaManager(), 20.0)
    request = ConfirmationRequest(
        action_request=make_action_request(ActionType.FILE_DELETE, path="a.txt"),
        risk_level=RiskLevel.HIGH,
        prompt_text="x",
    )

    outcome = service.request_confirmation(request)  # must not raise

    assert outcome is ConfirmationOutcome.TIMED_OUT


def test_capture_and_transcribe_reply_raising_degrades_to_timed_out_not_an_exception():
    session_manager = _FakeSessionManager(active=True)
    session_manager.raise_on_capture = RuntimeError("unexpected capture failure")
    service = VoiceConfirmationService(session_manager, _FakePersonaManager(), 20.0)
    request = ConfirmationRequest(
        action_request=make_action_request(ActionType.FILE_DELETE, path="a.txt"),
        risk_level=RiskLevel.HIGH,
        prompt_text="x",
    )

    outcome = service.request_confirmation(request)  # must not raise

    assert outcome is ConfirmationOutcome.TIMED_OUT
    assert len(session_manager.speak_reply_calls) == 1  # the prompt was genuinely spoken first
