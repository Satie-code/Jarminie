"""MinieMessageBar — Minie Persona UI workstream.

The reference image's own bottom pill-shaped input bar: a mic status
glyph on the left, "Type your message to Minie..." text entry, a send
button, and three small circular shortcut buttons near the bottom-right
(♡ relationship/Minie shortcut, ✦ companion/emotion shortcut, ⌂ home/
dashboard shortcut).

Text submission mirrors ui/jarvis/command_bar.py's CommandBar closely —
`voice/pipeline.py`'s `CommunicationPipeline.submit_text()` is the real,
existing conversational entry point (genuinely slow — LLM calls, DB
reads), so it must never run on the Qt main thread. This widget spawns a
plain `threading.Thread(daemon=True)` per submission and marshals the
result back via `QTimer.singleShot(0, self, callback)` — this project's
own established background-work idiom, not something reinvented here.

**The Microphone Rule (hard structural constraint, not a style
preference)**: `voice/quiet_mode.py`'s `QuietModeController` enforces
that "the only path from DORMANT to ACTIVE [starting a voice session] is
a successful wake-word detection... the only path back is a Voice
Session Manager session-end event." There is no public method anywhere
in this codebase for a UI button to force-start or force-stop a voice
session — this is intentional. This widget therefore takes NO
VoiceSessionManager/QuietModeController dependency at all (see
MinieMessageBar's own constructor — only `pipeline` and
`ui_state_adapter`), and its mic glyph (`_MicStatusIndicator`) is wired
exclusively to `ui_state_adapter.session_state_updated`, a read-only
signal — nothing in this file ever calls a session-starting/stopping
method, structurally, not just by convention.
"""

import threading
import uuid

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.logging_setup import get_logger
from presentation import minie_theme
from ui.minie.ui_state_adapter import MinieUiStateAdapter
from ui.minie.widgets.glass_panel import GlassPanel
from voice.pipeline import CommunicationPipeline
from voice.session_manager import SessionState

logger = get_logger(__name__)

_MAX_REPLY_PREVIEW_CHARS = 160
_MIC_TOOLTIP = "Voice activation is wake-word only — just say the wake word to talk to Minie."
_PULSE_DURATION_MS = 1200

_MIC_STATE_COLOR: dict[SessionState, str] = {
    SessionState.IDLE: minie_theme.TEXT_DIM,
    SessionState.LISTENING: minie_theme.BORDER_ACCENT,
    SessionState.PROCESSING: minie_theme.STATUS_AMBER,
    SessionState.SPEAKING: minie_theme.SECONDARY_ACCENT,
    SessionState.AWAITING_NEXT_TURN: minie_theme.STATUS_AMBER,
}


def _circular_button(glyph: str) -> QPushButton:
    button = QPushButton(glyph)
    button.setFixedSize(32, 32)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(
        f"QPushButton {{ border-radius: 16px; border: 1px solid {minie_theme.BORDER_DIM};"
        f" background-color: {minie_theme.BG_PANEL_RAISED};"
        f" color: {minie_theme.TEXT_PRIMARY}; padding: 0px; }}"
        f"QPushButton:hover {{ border: 1px solid {minie_theme.BORDER_ACCENT};"
        f" color: {minie_theme.BORDER_ACCENT}; }}"
    )
    return button


class _MicStatusIndicator(QWidget):
    """A STATUS INDICATOR ONLY — see this module's own docstring for the
    Microphone Rule this enforces structurally by omission: no method
    here starts/stops a voice session, or holds any reference capable of
    doing so. Purely a read-only reflection of
    MinieUiStateAdapter.session_state_updated, with a tooltip explaining
    wake-word activation. Gently pulses while LISTENING (a real,
    state-driven signal — never a fabricated waveform, the same
    discipline ui/jarvis/voice_visualizer.py's own docstring already
    establishes), sits calm/dim otherwise."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setToolTip(_MIC_TOOLTIP)
        self._state = SessionState.IDLE

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.55)
        self.setGraphicsEffect(self._opacity_effect)

        self._pulse_animation = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._pulse_animation.setDuration(_PULSE_DURATION_MS)
        self._pulse_animation.setKeyValueAt(0.0, 0.45)
        self._pulse_animation.setKeyValueAt(0.5, 1.0)
        self._pulse_animation.setKeyValueAt(1.0, 0.45)
        self._pulse_animation.setLoopCount(-1)
        self._pulse_animation.setEasingCurve(QEasingCurve.Type.InOutSine)

    def set_session_state(self, state: SessionState) -> None:
        self._state = state
        if state is SessionState.LISTENING:
            if self._pulse_animation.state() != QPropertyAnimation.State.Running:
                self._pulse_animation.start()
        else:
            self._pulse_animation.stop()
            self._opacity_effect.setOpacity(0.55)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        color = QColor(_MIC_STATE_COLOR.get(self._state, minie_theme.TEXT_DIM))
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color, 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

        cx = rect.center().x()
        capsule_width = rect.width() * 0.28
        capsule_height = rect.height() * 0.4
        capsule_top = rect.top() + rect.height() * 0.2
        capsule_rect = QRectF(cx - capsule_width / 2, capsule_top, capsule_width, capsule_height)
        painter.setBrush(color)
        painter.drawRoundedRect(capsule_rect, capsule_width / 2, capsule_width / 2)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        stand_rect = QRectF(
            cx - capsule_width, capsule_top - 1, capsule_width * 2, capsule_height + 6
        )
        painter.drawArc(stand_rect, 200 * 16, 140 * 16)
        stand_bottom = capsule_top + capsule_height + 4
        painter.drawLine(QPointF(cx, stand_bottom), QPointF(cx, rect.bottom() - 1))
        painter.end()


class MinieMessageBar(QWidget):
    """Constructor DI: (pipeline, ui_state_adapter, parent) — no
    VoiceSessionManager/QuietModeController dependency at all, by
    design (see this module's own docstring, the Microphone Rule)."""

    reply_received = Signal(str)
    """Emitted with the full reply text once a submission completes —
    including the fallback error string on failure, deliberately (see
    _display_reply()'s own docstring), so a subscriber like a speech-
    bubble widget still gets SOME feedback rather than silently missing
    the turn entirely."""

    relationship_shortcut_requested = Signal()
    """♡ — the Minie/relationship shortcut. No navigation logic here;
    other code connects to this signal."""

    companion_shortcut_requested = Signal()
    """✦ — the companion/emotion shortcut. No navigation logic here;
    other code connects to this signal."""

    home_requested = Signal()
    """⌂ — the home/dashboard shortcut. No navigation logic here; other
    code connects to this signal."""

    def __init__(
        self,
        pipeline: CommunicationPipeline,
        ui_state_adapter: MinieUiStateAdapter,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pipeline = pipeline
        self._session_id = str(uuid.uuid4())

        self._panel = GlassPanel(self, border_radius=28)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self._panel)

        self._reply_label = QLabel("")
        self._reply_label.setStyleSheet(
            f"color: {minie_theme.TEXT_SECONDARY}; font-size: 9pt; border: none;"
        )
        self._reply_label.setWordWrap(False)

        self._mic_indicator = _MicStatusIndicator()

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type your message to Minie...")
        self._input.setStyleSheet(
            f"QLineEdit {{ border-radius: 18px; padding: 8px 16px;"
            f" background-color: {minie_theme.BG_PANEL_RAISED};"
            f" border: 1px solid {minie_theme.BORDER_DIM}; }}"
            f"QLineEdit:focus {{ border: 1px solid {minie_theme.BORDER_ACCENT}; }}"
        )
        self._input.returnPressed.connect(self._submit)

        self._send_button = _circular_button("➤")
        self._send_button.clicked.connect(self._submit)

        self._relationship_button = _circular_button("♡")
        self._relationship_button.clicked.connect(self.relationship_shortcut_requested.emit)
        self._companion_button = _circular_button("✦")
        self._companion_button.clicked.connect(self.companion_shortcut_requested.emit)
        self._home_button = _circular_button("⌂")
        self._home_button.clicked.connect(self.home_requested.emit)

        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        input_row.addWidget(self._mic_indicator)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(self._send_button)
        input_row.addWidget(self._relationship_button)
        input_row.addWidget(self._companion_button)
        input_row.addWidget(self._home_button)

        self._panel.layout_().addWidget(self._reply_label)
        self._panel.layout_().addLayout(input_row)

        ui_state_adapter.session_state_updated.connect(self._on_session_state_updated)

    def _on_session_state_updated(self, session_state: object) -> None:
        """Fail Gracefully: an unrecognized session_state value (e.g. a
        MagicMock in a test, or a future enum member) just falls back to
        the dim/idle look via _MIC_STATE_COLOR.get()'s own default —
        never a crash."""
        try:
            self._mic_indicator.set_session_state(session_state)
        except Exception:
            logger.exception("MinieMessageBar failed to update the mic status indicator.")

    def _submit(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.setEnabled(False)
        self._send_button.setEnabled(False)
        self._input.clear()
        self._reply_label.setText("Thinking about that... ♡")

        thread = threading.Thread(
            target=self._run_submit_text,
            args=(text,),
            name="minie-message-bar-submit",
            daemon=True,
        )
        thread.start()

    def _run_submit_text(self, text: str) -> None:
        """Runs on a background thread — mirrors
        ui/jarvis/command_bar.py's CommandBar._run_submit_text() exactly:
        self._pipeline.submit_text() already never raises (its own Fail
        Gracefully contract), but this is still wrapped defensively
        since an uncaught exception on a bare threading.Thread would
        otherwise vanish silently rather than reaching this widget's own
        display update."""
        try:
            reply = self._pipeline.submit_text(text, self._session_id)
        except Exception:
            logger.exception("MinieMessageBar failed to submit text unexpectedly.")
            reply = "Sorry, something went wrong processing that."
        QTimer.singleShot(0, self, lambda: self._display_reply(reply))

    def _display_reply(self, reply: str) -> None:
        if len(reply) <= _MAX_REPLY_PREVIEW_CHARS:
            preview = reply
        else:
            preview = reply[:_MAX_REPLY_PREVIEW_CHARS] + "…"
        self._reply_label.setText(preview)
        self._reply_label.setToolTip(reply)
        self._input.setEnabled(True)
        self._send_button.setEnabled(True)
        self._input.setFocus(Qt.FocusReason.OtherFocusReason)
        # Emitted for both a real reply and the fallback error string
        # above, deliberately — see reply_received's own docstring.
        self.reply_received.emit(reply)
