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


def test_hud_shell_is_embedded_and_functioning(qtbot, mock_core_manager, mock_presentation_handles):
    """JARVIS Holographic HUD reskin, Phase 5: StatusPanel is no longer
    embedded in MainWindow — its role (module states + resource usage)
    is fully superseded by HudShell's own right-rail panels, which read
    through MetricsAdapter (core_manager.check_resources()/
    runtime_manager()), not module_states()."""
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    assert window._hud_shell is not None
    mock_core_manager.check_resources.assert_called()
    mock_core_manager.runtime_manager.assert_called()


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


def test_runtime_diagnostics_menu_action_exists(
    qtbot, mock_core_manager, mock_presentation_handles
):
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    debug_menu = window.menuBar().actions()[1].menu()
    action_texts = [action.text() for action in debug_menu.actions()]
    assert "Open Runtime Diagnostics" in action_texts


def test_open_runtime_diagnostics_shows_a_real_panel(
    qtbot, mock_core_manager, mock_presentation_handles
):
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    window._open_runtime_diagnostics()

    assert window._runtime_diagnostics_panel is not None
    mock_core_manager.runtime_manager.assert_called()
    window._runtime_diagnostics_panel.close()


def test_closing_main_window_also_closes_an_open_runtime_diagnostics_panel(
    qtbot, mock_core_manager, mock_presentation_handles
):
    """Regression test: same shape as the Debug Console one above — a
    Runtime Diagnostics Panel left open is also a separate top-level
    window that would otherwise keep Qt's event loop alive after the
    main window closes."""
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)
    window._open_runtime_diagnostics()
    panel = window._runtime_diagnostics_panel
    assert panel.isVisible()

    window.close()

    assert not panel.isVisible()


# --- Minie Persona UI workstream -----------------------------------------------------------


def test_minie_shell_is_embedded_alongside_hud_shell(
    qtbot, mock_core_manager, mock_presentation_handles
):
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    assert window._minie_shell is not None
    assert window._persona_stack.indexOf(window._hud_shell) != -1
    assert window._persona_stack.indexOf(window._minie_shell) != -1


def test_persona_stack_defaults_to_jarvis_when_jarvis_is_mounted(
    qtbot, mock_core_manager, mock_presentation_handles
):
    mock_presentation_handles["presentation_controller"].mounted_persona_name = "jarvis"
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    assert window._persona_stack.currentWidget() is window._hud_shell


def test_persona_stack_switches_to_minie_when_minie_becomes_mounted(
    qtbot, mock_core_manager, mock_presentation_handles
):
    mock_presentation_handles["presentation_controller"].mounted_persona_name = "jarvis"
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)
    assert window._persona_stack.currentWidget() is window._hud_shell

    mock_presentation_handles["presentation_controller"].mounted_persona_name = "minie"
    window._sync_persona_stack()

    assert window._persona_stack.currentWidget() is window._minie_shell


class _RaisingPersonaController:
    """A tiny stub (not a MagicMock) whose mounted_persona_name always
    raises — mutating a shared MagicMock's own class-level property
    would leak into every other MagicMock instance process-wide, so a
    plain local class is used instead."""

    @property
    def mounted_persona_name(self):
        raise RuntimeError("boom")


def test_persona_stack_sync_survives_a_raising_presentation_controller(
    qtbot, mock_core_manager, mock_presentation_handles
):
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)
    current_before = window._persona_stack.currentWidget()

    window._presentation_controller = _RaisingPersonaController()
    window._sync_persona_stack()  # must not raise

    assert window._persona_stack.currentWidget() is current_before


def test_minie_shell_minimize_requested_minimizes_the_window(
    qtbot, mock_core_manager, mock_presentation_handles, monkeypatch
):
    # Patched on the CLASS, before construction: `.connect(self.showMinimized)`
    # inside __init__ captures a bound method at connect time, so patching
    # the instance attribute AFTER construction (as other tests in this
    # file do for e.g. SettingsWindow.exec) would not affect an already-
    # established Qt connection — mirrors test_app.py's own
    # monkeypatch.setattr(MainWindow, "show", ...) precedent for the same
    # reason.
    called = []
    monkeypatch.setattr(MainWindow, "showMinimized", lambda self: called.append(True))
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    window._minie_shell.minimize_requested.emit()

    assert called == [True]


def test_minie_shell_close_requested_closes_the_window(
    qtbot, mock_core_manager, mock_presentation_handles
):
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    window._minie_shell.close_requested.emit()

    mock_core_manager.shutdown.assert_called_once()


def test_minie_shell_settings_requested_opens_settings(
    qtbot, mock_core_manager, mock_presentation_handles, monkeypatch
):
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)
    monkeypatch.setattr(main_window_module.SettingsWindow, "exec", lambda self: None)

    window._minie_shell.settings_requested.emit()

    mock_core_manager.config.assert_called_once()


def test_toggle_maximize_restore_maximizes_when_not_maximized(
    qtbot, mock_core_manager, mock_presentation_handles, monkeypatch
):
    called = []
    monkeypatch.setattr(MainWindow, "isMaximized", lambda self: False)
    monkeypatch.setattr(MainWindow, "showMaximized", lambda self: called.append(True))
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    window._minie_shell.maximize_requested.emit()

    assert called == [True]


def test_toggle_maximize_restore_restores_when_already_maximized(
    qtbot, mock_core_manager, mock_presentation_handles, monkeypatch
):
    called = []
    monkeypatch.setattr(MainWindow, "isMaximized", lambda self: True)
    monkeypatch.setattr(MainWindow, "showNormal", lambda self: called.append(True))
    window = MainWindow(mock_core_manager, **mock_presentation_handles)
    qtbot.addWidget(window)

    window._minie_shell.maximize_requested.emit()

    assert called == [True]
