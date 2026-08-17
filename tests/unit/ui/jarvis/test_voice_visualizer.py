"""Unit tests for ui.jarvis.voice_visualizer."""

from unittest.mock import MagicMock

from ui.jarvis.voice_visualizer import VoiceVisualizer, VoiceVisualState
from voice.session_manager import SessionState


def _session_manager(state: SessionState) -> MagicMock:
    manager = MagicMock()
    manager.current_session_state.return_value = state
    return manager


def test_defaults_to_idle_before_first_tick_result(qtbot):
    widget = VoiceVisualizer(_session_manager(SessionState.IDLE))
    qtbot.addWidget(widget)

    assert widget._state == VoiceVisualState.IDLE


def test_reflects_listening_state(qtbot):
    widget = VoiceVisualizer(_session_manager(SessionState.LISTENING))
    qtbot.addWidget(widget)

    assert widget._state == VoiceVisualState.LISTENING
    assert widget._status_label.text() == "Listening..."


def test_reflects_speaking_state(qtbot):
    widget = VoiceVisualizer(_session_manager(SessionState.SPEAKING))
    qtbot.addWidget(widget)

    assert widget._state == VoiceVisualState.SPEAKING
    assert widget._status_label.text() == "Speaking..."


def test_awaiting_next_turn_maps_to_processing(qtbot):
    widget = VoiceVisualizer(_session_manager(SessionState.AWAITING_NEXT_TURN))
    qtbot.addWidget(widget)

    assert widget._state == VoiceVisualState.PROCESSING


def test_updates_when_session_state_changes(qtbot):
    manager = _session_manager(SessionState.IDLE)
    widget = VoiceVisualizer(manager)
    qtbot.addWidget(widget)

    manager.current_session_state.return_value = SessionState.LISTENING
    widget._on_tick()

    assert widget._state == VoiceVisualState.LISTENING


def test_survives_a_raising_session_manager(qtbot):
    manager = MagicMock()
    manager.current_session_state.side_effect = RuntimeError("boom")

    widget = VoiceVisualizer(manager)  # construction itself calls _on_tick() once
    qtbot.addWidget(widget)

    widget._on_tick()  # must not raise on a later call either
    assert widget._state == VoiceVisualState.IDLE


def test_keeps_last_known_good_state_after_a_later_failure(qtbot):
    manager = _session_manager(SessionState.SPEAKING)
    widget = VoiceVisualizer(manager)
    qtbot.addWidget(widget)

    manager.current_session_state.side_effect = RuntimeError("boom")
    widget._on_tick()

    assert widget._state == VoiceVisualState.SPEAKING


def test_paints_without_raising(qtbot):
    widget = VoiceVisualizer(_session_manager(SessionState.LISTENING))
    qtbot.addWidget(widget)
    widget.resize(140, 40)

    pixmap = widget.grab()

    assert not pixmap.isNull()


def test_pulse_advances_over_real_ticks(qtbot):
    widget = VoiceVisualizer(_session_manager(SessionState.LISTENING))
    qtbot.addWidget(widget)
    phase_before = widget._pulse._phase

    qtbot.wait(200)  # several ticks at the widget's own 60ms interval

    assert widget._pulse._phase != phase_before
