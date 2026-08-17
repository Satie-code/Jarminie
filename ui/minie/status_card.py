"""MinieStatusCard — Minie Persona UI workstream.

The bottom-left "avatar + online status" card from the companion-app
reference image: a small circular avatar glyph, a live status line
("Online ♡" / "Listening ♡" / ...), and a fixed warm subtext
("Always here for you ♡"). Sourced entirely from
`ui.minie.ui_state_adapter.MinieUiStateAdapter`'s own
`session_state_updated`/`avatar_status_updated` signals rather than a
private QTimer of its own — both are already the adapter's job to poll
(see that module's own docstring), and this card has no other data need
that would justify a second poller.

Status derivation is deliberately connection-first: until
`avatar_status_updated` reports the VTube Studio connection as live, the
card shows "Connecting..." regardless of whatever `SessionState` the
voice pipeline happens to report — an honest reflection of "the avatar
itself isn't actually here yet" rather than a session-state readout that
could otherwise claim "Online" while nothing is really connected. Once
connected, every `SessionState` reads as some flavor of "actively fine"
(green dot) — Minie has no unhealthy/error session state to distinguish
today, so no amber/red case exists on that branch."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from presentation import minie_theme
from ui.minie.ui_state_adapter import MinieUiStateAdapter
from voice.session_manager import SessionState

logger = get_logger(__name__)

_AVATAR_DIAMETER = 40

_SESSION_STATUS_TEXT: dict[SessionState, str] = {
    SessionState.LISTENING: "Listening ♡",
    SessionState.PROCESSING: "Thinking ♡",
    SessionState.AWAITING_NEXT_TURN: "Thinking ♡",
    SessionState.SPEAKING: "Speaking ♡",
    SessionState.IDLE: "Online ♡",
}

_CONNECTING_TEXT = "Connecting..."
_SUBTEXT = "Always here for you ♡"


def _status_html(text: str, dot_color: str) -> str:
    """Rich-text dot + label in one QLabel — the identical shape
    `ui/jarvis/mission_status_panel.py`'s own `_row_html()` already
    establishes, avoiding the plain-`QWidget`-background QSS gotcha
    `GlassPanel`'s own docstring documents (a separate QLabel styled with
    a `border-radius` fill would need `WA_StyledBackground` of its own;
    an inline `<span>` dot needs none)."""
    return (
        f'<span style="color:{dot_color};">&#9679;</span> '
        f'<span style="color:{minie_theme.TEXT_PRIMARY}; font-weight:600;">{text}</span>'
    )


class _AvatarGlyph(QWidget):
    """Self-painted circular placeholder avatar — a `PRIMARY_ACCENT_DEFAULT`
    -tinted circle with a monogram "M". No real portrait image exists or
    is expected anywhere in this codebase (Minie's real avatar renders
    inside the separately-running VTube Studio window, per
    `presentation/minie_renderer.py`'s own "JARMINEI never renders Live2D
    itself" boundary) — this glyph is deliberately abstract, never a
    stand-in pretending to be the real thing."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_AVATAR_DIAMETER, _AVATAR_DIAMETER)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(minie_theme.PRIMARY_ACCENT_DEFAULT))
        painter.drawEllipse(rect)

        font = QFont(minie_theme.FONT_FAMILY)
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(minie_theme.BG_VOID))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "M")
        painter.end()


class MinieStatusCard(QWidget):
    """Constructor DI: only the shared `MinieUiStateAdapter` — see this
    module's own docstring for the two signals it subscribes to and the
    connection-first status derivation rule."""

    def __init__(
        self, ui_state_adapter: MinieUiStateAdapter, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._avatar_connected = False
        self._session_state: SessionState | None = None

        self._status_label = QLabel()
        status_font = QFont(minie_theme.FONT_FAMILY)
        status_font.setPointSize(10)
        self._status_label.setFont(status_font)

        subtext_label = QLabel(_SUBTEXT)
        subtext_font = QFont(minie_theme.FONT_FAMILY)
        subtext_font.setPointSize(8)
        subtext_label.setFont(subtext_font)
        subtext_label.setStyleSheet(f"color: {minie_theme.TEXT_SECONDARY};")

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(2)
        text_column.addWidget(self._status_label)
        text_column.addWidget(subtext_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(_AvatarGlyph())
        layout.addLayout(text_column, 1)

        ui_state_adapter.session_state_updated.connect(self._on_session_state_updated)
        ui_state_adapter.avatar_status_updated.connect(self._on_avatar_status_updated)

        self._refresh_status()

    def _on_session_state_updated(self, session_state: object) -> None:
        self._session_state = session_state
        self._refresh_status()

    def _on_avatar_status_updated(self, connected: bool) -> None:
        self._avatar_connected = connected
        self._refresh_status()

    def _refresh_status(self) -> None:
        """Recomputes the displayed status from the latest reading of
        both signals — safe to call before either has fired even once
        (both default to a "not yet known"/falsy value, which correctly
        reads as "Connecting...")."""
        try:
            if not self._avatar_connected:
                self._status_label.setText(_status_html(_CONNECTING_TEXT, minie_theme.STATUS_AMBER))
                return
            text = _SESSION_STATUS_TEXT.get(self._session_state, "Online ♡")
            self._status_label.setText(_status_html(text, minie_theme.STATUS_GREEN))
        except Exception:
            logger.exception(
                "MinieStatusCard failed to render status; keeping last displayed value."
            )
