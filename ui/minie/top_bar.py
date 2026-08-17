"""MinieTopBar — Minie Persona UI workstream.

The top chrome bar for Minie's warm, companion-style shell: a live date/
time readout on the left, and on the right a small honest status cluster
(network, volume, battery) followed by Minie's own glass-styled window
controls — the sibling to `ui/jarvis/top_bar.py`'s own branding+clock+
greeting bar, but this bar carries no branding of its own (MinieSidebar
already owns that, see `ui/minie/sidebar.py`) and adds window controls
Jarvis's own bar never needed.

Network and volume are honest static "N/A" readouts, never fabricated
numbers: this workstream's own research (echoed by `ui/jarvis/
network_panel.py`'s own docstring) confirms there is no network probe
(`psutil.net_io_counters()` or otherwise) and no system-volume probe
anywhere in this codebase. Battery is real —
`CoreManager.check_resources().battery_percent`, a genuine
`psutil`-backed reading that is honestly `None` on a desktop with no
battery, shown as "N/A" in that case rather than a fabricated "100%".

Two separate QTimers, a deliberate deviation from `ui/jarvis/top_bar.py`'s
own single 1s timer for everything: the clock/date read is free
(`datetime.now()`), but `CoreManager.check_resources()` samples CPU via
`psutil` — running that at 1Hz would be wasted, needless work for a
battery reading that only meaningfully changes over minutes, not seconds.
The clock/date stays on its own free-running 1s timer; the battery
readout instead shares `core_manager.ui_config().status_refresh_interval_ms`,
the same shared, already-tunable cadence every other status-polling
widget in this codebase uses.

`minimize_requested`/`maximize_requested`/`close_requested` exist because
this widget owns no `QMainWindow` reference: window-control buttons are
drawn here (Minie's own small circular glass buttons, never native OS
chrome) but the real window action is entirely the embedder's job, the
same "emit a Signal, let the owner wire the real action" boundary this
codebase already keeps between UI widgets and the objects they affect."""

from datetime import datetime

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QLabel, QWidget

from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation import minie_theme

logger = get_logger(__name__)

_CLOCK_INTERVAL_MS = 1000
"""A plain QLabel text update from a free `datetime.now()` read — cheap
enough to need no config field of its own, the same judgment
`ui/jarvis/top_bar.py`'s own `_CLOCK_INTERVAL_MS` already documents."""

_CONTROL_BUTTON_SIZE = 26


class _WindowControlButton(QAbstractButton):
    """A small self-painted circular glass button — Minie's own window
    chrome never borrows native OS button styling. Purely presentational:
    clicking only emits `QAbstractButton.clicked`, wired by
    `MinieTopBar` to its own Signal — see this module's own docstring for
    why the real window action lives entirely with the embedder."""

    def __init__(self, glyph: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._glyph = glyph
        self._hovered = False
        self.setFixedSize(_CONTROL_BUTTON_SIZE, _CONTROL_BUTTON_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        if self._hovered:
            fill = QColor(minie_theme.BORDER_ACCENT)
            fill.setAlpha(50)
            painter.setPen(QPen(QColor(minie_theme.BORDER_ACCENT), 1))
            painter.setBrush(fill)
        else:
            painter.setPen(QPen(QColor(minie_theme.BORDER_DIM), 1))
            painter.setBrush(QColor(minie_theme.BG_PANEL_RAISED))
        painter.drawEllipse(rect)

        font = QFont(minie_theme.FONT_FAMILY)
        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(QColor(minie_theme.TEXT_PRIMARY))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), self._glyph)
        painter.end()


class MinieTopBar(QWidget):
    """Constructor DI: only CoreManager — `ui_config().status_refresh_interval_ms`
    (battery cadence) and `check_resources()` (the battery reading
    itself) are this widget's only two real data needs, the same narrow
    "UI layer only needs CoreManager's UI-relevant slice" boundary
    `ui/jarvis/top_bar.py`'s own docstring already establishes."""

    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    def __init__(self, core_manager: CoreManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._core_manager = core_manager

        self._datetime_label = QLabel()
        datetime_font = QFont(minie_theme.FONT_FAMILY)
        datetime_font.setPointSize(10)
        self._datetime_label.setFont(datetime_font)
        self._datetime_label.setStyleSheet(f"color: {minie_theme.TEXT_PRIMARY};")

        self._network_label = QLabel("Network: N/A")
        self._network_label.setStyleSheet(f"color: {minie_theme.TEXT_SECONDARY};")

        self._volume_label = QLabel("Volume: N/A")
        self._volume_label.setStyleSheet(f"color: {minie_theme.TEXT_SECONDARY};")

        self._battery_label = QLabel("\U0001f50b N/A")
        self._battery_label.setStyleSheet(f"color: {minie_theme.TEXT_SECONDARY};")

        self._minimize_button = _WindowControlButton("–")
        self._minimize_button.clicked.connect(self.minimize_requested.emit)
        self._maximize_button = _WindowControlButton("▢")
        self._maximize_button.clicked.connect(self.maximize_requested.emit)
        self._close_button = _WindowControlButton("×")
        self._close_button.clicked.connect(self.close_requested.emit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 12, 6)
        layout.setSpacing(14)
        layout.addWidget(self._datetime_label)
        layout.addStretch(1)
        layout.addWidget(self._network_label)
        layout.addWidget(self._volume_label)
        layout.addWidget(self._battery_label)
        layout.addSpacing(10)
        layout.addWidget(self._minimize_button)
        layout.addWidget(self._maximize_button)
        layout.addWidget(self._close_button)

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(_CLOCK_INTERVAL_MS)
        self._clock_timer.timeout.connect(self._refresh_clock)
        self._clock_timer.start()
        self._refresh_clock()

        interval_ms = core_manager.ui_config().status_refresh_interval_ms
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(interval_ms)
        self._status_timer.timeout.connect(self.refresh)
        self._status_timer.start()
        self.refresh()

    def _refresh_clock(self) -> None:
        now = datetime.now()
        self._datetime_label.setText(now.strftime("%A, %d %b %Y | %I:%M %p"))

    def refresh(self) -> None:
        """Fail Gracefully: a transient `check_resources()` failure keeps
        the last-known-good battery reading rather than crashing the
        recurring QTimer callback — the same shape `TopBar.refresh()`/
        `RemindersPanel.refresh()` already establish."""
        try:
            snapshot = self._core_manager.check_resources()
        except Exception:
            logger.exception(
                "Minie top bar status refresh failed; keeping the last battery reading."
            )
            return

        if snapshot.battery_percent is None:
            battery_text = "\U0001f50b N/A"
        else:
            battery_text = f"\U0001f50b {snapshot.battery_percent:.0f}%"
        self._battery_label.setText(battery_text)
