"""ParticleFieldWidget (JARVIS Holographic HUD reskin, Phase 3).

A small, bounded ring of orbiting particles around Jarvis's holographic
core — the brief's own "orbital elements... tiny particles" requirement.
Same "target vs. animated phase" separation `HolographicSphereWidget`/
`SegmentedRingWidget` already established: `set_target()` sets what to
animate toward; a private, continuously-advancing per-particle angle is
stepped by `_on_tick()`.

**Particle count is deliberately NOT driven by `PresentationState.
particle_density` alone.** Jarvis's own locked identity
(`config/schema.py`'s `PresentationConfig.jarvis_particle_density_min/max`,
Sprint 5.5 — Level 5 Part A, frozen) pins that field to 0.0-0.05 —
structurally near-zero, "Minimal. Confident. No flashy cyberpunk
effects." Scaling this widget's particle count directly off that value
alone would make the hologram look broken/empty rather than "alive" for
the vast majority of Jarvis's real operating range — and widening that
locked, tested range would alter an already-frozen Level 5 design
decision this workstream has no standing to change unilaterally. Instead,
`target_count()` below adds `particle_density`'s own contribution on TOP
of a small, always-present `ambient_minimum` (a new, Phase-3-owned
config value — see `config/schema.py`'s `PresentationConfig` docstring)
— so the core always has a few slowly-orbiting particles regardless of
emotional state, with `particle_density` free to add visibly more during
a more emotionally engaged moment, never fewer than the ambient floor.

Bounded, pre-allocated particle pool (never grows/shrinks at runtime) —
section 25's "no unbounded particle lists" mandate: `max_particles`
particles are constructed once, at `__init__`; only how many of them are
currently *visible* (`_visible_count`) changes.
"""

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from core.logging_setup import get_logger
from presentation.animation_manager import DegradationLevel

logger = get_logger(__name__)

_DEFAULT_COLOR = QColor("#0A84FF")
_MIN_ORBIT_FRACTION = 1.05
_MAX_ORBIT_FRACTION = 1.3
"""Each particle orbits at a fixed radius, expressed as a fraction of
the CORE's own half-size (the ring's radius — see set_orbit_geometry()
below), not this widget's own rect. Orbiting at 1.05-1.3x that radius
keeps every particle clearly OUTSIDE the ring's edge, reading as
orbiting around the core rather than overlapping or hiding inside it —
found necessary by this phase's own real-screenshot verification: an
earlier version scaled off this widget's own rect while ALSO sizing that
rect to match the ring, which meant "outside the ring" was also "outside
this widget's own bounds" and got silently clipped by Qt. Decoupling the
orbit anchor from this widget's own geometry (JarvisRenderer's
`_HologramStage.add_orbit_layer()` gives this widget the full stage rect,
so nothing it draws is ever clipped) fixes that."""

_BASE_ANGULAR_STEP = 0.012
_PARTICLE_RADIUS_PX = 1.6


@dataclass
class _Particle:
    orbit_fraction: float
    angle: float
    angular_speed: float
    phase_offset: float

    def advance(self, animation_speed: float) -> None:
        self.angle = (self.angle + _BASE_ANGULAR_STEP * self.angular_speed * animation_speed) % (
            2 * math.pi
        )


def target_count(particle_density: float, ambient_minimum: int, max_particles: int) -> int:
    """See this module's own docstring for why ambient_minimum is a
    floor, not a scale — particle_density (0.0-1.0, structurally capped
    low for Jarvis) only ever adds on top of it."""
    density = max(0.0, min(1.0, particle_density))
    extra = round(density * max(0, max_particles - ambient_minimum))
    return min(max_particles, ambient_minimum + extra)


class ParticleFieldWidget(QWidget):
    """Constructor DI: max_particles (PresentationConfig) bounds the
    pre-allocated pool. A fixed random seed (not the process-global
    `random` module state) makes each particle's own orbit radius/speed/
    starting angle deterministic per widget instance — reproducible in
    tests, and avoids perturbing unrelated code's own use of the global
    random state (the same "don't touch shared global state you don't
    own" discipline this project's other tuned-default modules already
    follow)."""

    def __init__(self, max_particles: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        rng = random.Random(1337)
        self._particles = [
            _Particle(
                orbit_fraction=rng.uniform(_MIN_ORBIT_FRACTION, _MAX_ORBIT_FRACTION),
                angle=rng.uniform(0.0, 2 * math.pi),
                angular_speed=rng.uniform(0.4, 1.3),
                phase_offset=rng.uniform(0.0, 2 * math.pi),
            )
            for _ in range(max(0, max_particles))
        ]
        self._visible_count = 0
        self._ambient_minimum = 0
        self._color = _DEFAULT_COLOR
        self._animation_speed = 1.0
        self._orbit_center = QPointF(0.0, 0.0)
        self._orbit_half_size = 0.0
        self._degradation = DegradationLevel.NORMAL
        self._tick_failure_logged = False

    def set_target(self, color: QColor, particle_density: float, animation_speed: float) -> None:
        self._color = color
        self._animation_speed = animation_speed
        self._visible_count = self._apply_degradation(
            target_count(particle_density, self._ambient_minimum, len(self._particles))
        )

    def set_resource_degradation(self, level: DegradationLevel) -> None:
        """JARVIS Holographic HUD reskin, Phase 7 — section 25's own
        "reduce particle count... disable non-essential effects" levers,
        applied for real under genuine resource pressure (see
        presentation/animation_manager.py's own docstring for the full
        mechanism). Takes effect on the next set_target() call, the same
        "target vs. animated phase" separation this widget's own orbit
        motion already uses — never retroactively changes a count
        already being animated toward mid-frame."""
        self._degradation = level

    def _apply_degradation(self, count: int) -> int:
        if self._degradation is DegradationLevel.MINIMAL:
            return 0
        if self._degradation is DegradationLevel.REDUCED:
            return min(count, self._ambient_minimum)
        return count

    def set_ambient_minimum(self, ambient_minimum: int) -> None:
        """Set once at construction time by whoever builds this widget
        (JarvisRenderer) — a plain setter rather than a constructor
        parameter so `target_count()`'s own pure function stays testable
        in isolation without also constructing a full widget."""
        self._ambient_minimum = max(0, min(ambient_minimum, len(self._particles)))

    def set_orbit_geometry(self, center: QPointF, core_half_size: float) -> None:
        """Called by `_HologramStage` (presentation/jarvis_renderer.py)
        whenever the core's own on-screen center/size changes — decouples
        "where do particles orbit" from this widget's own rect (see this
        module's own docstring for why that separation is necessary)."""
        self._orbit_center = center
        self._orbit_half_size = max(0.0, core_half_size)

    def _on_tick(self) -> None:
        """Sprint 5.15's own per-tick exception-guarding discipline
        (see HolographicSphereWidget's identical pattern): a single bad
        tick is caught, logged once, and the last-good frame retained."""
        try:
            for particle in self._particles[: self._visible_count]:
                particle.advance(self._animation_speed)
            self.update()
        except Exception:
            if not self._tick_failure_logged:
                logger.exception(
                    "ParticleFieldWidget._on_tick() failed; retaining the last-painted frame."
                )
                self._tick_failure_logged = True
            return
        self._tick_failure_logged = False

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's own naming convention)
        if self._orbit_half_size <= 0 or self._visible_count <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for particle in self._particles[: self._visible_count]:
            radius = self._orbit_half_size * particle.orbit_fraction
            x = self._orbit_center.x() + math.cos(particle.angle) * radius
            y = self._orbit_center.y() + math.sin(particle.angle) * radius
            twinkle = 0.5 + 0.5 * math.sin(particle.angle * 2.0 + particle.phase_offset)
            color = QColor(self._color)
            color.setAlphaF(0.35 + 0.5 * twinkle)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x, y), _PARTICLE_RADIUS_PX, _PARTICLE_RADIUS_PX)
        painter.end()
