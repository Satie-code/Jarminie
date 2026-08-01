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


# --- announce_first passthrough (Sprint 4.18) ---------------------------------


def test_activate_without_announce_first_passes_none(fake_session_manager):
    controller = QuietModeController(fake_session_manager)
    controller.start()

    controller.activate(ActivationReason.WAKE_WORD)

    assert fake_session_manager.announce_first_calls == [None]


def test_activate_with_announce_first_passes_it_through(fake_session_manager):
    controller = QuietModeController(fake_session_manager)
    controller.start()

    controller.activate(
        ActivationReason.SCHEDULED_ALERT, announce_first=("Your reminder is due.", "p340")
    )

    assert fake_session_manager.announce_first_calls == [("Your reminder is due.", "p340")]
    assert controller.current_mode() is OperatingMode.ACTIVE


def test_activate_with_announce_first_failure_rolls_back_to_dormant(fake_session_manager):
    fake_session_manager.raise_on_begin_session = True
    controller = QuietModeController(fake_session_manager)
    controller.start()

    controller.activate(
        ActivationReason.SCHEDULED_ALERT, announce_first=("Your reminder is due.", "p340")
    )

    assert controller.current_mode() is OperatingMode.DORMANT


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


def test_activate_reverts_to_dormant_when_begin_session_fails(fake_session_manager):
    """Sprint 2.14 hardening (found during the Level 2 adversarial
    re-read): without this, a begin_session() failure left the
    controller stuck believing it was ACTIVE with no real session ever
    started — exactly the inconsistent state health_check() exists to
    catch, but with no way back to DORMANT on its own."""
    fake_session_manager.raise_on_begin_session = True
    controller = QuietModeController(fake_session_manager)
    controller.start()

    controller._on_wake_word_detected("hey jarminei")  # must not raise

    assert controller.current_mode() is OperatingMode.DORMANT
    assert controller.health_check() is True
