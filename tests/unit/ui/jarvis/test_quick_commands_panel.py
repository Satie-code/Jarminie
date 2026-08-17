"""Unit tests for ui.jarvis.quick_commands_panel."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from PySide6.QtWidgets import QPushButton

from device_control.action_engine import ActionResult, ActionStatus, ActionType
from ui.jarvis.quick_commands_panel import QuickCommandsPanel


def _result(status: ActionStatus, error_message: str | None = None) -> ActionResult:
    return ActionResult(
        request=MagicMock(),
        status=status,
        completed_at=datetime.now(UTC),
        error_message=error_message,
    )


def _buttons(panel: QuickCommandsPanel) -> dict[str, QPushButton]:
    return {b.text(): b for b in panel.findChildren(QPushButton)}


def test_open_vscode_dispatches_a_launch_application_request(qtbot):
    registry = MagicMock()
    registry.dispatch.return_value = _result(ActionStatus.SUCCEEDED)
    panel = QuickCommandsPanel(registry)
    qtbot.addWidget(panel)

    panel.open_vscode()

    registry.dispatch.assert_called_once()
    request = registry.dispatch.call_args[0][0]
    assert request.action_type == ActionType.LAUNCH_APPLICATION
    assert request.parameters["executable_path"] == "code"
    assert request.context.requested_by == "ui"


def test_open_vscode_success_updates_the_status_label(qtbot):
    registry = MagicMock()
    registry.dispatch.return_value = _result(ActionStatus.SUCCEEDED)
    panel = QuickCommandsPanel(registry)
    qtbot.addWidget(panel)

    panel.open_vscode()

    assert panel._status_label.text() == "Opened VS Code."


def test_open_vscode_denial_shows_the_error_message(qtbot):
    registry = MagicMock()
    registry.dispatch.return_value = _result(ActionStatus.DENIED, "Denied by permission policy.")
    panel = QuickCommandsPanel(registry)
    qtbot.addWidget(panel)

    panel.open_vscode()

    assert panel._status_label.text() == "Denied by permission policy."


def test_dispatch_survives_a_raising_action_registry(qtbot):
    registry = MagicMock()
    registry.dispatch.side_effect = RuntimeError("boom")
    panel = QuickCommandsPanel(registry)
    qtbot.addWidget(panel)

    panel.open_vscode()  # must not raise

    assert "wrong" in panel._status_label.text().lower()


def test_screenshot_button_is_disabled_with_a_tooltip(qtbot):
    panel = QuickCommandsPanel(MagicMock())
    qtbot.addWidget(panel)

    buttons = _buttons(panel)
    assert not buttons["Take Screenshot"].isEnabled()
    assert buttons["Take Screenshot"].toolTip() != ""


def test_focus_mode_button_is_disabled_with_a_tooltip(qtbot):
    panel = QuickCommandsPanel(MagicMock())
    qtbot.addWidget(panel)

    buttons = _buttons(panel)
    assert not buttons["Start Focus Mode"].isEnabled()
    assert buttons["Start Focus Mode"].toolTip() != ""


def test_open_vscode_and_show_stats_buttons_are_enabled(qtbot):
    panel = QuickCommandsPanel(MagicMock())
    qtbot.addWidget(panel)

    buttons = _buttons(panel)
    assert buttons["Open VS Code"].isEnabled()
    assert buttons["Show System Stats"].isEnabled()


def test_show_system_stats_button_emits_signal(qtbot):
    panel = QuickCommandsPanel(MagicMock())
    qtbot.addWidget(panel)
    received = []
    panel.system_stats_requested.connect(lambda: received.append(True))

    _buttons(panel)["Show System Stats"].click()

    assert received == [True]
