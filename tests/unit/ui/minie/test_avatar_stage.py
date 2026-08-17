"""Unit tests for ui.minie.avatar_stage."""

from unittest.mock import MagicMock

from config.schema import PresentationConfig, UIConfig
from emotion.state_manager import EmotionalState
from ui.minie.avatar_stage import MinieAvatarStage
from ui.minie.ui_state_adapter import MinieUiStateAdapter
from voice.session_manager import SessionState


def _core_manager():
    manager = MagicMock()
    manager.presentation_config.return_value = PresentationConfig()
    manager.ui_config.return_value = UIConfig()
    return manager


def _adapter(core_manager, *, avatar_connected=False, session_state=SessionState.IDLE):
    presentation_controller = MagicMock()
    presentation_controller.last_state_for.return_value = None
    emotional_state_manager = MagicMock()
    emotional_state_manager.current_state.return_value = EmotionalState()
    voice_session_manager = MagicMock()
    voice_session_manager.current_session_state.return_value = session_state
    avatar_renderer = MagicMock()
    avatar_renderer.is_connected.return_value = avatar_connected
    adapter = MinieUiStateAdapter(
        presentation_controller,
        emotional_state_manager,
        voice_session_manager,
        avatar_renderer,
        core_manager,
    )
    return adapter, avatar_renderer


def test_shows_unavailable_state_when_avatar_disconnected(qtbot):
    core_manager = _core_manager()
    adapter, avatar_renderer = _adapter(core_manager, avatar_connected=False)

    stage = MinieAvatarStage(avatar_renderer, adapter, core_manager)
    qtbot.addWidget(stage)
    stage.show()  # isVisible() below reflects effective ancestor visibility too
    # MinieUiStateAdapter.__init__() already ran refresh() once, before
    # `stage` existed to subscribe -- the identical gap
    # ui/jarvis/hud_shell.py's own docstring documents for MetricsAdapter,
    # closed there (and here, by real production code in minie_shell.py)
    # with one more refresh() call after every subscriber is wired up.
    adapter.refresh()

    assert stage._connected is False
    assert stage._status_label.isVisible()
    assert stage._retry_button.isVisible()


def test_shows_connected_state_when_avatar_connected(qtbot):
    core_manager = _core_manager()
    adapter, avatar_renderer = _adapter(core_manager, avatar_connected=True)

    stage = MinieAvatarStage(avatar_renderer, adapter, core_manager)
    qtbot.addWidget(stage)
    adapter.refresh()  # see the sibling test above for why this is needed

    assert stage._connected is True
    assert not stage._status_label.isVisible()
    assert not stage._retry_button.isVisible()


def test_retry_button_calls_avatar_mount_on_a_background_thread(qtbot):
    core_manager = _core_manager()
    adapter, avatar_renderer = _adapter(core_manager, avatar_connected=False)
    stage = MinieAvatarStage(avatar_renderer, adapter, core_manager)
    qtbot.addWidget(stage)

    stage._retry_button.click()

    qtbot.waitUntil(lambda: avatar_renderer.mount.called, timeout=2000)


def test_speaking_session_state_increases_glow_intensity(qtbot):
    core_manager = _core_manager()
    adapter, avatar_renderer = _adapter(core_manager, session_state=SessionState.SPEAKING)
    stage = MinieAvatarStage(avatar_renderer, adapter, core_manager)
    qtbot.addWidget(stage)

    adapter.refresh()

    assert stage._glow_intensity > 1.0


def test_idle_session_state_keeps_neutral_glow_intensity(qtbot):
    core_manager = _core_manager()
    adapter, avatar_renderer = _adapter(core_manager, session_state=SessionState.IDLE)
    stage = MinieAvatarStage(avatar_renderer, adapter, core_manager)
    qtbot.addWidget(stage)

    adapter.refresh()

    assert stage._glow_intensity == 1.0


def test_tick_survives_a_nan_particle_density(qtbot):
    core_manager = _core_manager()
    adapter, avatar_renderer = _adapter(core_manager)
    stage = MinieAvatarStage(avatar_renderer, adapter, core_manager)
    qtbot.addWidget(stage)

    stage._particle_density = float("nan")
    stage._on_tick()  # must not raise


def test_paints_without_raising(qtbot):
    core_manager = _core_manager()
    adapter, avatar_renderer = _adapter(core_manager)
    stage = MinieAvatarStage(avatar_renderer, adapter, core_manager)
    qtbot.addWidget(stage)
    stage.resize(300, 340)

    pixmap = stage.grab()

    assert not pixmap.isNull()
