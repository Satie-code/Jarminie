"""MinieSpeechBubble — Minie Persona UI workstream.

The reference image's own speech bubble anchored near the avatar
("Hello Sattie! How can I help you today? ♡") — the one place in this
UI where Minie's own words (or an honest "thinking" placeholder) are
displayed as short-form conversational text, distinct from any
transcript/log surface elsewhere in this codebase.

`show_reply()` is a plain public method, not wired to a signal itself —
per this workstream's own scope, the real caller (composed once a
conversation turn completes) is built elsewhere; this file only
guarantees the method exists and behaves correctly when called.

The "Thinking... ♡" placeholder is sourced from exactly one place:
`MinieUiStateAdapter.session_state_updated` (`SessionState.PROCESSING`
or `SessionState.AWAITING_NEXT_TURN`). This is deliberately the ONLY
file in this codebase that renders a "thinking" placeholder for the
speech bubble — no other panel duplicates this logic.
"""

from PySide6.QtCore import QPropertyAnimation, Qt
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from presentation import minie_theme
from ui.minie.ui_state_adapter import MinieUiStateAdapter
from voice.session_manager import SessionState

logger = get_logger(__name__)

_DEFAULT_TEXT = "Hello! How can I help you today? ♡"
_THINKING_TEXT = "Thinking... ♡"
_FADE_IN_MS = 300
_THINKING_STATES = frozenset({SessionState.PROCESSING, SessionState.AWAITING_NEXT_TURN})


class MinieSpeechBubble(QWidget):
    """Constructor DI: (ui_state_adapter, parent) — the shared polling
    adapter's own session_state_updated signal is the only backend
    source this widget consults; show_reply() itself takes plain text
    from a caller outside this file (see this module's own docstring)."""

    def __init__(
        self,
        ui_state_adapter: MinieUiStateAdapter,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("minie_speech_bubble")
        self.setStyleSheet(
            f"#minie_speech_bubble {{"
            f" background-color: {minie_theme.BG_PANEL_RAISED};"
            f" border: 1px solid {minie_theme.BORDER_ACCENT};"
            f" border-radius: 18px;"
            f" }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        self._body_label = QLabel(_DEFAULT_TEXT)
        self._body_label.setWordWrap(True)
        self._body_label.setStyleSheet(f"color: {minie_theme.TEXT_PRIMARY}; border: none;")
        layout.addWidget(self._body_label)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_animation.setDuration(_FADE_IN_MS)

        self._showing_thinking_placeholder = False

        ui_state_adapter.session_state_updated.connect(self._on_session_state_updated)

    def show_reply(self, text: str) -> None:
        """Sets the bubble's body text to a real reply and plays a short
        fade-in. Overwrites any "Thinking... ♡" placeholder currently
        showing — this is the only way a placeholder is ever cleared
        other than the session state itself moving on (see
        _on_session_state_updated())."""
        self._showing_thinking_placeholder = False
        self._set_text_and_animate(text)

    def _on_session_state_updated(self, session_state: object) -> None:
        """Fail Gracefully: an unrecognized session_state value (e.g. a
        MagicMock in a test, or a future enum member) simply isn't
        treated as a "thinking" state — never a crash."""
        try:
            is_thinking = session_state in _THINKING_STATES
        except Exception:
            logger.exception("MinieSpeechBubble failed to interpret session state.")
            return

        if is_thinking:
            self._showing_thinking_placeholder = True
            self._set_text_and_animate(_THINKING_TEXT)
        elif self._showing_thinking_placeholder:
            # The session moved on from PROCESSING/AWAITING_NEXT_TURN
            # without a real show_reply() ever landing (e.g. the turn
            # was aborted) — fall back to the default greeting rather
            # than leaving a stale "Thinking... ♡" on screen forever.
            self._showing_thinking_placeholder = False
            self._set_text_and_animate(_DEFAULT_TEXT)

    def _set_text_and_animate(self, text: str) -> None:
        if self._body_label.text() == text:
            return
        self._body_label.setText(text)
        self._fade_animation.stop()
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.start()
