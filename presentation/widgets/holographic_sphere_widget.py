"""HolographicSphereWidget (Sprint 5.7 — Level 5 Part A).

Jarvis's central translucent sphere: a `QPainter`-drawn radial-gradient
ellipse with a slow, continuous "breathing" pulse (radius oscillation).

**Target vs. animated phase, deliberately separate** (this sprint's own
Engineering Rationale, decision 2): `set_target()` sets the color/
animation-speed this widget should animate *toward* — called from
`JarvisRenderer.render_state()`, which `PresentationController.refresh()`
(Sprint 5.6) may invoke as infrequently as once per conversation turn.
The actual breathing-pulse *phase* is this widget's own private,
continuously-advancing float, stepped forward once per `_on_tick()` call
(driven by `JarvisRenderer`'s own shared `QTimer`, many times per
second) — never by `render_state()` itself. Conflating the two would
make the sphere visibly jump between infrequent `render_state()` calls
instead of animate smoothly.

**Per-tick exception guarding (Sprint 5.15, scenario c)**: `_on_tick()`
is a `QTimer` slot — an uncaught exception there is a structurally
different risk from a bad `render_state()` call (already `Presentation
Controller.refresh()`'s own job to guard, Sprint 5.6), since nothing
upstream of a `QTimer.timeout` signal can catch it. A single bad tick is
caught, logged once (rate-limited via `_tick_failure_logged` — reset on
the next successful tick — so a persistently-broken tick doesn't flood
the log every ~33ms), and the previous frame's own last-good `_phase`/
`update()` state is retained rather than a crashed timer or a half-drawn
widget.
"""

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from core.logging_setup import get_logger

logger = get_logger(__name__)

_DEFAULT_COLOR = QColor("#0A84FF")
_MIN_PULSE_SCALE = 0.85
_MAX_PULSE_SCALE = 1.0
"""The breathing pulse oscillates the sphere's own radius between these
two fractions of its base (widget-size-derived) radius — a small,
deliberate range matching the brief's own "smooth, deliberate,
purposeful" mandate, never a dramatic pulsate. Real, disclosed,
unvalidated first-pass numbers, same category as every other Level 5
visual constant so far."""
_BASE_PHASE_STEP = 0.05
"""Radians advanced per _on_tick() call at animation_speed=1.0 — a real,
disclosed first-pass pace (at the default ~30fps tick rate, one full
breathing cycle takes ~2*pi/0.05 ticks, roughly 4 seconds)."""


class HolographicSphereWidget(QWidget):
    """Owns the sphere's own paint logic and private animation phase.
    Never reads PresentationConfig/EmotionalState directly — every input
    arrives via set_target(), the same "renderer consumes, does not
    determine" discipline Sprint 5.6 established for Renderer itself."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._target_color = _DEFAULT_COLOR
        self._animation_speed = 1.0
        self._phase = 0.0
        self._tick_failure_logged = False

    def set_target(self, color: QColor, animation_speed: float) -> None:
        """Sets the next animation target. Takes effect on the very next
        tick's own phase advance — never an instant jump-cut (this
        sprint's own Expected Functions)."""
        self._target_color = color
        self._animation_speed = animation_speed

    def _on_tick(self) -> None:
        """Advance the breathing-pulse phase by one tick's worth,
        scaled by the current animation_speed multiplier
        (PresentationState.animation_speed, Sprint 5.5). Called by
        JarvisRenderer's own shared QTimer loop — never by set_target()/
        render_state() itself. Sprint 5.15 scenario (c): never raises —
        see this module's own "Per-tick exception guarding" docstring
        section."""
        try:
            self._phase = (self._phase + _BASE_PHASE_STEP * self._animation_speed) % (
                2 * math.pi
            )
            self.update()
        except Exception:
            if not self._tick_failure_logged:
                logger.exception(
                    "HolographicSphereWidget._on_tick() failed; retaining the last-painted "
                    "frame."
                )
                self._tick_failure_logged = True
            return
        self._tick_failure_logged = False

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        pulse = _MIN_PULSE_SCALE + (_MAX_PULSE_SCALE - _MIN_PULSE_SCALE) * (
            0.5 + 0.5 * math.sin(self._phase)
        )
        rect = self.rect()
        center = rect.center()
        base_radius = min(rect.width(), rect.height()) / 2.0
        radius = base_radius * pulse

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QRadialGradient(center, max(radius, 1.0))
        gradient.setColorAt(0.0, self._target_color.lighter(150))
        gradient.setColorAt(1.0, self._target_color.darker(150))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(center, radius, radius)
        painter.end()
