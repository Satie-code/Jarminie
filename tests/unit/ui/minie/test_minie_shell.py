"""Unit tests for ui.minie.minie_shell."""

from unittest.mock import MagicMock

from config.schema import PresentationConfig, UIConfig
from emotion.state_manager import EmotionalState
from scheduler.scheduler_model import ItemType, ScheduledItem
from services.weather_service import NullWeatherService
from ui.minie.minie_shell import MinieShell
from voice.session_manager import SessionState


def _core_manager():
    manager = MagicMock()
    manager.presentation_config.return_value = PresentationConfig()
    manager.ui_config.return_value = UIConfig(user_display_name="Sattie")
    manager.check_resources.return_value = MagicMock(battery_percent=80.0)
    return manager


def _collaborators():
    core_manager = _core_manager()
    avatar_renderer = MagicMock()
    avatar_renderer.is_connected.return_value = False
    presentation_controller = MagicMock()
    presentation_controller.last_state_for.return_value = None
    emotional_state_manager = MagicMock()
    emotional_state_manager.current_state.return_value = EmotionalState()
    voice_session_manager = MagicMock()
    voice_session_manager.current_session_state.return_value = SessionState.IDLE
    calendar_store = MagicMock()
    calendar_store.list_due_within.return_value = []
    pipeline = MagicMock()
    weather_service = NullWeatherService()
    return dict(
        core_manager=core_manager,
        avatar_renderer=avatar_renderer,
        presentation_controller=presentation_controller,
        emotional_state_manager=emotional_state_manager,
        voice_session_manager=voice_session_manager,
        calendar_store=calendar_store,
        pipeline=pipeline,
        weather_service=weather_service,
    )


def test_constructs_without_raising(qtbot):
    shell = MinieShell(**_collaborators())
    qtbot.addWidget(shell)

    assert shell._current_page_id == "home"


def test_defaults_to_home_page_with_real_content(qtbot):
    shell = MinieShell(**_collaborators())
    qtbot.addWidget(shell)

    assert shell._content_layout.itemAt(0).widget() is shell._home_page


def test_switching_to_a_non_home_page_shows_a_placeholder(qtbot):
    shell = MinieShell(**_collaborators())
    qtbot.addWidget(shell)

    shell._on_page_selected("chat")

    current_widget = shell._content_layout.itemAt(0).widget()
    assert current_widget is not shell._home_page
    assert "chat" in shell._placeholder_pages


def test_switching_back_to_home_restores_the_real_dashboard(qtbot):
    shell = MinieShell(**_collaborators())
    qtbot.addWidget(shell)

    shell._on_page_selected("tasks")
    shell._on_page_selected("home")

    assert shell._content_layout.itemAt(0).widget() is shell._home_page


def test_view_calendar_from_plan_panel_switches_to_calendar_page(qtbot):
    shell = MinieShell(**_collaborators())
    qtbot.addWidget(shell)

    shell._plan_panel.view_calendar_requested.emit()

    assert shell._current_page_id == "calendar"


def test_message_bar_home_shortcut_returns_to_home(qtbot):
    shell = MinieShell(**_collaborators())
    qtbot.addWidget(shell)
    shell._on_page_selected("wellness")

    shell._message_bar.home_requested.emit()

    assert shell._current_page_id == "home"


def test_message_bar_reply_reaches_the_speech_bubble(qtbot):
    shell = MinieShell(**_collaborators())
    qtbot.addWidget(shell)

    shell._message_bar.reply_received.emit("Hello there! ♡")

    assert shell._speech_bubble._body_label.text() == "Hello there! ♡"


def test_top_bar_window_control_signals_bubble_up(qtbot):
    shell = MinieShell(**_collaborators())
    qtbot.addWidget(shell)

    received = []
    shell.minimize_requested.connect(lambda: received.append("minimize"))
    shell.maximize_requested.connect(lambda: received.append("maximize"))
    shell.close_requested.connect(lambda: received.append("close"))

    shell._top_bar.minimize_requested.emit()
    shell._top_bar.maximize_requested.emit()
    shell._top_bar.close_requested.emit()

    assert received == ["minimize", "maximize", "close"]


def test_sidebar_settings_signal_bubbles_up(qtbot):
    shell = MinieShell(**_collaborators())
    qtbot.addWidget(shell)

    received = []
    shell.settings_requested.connect(lambda: received.append(True))
    shell._sidebar.settings_requested.emit()

    assert received == [True]


def test_plan_panel_shows_a_real_today_item(qtbot):
    from datetime import UTC, datetime

    collaborators = _collaborators()
    collaborators["calendar_store"].list_due_within.return_value = [
        ScheduledItem(
            item_id="1",
            item_type=ItemType.EVENT,
            title="Finish ROS 2 project",
            scheduled_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
    ]
    shell = MinieShell(**collaborators)
    qtbot.addWidget(shell)

    assert shell._plan_panel._rows_layout.count() >= 1


def test_construction_never_touches_heavy_ai_subsystems(qtbot):
    """No collaborator here is a real Whisper/Coqui/Chroma/Ollama-backed
    object -- every one is a MagicMock or a pure in-memory value (see
    _collaborators() above) -- so simply constructing MinieShell without
    any of those mocks recording an unexpected call is itself evidence
    the shell never reaches for a heavy subsystem on its own."""
    collaborators = _collaborators()
    shell = MinieShell(**collaborators)
    qtbot.addWidget(shell)

    collaborators["avatar_renderer"].mount.assert_not_called()
    collaborators["pipeline"].submit_text.assert_not_called()
