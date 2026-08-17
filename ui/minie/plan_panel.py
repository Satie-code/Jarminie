"""MinieTodaysPlanPanel — Minie Persona UI workstream.

The reference image's own "Today's Plan" panel — checkbox rows with
times (e.g. "✓ Finish ROS 2 project — 10:00 PM"). Real data only, from
`CalendarStore.list_due_within()` (`scheduler/calendar_store.py`) — the
same real "upcoming reminders" query `ui/jarvis/reminders_panel.py`
already uses, here filtered down to items scheduled on today's UTC
calendar date. `ScheduledItem` (`scheduler/scheduler_model.py`) has no
priority field at all — the only "priority" concept in this codebase
(`decision.priority_queue.PriorityLevel.SCHEDULED_REMINDER`) is a
transient dispatch-time value, never persisted per-item — so, exactly
like `ui/jarvis/reminders_panel.py`'s own documented finding, this panel
never fabricates a priority badge.

"Today" means everything due before the end of the current UTC calendar
day. `list_due_within(window_end)` has no lower bound of its own (an
overdue-from-earlier-days item still surfaces, by that method's own
design — see its docstring) so `window_end` alone is not enough to mean
"today": this panel additionally filters the returned items in Python to
only those whose `scheduled_at` falls within [start_of_today,
window_end), matching the UTC-calendar-day convention
`analytics/dashboard_data.py`'s own `daily_summary()` already
establishes for "one day" in this codebase. `include_completed=True` is
used deliberately so a user can see what they already finished today,
not only what's left.
"""

from datetime import UTC, datetime, timedelta

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation import minie_theme
from scheduler.calendar_store import CalendarStore
from scheduler.scheduler_model import ScheduledItem
from ui.minie.widgets.glass_panel import GlassPanel

logger = get_logger(__name__)


class MinieTodaysPlanPanel(QWidget):
    """Constructor DI: (calendar_store, core_manager, parent) —
    core_manager only for its own ui_config().status_refresh_interval_ms,
    the same shared, already-tunable interval every other panel in this
    workstream uses."""

    view_calendar_requested = Signal()
    """Emitted when "View Calendar" is clicked. Navigation itself is not
    this panel's concern — another, not-yet-built part of the shell
    connects to this signal; see this file's own brief."""

    def __init__(
        self,
        calendar_store: CalendarStore,
        core_manager: CoreManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._calendar_store = calendar_store

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self._panel = GlassPanel(self)
        outer_layout.addWidget(self._panel)

        header_row = QHBoxLayout()
        header = QLabel("Today's Plan")
        header.setStyleSheet(f"color: {minie_theme.PRIMARY_ACCENT_DEFAULT}; font-weight: 600;")
        header_row.addWidget(header)
        header_row.addStretch(1)
        view_calendar_button = QPushButton("View Calendar")
        view_calendar_button.setFlat(True)
        view_calendar_button.setStyleSheet(
            f"color: {minie_theme.TEXT_SECONDARY}; text-decoration: underline; border: none;"
        )
        view_calendar_button.clicked.connect(self.view_calendar_requested.emit)
        header_row.addWidget(view_calendar_button)
        self._panel.layout_().addLayout(header_row)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(6)
        self._panel.layout_().addLayout(self._rows_layout)

        interval_ms = core_manager.ui_config().status_refresh_interval_ms
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        """Fail Gracefully: a transient CalendarStore read (or an
        unexpected failure while filtering its result down to "today")
        shows an honest "unavailable" row rather than crashing the
        recurring QTimer callback — mirrors
        ui/jarvis/reminders_panel.py's own refresh()."""
        self._clear_rows()
        try:
            start_of_today = datetime.now(UTC).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            window_end = start_of_today + timedelta(days=1)
            items = self._calendar_store.list_due_within(window_end, include_completed=True)
            todays_items = [
                item for item in items if start_of_today <= item.scheduled_at < window_end
            ]
        except Exception:
            logger.exception("Today's Plan panel refresh failed; showing nothing this cycle.")
            self._add_message_row("Plan unavailable right now.")
            return

        if not todays_items:
            self._add_message_row("Nothing scheduled for today.")
            return
        for item in todays_items:
            self._rows_layout.addWidget(self._build_row(item))

    def _build_row(self, item: ScheduledItem) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        glyph_button = QPushButton("✓" if item.is_completed else "○")
        glyph_button.setFlat(True)
        glyph_color = minie_theme.STATUS_GREEN if item.is_completed else minie_theme.TEXT_SECONDARY
        glyph_button.setStyleSheet(
            f"color: {glyph_color}; border: none; font-weight: 600; padding: 0px 6px 0px 0px;"
        )
        if item.is_completed:
            glyph_button.setEnabled(False)
        else:
            glyph_button.clicked.connect(
                lambda _checked, item_id=item.item_id: self._mark_done(item_id)
            )
        row_layout.addWidget(glyph_button)

        title_label = QLabel(item.title)
        title_label.setStyleSheet(f"color: {minie_theme.TEXT_PRIMARY};")
        row_layout.addWidget(title_label, 1)

        time_text = item.scheduled_at.strftime("%I:%M %p").lstrip("0")
        time_label = QLabel(f"— {time_text}")
        time_label.setStyleSheet(f"color: {minie_theme.TEXT_SECONDARY};")
        row_layout.addWidget(time_label)

        return row

    def _add_message_row(self, text: str) -> None:
        label = QLabel(text)
        label.setStyleSheet(f"color: {minie_theme.TEXT_SECONDARY};")
        self._rows_layout.addWidget(label)

    def _clear_rows(self) -> None:
        while self._rows_layout.count():
            taken = self._rows_layout.takeAt(0)
            widget = taken.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _mark_done(self, item_id: str) -> None:
        try:
            self._calendar_store.mark_completed(item_id)
        except Exception:
            logger.exception("Failed to mark plan item %s as done.", item_id)
        self.refresh()
