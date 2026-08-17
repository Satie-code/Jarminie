"""TemperaturePanel — JARVIS Holographic HUD reskin, Phase 5.

The brief's own "System Temperature" panel — CPU/GPU/Motherboard rows
with thin holographic progress bars. `core.resource_monitor.
ResourceMonitor` gathers no temperature data at all today (confirmed by
this workstream's own research: no `psutil.sensors_temperatures()` call
exists anywhere in this codebase) — every row is therefore built once,
honestly showing "N/A" with an empty bar, per the brief's own explicit
"If a sensor is unavailable: Display N/A. Do not invent temperature
values." Deliberately built to the brief's own visual shape (bars, not
just bare text) so it activates for free, no code change needed here,
if a real temperature source is ever added to ResourceMonitor — only
`core/resource_monitor.py` and this panel's own (not-yet-written)
`set_value()` caller would need to change.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from presentation import theme

_ROWS = ("CPU", "GPU", "Motherboard")
_BAR_HEIGHT = 6


class _EmptyBar(QWidget):
    """A thin, permanently-empty holographic progress bar — this
    panel's own honest "no data" visual, matching the brief's own "thin
    holographic progress bars" shape rather than bare text alone."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(_BAR_HEIGHT)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.BORDER_DIM))
        painter.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 3, 3)
        painter.end()


class TemperaturePanel(QWidget):
    """No constructor collaborators — every row is static N/A; there is
    nothing in this codebase to poll."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QLabel("SYSTEM TEMPERATURE")
        header.setStyleSheet(f"color: {theme.ACCENT_CYAN}; font-weight: 600;")
        layout.addWidget(header)

        for name in _ROWS:
            row = QHBoxLayout()
            name_label = QLabel(name)
            name_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
            row.addWidget(name_label)
            row.addWidget(_EmptyBar(), 1)
            value_label = QLabel("N/A")
            value_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
            row.addWidget(value_label)
            layout.addLayout(row)

        layout.addStretch(1)
