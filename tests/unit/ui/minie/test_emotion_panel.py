"""Unit tests for ui.minie.emotion_panel."""

from unittest.mock import MagicMock

from config.schema import PresentationConfig, UIConfig
from emotion.state_manager import EmotionalState
from presentation.minie_emotion_adapter import MinieDisplayEmotions
from ui.minie.emotion_panel import MinieEmotionPanel
from ui.minie.ui_state_adapter import MinieUiStateAdapter


def _core_manager(accent: str = "#B76E79") -> MagicMock:
    manager = MagicMock()
    manager.presentation_config.return_value = PresentationConfig(minie_ui_accent=accent)
    manager.ui_config.return_value = UIConfig()
    return manager


def _real_adapter(
    core_manager, *, emotional_state: EmotionalState | None = None
) -> MinieUiStateAdapter:
    """A real MinieUiStateAdapter (not a MagicMock) so its own real Qt
    Signals fire end-to-end — mirrors test_avatar_stage.py's own
    _adapter() helper, the established precedent for this workstream."""
    presentation_controller = MagicMock()
    presentation_controller.last_state_for.return_value = None
    emotional_state_manager = MagicMock()
    emotional_state_manager.current_state.return_value = emotional_state or EmotionalState()
    voice_session_manager = MagicMock()
    avatar_renderer = MagicMock()
    return MinieUiStateAdapter(
        presentation_controller,
        emotional_state_manager,
        voice_session_manager,
        avatar_renderer,
        core_manager,
    )


def test_bars_start_at_zero_before_any_emotion_update(qtbot):
    panel = MinieEmotionPanel(MagicMock(), _core_manager())
    qtbot.addWidget(panel)

    assert panel._happiness_bar._value == 0.0
    assert panel._calmness_bar._value == 0.0
    assert panel._trust_bar._value == 0.0
    assert panel._affection_bar._value == 0.0


def test_subscribes_to_the_adapters_emotion_updated_signal(qtbot):
    adapter = MagicMock()
    panel = MinieEmotionPanel(adapter, _core_manager())
    qtbot.addWidget(panel)

    adapter.emotion_updated.connect.assert_called_once()


def test_emotion_update_routes_each_dimension_to_its_matching_bar(qtbot):
    panel = MinieEmotionPanel(MagicMock(), _core_manager())
    qtbot.addWidget(panel)

    display_emotions = MinieDisplayEmotions(
        happiness=80.0, calmness=40.0, trust=60.0, affection=25.0
    )
    panel._on_emotion_updated(display_emotions)

    # EmotionBar.set_value() animates toward the new value via
    # QPropertyAnimation rather than snapping instantly (see
    # ui/minie/widgets/emotion_bar.py), so assert against the animation's
    # own target rather than the bar's current (still mid-animation)
    # displayed value.
    assert panel._happiness_bar._animation.endValue() == 80.0
    assert panel._calmness_bar._animation.endValue() == 40.0
    assert panel._trust_bar._animation.endValue() == 60.0
    assert panel._affection_bar._animation.endValue() == 25.0


def test_a_real_adapter_refresh_updates_the_bars_end_to_end(qtbot):
    core_manager = _core_manager()
    adapter = _real_adapter(core_manager)
    panel = MinieEmotionPanel(adapter, core_manager)
    qtbot.addWidget(panel)

    adapter.refresh()

    # EmotionalState()'s own neutral-midpoint defaults (mood=0.0 ->
    # happiness 50%, stress=50.0 -> calmness 50%, comfort=50.0 -> trust
    # 50%, social_energy=50.0 -> affection 50%) — see
    # presentation/minie_emotion_adapter.py's own derivation.
    assert panel._happiness_bar._animation.endValue() == 50.0
    assert panel._calmness_bar._animation.endValue() == 50.0
    assert panel._trust_bar._animation.endValue() == 50.0
    assert panel._affection_bar._animation.endValue() == 50.0


def test_falls_back_to_default_accent_when_config_read_fails(qtbot):
    manager = MagicMock()
    manager.presentation_config.side_effect = RuntimeError("boom")

    panel = MinieEmotionPanel(MagicMock(), manager)  # must not raise
    qtbot.addWidget(panel)


def test_survives_an_unreadable_emotion_update(qtbot):
    panel = MinieEmotionPanel(MagicMock(), _core_manager())
    qtbot.addWidget(panel)

    panel._on_emotion_updated(object())  # must not raise

    assert panel._happiness_bar._value == 0.0
