"""ConfirmationDialog — JARVIS Holographic HUD reskin, Phase 4.

The Qt-native half of security/qt_confirmation_service.py's own
QtConfirmationService: a small modal dialog showing exactly what an
action will do (ConfirmationRequest.prompt_text — the same
Explainability-Rule text VoiceConfirmationService would otherwise speak)
with Allow/Deny buttons, plus a real timeout matching
SecurityConfig.confirmation_timeout_seconds — the same "a confirmation
timeout defaults to DENY, never ALLOW" hard rule
security/confirmation_service.py's own docstring establishes for every
ConfirmationService implementation, not just the voice one.
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from presentation import theme


class ConfirmationDialog(QDialog):
    """timed_out is checked by QtConfirmationService after exec()
    returns — a timeout calls reject() itself (same DialogCode as
    clicking Deny), so the caller must consult this flag to tell an
    honest timeout apart from an explicit decline."""

    def __init__(
        self, prompt_text: str, timeout_seconds: float, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm Action")
        self.setModal(True)
        self.timed_out = False

        layout = QVBoxLayout(self)
        label = QLabel(prompt_text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 11pt;")
        layout.addWidget(label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
        )
        buttons.button(QDialogButtonBox.StandardButton.Yes).setText("Allow")
        buttons.button(QDialogButtonBox.StandardButton.No).setText("Deny")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if timeout_seconds > 0:
            self._timeout_timer = QTimer(self)
            self._timeout_timer.setSingleShot(True)
            self._timeout_timer.timeout.connect(self._on_timeout)
            self._timeout_timer.start(int(timeout_seconds * 1000))

    def _on_timeout(self) -> None:
        self.timed_out = True
        self.reject()
