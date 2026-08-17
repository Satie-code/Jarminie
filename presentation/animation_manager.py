"""AnimationManager — JARVIS Holographic HUD reskin, Phase 7.

The brief's own "centralized animation system" (section 23) and
"resource-aware rendering" (section 25) requirements, resolved together
since they're two views of the same seam: this class classifies each
`ResourceSnapshot` `ui/jarvis/metrics_adapter.py`'s `MetricsAdapter`
already samples (Phase 5 — no NEW polling of its own; this class
subscribes to `MetricsAdapter.resources_updated` instead) into a
`DegradationLevel`. Animated widgets that opt in (today:
`JarvisRenderer`, via `apply_resource_degradation()`) scale down their
own particle count/tick interval under real pressure — "reduce particle
count... reduce refresh rate... disable non-essential effects," the
brief's own named levers, applied for real rather than only documented
as an intention.

**A deliberately narrow, disclosed scope**: this does NOT merge
`JarvisRenderer`'s/`VoiceVisualizer`'s own already-justified independent
`QTimer`s into one shared clock. Both already run at their own natural,
distinct cadence for a clear reason (a ~30fps hologram tick vs a 60ms
voice pulse vs `TopBar`'s 1Hz clock vs the 3s-default CoreManager-backed
panels) — this HUD has roughly seven `QTimer`s total, not "hundreds,"
and forcibly unifying cadences that differ by two orders of magnitude
would either waste CPU (fast things ticking needlessly slowly) or waste
more CPU (slow things ticking needlessly fast) — the opposite of section
25's own goal. Instead, this follows the same "opt-in resource-
sensitivity flag" precedent `scheduler/task_scheduler.py`'s own
`TaskScheduler.resource_sensitive` mechanism (Sprint 6.19) already
established for an equivalent problem in this codebase — a real,
already-proven pattern here, not a new idiom invented for this phase.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, Signal

from config.schema import ResourceThresholds
from core.logging_setup import get_logger
from core.resource_monitor import ResourceMonitor, ResourceSnapshot

logger = get_logger(__name__)


class DegradationLevel(Enum):
    NORMAL = "normal"
    REDUCED = "reduced"
    MINIMAL = "minimal"


class AnimationManager(QObject):
    """Constructor DI: (resource_thresholds,) — internally holds its own
    `ResourceMonitor(resource_thresholds)` purely to reuse
    `breached_resources()`/`critical_alerts()`'s own already-tested
    classification logic, never to sample on its own (see this module's
    own docstring: every `ResourceSnapshot` it classifies arrives via
    `on_resources_updated()`, pushed by `MetricsAdapter`'s own existing
    poll)."""

    level_changed = Signal(object)

    def __init__(
        self, resource_thresholds: ResourceThresholds, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._resource_monitor = ResourceMonitor(resource_thresholds)
        self._level = DegradationLevel.NORMAL

    def current_level(self) -> DegradationLevel:
        return self._level

    def on_resources_updated(self, snapshot: ResourceSnapshot) -> None:
        """The real, live entry point — connected to `MetricsAdapter`'s
        own `resources_updated` signal. Fail Gracefully: a
        classification failure keeps the last-known level rather than
        raising into whatever emitted the signal. `level_changed` only
        fires on an actual change, so a subscriber never redoes the same
        degradation work every single tick."""
        try:
            if self._resource_monitor.critical_alerts(snapshot):
                new_level = DegradationLevel.MINIMAL
            elif self._resource_monitor.breached_resources(snapshot):
                new_level = DegradationLevel.REDUCED
            else:
                new_level = DegradationLevel.NORMAL
        except Exception:
            logger.exception(
                "AnimationManager failed to classify a resource snapshot; keeping last level."
            )
            return

        if new_level is not self._level:
            self._level = new_level
            logger.info("Animation degradation level changed: %s.", new_level.value)
            self.level_changed.emit(new_level)
