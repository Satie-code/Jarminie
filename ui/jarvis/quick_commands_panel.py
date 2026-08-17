"""QuickCommandsPanel — JARVIS Holographic HUD reskin, Phase 4.

The brief's own "Quick Commands" panel: buttons that call the EXISTING
command system (`device_control.action_engine.ActionRegistry.dispatch()`
— the real chokepoint every action, voice-triggered or otherwise, must
go through) rather than duplicating command execution here. Every
ActionRequest this panel builds carries `context.requested_by="ui"`, the
routing key `security/qt_confirmation_service.py`'s
`RequestedByConfirmationService` uses to give a MEDIUM/HIGH-risk
UI-originated action a real Qt confirmation dialog instead of the
voice-only confirmation path — see that module's own docstring for the
full mechanism.

Only two of the reference image's four example buttons have a real,
already-existing backend capability today, confirmed by this workstream's
own research (no "take a screenshot" `ActionType` exists; wiring "Start
Focus Mode" would mean threading `voice.quiet_mode.QuietModeController`
into `MainWindow` as a THIRD new collaborator beyond this phase's own
disclosed `CalendarStore`/`ActionRegistry` scope). Rather than silently
no-op or fabricate a capability, both stay in the panel — matching the
reference image — but disabled with an honest tooltip, the same
"present, honestly disclosed as not-yet-wired" precedent Phase 2's own
Code nav button already established.
"""

from datetime import UTC, datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from device_control.action_engine import (
    ActionContext,
    ActionRegistry,
    ActionRequest,
    ActionStatus,
    ActionType,
)
from presentation import theme

logger = get_logger(__name__)

_VSCODE_EXECUTABLE = "code"
"""VS Code's own CLI launcher name, resolved via PATH the same way a
user typing `code` in a terminal would rely on — real, disclosed,
unvalidated first-pass default (same category as this codebase's other
tuned defaults): only works if VS Code was installed with "Add to PATH"
enabled, which is VS Code's own default installer option on Windows."""


class QuickCommandsPanel(QWidget):
    """Constructor DI: only ActionRegistry — the panel never touches
    PermissionGate/ConfirmationService/etc. directly, exactly like every
    other real caller of dispatch() in this codebase (voice-triggered
    actions included)."""

    system_stats_requested = Signal()

    def __init__(self, action_registry: ActionRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._action_registry = action_registry

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QLabel("QUICK COMMANDS")
        header.setStyleSheet(f"color: {theme.ACCENT_CYAN}; font-weight: 600;")
        layout.addWidget(header)

        open_vscode = QPushButton("Open VS Code")
        open_vscode.clicked.connect(self.open_vscode)
        layout.addWidget(open_vscode)

        show_stats = QPushButton("Show System Stats")
        show_stats.clicked.connect(self.system_stats_requested.emit)
        layout.addWidget(show_stats)

        screenshot = QPushButton("Take Screenshot")
        screenshot.setEnabled(False)
        screenshot.setToolTip("No screenshot action exists in the backend yet.")
        layout.addWidget(screenshot)

        focus_mode = QPushButton("Start Focus Mode")
        focus_mode.setEnabled(False)
        focus_mode.setToolTip("Quiet Mode isn't wired into the desktop UI yet.")
        layout.addWidget(focus_mode)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)
        layout.addStretch(1)

    def open_vscode(self) -> None:
        """Public: the nav rail's own "Code" item (Phase 2, wired for
        real starting this phase) reuses this exact same action rather
        than duplicating a second ActionRequest-building call site."""
        request = ActionRequest(
            action_type=ActionType.LAUNCH_APPLICATION,
            parameters={"executable_path": _VSCODE_EXECUTABLE},
            context=ActionContext(requested_by="ui"),
            requested_at=datetime.now(UTC),
        )
        self._dispatch(request, success_text="Opened VS Code.")

    def _dispatch(self, request: ActionRequest, success_text: str) -> None:
        """dispatch() itself never raises (ActionRegistry's own Fail
        Gracefully contract) — this try/except is defense in depth
        against a genuinely unexpected failure in this panel's own
        surrounding code, not a substitute for that contract."""
        try:
            result = self._action_registry.dispatch(request)
        except Exception:
            logger.exception("Quick Command dispatch failed unexpectedly: %s", request.action_type)
            self._status_label.setText("Something went wrong running that command.")
            return

        if result.status is ActionStatus.SUCCEEDED:
            self._status_label.setText(success_text)
        else:
            logger.info(
                "Quick Command %s did not succeed: %s (%s)",
                request.action_type.value,
                result.status.value,
                result.error_message,
            )
            self._status_label.setText(result.error_message or f"Not done: {result.status.value}.")
