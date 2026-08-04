"""Wellness Tracker — decides *when* a wellness prompt should fire. See
docs/sprint_book/sprint_5/sprint_5_18.md.

**Independence from analytics/usage_tracker.py, a real, disclosed
decision**: Part 2 names Wellness Engine and Analytics Engine as sibling
top-level engines, not a dependency chain. WellnessTracker only needs to
know whether the user is currently present and active, not which
application they are using — so it reads raw, lightweight OS-level idle
time directly (win32api.GetLastInputInfo()/win32api.GetTickCount(),
already available via the locked pywin32 dependency) rather than
depending on Sprint 5.17's richer, per-application UsageTracker. This
keeps the two engines honestly decoupled, exactly as Part 2's own
architecture describes them.

**The Soft Wellness Rule ("Recommend. Never force.") is enforced
structurally, not just documented**: no method on this class can pause,
block, or lock any other subsystem, any voice session, or the UI — every
public method either returns a value (an evaluated WellnessPrompt | None)
or manages this class's own internal counter state. See
tests/unit/wellness/test_wellness_tracker.py's own AST-based import-
boundary test confirming this module imports nothing from voice/, ui/,
or device_control/.

**In-memory-only, no calendar-day boundary tracking**: _daily_active_
seconds means "cumulative active time since the last significant break,"
not "since local midnight" — a real, disclosed simplification (no Part 2
text names calendar-day-boundary handling), and a process restart loses
all of it (see this module's own sprint file Potential Risks). Each of
BREAK/HYDRATION/EYE_PROTECTION/OVERWORK tracks its own independent
"elapsed since last acknowledged/reset" baseline against the shared
_continuous_active_seconds (the first three) or _daily_active_seconds
(OVERWORK) accumulator, so acknowledge_prompt() can reset exactly one
trigger's own counter without disturbing the others. LATE_NIGHT has no
counter at all — it is a pure function of the current wall-clock hour
against the configured wrapping window, so acknowledge_prompt() is a
safe, documented no-op for it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import win32api

from config.schema import WellnessConfig
from core.logging_setup import get_logger
from emotion.state_manager import EmotionalStateManager
from scheduler.task_scheduler import TaskScheduler
from wellness.escalation import WellnessEscalationManager
from wellness.wellness_model import WellnessPrompt, WellnessTriggerType

logger = get_logger(__name__)

_JOB_ID = "wellness_tracker_idle_check"

# Continuous-active-time-driven triggers (compared against
# _continuous_active_seconds). OVERWORK is compared against
# _daily_active_seconds instead; LATE_NIGHT has no counter at all — see
# module docstring.
_CONTINUOUS_TRIGGERS: tuple[WellnessTriggerType, ...] = (
    WellnessTriggerType.BREAK,
    WellnessTriggerType.HYDRATION,
    WellnessTriggerType.EYE_PROTECTION,
)

_DEFAULT_MESSAGES: dict[WellnessTriggerType, str] = {
    WellnessTriggerType.BREAK: "You've been active for a while — consider taking a short break.",
    WellnessTriggerType.HYDRATION: "It might be a good time to drink some water.",
    WellnessTriggerType.EYE_PROTECTION: (
        "Consider looking at something 20 feet away for 20 seconds to rest your eyes."
    ),
    WellnessTriggerType.OVERWORK: (
        "You've been active for a long stretch — consider taking a longer break."
    ),
    WellnessTriggerType.LATE_NIGHT: (
        "It's getting late — you might want to consider wrapping up soon."
    ),
}


class WellnessTracker:
    """Constructor DI: (task_scheduler, wellness_config,
    emotional_state_manager=None, escalation_manager=None).
    emotional_state_manager is optional — a null EmotionalStateManager
    degrades evaluate_triggers() to the plain time-threshold check alone,
    never a hard failure. escalation_manager (Sprint 5.19) is likewise
    optional — a null WellnessEscalationManager degrades evaluate_
    triggers() to Sprint 5.18's own original behavior exactly (no hard-
    limit gating, escalation_level always 1, the plain default message),
    and _on_tick()'s own significant-inactivity branch simply skips the
    reset_all() call it would otherwise make."""

    def __init__(
        self,
        task_scheduler: TaskScheduler,
        wellness_config: WellnessConfig,
        emotional_state_manager: EmotionalStateManager | None = None,
        escalation_manager: WellnessEscalationManager | None = None,
    ) -> None:
        self._task_scheduler = task_scheduler
        self._config = wellness_config
        self._emotional_state_manager = emotional_state_manager
        self._escalation_manager = escalation_manager
        self._started = False
        self._continuous_active_seconds = 0.0
        self._daily_active_seconds = 0.0
        self._trigger_baseline: dict[WellnessTriggerType, float] = {
            WellnessTriggerType.BREAK: 0.0,
            WellnessTriggerType.HYDRATION: 0.0,
            WellnessTriggerType.EYE_PROTECTION: 0.0,
            WellnessTriggerType.OVERWORK: 0.0,
        }
        self._last_prompt: WellnessPrompt | None = None

    def start(self) -> None:
        self._task_scheduler.add_job(
            self._on_tick, self._config.idle_check_interval_seconds, _JOB_ID
        )
        self._started = True
        logger.info(
            "Wellness tracker started (idle_check_interval_seconds=%s).",
            self._config.idle_check_interval_seconds,
        )

    def stop(self) -> None:
        self._task_scheduler.remove_job(_JOB_ID)
        self._started = False
        logger.info("Wellness tracker stopped.")

    def health_check(self) -> bool:
        return self._started

    def evaluate_triggers(
        self,
        now: datetime | None = None,
        escalation_manager: WellnessEscalationManager | None = None,
        interval_overrides: dict[WellnessTriggerType, float] | None = None,
    ) -> WellnessPrompt | None:
        """A pure function of this tracker's own current counters plus
        wellness_config — deliberately callable directly in tests,
        independent of the timer. Checks each WellnessTriggerType in
        trigger_priority_order, returns the first whose own threshold is
        currently crossed AND not hard-limited, or None if none qualify.
        Never mutates any counter itself — only _on_tick()/
        acknowledge_prompt() do.

        escalation_manager defaults to whatever this tracker was
        constructed with (self._escalation_manager) — an explicit
        argument here overrides that for one call only, the same shape
        Persona.compose_reply()'s emotional_state/decision_trace
        parameters already established. A hard-limited trigger type is
        skipped entirely (never even considered a candidate, not merely
        suppressed after being chosen) so a lower-priority trigger can
        still fire in its place. When an escalation_manager is in play, a
        produced WellnessPrompt's escalation_level/message reflect its
        own current level for that trigger; with none supplied, this
        behaves identically to Sprint 5.18's own original behavior
        (escalation_level always 1, the plain default message).

        interval_overrides (Sprint 5.22 — Adaptive Wellness) is a plain
        per-trigger multiplier dict — this class has no idea it might come
        from wellness/adaptive_wellness.py's AdaptiveWellnessAdjuster
        (that adapter is the ONE file allowed to know both WellnessTracker
        and PatternStore exist; this class knows neither Learning nor
        Pattern Recognition exist at all). A trigger type absent from the
        dict, or interval_overrides itself absent/None, behaves exactly
        as Sprint 5.18/5.19 already specified — a strictly additive,
        backward-compatible change with no effect on LATE_NIGHT (which
        has no numeric interval for a multiplier to scale)."""
        now = now if now is not None else datetime.now(UTC)
        manager = escalation_manager if escalation_manager is not None else self._escalation_manager
        stress = self._current_stress()
        for trigger_name in self._config.trigger_priority_order:
            trigger_type = WellnessTriggerType(trigger_name)
            if manager is not None and manager.is_hard_limited(trigger_type):
                continue
            if not self._is_crossed(trigger_type, now, stress, interval_overrides):
                continue
            if manager is not None:
                escalation_level = manager.current_level(trigger_type)
                message = manager.message_for(trigger_type)
            else:
                escalation_level = 1
                message = _DEFAULT_MESSAGES[trigger_type]
            return WellnessPrompt(
                trigger_type=trigger_type,
                message=message,
                triggered_at=now,
                escalation_level=escalation_level,
            )
        return None

    def acknowledge_prompt(self, trigger_type: WellnessTriggerType) -> None:
        """Resets that trigger's own elapsed counter back to zero —
        deliberately separate from the tick-driven _continuous_active_
        seconds/_daily_active_seconds reset, since acknowledging a
        hydration reminder should not also reset the break timer.
        LATE_NIGHT has no counter (see module docstring) — acknowledging
        it is a safe, documented no-op."""
        if trigger_type is WellnessTriggerType.LATE_NIGHT:
            logger.debug("acknowledge_prompt(LATE_NIGHT): no counter to reset, no-op.")
            return
        if trigger_type is WellnessTriggerType.OVERWORK:
            self._trigger_baseline[trigger_type] = self._daily_active_seconds
        else:
            self._trigger_baseline[trigger_type] = self._continuous_active_seconds
        logger.info("Wellness prompt acknowledged: %s", trigger_type.value)

    def _sample_idle_seconds(self) -> float:
        last_input_tick = win32api.GetLastInputInfo()
        current_tick = win32api.GetTickCount()
        return max(0.0, (current_tick - last_input_tick) / 1000.0)

    def _on_tick(self) -> None:
        idle_seconds = self._sample_idle_seconds()
        if idle_seconds >= self._config.inactivity_reset_seconds:
            self._continuous_active_seconds = 0.0
            self._daily_active_seconds = 0.0
            self._trigger_baseline = dict.fromkeys(self._trigger_baseline, 0.0)
            if self._escalation_manager is not None:
                self._escalation_manager.reset_all()
            return
        self._continuous_active_seconds += self._config.idle_check_interval_seconds
        self._daily_active_seconds += self._config.idle_check_interval_seconds
        self._last_prompt = self.evaluate_triggers()

    def _current_stress(self) -> float | None:
        if self._emotional_state_manager is None:
            return None
        return self._emotional_state_manager.current_state().stress

    def _is_crossed(
        self,
        trigger_type: WellnessTriggerType,
        now: datetime,
        stress: float | None,
        interval_overrides: dict[WellnessTriggerType, float] | None,
    ) -> bool:
        if trigger_type is WellnessTriggerType.LATE_NIGHT:
            return self._is_late_night(now)
        override_multiplier = (
            interval_overrides.get(trigger_type, 1.0) if interval_overrides is not None else 1.0
        )
        if trigger_type is WellnessTriggerType.OVERWORK:
            threshold = self._effective_threshold(self._config.overwork_daily_seconds, stress)
            threshold *= override_multiplier
            elapsed = self._daily_active_seconds - self._trigger_baseline[trigger_type]
            return elapsed >= threshold
        base_thresholds = {
            WellnessTriggerType.BREAK: self._config.break_interval_seconds,
            WellnessTriggerType.HYDRATION: self._config.hydration_interval_seconds,
            WellnessTriggerType.EYE_PROTECTION: self._config.eye_protection_interval_seconds,
        }
        threshold = base_thresholds[trigger_type]
        if trigger_type is WellnessTriggerType.BREAK:
            threshold = self._effective_threshold(threshold, stress)
        threshold *= override_multiplier
        elapsed = self._continuous_active_seconds - self._trigger_baseline[trigger_type]
        return elapsed >= threshold

    def _effective_threshold(self, base_threshold: float, stress: float | None) -> float:
        """Shortens base_threshold by stress_sensitivity_factor when
        stress reads at or above high_stress_threshold — narrow, bounded,
        opt-in-by-default-zero (see WellnessConfig's own docstring)."""
        if stress is None or stress < self._config.high_stress_threshold:
            return base_threshold
        return base_threshold * (1.0 - self._config.stress_sensitivity_factor)

    def _is_late_night(self, now: datetime) -> bool:
        start = self._config.late_night_start_hour
        end = self._config.late_night_end_hour
        hour = now.hour
        if start > end:
            return hour >= start or hour < end
        return start <= hour < end
