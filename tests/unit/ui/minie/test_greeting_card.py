"""Unit tests for ui.minie.greeting_card."""

from unittest.mock import MagicMock

from config.schema import UIConfig
from emotion.state_manager import EmotionalState
from presentation import minie_theme
from ui.minie.greeting_card import MinieGreetingCard
from ui.minie.ui_state_adapter import MinieUiStateAdapter
from voice.session_manager import SessionState


def _core_manager(display_name: str | None = None, interval_ms: int = 3000) -> MagicMock:
    manager = MagicMock()
    manager.ui_config.return_value = UIConfig(
        user_display_name=display_name, status_refresh_interval_ms=interval_ms
    )
    return manager


def _real_adapter(core_manager, *, session_state=SessionState.IDLE) -> MinieUiStateAdapter:
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
    return MinieUiStateAdapter(
        presentation_controller,
        emotional_state_manager,
        voice_session_manager,
        avatar_renderer,
        core_manager,
    )


def test_heading_falls_back_to_there_when_no_display_name_configured(qtbot):
    card = MinieGreetingCard(MagicMock(), _core_manager(display_name=None))
    qtbot.addWidget(card)

    assert card._heading_label.text() == "Hi There! ♡"


def test_heading_uses_the_configured_display_name_title_cased(qtbot):
    card = MinieGreetingCard(MagicMock(), _core_manager(display_name="sattie"))
    qtbot.addWidget(card)

    assert card._heading_label.text() == "Hi Sattie! ♡"


def test_subtext_defaults_to_the_idle_line_on_construction(qtbot):
    card = MinieGreetingCard(MagicMock(), _core_manager())
    qtbot.addWidget(card)

    assert card._subtext_label.text() == "I'm Minie — your cute AI friend, always with you!"


def test_refresh_survives_a_failed_config_read_without_crashing(qtbot):
    # The interval read at construction is a one-time DI read, not
    # guarded (the same established precedent RemindersPanel/
    # MinieUiStateAdapter already set for their own construction-time
    # ui_config() read) — Fail Gracefully covers the recurring refresh()
    # callback, exercised here only after construction has succeeded.
    manager = _core_manager(display_name="Sattie")
    card = MinieGreetingCard(MagicMock(), manager)
    qtbot.addWidget(card)

    manager.ui_config.side_effect = RuntimeError("config exploded")
    card.refresh()  # must not raise


def test_refresh_keeps_last_known_good_name_after_a_later_failure(qtbot):
    manager = _core_manager(display_name="Sattie")
    card = MinieGreetingCard(MagicMock(), manager)
    qtbot.addWidget(card)
    good_text = card._heading_label.text()

    manager.ui_config.side_effect = RuntimeError("config exploded")
    card.refresh()

    assert card._heading_label.text() == good_text


def test_refresh_timer_interval_comes_from_config(qtbot):
    card = MinieGreetingCard(MagicMock(), _core_manager(interval_ms=1234))
    qtbot.addWidget(card)

    assert card._timer.interval() == 1234


def test_subscribes_to_the_adapters_session_state_updated_signal(qtbot):
    adapter = MagicMock()
    card = MinieGreetingCard(adapter, _core_manager())
    qtbot.addWidget(card)

    adapter.session_state_updated.connect.assert_called_once()


def test_session_state_updates_route_to_the_matching_subtext(qtbot):
    card = MinieGreetingCard(MagicMock(), _core_manager())
    qtbot.addWidget(card)

    card._on_session_state_updated(SessionState.LISTENING)
    assert card._subtext_label.text() == "Listening..."

    card._on_session_state_updated(SessionState.PROCESSING)
    assert card._subtext_label.text() == "Thinking... ♡"

    card._on_session_state_updated(SessionState.AWAITING_NEXT_TURN)
    assert card._subtext_label.text() == "Thinking... ♡"

    card._on_session_state_updated(SessionState.SPEAKING)
    assert card._subtext_label.text() == "Sharing my thoughts... ♡"

    card._on_session_state_updated(SessionState.IDLE)
    assert card._subtext_label.text() == "I'm Minie — your cute AI friend, always with you!"


def test_subtext_change_starts_the_fade_animation(qtbot):
    card = MinieGreetingCard(MagicMock(), _core_manager())
    qtbot.addWidget(card)
    card._fade_animation.start = MagicMock()

    card._on_session_state_updated(SessionState.LISTENING)

    card._fade_animation.start.assert_called_once()
    assert card._fade_animation.startValue() == 0.0
    assert card._fade_animation.endValue() == 1.0


def test_repeating_the_same_session_state_does_not_restart_the_animation(qtbot):
    card = MinieGreetingCard(MagicMock(), _core_manager())
    qtbot.addWidget(card)
    card._fade_animation.start = MagicMock()

    # IDLE is already the default text at construction — no real change.
    card._on_session_state_updated(SessionState.IDLE)

    card._fade_animation.start.assert_not_called()


def test_is_built_on_a_glass_panel_with_the_default_dim_border(qtbot):
    card = MinieGreetingCard(MagicMock(), _core_manager())
    qtbot.addWidget(card)

    assert minie_theme.BORDER_DIM in card.styleSheet()


def test_a_real_adapter_refresh_updates_the_subtext_end_to_end(qtbot):
    core_manager = _core_manager()
    adapter = _real_adapter(core_manager, session_state=SessionState.SPEAKING)
    card = MinieGreetingCard(adapter, core_manager)
    qtbot.addWidget(card)

    adapter.refresh()

    assert card._subtext_label.text() == "Sharing my thoughts... ♡"
