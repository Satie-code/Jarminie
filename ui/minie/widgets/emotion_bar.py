"""EmotionBar — Minie Persona UI workstream.

A small, reusable animated labeled progress bar — ui/minie/emotion_panel.py's
own "Happiness ████████░░ 92%" rows, generalized as a standalone widget
so other panels can reuse the same look for any future 0-100 reading.
Self-painted (QPainter, matching ui/jarvis/widgets/circular_metric.py's
own "no QProgressBar chrome to fight with" precedent) rather than a
styled QProgressBar, for the same rounded/glowing look CircularMetric
already established for Jarvis's own ring gauges.

set_value() animates toward the new percentage via QPropertyAnimation
over a real Qt property (`value`) rather than snapping instantly — the
brief's own "emotion bar changes" required animation (section 24),
using this project's preferred Qt-native animation mechanism rather than
a hand-rolled QTimer.
"""

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from presentation import minie_theme

_BAR_HEIGHT = 8.0
_ANIMATION_MS = 450
_LABEL_ROW_HEIGHT = 18
_TRACK_Y = 30


class EmotionBar(QWidget):
    def __init__(
        self,
        label: str,
        accent_color: str = minie_theme.PRIMARY_ACCENT_DEFAULT,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label_text = label
        self._accent_color = QColor(accent_color)
        self._value = 0.0
        self.setMinimumHeight(_TRACK_Y + 12)

        self._animation = QPropertyAnimation(self, b"value", self)
        self._animation.setDuration(_ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_value(self, percent: float) -> None:
        """percent is clamped to 0.0-100.0 defensively — callers pass
        already-clamped MinieDisplayEmotions fields, but this widget
        makes no assumption about its caller."""
        percent = max(0.0, min(100.0, percent))
        self._animation.stop()
        self._animation.setStartValue(self._value)
        self._animation.setEndValue(percent)
        self._animation.start()

    def _get_value(self) -> float:
        return self._value

    def _set_value(self, value: float) -> None:
        self._value = value
        self.update()

    value = Property(float, _get_value, _set_value)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        label_font = QFont(minie_theme.FONT_FAMILY)
        label_font.setPointSize(9)
        painter.setFont(label_font)
        painter.setPen(QColor(minie_theme.TEXT_SECONDARY))
        painter.drawText(
            0,
            0,
            max(0, self.width() - 44),
            _LABEL_ROW_HEIGHT,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._label_text,
        )

        percent_font = QFont(minie_theme.FONT_FAMILY_MONO)
        percent_font.setPointSize(9)
        percent_font.setBold(True)
        painter.setFont(percent_font)
        painter.setPen(QColor(minie_theme.TEXT_PRIMARY))
        painter.drawText(
            max(0, self.width() - 44),
            0,
            44,
            _LABEL_ROW_HEIGHT,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            f"{self._value:.0f}%",
        )

        track_pen = QPen(QColor(minie_theme.BORDER_DIM))
        track_pen.setWidthF(_BAR_HEIGHT)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        half = _BAR_HEIGHT / 2.0
        painter.drawLine(int(half), _TRACK_Y, max(int(half), self.width() - int(half)), _TRACK_Y)

        if self._value > 0:
            fill_pen = QPen(self._accent_color)
            fill_pen.setWidthF(_BAR_HEIGHT)
            fill_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(fill_pen)
            fraction = self._value / 100.0
            usable_width = max(0.0, self.width() - _BAR_HEIGHT)
            end_x = half + fraction * usable_width
            painter.drawLine(int(half), _TRACK_Y, int(end_x), _TRACK_Y)
        painter.end()
