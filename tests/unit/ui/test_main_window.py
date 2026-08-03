"""Unit tests for ui.main_window."""

from ui import main_window as main_window_module
from ui.main_window import MainWindow


def test_main_window_constructs_without_error(qtbot, mock_core_manager, mock_presentation_handles):
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    assert window.windowTitle() == "JARMINEI"


def test_close_calls_core_manager_shutdown_exactly_once(
    qtbot, mock_core_manager, mock_presentation_handles
):
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    window.close()

    mock_core_manager.shutdown.assert_called_once()


def test_status_panel_is_embedded_and_functioning(
    qtbot, mock_core_manager, mock_presentation_handles
):
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    assert window._status_panel is not None
    mock_core_manager.check_resources.assert_called()
    mock_core_manager.module_states.assert_called()


def test_settings_menu_action_exists(qtbot, mock_core_manager, mock_presentation_handles):
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    settings_menu = window.menuBar().actions()[0].menu()
    action_texts = [action.text() for action in settings_menu.actions()]
    assert "Open Settings..." in action_texts


def test_open_settings_constructs_dialog_from_core_manager_config(
    qtbot, mock_core_manager, mock_presentation_handles, monkeypatch
):
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)
    # Avoid actually blocking the test on a modal dialog.exec() call.
    monkeypatch.setattr(main_window_module.SettingsWindow, "exec", lambda self: None)

    window._open_settings()

    mock_core_manager.config.assert_called_once()
    mock_core_manager.config_loader.assert_called_once()


def test_debug_menu_action_exists(qtbot, mock_core_manager, mock_presentation_handles):
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    debug_menu = window.menuBar().actions()[1].menu()
    action_texts = [action.text() for action in debug_menu.actions()]
    assert "Open Debug Console" in action_texts


def test_open_debug_console_shows_a_real_console_and_logs_appear_live(
    qtbot, mock_core_manager, mock_presentation_handles
):
    import logging

    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    window._open_debug_console()

    assert window._debug_console is not None
    test_logger = logging.getLogger("test.main_window.debug_console")
    test_logger.setLevel(logging.INFO)  # independent of whatever root's level is right now
    test_logger.info("visible from main window")
    assert "visible from main window" in window._debug_console._text_view.toPlainText()

    window._debug_console.close()


def test_closing_main_window_also_closes_an_open_debug_console(
    qtbot, mock_core_manager, mock_presentation_handles
):
    """Regression test: a Debug Console left open is a separate top-level
    window, not a child dialog — without main_window.py explicitly closing
    it too, Qt's event loop keeps running (process alive, no visible
    window) after the user closes the main window. Caught by actually
    running the app with Debug Console open, not by any mocked test."""
    import logging

    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)
    window._open_debug_console()
    handler = window._debug_console._handler
    assert handler in logging.getLogger().handlers

    window.close()

    assert handler not in logging.getLogger().handlers
