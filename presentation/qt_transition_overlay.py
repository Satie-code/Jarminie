"""QtTransitionOverlay (Sprint 5.14 — Level 5 Part A).

The real, on-screen `TransitionOverlay` (`presentation/transition_engine.py`,
Sprint 5.10) — a minimal, honest visual for the "Display JARMINEI Core ->
Particle transition" phases of `TransitionEngine.transition()`'s own
seven-step choreography. Deliberately not a literal rendered "JARMINEI
Core" 3D/particle system (real content work, not this sprint's own
architecture-wiring job, per Sprint 5.10's own docstring naming this as
future work) — a semi-transparent full-parent overlay with a centered
label naming the current `TransitionPhase`, drawing a slow neutral pulse
during `SHOWING_CORE`/`PARTICLE_TRANSITION` specifically (the two phases
Sprint 5.10's own docstring names as needing a real visual), and a plain
phase label the rest of the time.

Parented to `PresentationHostWidget` (Sprint 5.14) and resized to cover
it exactly, so it visually sits atop whichever renderer is currently
mounted underneath — matches this sprint's own Engineering Rationale
("A real, on-screen overlay is Sprint 5.14's job, embedded into
MainWindow alongside the renderer-hosting work"). Wired in via
`TransitionEngine.set_overlay()` (this sprint's own necessary addition
to that class — see its own docstring for why a real `QWidget` cannot
be constructed at `main.py`'s composition-root time).

Every method degrades to a safe, logged no-op rather than raising back
into `TransitionEngine`'s own `_call_overlay_safely()` wrapper — belt
and suspenders, since that wrapper already catches any exception here,
but a presentation-only overlay should never risk a real Qt failure
propagating regardless.

**Per-tick exception guarding (Sprint 5.16 adversarial re-read, a
Post-Sprint Fix)**: `_on_tick()` is a `QTimer` slot with nothing
upstream of it to catch an exception — the same risk class Sprint
5.15's own scenario (c) fixed for `HolographicSphereWidget`/
`SegmentedRingWidget`, missed for this file since it wasn't in that
sprint's own Files to Modify list. Fixed here with the identical
pattern: a single bad tick is caught, logged once per failure streak
(reset on recovery), the last-painted frame retained.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from presentation.transition_engine import TransitionPhase

logger = get_logger(__name__)

_PULSE_PHASES = frozenset({TransitionPhase.SHOWING_CORE, TransitionPhase.PARTICLE_TRANSITION})
_PULSE_TICK_MS = 33
_BACKGROUND_COLOR = QColor(10, 14, 20, 190)
_PULSE_COLOR = QColor(34, 211, 238)

_PHASE_LABELS: dict[TransitionPhase, str] = {
    TransitionPhase.SAVING_STATE: "Saving state...",
    TransitionPhase.SYNCING_MEMORY: "Syncing memory...",
    TransitionPhase.SHOWING_CORE: "JARMINEI",
    TransitionPhase.PARTICLE_TRANSITION: "JARMINEI",
    TransitionPhase.LOADING_TARGET: "Loading...",
    TransitionPhase.RESTORING_CONVERSATION: "Restoring conversation...",
    TransitionPhase.COMPLETE: "",
}


class QtTransitionOverlay(QWidget):
    """Constructor DI: receives the QWidget it should overlay (typically
    `PresentationHostWidget`). Starts hidden — `show()` is the real
    caller, matching `TransitionOverlay`'s own Protocol contract."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        self._phase: TransitionPhase | None = None
        self._pulse_phase = 0.0
        self._tick_failure_logged = False

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("color: white; font-size: 16pt;")
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)

        self._timer = QTimer(self)
        self._timer.setInterval(_PULSE_TICK_MS)
        self._timer.timeout.connect(self._on_tick)

        self.hide()

    def show(self) -> None:
        try:
            self.setGeometry(self._host.rect())
            self.raise_()
            self._timer.start()
            super().show()
        except Exception:
            logger.exception("QtTransitionOverlay.show() failed; continuing.")

    def set_phase(self, phase: TransitionPhase) -> None:
        try:
            self._phase = phase
            self._label.setText(_PHASE_LABELS.get(phase, ""))
        except Exception:
            logger.exception("QtTransitionOverlay.set_phase(%s) failed; continuing.", phase)

    def hide(self) -> None:
        try:
            self._timer.stop()
            self._phase = None
            super().hide()
        except Exception:
            logger.exception("QtTransitionOverlay.hide() failed; continuing.")

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override, not our naming convention)
        painter = QPainter(self)
        painter.fillRect(self.rect(), _BACKGROUND_COLOR)
        if self._phase in _PULSE_PHASES:
            import math

            radius = 40 + 15 * math.sin(self._pulse_phase)
            center = self.rect().center()
            painter.setBrush(_PULSE_COLOR)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(center, radius, radius)
        painter.end()

    def _on_tick(self) -> None:
        """Sprint 5.16 (adversarial re-read): never raises — see this
        module's own "Per-tick exception guarding" docstring section."""
        try:
            self._pulse_phase += 0.2
            self.update()
        except Exception:
            if not self._tick_failure_logged:
                logger.exception(
                    "QtTransitionOverlay._on_tick() failed; retaining the last-painted frame."
                )
                self._tick_failure_logged = True
            return
        self._tick_failure_logged = False
