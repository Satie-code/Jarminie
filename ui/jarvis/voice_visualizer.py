"""VoiceVisualizer — JARVIS Holographic HUD reskin, Phase 6.

The brief's own top-right "Voice Interaction Indicator": a mic glyph, a
small pulse cluster standing in for the brief's own "audio waveform,"
and a status label. Polls `VoiceSessionManager.current_session_state()`
(`voice/session_manager.py`) — a Sprint 5.14 addition specifically for
renderer use — on a fast, fixed tick; there is no push/signal mechanism
for session state anywhere in this codebase (confirmed by this
workstream's own research), so polling matches the same established
pattern `PresentationHostWidget`'s own mounted-persona polling already
uses for an equivalent gap. The read itself (`current_session_state()`)
is a cheap in-memory enum access, not I/O — safe to poll faster than the
shared `status_refresh_interval_ms` cadence real CoreManager/CalendarStore
reads use elsewhere in this HUD.

**An honest, disclosed limitation**: no live microphone-amplitude data
source exists anywhere in this codebase — `VoiceSessionManager`'s own
RMS amplitude helper is private, used only for internal silence
detection, never exposed. The brief's own instruction not to "animate a
fake waveform permanently" is honored literally: the pulse below is
state-driven (real `SessionState`, real transitions), never amplitude-
driven, and sits still (no animation at all) in `IDLE`.

`VoiceVisualState.ERROR` is declared for structural completeness (the
brief's own named state) but has no live trigger today — `SessionState`
itself has no ERROR member; only `SessionEndReason.ERROR` exists, and
that describes why a session *ended*, not an ongoing state a mid-session
indicator could show. Declared now so a future sprint that adds one
changes zero call sites here — the same "declared but currently
unreachable" precedent `security/permission_gate.py`'s own
`PermissionDecision.REQUIRE_CONFIRMATION` already established.
"""

import math
from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from presentation import theme
from voice.session_manager import SessionState, VoiceSessionManager

logger = get_logger(__name__)

_TICK_MS = 60
_BAR_COUNT = 4
_BASE_PHASE_STEP = 0.12


class VoiceVisualState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"


_SESSION_STATE_MAP: dict[SessionState, VoiceVisualState] = {
    SessionState.IDLE: VoiceVisualState.IDLE,
    SessionState.LISTENING: VoiceVisualState.LISTENING,
    SessionState.PROCESSING: VoiceVisualState.PROCESSING,
    SessionState.SPEAKING: VoiceVisualState.SPEAKING,
    SessionState.AWAITING_NEXT_TURN: VoiceVisualState.PROCESSING,
}

_STATE_LABEL: dict[VoiceVisualState, str] = {
    VoiceVisualState.IDLE: "Idle",
    VoiceVisualState.LISTENING: "Listening...",
    VoiceVisualState.PROCESSING: "Processing...",
    VoiceVisualState.SPEAKING: "Speaking...",
    VoiceVisualState.ERROR: "Error",
}

_STATE_AMPLITUDE: dict[VoiceVisualState, float] = {
    VoiceVisualState.IDLE: 0.0,
    VoiceVisualState.LISTENING: 1.0,
    VoiceVisualState.PROCESSING: 0.4,
    VoiceVisualState.SPEAKING: 0.85,
    VoiceVisualState.ERROR: 0.0,
}

_STATE_COLOR: dict[VoiceVisualState, str] = {
    VoiceVisualState.IDLE: theme.TEXT_DIM,
    VoiceVisualState.LISTENING: theme.ACCENT_CYAN,
    VoiceVisualState.PROCESSING: theme.STATUS_AMBER,
    VoiceVisualState.SPEAKING: theme.ACCENT_CYAN,
    VoiceVisualState.ERROR: theme.STATUS_RED,
}


class _PulseCluster(QWidget):
    """A small row of bars whose heights oscillate together, scaled by
    the current state's own amplitude — never random/chaotic, the same
    "smooth, deliberate" discipline HolographicSphereWidget's own
    breathing pulse already established."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(48, 20)
        self._phase = 0.0
        self._state = VoiceVisualState.IDLE

    def set_state(self, state: VoiceVisualState) -> None:
        self._state = state

    def advance(self) -> None:
        self._phase = (self._phase + _BASE_PHASE_STEP) % (2 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        amplitude = _STATE_AMPLITUDE[self._state]
        color = QColor(_STATE_COLOR[self._state])
        rect = self.rect()
        bar_width = rect.width() / (_BAR_COUNT * 2 - 1)
        mid_y = rect.height() / 2.0

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color)
        pen.setWidthF(max(bar_width, 2.0))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        for index in range(_BAR_COUNT):
            x = bar_width * (index * 2 + 0.5)
            wave = 0.5 + 0.5 * math.sin(self._phase + index * 1.1)
            half_height = max(1.0, (rect.height() / 2.0) * amplitude * wave)
            painter.drawLine(QPointF(x, mid_y - half_height), QPointF(x, mid_y + half_height))
        painter.end()


class _MicGlyph(QWidget):
    """A minimal line-art microphone icon, colored by connection/session
    state — doubles as the brief's own "connection/status indicator"."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self._state = VoiceVisualState.IDLE

    def set_state(self, state: VoiceVisualState) -> None:
        self._state = state
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        color = QColor(_STATE_COLOR[self._state])
        rect = self.rect()
        cx = rect.width() / 2.0

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color)
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        capsule_width = rect.width() * 0.34
        capsule_top = 1.0
        capsule_height = rect.height() * 0.5
        capsule_rect = QRectF(cx - capsule_width / 2, capsule_top, capsule_width, capsule_height)
        painter.drawRoundedRect(capsule_rect, capsule_width / 2, capsule_width / 2)

        stand_rect = QRectF(
            cx - capsule_width, capsule_top - 2, capsule_width * 2, capsule_height + 6
        )
        painter.drawArc(stand_rect, 200 * 16, 140 * 16)

        stand_bottom = capsule_top + capsule_height + 4
        painter.drawLine(QPointF(cx, stand_bottom), QPointF(cx, rect.height() - 1))
        painter.end()


class VoiceVisualizer(QWidget):
    """Constructor DI: (session_manager,) — no CoreManager needed since
    the poll interval here is a fixed, cheap constant (see this module's
    own docstring), not one of the shared config-driven cadences."""

    def __init__(self, session_manager: VoiceSessionManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session_manager = session_manager
        self._state = VoiceVisualState.IDLE

        self._mic = _MicGlyph()
        self._pulse = _PulseCluster()
        self._status_label = QLabel(_STATE_LABEL[VoiceVisualState.IDLE])
        self._status_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 8pt;")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.addWidget(self._mic)
        top_row.addWidget(self._pulse)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(top_row)
        layout.addWidget(self._status_label)

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()
        self._on_tick()

    def _on_tick(self) -> None:
        """A single QTimer slot with no upstream caller to guard it —
        the same per-tick exception-guarding discipline every other
        animated widget in this HUD already follows (see e.g.
        HolographicSphereWidget._on_tick()'s own docstring)."""
        try:
            session_state = self._session_manager.current_session_state()
            state = _SESSION_STATE_MAP.get(session_state, VoiceVisualState.IDLE)
        except Exception:
            logger.exception("VoiceVisualizer failed to read session state; keeping last state.")
            state = self._state

        if state != self._state:
            self._state = state
            self._mic.set_state(state)
            self._pulse.set_state(state)
            self._status_label.setText(_STATE_LABEL[state])
        self._pulse.advance()
