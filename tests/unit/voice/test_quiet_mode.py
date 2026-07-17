"""Unit tests for voice.quiet_mode.

All tests exercise QuietModeController against a FakeVoiceSessionManager —
no real microphone, wake-word model, STT, or TTS is involved (per this
sprint's own Testing Checklist: "verified against fakes for
WakeWordDetector/VoiceSessionManager, not real hardware").
"""

from voice.quiet_mode import ActivationReason, OperatingMode, QuietModeController
from voice.session_manager import SessionEndReason


def test_starts_in_dormant_mode(fake_session_manager):
    controller = QuietModeController(fake_session_manager)

    assert controller.current_mode() is OperatingMode.DORMANT


def test_wake_word_detection_while_dormant_activates_and_begins_session(fake_session_manager):
    controller = QuietModeController(fake_session_manager)
    controller.start()

    controller._on_wake_word_detected("hey jarminei")

    assert controller.current_mode() is OperatingMode.ACTIVE
    assert fake_session_manager.begin_session_calls == 1


def test_activate_records_reason_and_transitions(fake_session_manager):
    controller = QuietModeController(fake_session_manager)
    controller.start()

    controller.activate(ActivationReason.WAKE_WORD)

    assert controller.current_mode() is OperatingMode.ACTIVE
    assert fake_session_manager.begin_session_calls == 1


def test_wake_word_detection_while_already_active_is_a_no_op(fake_session_manager):
    controller = QuietModeController(fake_session_manager)
    controller.start()
    controller._on_wake_word_detected("hey jarminei")

    controller._on_wake_word_detected("hey jarminei")

    assert controller.current_mode() is OperatingMode.ACTIVE
    assert fake_session_manager.begin_session_calls == 1


def test_session_end_transitions_back_to_dormant(fake_session_manager):
    controller = QuietModeController(fake_session_manager)
    controller.start()
    controller._on_wake_word_detected("hey jarminei")
    fake_session_manager.set_active(False)

    controller._on_session_ended(SessionEndReason.EXPLICIT_END)

    assert controller.current_mode() is OperatingMode.DORMANT


def test_session_end_transitions_back_to_dormant_regardless_of_reason(fake_session_manager):
    for reason in SessionEndReason:
        controller = QuietModeController(fake_session_manager)
        controller.start()
        controller._on_wake_word_detected("hey jarminei")
        fake_session_manager.set_active(False)

        controller._on_session_ended(reason)

        assert controller.current_mode() is OperatingMode.DORMANT


def test_wake_word_callback_ignored_while_not_started(fake_session_manager):
    controller = QuietModeController(fake_session_manager)

    controller._on_wake_word_detected("hey jarminei")

    assert controller.current_mode() is OperatingMode.DORMANT
    assert fake_session_manager.begin_session_calls == 0


def test_session_end_callback_ignored_while_not_started(fake_session_manager):
    controller = QuietModeController(fake_session_manager)
    controller.start()
    controller._on_wake_word_detected("hey jarminei")
    controller.stop()

    controller._on_session_ended(SessionEndReason.SILENCE_TIMEOUT)

    assert controller.current_mode() is OperatingMode.ACTIVE


def test_health_check_false_before_start(fake_session_manager):
    controller = QuietModeController(fake_session_manager)

    assert controller.health_check() is False


def test_health_check_true_when_dormant_and_no_session_running(fake_session_manager):
    controller = QuietModeController(fake_session_manager)
    controller.start()

    assert controller.health_check() is True


def test_health_check_true_when_active_and_session_running(fake_session_manager):
    controller = QuietModeController(fake_session_manager)
    controller.start()
    controller._on_wake_word_detected("hey jarminei")

    assert controller.health_check() is True


def test_health_check_false_when_active_but_no_session_running(fake_session_manager):
    controller = QuietModeController(fake_session_manager)
    controller.start()
    controller._on_wake_word_detected("hey jarminei")
    fake_session_manager.set_active(False)

    assert controller.health_check() is False


def test_health_check_false_when_dormant_but_session_running(fake_session_manager):
    controller = QuietModeController(fake_session_manager)
    controller.start()
    fake_session_manager.set_active(True)

    assert controller.health_check() is False
