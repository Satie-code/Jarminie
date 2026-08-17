"""HudFrame — JARVIS Holographic HUD reskin, Phase 2.

The brief's own "Global HUD Frame" section: thin corner brackets around
the whole window, atmosphere rather than content. A transparent overlay
widget stacked on top of `HudShell` (parented to it, always resized to
match, always raised above every sibling), painting four small
L-shaped corner brackets and nothing else — no background fill (so
everything beneath it stays fully visible), and
`WA_TransparentForMouseEvents` so it never intercepts a click meant for
whatever is underneath it.

Deliberately not animated and not timer-driven: `paintEvent()` only runs
when Qt actually needs to repaint this widget (construction, resize,
expose) — there is no `QTimer` here, so "painted once and cached" in
this module's own name is really "painted only when it must be,"
satisfying section 25's "don't run expensive work every paint event"
guidance about as cheaply as a widget can.

**Phase 9**: `set_accent_color()` lets `ui/jarvis/hud_shell.py` source
the bracket color from the mounted persona's own locked `ui_accent`
(a one-time construction-time read) instead of always the fixed
`theme.BORDER_ACCENT` default — "PresentationState-driven accent color
flowing into the HUD chrome, not just the sphere."
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from presentation import theme

_BRACKET_LENGTH = 22.0
_BRACKET_MARGIN = 6.0
_BRACKET_WIDTH = 1.6


class HudFrame(QWidget):
    """A raised, click-through overlay drawing the four corner brackets.
    Call `sync_geometry()` whenever the parent it's meant to cover
    resizes (HudShell's own resizeEvent does this) — this widget has no
    layout of its own since it must overlay its parent rather than
    participate in its parent's own layout."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._accent_color = theme.BORDER_ACCENT
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.sync_geometry()
        self.show()
        self.raise_()

    def sync_geometry(self) -> None:
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())

    def set_accent_color(self, hex_color: str) -> None:
        self._accent_color = hex_color
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        rect = self.rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(self._accent_color))
        pen.setWidthF(_BRACKET_WIDTH)
        painter.setPen(pen)

        corners = (
            (rect.left() + _BRACKET_MARGIN, rect.top() + _BRACKET_MARGIN, 1, 1),
            (rect.right() - _BRACKET_MARGIN, rect.top() + _BRACKET_MARGIN, -1, 1),
            (rect.left() + _BRACKET_MARGIN, rect.bottom() - _BRACKET_MARGIN, 1, -1),
            (rect.right() - _BRACKET_MARGIN, rect.bottom() - _BRACKET_MARGIN, -1, -1),
        )
        for x, y, dx, dy in corners:
            origin = QPointF(x, y)
            painter.drawLine(origin, QPointF(x + dx * _BRACKET_LENGTH, y))
            painter.drawLine(origin, QPointF(x, y + dy * _BRACKET_LENGTH))
        painter.end()
