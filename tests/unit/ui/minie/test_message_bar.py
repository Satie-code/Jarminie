"""Unit tests for ui.minie.message_bar.

Background-thread submission tests mirror
tests/unit/ui/jarvis/test_command_bar.py's own established pattern
exactly (qtbot.waitUntil() to wait for the marshaled UI update after a
threading.Thread + QTimer.singleShot(0, ...) round trip).
"""

import inspect
from unittest.mock import MagicMock

from config.schema import UIConfig
from emotion.state_manager import EmotionalState
from ui.minie.message_bar import MinieMessageBar
from ui.minie.ui_state_adapter import MinieUiStateAdapter
from voice.session_manager import SessionState


def _real_adapter(*, session_state: SessionState = SessionState.IDLE) -> MinieUiStateAdapter:
    """A real MinieUiStateAdapter (not a MagicMock) so its own real Qt
    Signals fire end-to-end — mirrors test_avatar_stage.py's/
    test_speech_bubble.py's own established precedent for this
    workstream."""
    core_manager = MagicMock()
    core_manager.ui_config.return_value = UIConfig()
    presentation_controller = MagicMock()
    presentation_controller.last_state_for.return_value = None
    emotional_state_manager = MagicMock()
    emotional_state_manager.current_state.return_value = EmotionalState()
    voice_session_manager = MagicMock()
    voice_session_manager.current_session_state.return_value = session_state
    avatar_renderer = MagicMock()
    return MinieUiStateAdapter(
        presentation_controller,
        emotional_state_manager,
        voice_session_manager,
        avatar_renderer,
        core_manager,
    )


def test_construction_does_not_crash(qtbot):
    pipeline = MagicMock()
    bar = MinieMessageBar(pipeline, MagicMock())
    qtbot.addWidget(bar)


def test_constructor_takes_no_voice_session_starting_dependency():
    """The Microphone Rule (voice/quiet_mode.py's own QuietModeController
    docstring): the only path from DORMANT to ACTIVE is a real wake-word
    detection, never a UI button. MinieMessageBar structurally can't
    violate this since its constructor never receives a
    VoiceSessionManager/QuietModeController at all — confirmed here via
    the real, declared signature rather than trusting a docstring."""
    parameters = inspect.signature(MinieMessageBar.__init__).parameters
    assert set(parameters) == {"self", "pipeline", "ui_state_adapter", "parent"}


def test_mic_indicator_never_receives_a_session_manager_and_never_calls_one(qtbot):
    """Belt-and-suspenders: even a mocked voice-session-shaped object
    handed nowhere near this widget is never touched — asserted by
    simply never constructing or passing one, and confirming the mic
    indicator has no method capable of starting/stopping a session."""
    pipeline = MagicMock()
    bar = MinieMessageBar(pipeline, MagicMock())
    qtbot.addWidget(bar)

    forbidden_method_names = {"begin_session", "end_session", "activate", "deactivate"}
    mic_methods = set(dir(bar._mic_indicator))
    assert forbidden_method_names.isdisjoint(mic_methods)


def test_mic_indicator_has_a_wake_word_tooltip(qtbot):
    pipeline = MagicMock()
    bar = MinieMessageBar(pipeline, MagicMock())
    qtbot.addWidget(bar)

    assert "wake word" in bar._mic_indicator.toolTip().lower()


def test_empty_input_does_not_dispatch(qtbot):
    pipeline = MagicMock()
    bar = MinieMessageBar(pipeline, MagicMock())
    qtbot.addWidget(bar)

    bar._input.setText("   ")
    bar._submit()

    pipeline.submit_text.assert_not_called()


def test_submitting_text_disables_input_and_clears_it(qtbot):
    pipeline = MagicMock()
    pipeline.submit_text.return_value = "Sure thing! ♡"
    bar = MinieMessageBar(pipeline, MagicMock())
    qtbot.addWidget(bar)
    bar._input.setText("how's my day looking")

    bar._submit()

    assert bar._input.text() == ""
    assert not bar._input.isEnabled()
    assert not bar._send_button.isEnabled()


def test_submitting_text_eventually_calls_pipeline_and_displays_the_reply(qtbot):
    pipeline = MagicMock()
    pipeline.submit_text.return_value = "Sure, done! ♡"
    bar = MinieMessageBar(pipeline, MagicMock())
    qtbot.addWidget(bar)
    bar._input.setText("how's my day looking")

    bar._submit()

    qtbot.waitUntil(lambda: bar._reply_label.text() == "Sure, done! ♡", timeout=2000)
    pipeline.submit_text.assert_called_once()
    call_args = pipeline.submit_text.call_args[0]
    assert call_args[0] == "how's my day looking"
    assert call_args[1] == bar._session_id


def test_input_is_re_enabled_after_the_reply_arrives(qtbot):
    pipeline = MagicMock()
    pipeline.submit_text.return_value = "Done."
    bar = MinieMessageBar(pipeline, MagicMock())
    qtbot.addWidget(bar)
    bar._input.setText("hello")

    bar._submit()

    qtbot.waitUntil(lambda: bar._input.isEnabled(), timeout=2000)
    assert bar._send_button.isEnabled()


def test_reply_received_is_emitted_with_the_real_reply(qtbot):
    pipeline = MagicMock()
    pipeline.submit_text.return_value = "Here's your answer! ♡"
    bar = MinieMessageBar(pipeline, MagicMock())
    qtbot.addWidget(bar)
    bar._input.setText("hello")

    with qtbot.waitSignal(bar.reply_received, timeout=2000) as blocker:
        bar._submit()

    assert blocker.args == ["Here's your answer! ♡"]


def test_a_raising_pipeline_still_produces_a_reply_and_still_emits_it(qtbot):
    pipeline = MagicMock()
    pipeline.submit_text.side_effect = RuntimeError("boom")
    bar = MinieMessageBar(pipeline, MagicMock())
    qtbot.addWidget(bar)
    bar._input.setText("hello")

    with qtbot.waitSignal(bar.reply_received, timeout=2000) as blocker:
        bar._submit()

    assert "wrong" in bar._reply_label.text().lower()
    assert "wrong" in blocker.args[0].lower()


def test_session_id_is_stable_across_submissions(qtbot):
    pipeline = MagicMock()
    pipeline.submit_text.return_value = "Done."
    bar = MinieMessageBar(pipeline, MagicMock())
    qtbot.addWidget(bar)

    bar._input.setText("first")
    bar._submit()
    qtbot.waitUntil(lambda: bar._input.isEnabled(), timeout=2000)
    bar._input.setText("second")
    bar._submit()
    qtbot.waitUntil(lambda: bar._input.isEnabled(), timeout=2000)

    first_session_id = pipeline.submit_text.call_args_list[0][0][1]
    second_session_id = pipeline.submit_text.call_args_list[1][0][1]
    assert first_session_id == second_session_id


def test_enter_key_submits(qtbot):
    pipeline = MagicMock()
    pipeline.submit_text.return_value = "Done."
    bar = MinieMessageBar(pipeline, MagicMock())
    qtbot.addWidget(bar)
    bar._input.setText("hello")

    bar._input.returnPressed.emit()

    qtbot.waitUntil(lambda: pipeline.submit_text.called, timeout=2000)


def test_subscribes_to_the_adapters_session_state_updated_signal(qtbot):
    adapter = MagicMock()
    bar = MinieMessageBar(MagicMock(), adapter)
    qtbot.addWidget(bar)

    adapter.session_state_updated.connect.assert_called_once()


def test_mic_indicator_pulses_only_while_listening(qtbot):
    pipeline = MagicMock()
    bar = MinieMessageBar(pipeline, MagicMock())
    qtbot.addWidget(bar)

    bar._on_session_state_updated(SessionState.LISTENING)
    assert bar._mic_indicator._pulse_animation.state().name == "Running"

    bar._on_session_state_updated(SessionState.IDLE)
    assert bar._mic_indicator._pulse_animation.state().name == "Stopped"


def test_mic_indicator_survives_an_unrecognized_session_state(qtbot):
    pipeline = MagicMock()
    bar = MinieMessageBar(pipeline, MagicMock())
    qtbot.addWidget(bar)

    bar._on_session_state_updated("not-a-real-session-state")  # must not raise

    assert bar._mic_indicator._state == "not-a-real-session-state"


def test_a_real_adapter_refresh_drives_the_mic_indicator_end_to_end(qtbot):
    adapter = _real_adapter(session_state=SessionState.SPEAKING)
    bar = MinieMessageBar(MagicMock(), adapter)
    qtbot.addWidget(bar)

    adapter.refresh()

    assert bar._mic_indicator._state == SessionState.SPEAKING


def test_shortcut_buttons_emit_their_own_signals(qtbot):
    bar = MinieMessageBar(MagicMock(), MagicMock())
    qtbot.addWidget(bar)

    with qtbot.waitSignal(bar.relationship_shortcut_requested, timeout=1000):
        bar._relationship_button.click()
    with qtbot.waitSignal(bar.companion_shortcut_requested, timeout=1000):
        bar._companion_button.click()
    with qtbot.waitSignal(bar.home_requested, timeout=1000):
        bar._home_button.click()
