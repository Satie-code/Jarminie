"""Unit tests for ui.jarvis.confirmation_dialog."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel

from ui.jarvis.confirmation_dialog import ConfirmationDialog


def test_shows_the_prompt_text(qtbot):
    dialog = ConfirmationDialog("This will delete a file. Should I proceed?", timeout_seconds=0)
    qtbot.addWidget(dialog)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert "This will delete a file. Should I proceed?" in texts


def test_buttons_are_labeled_allow_and_deny(qtbot):
    dialog = ConfirmationDialog("Proceed?", timeout_seconds=0)
    qtbot.addWidget(dialog)

    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons.button(QDialogButtonBox.StandardButton.Yes).text() == "Allow"
    assert buttons.button(QDialogButtonBox.StandardButton.No).text() == "Deny"


def test_accepting_returns_accepted_and_is_not_a_timeout(qtbot):
    dialog = ConfirmationDialog("Proceed?", timeout_seconds=0)
    qtbot.addWidget(dialog)
    QTimer.singleShot(20, dialog.accept)

    result = dialog.exec()

    assert result == QDialog.DialogCode.Accepted
    assert not dialog.timed_out


def test_rejecting_returns_rejected_and_is_not_a_timeout(qtbot):
    dialog = ConfirmationDialog("Proceed?", timeout_seconds=0)
    qtbot.addWidget(dialog)
    QTimer.singleShot(20, dialog.reject)

    result = dialog.exec()

    assert result == QDialog.DialogCode.Rejected
    assert not dialog.timed_out


def test_zero_timeout_means_no_auto_close(qtbot):
    dialog = ConfirmationDialog("Proceed?", timeout_seconds=0)
    qtbot.addWidget(dialog)

    assert not hasattr(dialog, "_timeout_timer")


def test_timeout_rejects_and_sets_timed_out_flag(qtbot):
    dialog = ConfirmationDialog("Proceed?", timeout_seconds=0.05)
    qtbot.addWidget(dialog)

    result = dialog.exec()  # nothing clicks Allow/Deny — the timer fires instead

    assert result == QDialog.DialogCode.Rejected
    assert dialog.timed_out
