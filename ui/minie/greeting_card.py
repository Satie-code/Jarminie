"""MinieGreetingCard — Minie Persona UI workstream.

The reference image's own "Hi Sattie! ♡ / I'm Minie — your cute AI
friend, always with you!" card: a warm per-user heading plus a live
subtext line that tracks the current voice-session state, faded between
states rather than snapped instantly.

Heading name: `core_manager.ui_config().user_display_name`, read once at
construction AND re-read on a QTimer at
`core_manager.ui_config().status_refresh_interval_ms` — a user could
change their display name in Settings mid-session, the same real gap
`ui/jarvis/top_bar.py`'s own `refresh()` already exists to cover for
Jarvis's greeting. Falls back to "there" exactly like that method's own
`(display_name or "there")` precedent, title-cased rather than
upper-cased here ("Hi Sattie! ♡", not "HI SATTIE! ♡") since this card is
a warm greeting, not a HUD readout.

Subtext: driven entirely by `MinieUiStateAdapter.session_state_updated`
(no separate poller of its own) — IDLE shows the default idle line,
every other `SessionState` shows a short present-tense line. A brief
`QGraphicsOpacityEffect` + `QPropertyAnimation` fade (0→1 over ~250ms,
the identical Qt-native animation mechanism `ui/minie/widgets/
emotion_bar.py`'s own `set_value()` already establishes for Minie's other
animated readouts) plays only when the text actually changes — the
adapter re-emits `session_state_updated` on every refresh tick regardless
of whether the state changed, so a same-text guard is what keeps this
card from replaying the fade every ~3 seconds at idle."""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

from core.logging_setup import get_logger
from core.manager import CoreManager
from presentation import minie_theme
from ui.minie.ui_state_adapter import MinieUiStateAdapter
from ui.minie.widgets.glass_panel import GlassPanel
from voice.session_manager import SessionState

logger = get_logger(__name__)

_FADE_MS = 250

_DEFAULT_SUBTEXT = "I'm Minie — your cute AI friend, always with you!"

_SESSION_SUBTEXT: dict[SessionState, str] = {
    SessionState.IDLE: _DEFAULT_SUBTEXT,
    SessionState.LISTENING: "Listening...",
    SessionState.PROCESSING: "Thinking... ♡",
    SessionState.AWAITING_NEXT_TURN: "Thinking... ♡",
    SessionState.SPEAKING: "Sharing my thoughts... ♡",
}


class MinieGreetingCard(GlassPanel):
    """Constructor DI: `ui_state_adapter` (subtext), `core_manager`
    (heading name, re-read on a timer — see this module's own
    docstring). Subclasses `GlassPanel` directly rather than composing
    one internally, since this whole widget IS one card with no other
    surrounding chrome — `glow=False` (the default) since this is a
    calm/idle card, never an alert."""

    def __init__(
        self,
        ui_state_adapter: MinieUiStateAdapter,
        core_manager: CoreManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, glow=False)
        self._core_manager = core_manager

        self._heading_label = QLabel()
        heading_font = QFont(minie_theme.FONT_FAMILY)
        heading_font.setPointSize(16)
        heading_font.setBold(True)
        self._heading_label.setFont(heading_font)
        self._heading_label.setStyleSheet(f"color: {minie_theme.TEXT_PRIMARY};")

        self._subtext_label = QLabel(_DEFAULT_SUBTEXT)
        subtext_font = QFont(minie_theme.FONT_FAMILY)
        subtext_font.setPointSize(10)
        self._subtext_label.setFont(subtext_font)
        self._subtext_label.setStyleSheet(f"color: {minie_theme.TEXT_SECONDARY};")
        self._subtext_label.setWordWrap(True)

        self._opacity_effect = QGraphicsOpacityEffect(self._subtext_label)
        self._opacity_effect.setOpacity(1.0)
        self._subtext_label.setGraphicsEffect(self._opacity_effect)
        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_animation.setDuration(_FADE_MS)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.layout_().addWidget(self._heading_label)
        self.layout_().addWidget(self._subtext_label)

        ui_state_adapter.session_state_updated.connect(self._on_session_state_updated)

        interval_ms = core_manager.ui_config().status_refresh_interval_ms
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        """Fail Gracefully: a transient `ui_config()` read failure keeps
        the last-known-good greeting name rather than crashing the
        recurring QTimer callback — the same shape `TopBar.refresh()`
        already establishes."""
        try:
            display_name = self._core_manager.ui_config().user_display_name
        except Exception:
            logger.exception(
                "Minie greeting card refresh failed to read config; keeping last name."
            )
            return
        name = (display_name or "there").title()
        self._heading_label.setText(f"Hi {name}! ♡")

    def _on_session_state_updated(self, session_state: object) -> None:
        text = _SESSION_SUBTEXT.get(session_state, _DEFAULT_SUBTEXT)
        if text == self._subtext_label.text():
            return
        self._subtext_label.setText(text)
        self._fade_animation.stop()
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.start()
