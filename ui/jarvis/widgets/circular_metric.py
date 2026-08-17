"""CircularMetric — JARVIS Holographic HUD reskin, Phase 5.

The brief's own "circular/donut indicators" for System Overview: a
thin, static (no animation — a resource percentage isn't a state worth
choreographing) ring gauge with the numeric value at its center and a
label beneath. `set_value(None)` renders an honest "N/A" — used for
GPU, since `core.resource_monitor.ResourceMonitor` has no GPU metric at
all (a documented limitation, not an oversight — see that module's own
docstring); never fabricated.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from presentation import theme

_TRACK_WIDTH = 5.0
_ARC_TOP_MARGIN = 4.0
_LABEL_HEIGHT = 16.0


class CircularMetric(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = label
        self._value: float | None = None
        self.setMinimumSize(64, 78)

    def set_value(self, value: float | None) -> None:
        """None means "no data source" (rendered as N/A) — distinct
        from 0.0, a real, honest zero-percent reading."""
        self._value = value
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        rect = self.rect()
        side = min(rect.width(), rect.height() - _LABEL_HEIGHT) - _ARC_TOP_MARGIN
        if side <= 0:
            return
        arc_rect = QRectF(
            (rect.width() - side) / 2.0, _ARC_TOP_MARGIN / 2.0, side, side
        )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track_pen = QPen(QColor(theme.BORDER_DIM))
        track_pen.setWidthF(_TRACK_WIDTH)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(arc_rect, 0, 360 * 16)

        if self._value is not None:
            fraction = max(0.0, min(1.0, self._value / 100.0))
            value_pen = QPen(QColor(theme.ACCENT_CYAN))
            value_pen.setWidthF(_TRACK_WIDTH)
            value_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(value_pen)
            span_sixteenths = int(-fraction * 360 * 16)
            painter.drawArc(arc_rect, 90 * 16, span_sixteenths)

        value_text = f"{self._value:.0f}%" if self._value is not None else "N/A"
        value_font = QFont(theme.FONT_FAMILY_MONO)
        value_font.setPointSize(10)
        value_font.setBold(True)
        painter.setFont(value_font)
        painter.setPen(QColor(theme.TEXT_PRIMARY))
        painter.drawText(arc_rect, int(Qt.AlignmentFlag.AlignCenter), value_text)

        label_font = QFont(theme.FONT_FAMILY)
        label_font.setPointSize(8)
        painter.setFont(label_font)
        painter.setPen(QColor(theme.TEXT_SECONDARY))
        label_rect = QRectF(0, arc_rect.bottom() + 2, rect.width(), _LABEL_HEIGHT)
        painter.drawText(label_rect, int(Qt.AlignmentFlag.AlignHCenter), self._label)
        painter.end()
