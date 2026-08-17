"""Unit tests for ui.minie.ui_state_adapter."""

from unittest.mock import MagicMock

from config.schema import UIConfig
from emotion.state_manager import EmotionalState
from presentation.minie_emotion_adapter import MinieDisplayEmotions
from presentation.presentation_state import PresentationState
from ui.minie.ui_state_adapter import MinieUiStateAdapter
from voice.session_manager import SessionState


def _core_manager(interval_ms: int = 3000) -> MagicMock:
    manager = MagicMock()
    manager.ui_config.return_value = UIConfig(status_refresh_interval_ms=interval_ms)
    return manager


def _collaborators(
    *,
    last_state=None,
    emotional_state=None,
    session_state=SessionState.IDLE,
    avatar_connected=False,
):
    presentation_controller = MagicMock()
    presentation_controller.last_state_for.return_value = last_state
    emotional_state_manager = MagicMock()
    emotional_state_manager.current_state.return_value = emotional_state or EmotionalState()
    voice_session_manager = MagicMock()
    voice_session_manager.current_session_state.return_value = session_state
    avatar_renderer = MagicMock()
    avatar_renderer.is_connected.return_value = avatar_connected
    return presentation_controller, emotional_state_manager, voice_session_manager, avatar_renderer


def test_timer_interval_comes_from_config(qtbot):
    presentation_controller, emotional_state_manager, voice_session_manager, avatar_renderer = (
        _collaborators()
    )
    adapter = MinieUiStateAdapter(
        presentation_controller,
        emotional_state_manager,
        voice_session_manager,
        avatar_renderer,
        _core_manager(interval_ms=1234),
    )

    assert adapter._timer.interval() == 1234


def test_emits_presentation_state_on_refresh(qtbot):
    state = MagicMock(spec=PresentationState)
    presentation_controller, emotional_state_manager, voice_session_manager, avatar_renderer = (
        _collaborators(last_state=state)
    )
    adapter = MinieUiStateAdapter(
        presentation_controller, emotional_state_manager, voice_session_manager,
        avatar_renderer, _core_manager(),
    )

    received = []
    adapter.presentation_state_updated.connect(received.append)
    adapter.refresh()

    assert received == [state]


def test_emits_derived_emotion_on_refresh(qtbot):
    emotional_state = EmotionalState(mood=50.0, stress=20.0, comfort=80.0, social_energy=90.0)
    presentation_controller, emotional_state_manager, voice_session_manager, avatar_renderer = (
        _collaborators(emotional_state=emotional_state)
    )
    adapter = MinieUiStateAdapter(
        presentation_controller, emotional_state_manager, voice_session_manager,
        avatar_renderer, _core_manager(),
    )

    received = []
    adapter.emotion_updated.connect(received.append)
    adapter.refresh()

    assert len(received) == 1
    assert isinstance(received[0], MinieDisplayEmotions)
    assert received[0].trust == 80.0


def test_emits_session_state_on_refresh(qtbot):
    presentation_controller, emotional_state_manager, voice_session_manager, avatar_renderer = (
        _collaborators(session_state=SessionState.SPEAKING)
    )
    adapter = MinieUiStateAdapter(
        presentation_controller, emotional_state_manager, voice_session_manager,
        avatar_renderer, _core_manager(),
    )

    received = []
    adapter.session_state_updated.connect(received.append)
    adapter.refresh()

    assert received == [SessionState.SPEAKING]


def test_emits_avatar_status_on_refresh(qtbot):
    presentation_controller, emotional_state_manager, voice_session_manager, avatar_renderer = (
        _collaborators(avatar_connected=True)
    )
    adapter = MinieUiStateAdapter(
        presentation_controller, emotional_state_manager, voice_session_manager,
        avatar_renderer, _core_manager(),
    )

    received = []
    adapter.avatar_status_updated.connect(received.append)
    adapter.refresh()

    assert received == [True]


def test_a_failing_source_does_not_suppress_the_others(qtbot):
    presentation_controller, emotional_state_manager, voice_session_manager, avatar_renderer = (
        _collaborators()
    )
    presentation_controller.last_state_for.side_effect = RuntimeError("boom")
    adapter = MinieUiStateAdapter(
        presentation_controller, emotional_state_manager, voice_session_manager,
        avatar_renderer, _core_manager(),
    )

    presentation_events = []
    emotion_events = []
    session_events = []
    avatar_events = []
    adapter.presentation_state_updated.connect(presentation_events.append)
    adapter.emotion_updated.connect(emotion_events.append)
    adapter.session_state_updated.connect(session_events.append)
    adapter.avatar_status_updated.connect(avatar_events.append)
    adapter.refresh()

    assert presentation_events == []
    assert len(emotion_events) == 1
    assert len(session_events) == 1
    assert len(avatar_events) == 1


def test_refresh_survives_every_source_failing(qtbot):
    presentation_controller, emotional_state_manager, voice_session_manager, avatar_renderer = (
        _collaborators()
    )
    presentation_controller.last_state_for.side_effect = RuntimeError("boom")
    emotional_state_manager.current_state.side_effect = RuntimeError("boom")
    voice_session_manager.current_session_state.side_effect = RuntimeError("boom")
    avatar_renderer.is_connected.side_effect = RuntimeError("boom")

    # construction itself calls refresh() once
    adapter = MinieUiStateAdapter(
        presentation_controller, emotional_state_manager, voice_session_manager,
        avatar_renderer, _core_manager(),
    )

    adapter.refresh()  # must not raise on a later call either
