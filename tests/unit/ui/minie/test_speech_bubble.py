"""Unit tests for ui.minie.speech_bubble."""

from unittest.mock import MagicMock

from config.schema import PresentationConfig, UIConfig
from emotion.state_manager import EmotionalState
from ui.minie.speech_bubble import MinieSpeechBubble
from ui.minie.ui_state_adapter import MinieUiStateAdapter
from voice.session_manager import SessionState

_DEFAULT_TEXT = "Hello! How can I help you today? ♡"
_THINKING_TEXT = "Thinking... ♡"


def _core_manager() -> MagicMock:
    manager = MagicMock()
    manager.presentation_config.return_value = PresentationConfig()
    manager.ui_config.return_value = UIConfig()
    return manager


def _real_adapter(
    core_manager, *, session_state: SessionState = SessionState.IDLE
) -> MinieUiStateAdapter:
    """A real MinieUiStateAdapter (not a MagicMock) so its own real Qt
    Signals fire end-to-end — mirrors test_avatar_stage.py's own
    _adapter() helper, the established precedent for this workstream."""
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


def test_default_text_before_any_reply(qtbot):
    bubble = MinieSpeechBubble(MagicMock())
    qtbot.addWidget(bubble)

    assert bubble._body_label.text() == _DEFAULT_TEXT


def test_subscribes_to_the_adapters_session_state_updated_signal(qtbot):
    adapter = MagicMock()
    bubble = MinieSpeechBubble(adapter)
    qtbot.addWidget(bubble)

    adapter.session_state_updated.connect.assert_called_once()


def test_show_reply_sets_the_body_text(qtbot):
    bubble = MinieSpeechBubble(MagicMock())
    qtbot.addWidget(bubble)

    bubble.show_reply("Sure, I can help with that! ♡")

    assert bubble._body_label.text() == "Sure, I can help with that! ♡"


def test_processing_state_shows_thinking_placeholder(qtbot):
    bubble = MinieSpeechBubble(MagicMock())
    qtbot.addWidget(bubble)

    bubble._on_session_state_updated(SessionState.PROCESSING)

    assert bubble._body_label.text() == _THINKING_TEXT


def test_awaiting_next_turn_state_shows_thinking_placeholder(qtbot):
    bubble = MinieSpeechBubble(MagicMock())
    qtbot.addWidget(bubble)

    bubble._on_session_state_updated(SessionState.AWAITING_NEXT_TURN)

    assert bubble._body_label.text() == _THINKING_TEXT


def test_idle_state_never_shows_the_thinking_placeholder(qtbot):
    bubble = MinieSpeechBubble(MagicMock())
    qtbot.addWidget(bubble)

    bubble._on_session_state_updated(SessionState.IDLE)

    assert bubble._body_label.text() == _DEFAULT_TEXT


def test_show_reply_overwrites_a_thinking_placeholder(qtbot):
    bubble = MinieSpeechBubble(MagicMock())
    qtbot.addWidget(bubble)
    bubble._on_session_state_updated(SessionState.PROCESSING)

    bubble.show_reply("Here's your answer! ♡")

    assert bubble._body_label.text() == "Here's your answer! ♡"


def test_leaving_a_thinking_state_without_a_real_reply_falls_back_to_default(qtbot):
    bubble = MinieSpeechBubble(MagicMock())
    qtbot.addWidget(bubble)
    bubble._on_session_state_updated(SessionState.PROCESSING)

    bubble._on_session_state_updated(SessionState.IDLE)

    assert bubble._body_label.text() == _DEFAULT_TEXT


def test_leaving_a_thinking_state_after_a_real_reply_keeps_the_reply(qtbot):
    bubble = MinieSpeechBubble(MagicMock())
    qtbot.addWidget(bubble)
    bubble._on_session_state_updated(SessionState.PROCESSING)
    bubble.show_reply("Here's your answer! ♡")

    bubble._on_session_state_updated(SessionState.IDLE)

    assert bubble._body_label.text() == "Here's your answer! ♡"


def test_survives_an_unhashable_session_state(qtbot):
    bubble = MinieSpeechBubble(MagicMock())
    qtbot.addWidget(bubble)

    bubble._on_session_state_updated([])  # unhashable against a frozenset; must not raise

    assert bubble._body_label.text() == _DEFAULT_TEXT


def test_a_real_adapter_refresh_drives_the_thinking_placeholder_end_to_end(qtbot):
    core_manager = _core_manager()
    adapter = _real_adapter(core_manager, session_state=SessionState.PROCESSING)
    bubble = MinieSpeechBubble(adapter)
    qtbot.addWidget(bubble)

    adapter.refresh()

    assert bubble._body_label.text() == _THINKING_TEXT
