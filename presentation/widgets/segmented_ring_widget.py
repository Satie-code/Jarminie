"""SegmentedRingWidget (Sprint 5.7 — Level 5 Part A).

Jarvis's segmented ring: a fixed number of arc segments
(`PresentationConfig.jarvis_ring_segment_count`) whose lit-segment
fraction and rotation speed encode the current `RingState` — the exact
five states the brief names for this ring (`IDLE`/`LISTENING`/
`THINKING`/`SPEAKING`/`PROCESSING`).

**Target vs. animated phase, deliberately separate** — same discipline
as `HolographicSphereWidget`'s own docstring: `set_ring_state()` sets
what this widget should animate *toward*; the actual rotation *phase*
is a private, continuously-advancing float stepped by `_on_tick()`
(`JarvisRenderer`'s own shared `QTimer`), never by `set_ring_state()`/
`render_state()` itself.

**Honest limitation, not this widget's own**: this widget correctly
implements all five `RingState` values — the gap is one level up, in
`presentation/jarvis_renderer.py`'s own `_derive_ring_state()`, which
this sprint can only ever produce `IDLE`/`PROCESSING` from
`PresentationState` alone (see that module's own Architecture Notes).
Building this widget's own mapping completely now means Sprint 5.14's
real turn-phase wiring needs no further changes here.

**Gesture accent pulse (Sprint 5.9)**: `trigger_pulse()` gives
`JarvisRenderer.trigger_gesture()` real content — a brief brightening
of every segment (lit or not) for a config-driven number of ticks, then
a clean return to the ring's own normal `RingState`-driven appearance.
Deliberately independent of `_ring_state`/`_rotation_phase` (the same
"target vs. animated phase" separation this widget's own rotation
already uses) so a pulse never interrupts or resets whatever the ring
was already doing.
"""

import math
from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class RingState(Enum):
    """The exact five states the brief names for the segmented ring."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    PROCESSING = "processing"


_LIT_FRACTION: dict[RingState, float] = {
    RingState.IDLE: 0.15,
    RingState.LISTENING: 0.5,
    RingState.THINKING: 0.7,
    RingState.SPEAKING: 0.85,
    RingState.PROCESSING: 1.0,
}
_ROTATION_MULTIPLIER: dict[RingState, float] = {
    RingState.IDLE: 0.3,
    RingState.LISTENING: 0.6,
    RingState.THINKING: 1.2,
    RingState.SPEAKING: 0.8,
    RingState.PROCESSING: 1.5,
}
"""Per-RingState lit-segment fraction / rotation-speed multiplier — real,
disclosed, unvalidated first-pass numbers, same category as every other
Level 5 visual constant so far (e.g. HolographicSphereWidget's own pulse
range)."""

_BASE_ROTATION_STEP = 0.04
"""Radians the ring's own lit-segment starting position advances per
_on_tick() call at animation_speed=1.0 and a RingState multiplier of
1.0 — same "real, disclosed first-pass pace" category as
HolographicSphereWidget's own _BASE_PHASE_STEP."""

_DEFAULT_COLOR = QColor("#0A84FF")
_UNLIT_ALPHA = 40
"""Alpha (0-255) for an unlit segment — dim but not fully invisible, so
the ring's own full segment count always reads clearly regardless of
how many are currently lit."""

_PULSE_UNLIT_ALPHA = 120
_PULSE_LIT_BRIGHTEN_PERCENT = 140
"""Sprint 5.9 — trigger_pulse()'s own brightening: unlit segments get a
higher alpha than _UNLIT_ALPHA, lit segments get QColor.lighter()'d,
for the pulse's own configured duration. Real, disclosed, unvalidated
first-pass numbers, same category as every other Level 5 visual
constant so far."""


class SegmentedRingWidget(QWidget):
    """Constructor DI: segment_count comes from PresentationConfig
    (Sprint 5.5's own established pattern), never hardcoded."""

    def __init__(self, segment_count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._segment_count = segment_count
        self._ring_state = RingState.IDLE
        self._animation_speed = 1.0
        self._color = _DEFAULT_COLOR
        self._rotation_phase = 0.0
        self._pulse_ticks_remaining = 0

    def set_ring_state(self, ring_state: RingState, animation_speed: float) -> None:
        self._ring_state = ring_state
        self._animation_speed = animation_speed

    def set_color(self, color: QColor) -> None:
        self._color = color

    def trigger_pulse(self, duration_ticks: int) -> None:
        """Starts (or restarts, if already pulsing) a brief accent pulse
        lasting duration_ticks _on_tick() calls — Sprint 5.9's
        JarvisRenderer.trigger_gesture() own real content. Independent
        of ring_state/rotation_phase (see this module's own docstring).
        A non-positive duration_ticks is a safe no-op."""
        self._pulse_ticks_remaining = max(duration_ticks, 0)

    def _on_tick(self) -> None:
        multiplier = _ROTATION_MULTIPLIER[self._ring_state]
        step = _BASE_ROTATION_STEP * self._animation_speed * multiplier
        self._rotation_phase = (self._rotation_phase + step) % (2 * math.pi)
        if self._pulse_ticks_remaining > 0:
            self._pulse_ticks_remaining -= 1
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        rect = self.rect()
        center = rect.center()
        radius = min(rect.width(), rect.height()) / 2.0 - 2.0
        if radius <= 0:
            return

        lit_fraction = _LIT_FRACTION[self._ring_state]
        lit_count = round(self._segment_count * lit_fraction)
        segment_angle = 2 * math.pi / self._segment_count
        gap = segment_angle * 0.15  # a small visual gap between segments
        is_pulsing = self._pulse_ticks_remaining > 0

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for index in range(self._segment_count):
            start_angle = self._rotation_phase + index * segment_angle
            lit = index < lit_count
            color = QColor(self._color)
            if lit:
                if is_pulsing:
                    color = color.lighter(_PULSE_LIT_BRIGHTEN_PERCENT)
            else:
                color.setAlpha(_PULSE_UNLIT_ALPHA if is_pulsing else _UNLIT_ALPHA)
            pen = QPen(color)
            pen.setWidthF(max(radius * 0.12, 1.5))
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawArc(
                int(center.x() - radius),
                int(center.y() - radius),
                int(radius * 2),
                int(radius * 2),
                int(math.degrees(start_angle) * 16),
                int(math.degrees(segment_angle - gap) * 16),
            )
        painter.end()
