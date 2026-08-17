"""HolographicFloorWidget (JARVIS Holographic HUD reskin, Phase 3).

The brief's own "Holographic Floor" section: a subtle projection plane
beneath the central core — concentric, perspective-flattened ellipses
and a few radial lines, anchoring the sphere without dominating the
screen. Deliberately static (no `_on_tick()`/animation): the brief's own
"keep it subtle... must not dominate the screen" is easiest to honor by
not giving it independent motion competing with the sphere/ring/particles
for attention — its only live input is `set_color()`, called whenever
the persona's accent color changes (mirrors the sphere/ring's own
`set_color`/`set_target`, just without a phase to animate).
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

_DEFAULT_COLOR = QColor("#0A84FF")
_FLOOR_CENTER_Y_FRACTION = 0.86
_RING_WIDTH_FRACTIONS = (0.85, 0.6, 0.35)
_ELLIPSE_HEIGHT_RATIO = 0.16
"""Height-to-width ratio for each ellipse — small, giving the flattened
"looking down at a floor" perspective the brief asks for ("perspective
distortion if practical") without genuine 3D projection math."""

_RADIAL_LINE_COUNT = 8


class HolographicFloorWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._color = _DEFAULT_COLOR

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        rect = self.rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return
        center_x = rect.width() / 2.0
        center_y = rect.height() * _FLOOR_CENTER_Y_FRACTION
        max_half_width = rect.width() * 0.42

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        outer_half_width = max_half_width * _RING_WIDTH_FRACTIONS[0]
        for fraction in _RING_WIDTH_FRACTIONS:
            half_width = max_half_width * fraction
            half_height = half_width * _ELLIPSE_HEIGHT_RATIO
            color = QColor(self._color)
            color.setAlphaF(0.12 + 0.1 * fraction)
            pen = QPen(color)
            pen.setWidthF(1.2)
            painter.setPen(pen)
            ellipse_rect = QRectF(
                center_x - half_width, center_y - half_height, half_width * 2, half_height * 2
            )
            painter.drawEllipse(ellipse_rect)

        line_color = QColor(self._color)
        line_color.setAlphaF(0.10)
        pen = QPen(line_color)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        for index in range(_RADIAL_LINE_COUNT):
            angle_fraction = index / _RADIAL_LINE_COUNT
            x_offset = (angle_fraction - 0.5) * 2 * outer_half_width
            y_offset = abs(angle_fraction - 0.5) * 2 * outer_half_width * _ELLIPSE_HEIGHT_RATIO
            painter.drawLine(
                QPointF(center_x, center_y), QPointF(center_x + x_offset, center_y - y_offset)
            )
        painter.end()
