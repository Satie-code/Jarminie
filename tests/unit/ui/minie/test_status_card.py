"""Unit tests for ui.minie.status_card."""

from unittest.mock import MagicMock

from emotion.state_manager import EmotionalState
from ui.minie.status_card import MinieStatusCard
from ui.minie.ui_state_adapter import MinieUiStateAdapter
from voice.session_manager import SessionState


def _real_adapter(
    *, session_state=SessionState.IDLE, avatar_connected=False
) -> MinieUiStateAdapter:
    """A real MinieUiStateAdapter (not a MagicMock) so its own real Qt
    Signals fire end-to-end — mirrors test_emotion_panel.py's own
    _real_adapter() helper, the established precedent for this
    workstream."""
    presentation_controller = MagicMock()
    presentation_controller.last_state_for.return_value = None
    emotional_state_manager = MagicMock()
    emotional_state_manager.current_state.return_value = EmotionalState()
    voice_session_manager = MagicMock()
    voice_session_manager.current_session_state.return_value = session_state
    avatar_renderer = MagicMock()
    avatar_renderer.is_connected.return_value = avatar_connected
    core_manager = MagicMock()
    from config.schema import UIConfig

    core_manager.ui_config.return_value = UIConfig()
    return MinieUiStateAdapter(
        presentation_controller,
        emotional_state_manager,
        voice_session_manager,
        avatar_renderer,
        core_manager,
    )


def test_shows_connecting_before_any_signal_has_fired(qtbot):
    card = MinieStatusCard(MagicMock())
    qtbot.addWidget(card)

    assert "Connecting" in card._status_label.text()


def test_subscribes_to_session_state_and_avatar_status_signals(qtbot):
    adapter = MagicMock()
    card = MinieStatusCard(adapter)
    qtbot.addWidget(card)

    adapter.session_state_updated.connect.assert_called_once()
    adapter.avatar_status_updated.connect.assert_called_once()


def test_stays_connecting_while_avatar_is_not_connected_regardless_of_session_state(qtbot):
    card = MinieStatusCard(MagicMock())
    qtbot.addWidget(card)

    card._on_session_state_updated(SessionState.SPEAKING)

    assert "Connecting" in card._status_label.text()


def test_shows_online_once_connected_and_idle(qtbot):
    card = MinieStatusCard(MagicMock())
    qtbot.addWidget(card)

    card._on_avatar_status_updated(True)
    card._on_session_state_updated(SessionState.IDLE)

    assert "Online" in card._status_label.text()


def test_shows_listening_when_connected_and_listening(qtbot):
    card = MinieStatusCard(MagicMock())
    qtbot.addWidget(card)

    card._on_avatar_status_updated(True)
    card._on_session_state_updated(SessionState.LISTENING)

    assert "Listening" in card._status_label.text()


def test_shows_thinking_for_processing_and_awaiting_next_turn(qtbot):
    card = MinieStatusCard(MagicMock())
    qtbot.addWidget(card)
    card._on_avatar_status_updated(True)

    card._on_session_state_updated(SessionState.PROCESSING)
    assert "Thinking" in card._status_label.text()

    card._on_session_state_updated(SessionState.AWAITING_NEXT_TURN)
    assert "Thinking" in card._status_label.text()


def test_shows_speaking_when_connected_and_speaking(qtbot):
    card = MinieStatusCard(MagicMock())
    qtbot.addWidget(card)

    card._on_avatar_status_updated(True)
    card._on_session_state_updated(SessionState.SPEAKING)

    assert "Speaking" in card._status_label.text()


def test_reverts_to_connecting_if_avatar_disconnects_again(qtbot):
    card = MinieStatusCard(MagicMock())
    qtbot.addWidget(card)
    card._on_avatar_status_updated(True)
    card._on_session_state_updated(SessionState.SPEAKING)

    card._on_avatar_status_updated(False)

    assert "Connecting" in card._status_label.text()


def test_subtext_is_always_present(qtbot):
    from PySide6.QtWidgets import QLabel

    card = MinieStatusCard(MagicMock())
    qtbot.addWidget(card)

    texts = [label.text() for label in card.findChildren(QLabel)]
    assert "Always here for you ♡" in texts


def test_refresh_survives_an_unhashable_session_state_without_crashing(qtbot):
    card = MinieStatusCard(MagicMock())
    qtbot.addWidget(card)
    card._on_avatar_status_updated(True)
    good_text = card._status_label.text()

    card._on_session_state_updated([1, 2, 3])  # unhashable; must not raise

    assert card._status_label.text() == good_text


def test_a_real_adapter_refresh_updates_the_status_end_to_end(qtbot):
    adapter = _real_adapter(session_state=SessionState.SPEAKING, avatar_connected=True)
    card = MinieStatusCard(adapter)
    qtbot.addWidget(card)

    adapter.refresh()

    assert "Speaking" in card._status_label.text()
