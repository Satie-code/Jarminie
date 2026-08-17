"""RemindersPanel — JARVIS Holographic HUD reskin, Phase 4.

The brief's own "Upcoming Reminders" panel: real items from
`CalendarStore.list_due_within()` (`scheduler/calendar_store.py`) — the
"real 'upcoming reminders' query" that module's own docstring names.
`ScheduledItem` (`scheduler/scheduler_model.py`) has no priority field at
all — the only "priority" concept in this codebase
(`decision.priority_queue.PriorityLevel.SCHEDULED_REMINDER`) is a
transient dispatch-time value, never persisted per-item — so this panel
shows time + title + type only, never a fabricated priority badge, per
this workstream's own confirmed research finding and section 10's "never
fake it" instruction generally.

"VIEW ALL" (the brief's own explicit requirement) opens `RemindersDialog`
below: every non-completed item within a wide lookahead window, each
with a "Mark Done" button calling `CalendarStore.mark_completed()`
directly — no `ReminderEngine` dependency (that class is equally
unreachable from `ui/` today, and both of its own read/write needs
here are already plain `CalendarStore` methods).
"""

from datetime import UTC, datetime, timedelta

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation import theme
from scheduler.calendar_store import CalendarStore
from scheduler.scheduler_model import ScheduledItem

logger = get_logger(__name__)

_PANEL_LOOKAHEAD = timedelta(days=7)
_PANEL_MAX_ROWS = 5
_DIALOG_LOOKAHEAD = timedelta(days=365)


def _format_row_text(item: ScheduledItem) -> str:
    time_text = item.scheduled_at.strftime("%I:%M %p").lstrip("0")
    return f"{time_text} — {item.title}"


class RemindersPanel(QWidget):
    """Constructor DI: (calendar_store, core_manager) — core_manager only
    for its own ui_config().status_refresh_interval_ms, the same shared,
    already-tunable interval every other panel in this workstream uses."""

    def __init__(
        self,
        calendar_store: CalendarStore,
        core_manager: CoreManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._calendar_store = calendar_store

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header_row = QHBoxLayout()
        header = QLabel("UPCOMING REMINDERS")
        header.setStyleSheet(f"color: {theme.ACCENT_CYAN}; font-weight: 600;")
        header_row.addWidget(header)
        header_row.addStretch(1)
        view_all = QPushButton("VIEW ALL")
        view_all.setFlat(True)
        view_all.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; text-decoration: underline;")
        view_all.clicked.connect(self._open_view_all)
        header_row.addWidget(view_all)
        layout.addLayout(header_row)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(4)
        layout.addLayout(self._rows_layout)
        layout.addStretch(1)

        interval_ms = core_manager.ui_config().status_refresh_interval_ms
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        """Fail Gracefully: a transient CalendarStore read failure shows
        an honest 'unavailable' row rather than crashing the recurring
        QTimer callback — CalendarStore.list_due_within() itself already
        degrades a SQLite failure to [], so this except only guards
        against a genuinely unexpected failure (e.g. a bad window_end)."""
        self._clear_rows()
        try:
            items = self._calendar_store.list_due_within(datetime.now(UTC) + _PANEL_LOOKAHEAD)
        except Exception:
            logger.exception("Reminders panel refresh failed; showing nothing this cycle.")
            self._add_message_row("Reminders unavailable right now.")
            return

        if not items:
            self._add_message_row("Nothing scheduled.")
            return
        for item in items[:_PANEL_MAX_ROWS]:
            label = QLabel(_format_row_text(item))
            label.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
            self._rows_layout.addWidget(label)

    def _add_message_row(self, text: str) -> None:
        label = QLabel(text)
        label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        self._rows_layout.addWidget(label)

    def _clear_rows(self) -> None:
        while self._rows_layout.count():
            taken = self._rows_layout.takeAt(0)
            widget = taken.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _open_view_all(self) -> None:
        dialog = RemindersDialog(self._calendar_store, self)
        dialog.exec()
        self.refresh()


class RemindersDialog(QDialog):
    """The brief's own "VIEW ALL" destination — every non-completed item
    within a wide lookahead window, each with a real "Mark Done" action
    (`CalendarStore.mark_completed()`). Read-only otherwise (no
    postpone/reschedule UI) — kept deliberately minimal per this
    workstream's own scope decision, not a full reminder-management
    surface."""

    def __init__(self, calendar_store: CalendarStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._calendar_store = calendar_store
        self.setWindowTitle("All Reminders")
        self.resize(420, 480)

        layout = QVBoxLayout(self)
        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setSpacing(6)
        self._rows_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._rows_container)
        layout.addWidget(scroll)

        self._reload()

    def _reload(self) -> None:
        while self._rows_layout.count() > 1:
            taken = self._rows_layout.takeAt(0)
            widget = taken.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        try:
            items = self._calendar_store.list_due_within(datetime.now(UTC) + _DIALOG_LOOKAHEAD)
        except Exception:
            logger.exception("Reminders dialog failed to load items.")
            items = []

        if not items:
            empty = QLabel("Nothing scheduled.")
            empty.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
            self._rows_layout.insertWidget(0, empty)
            return
        for item in items:
            self._rows_layout.insertWidget(self._rows_layout.count() - 1, self._build_row(item))

    def _build_row(self, item: ScheduledItem) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(f"{_format_row_text(item)} ({item.item_type.value})")
        label.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        row_layout.addWidget(label, 1)
        mark_done = QPushButton("Mark Done")
        mark_done.clicked.connect(lambda _checked, item_id=item.item_id: self._mark_done(item_id))
        row_layout.addWidget(mark_done)
        return row

    def _mark_done(self, item_id: str) -> None:
        try:
            self._calendar_store.mark_completed(item_id)
        except Exception:
            logger.exception("Failed to mark reminder %s as done.", item_id)
        self._reload()
