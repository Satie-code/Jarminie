"""Unit tests for wellness.wellness_tracker.

evaluate_triggers() is directly exercised against tracker-internal
counters set directly by each test — accumulating exact boundary values
via real ticks would be subject to floating-point drift, so this mirrors
presentation/gesture_engine.py's own "pure decision, precisely testable
at its own exact boundary" precedent. Tests that need a fixed wall-clock
time pass an explicit `now` to evaluate_triggers() rather than relying on
whatever time the suite happens to run at, so a real late-night test run
can never make an unrelated boundary test flaky.

start()/stop() are exercised against a REAL TaskScheduler, matching
tests/unit/analytics/test_usage_tracker.py's own established "real
collaborator, short interval, bounded poll-until wait" precedent
(Sprint 5.17) for the identical class of test.
"""

import ast
import os
import time
from datetime import UTC, datetime

import pytest

from config.schema import WellnessConfig
from scheduler.task_scheduler import TaskScheduler
from wellness.escalation import WellnessEscalationManager
from wellness.wellness_model import WellnessTriggerType
from wellness.wellness_tracker import WellnessTracker

_WAIT_TIMEOUT = 2.0
_DAY = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)


def _wait_until(predicate, timeout: float = _WAIT_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _isolated_config(**overrides) -> WellnessConfig:
    """A WellnessConfig with every continuous/daily threshold set far out
    of reach except whatever the caller overrides — isolates one trigger
    at a time regardless of trigger_priority_order's own default
    ordering."""
    base = {
        "break_interval_seconds": 1e9,
        "hydration_interval_seconds": 1e9,
        "eye_protection_interval_seconds": 1e9,
        "overwork_daily_seconds": 1e9,
    }
    base.update(overrides)
    return WellnessConfig(**base)


class _FakeState:
    def __init__(self, stress: float) -> None:
        self.stress = stress


class _FakeEmotionalStateManager:
    def __init__(self, stress: float) -> None:
        self._stress = stress

    def current_state(self) -> _FakeState:
        return _FakeState(self._stress)


@pytest.fixture
def task_scheduler():
    ts = TaskScheduler()
    ts.start()
    yield ts
    ts.stop()


@pytest.fixture
def tracker(task_scheduler) -> WellnessTracker:
    return WellnessTracker(task_scheduler, WellnessConfig())


# --- evaluate_triggers(): per-trigger threshold crossing, boundary exact -----------------


def test_break_fires_at_or_over_threshold_not_before(task_scheduler):
    config = _isolated_config(break_interval_seconds=100.0)
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 99.99

    assert tracker.evaluate_triggers(now=_DAY) is None

    tracker._continuous_active_seconds = 100.0
    prompt = tracker.evaluate_triggers(now=_DAY)

    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.BREAK


def test_hydration_fires_at_or_over_threshold_not_before(task_scheduler):
    config = _isolated_config(hydration_interval_seconds=100.0)
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 99.99

    assert tracker.evaluate_triggers(now=_DAY) is None

    tracker._continuous_active_seconds = 100.0
    prompt = tracker.evaluate_triggers(now=_DAY)

    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.HYDRATION


def test_eye_protection_fires_at_or_over_threshold_not_before(task_scheduler):
    config = _isolated_config(eye_protection_interval_seconds=100.0)
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 99.99

    assert tracker.evaluate_triggers(now=_DAY) is None

    tracker._continuous_active_seconds = 100.0
    prompt = tracker.evaluate_triggers(now=_DAY)

    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.EYE_PROTECTION


def test_overwork_fires_at_or_over_threshold_not_before(task_scheduler):
    config = _isolated_config(overwork_daily_seconds=100.0)
    tracker = WellnessTracker(task_scheduler, config)
    tracker._daily_active_seconds = 99.99

    assert tracker.evaluate_triggers(now=_DAY) is None

    tracker._daily_active_seconds = 100.0
    prompt = tracker.evaluate_triggers(now=_DAY)

    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.OVERWORK


def test_late_night_fires_inside_the_window_not_outside(tracker):
    inside = datetime(2026, 8, 4, 23, 30, tzinfo=UTC)
    outside = datetime(2026, 8, 4, 14, 0, tzinfo=UTC)

    prompt = tracker.evaluate_triggers(now=inside)
    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.LATE_NIGHT

    assert tracker.evaluate_triggers(now=outside) is None


# --- trigger_priority_order tie resolution ------------------------------------------------


def test_trigger_priority_order_resolves_a_simultaneous_crossing_tie_using_default_order(
    task_scheduler,
):
    config = WellnessConfig(
        break_interval_seconds=100.0,
        eye_protection_interval_seconds=100.0,
        hydration_interval_seconds=100.0,
        overwork_daily_seconds=100.0,
    )
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 200.0
    tracker._daily_active_seconds = 200.0

    prompt = tracker.evaluate_triggers(now=_DAY)

    assert prompt.trigger_type is WellnessTriggerType.BREAK


def test_trigger_priority_order_tie_resolution_is_config_driven(task_scheduler):
    config = WellnessConfig(
        break_interval_seconds=100.0,
        eye_protection_interval_seconds=100.0,
        hydration_interval_seconds=100.0,
        overwork_daily_seconds=100.0,
        trigger_priority_order=["hydration", "break", "eye_protection", "overwork", "late_night"],
    )
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 200.0

    prompt = tracker.evaluate_triggers(now=_DAY)

    assert prompt.trigger_type is WellnessTriggerType.HYDRATION


# --- late-night wrapping-window edges -----------------------------------------------------


def test_late_night_window_wraps_past_midnight_at_both_configured_edges(tracker):
    at_start_edge = datetime(2026, 8, 4, 23, 0, tzinfo=UTC)
    at_end_edge = datetime(2026, 8, 5, 4, 59, tzinfo=UTC)
    just_before_start = datetime(2026, 8, 4, 22, 59, tzinfo=UTC)
    at_end_boundary_exclusive = datetime(2026, 8, 5, 5, 0, tzinfo=UTC)

    start_prompt = tracker.evaluate_triggers(now=at_start_edge)
    end_prompt = tracker.evaluate_triggers(now=at_end_edge)
    assert start_prompt.trigger_type is WellnessTriggerType.LATE_NIGHT
    assert end_prompt.trigger_type is WellnessTriggerType.LATE_NIGHT
    assert tracker.evaluate_triggers(now=just_before_start) is None
    assert tracker.evaluate_triggers(now=at_end_boundary_exclusive) is None


def test_late_night_window_non_wrapping_when_start_before_end(task_scheduler):
    config = WellnessConfig(late_night_start_hour=1, late_night_end_hour=3)
    tracker = WellnessTracker(task_scheduler, config)

    assert tracker.evaluate_triggers(now=datetime(2026, 8, 4, 2, 0, tzinfo=UTC)) is not None
    assert tracker.evaluate_triggers(now=datetime(2026, 8, 4, 0, 59, tzinfo=UTC)) is None
    assert tracker.evaluate_triggers(now=datetime(2026, 8, 4, 3, 0, tzinfo=UTC)) is None


# --- significant-inactivity reset, including the counter-suppression consequence ---------


def test_on_tick_accumulates_continuous_and_daily_active_seconds(task_scheduler, monkeypatch):
    config = WellnessConfig(idle_check_interval_seconds=10.0)
    tracker = WellnessTracker(task_scheduler, config)
    monkeypatch.setattr(tracker, "_sample_idle_seconds", lambda: 0.0)

    tracker._on_tick()

    assert tracker._continuous_active_seconds == 10.0
    assert tracker._daily_active_seconds == 10.0


def test_on_tick_resets_counters_on_significant_inactivity_and_suppresses_pending_trigger(
    task_scheduler, monkeypatch
):
    config = _isolated_config(break_interval_seconds=5.0, idle_check_interval_seconds=10.0)
    tracker = WellnessTracker(task_scheduler, config)
    monkeypatch.setattr(tracker, "_sample_idle_seconds", lambda: 0.0)

    tracker._on_tick()
    assert tracker.evaluate_triggers(now=_DAY) is not None

    monkeypatch.setattr(
        tracker, "_sample_idle_seconds", lambda: config.inactivity_reset_seconds
    )
    tracker._on_tick()

    assert tracker._continuous_active_seconds == 0.0
    assert tracker._daily_active_seconds == 0.0
    assert tracker.evaluate_triggers(now=_DAY) is None


# --- acknowledge_prompt() per-trigger isolation -------------------------------------------


def test_acknowledge_prompt_resets_only_that_triggers_own_counter(task_scheduler):
    config = _isolated_config(break_interval_seconds=1000.0, hydration_interval_seconds=1000.0)
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 5000.0

    tracker.acknowledge_prompt(WellnessTriggerType.BREAK)
    prompt = tracker.evaluate_triggers(now=_DAY)

    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.HYDRATION


def test_acknowledge_prompt_overwork_resets_its_own_daily_baseline(task_scheduler):
    config = _isolated_config(overwork_daily_seconds=1000.0)
    tracker = WellnessTracker(task_scheduler, config)
    tracker._daily_active_seconds = 5000.0
    assert tracker.evaluate_triggers(now=_DAY).trigger_type is WellnessTriggerType.OVERWORK

    tracker.acknowledge_prompt(WellnessTriggerType.OVERWORK)

    assert tracker.evaluate_triggers(now=_DAY) is None


def test_acknowledge_prompt_late_night_is_a_safe_no_op(tracker):
    tracker.acknowledge_prompt(WellnessTriggerType.LATE_NIGHT)

    inside = datetime(2026, 8, 4, 23, 30, tzinfo=UTC)
    assert tracker.evaluate_triggers(now=inside) is not None


# --- emotional_state_manager present vs. absent -------------------------------------------


def test_evaluate_triggers_without_emotional_state_manager_never_raises(task_scheduler):
    config = _isolated_config(break_interval_seconds=100.0)
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 100.0

    prompt = tracker.evaluate_triggers(now=_DAY)

    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.BREAK


def test_evaluate_triggers_with_low_stress_does_not_shorten_the_threshold(task_scheduler):
    config = _isolated_config(break_interval_seconds=100.0, stress_sensitivity_factor=0.5)
    tracker = WellnessTracker(
        task_scheduler, config, emotional_state_manager=_FakeEmotionalStateManager(stress=10.0)
    )
    tracker._continuous_active_seconds = 90.0

    assert tracker.evaluate_triggers(now=_DAY) is None


def test_evaluate_triggers_with_high_stress_shortens_break_threshold(task_scheduler):
    config = _isolated_config(break_interval_seconds=100.0, stress_sensitivity_factor=0.5)
    tracker = WellnessTracker(
        task_scheduler, config, emotional_state_manager=_FakeEmotionalStateManager(stress=90.0)
    )
    tracker._continuous_active_seconds = 60.0

    prompt = tracker.evaluate_triggers(now=_DAY)

    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.BREAK


def test_evaluate_triggers_with_high_stress_shortens_overwork_threshold(task_scheduler):
    config = _isolated_config(overwork_daily_seconds=1000.0, stress_sensitivity_factor=0.5)
    tracker = WellnessTracker(
        task_scheduler, config, emotional_state_manager=_FakeEmotionalStateManager(stress=90.0)
    )
    tracker._daily_active_seconds = 600.0

    prompt = tracker.evaluate_triggers(now=_DAY)

    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.OVERWORK


# --- _sample_idle_seconds() against the real, live desktop -------------------------------


def test_sample_idle_seconds_against_the_real_live_desktop_never_raises(tracker):
    """A real, non-mocked smoke check — win32api.GetLastInputInfo()/
    GetTickCount() against whatever this machine's own real idle state
    actually is right now. Never asserts a specific value, only that it
    is a well-formed, non-negative float."""
    idle_seconds = tracker._sample_idle_seconds()

    assert isinstance(idle_seconds, float)
    assert idle_seconds >= 0.0


# --- start()/stop()/health_check() against a real TaskScheduler --------------------------


def test_health_check_false_before_start(tracker):
    assert tracker.health_check() is False


def test_health_check_true_after_start_false_after_stop(tracker):
    tracker.start()
    assert tracker.health_check() is True
    tracker.stop()
    assert tracker.health_check() is False


def test_start_registers_a_real_recurring_job_that_ticks(task_scheduler, monkeypatch):
    config = WellnessConfig(idle_check_interval_seconds=0.05)
    tracker = WellnessTracker(task_scheduler, config)
    monkeypatch.setattr(tracker, "_sample_idle_seconds", lambda: 0.0)

    tracker.start()
    try:
        assert _wait_until(lambda: tracker._continuous_active_seconds > 0.0)
    finally:
        tracker.stop()


def test_stop_removes_the_job_and_no_further_ticks_occur(task_scheduler, monkeypatch):
    config = WellnessConfig(idle_check_interval_seconds=0.05)
    tracker = WellnessTracker(task_scheduler, config)
    monkeypatch.setattr(tracker, "_sample_idle_seconds", lambda: 0.0)

    tracker.start()
    tracker.stop()
    accumulated_after_stop = tracker._continuous_active_seconds
    time.sleep(0.2)

    assert tracker._continuous_active_seconds == accumulated_after_stop


def test_a_raising_tick_does_not_stop_future_recurrence(task_scheduler, monkeypatch):
    """Sprint 6.17 (Async Background Task Audit) — one of the 12 jobs
    not yet individually verified against TaskScheduler's own explicit
    max_instances=1, mirroring Sprint 6.14's own established shape
    (proactive/test_proactive_assistant.py's test_a_raising_tick_does_
    not_stop_future_recurrence). _on_tick() has no try/except of its
    own around _sample_idle_seconds() (that method's own narrower
    pywintypes.error degrade is a different, already-covered scenario —
    see this file's own docstring), so forcing it to raise unconditionally
    produces a real, genuinely propagating exception."""
    config = WellnessConfig(idle_check_interval_seconds=0.05)
    tracker = WellnessTracker(task_scheduler, config)
    tick_count = 0

    def _raising_sample_idle_seconds():
        nonlocal tick_count
        tick_count += 1
        raise RuntimeError("_sample_idle_seconds() exploded")

    monkeypatch.setattr(tracker, "_sample_idle_seconds", _raising_sample_idle_seconds)

    tracker.start()
    try:
        assert _wait_until(lambda: tick_count >= 3)
        assert task_scheduler.health_check() is True
        assert tracker.health_check() is True
    finally:
        tracker.stop()


# --- escalation_manager wiring (Sprint 5.19) ------------------------------------------------


def test_evaluate_triggers_skips_a_hard_limited_trigger_and_falls_through_to_next_candidate(
    task_scheduler,
):
    config = WellnessConfig(
        break_interval_seconds=100.0,
        eye_protection_interval_seconds=1e9,
        hydration_interval_seconds=100.0,
        overwork_daily_seconds=1e9,
        max_postponements_before_hard_limit=1,
    )
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 200.0
    manager = WellnessEscalationManager(config)
    manager.register_postponed(WellnessTriggerType.BREAK)

    prompt = tracker.evaluate_triggers(now=_DAY, escalation_manager=manager)

    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.HYDRATION


def test_evaluate_triggers_returns_none_when_every_crossed_trigger_is_hard_limited(
    task_scheduler,
):
    config = WellnessConfig(
        break_interval_seconds=100.0,
        eye_protection_interval_seconds=1e9,
        hydration_interval_seconds=1e9,
        overwork_daily_seconds=1e9,
        max_postponements_before_hard_limit=1,
    )
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 200.0
    manager = WellnessEscalationManager(config)
    manager.register_postponed(WellnessTriggerType.BREAK)

    assert tracker.evaluate_triggers(now=_DAY, escalation_manager=manager) is None


def test_evaluate_triggers_reflects_the_escalation_managers_own_level_and_message(
    task_scheduler,
):
    config = _isolated_config(
        break_interval_seconds=100.0,
        max_postponements_before_hard_limit=10,
        escalation_message_templates={"break": ["one", "two", "three"]},
    )
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 100.0
    manager = WellnessEscalationManager(config)
    manager.register_postponed(WellnessTriggerType.BREAK)

    prompt = tracker.evaluate_triggers(now=_DAY, escalation_manager=manager)

    assert prompt.escalation_level == 2
    assert prompt.message == "two"


def test_evaluate_triggers_with_no_escalation_manager_matches_sprint_5_18_behavior(
    task_scheduler,
):
    """Regression: no escalation_manager (neither constructor-supplied
    nor call-time) behaves identically to Sprint 5.18's own original
    behavior — escalation_level always 1, the plain default message."""
    config = _isolated_config(break_interval_seconds=100.0)
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 100.0

    prompt = tracker.evaluate_triggers(now=_DAY)

    assert prompt is not None
    assert prompt.escalation_level == 1


def test_constructor_supplied_escalation_manager_is_used_by_default(task_scheduler):
    config = _isolated_config(break_interval_seconds=100.0, max_postponements_before_hard_limit=1)
    manager = WellnessEscalationManager(config)
    manager.register_postponed(WellnessTriggerType.BREAK)
    tracker = WellnessTracker(task_scheduler, config, escalation_manager=manager)
    tracker._continuous_active_seconds = 200.0

    assert tracker.evaluate_triggers(now=_DAY) is None


def test_call_time_escalation_manager_overrides_the_constructor_supplied_one(task_scheduler):
    config = _isolated_config(break_interval_seconds=100.0, max_postponements_before_hard_limit=1)
    constructor_manager = WellnessEscalationManager(config)
    constructor_manager.register_postponed(WellnessTriggerType.BREAK)
    tracker = WellnessTracker(task_scheduler, config, escalation_manager=constructor_manager)
    tracker._continuous_active_seconds = 200.0

    override_manager = WellnessEscalationManager(config)
    prompt = tracker.evaluate_triggers(now=_DAY, escalation_manager=override_manager)

    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.BREAK


def test_on_tick_significant_inactivity_calls_escalation_manager_reset_all(
    task_scheduler, monkeypatch
):
    config = WellnessConfig(idle_check_interval_seconds=10.0, max_postponements_before_hard_limit=1)
    manager = WellnessEscalationManager(config)
    manager.register_postponed(WellnessTriggerType.BREAK)
    assert manager.is_hard_limited(WellnessTriggerType.BREAK) is True
    tracker = WellnessTracker(task_scheduler, config, escalation_manager=manager)
    monkeypatch.setattr(tracker, "_sample_idle_seconds", lambda: config.inactivity_reset_seconds)

    tracker._on_tick()

    assert manager.is_hard_limited(WellnessTriggerType.BREAK) is False


def test_on_tick_without_escalation_manager_never_raises_on_significant_inactivity(
    task_scheduler, monkeypatch
):
    config = WellnessConfig(idle_check_interval_seconds=10.0)
    tracker = WellnessTracker(task_scheduler, config)
    monkeypatch.setattr(tracker, "_sample_idle_seconds", lambda: config.inactivity_reset_seconds)

    tracker._on_tick()

    assert tracker._continuous_active_seconds == 0.0


# --- interval_overrides (Sprint 5.22) ------------------------------------------------------


def test_evaluate_triggers_with_no_interval_overrides_matches_sprint_5_19_behavior(
    task_scheduler,
):
    config = _isolated_config(break_interval_seconds=100.0)
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 100.0

    prompt = tracker.evaluate_triggers(now=_DAY)

    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.BREAK


def test_interval_overrides_widens_the_effective_threshold(task_scheduler):
    config = _isolated_config(break_interval_seconds=100.0)
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 110.0

    assert tracker.evaluate_triggers(now=_DAY) is not None

    widened = tracker.evaluate_triggers(
        now=_DAY, interval_overrides={WellnessTriggerType.BREAK: 1.5}
    )
    assert widened is None


def test_interval_overrides_only_affects_the_named_trigger(task_scheduler):
    config = _isolated_config(break_interval_seconds=100.0, hydration_interval_seconds=100.0)
    tracker = WellnessTracker(task_scheduler, config)
    tracker._continuous_active_seconds = 110.0

    prompt = tracker.evaluate_triggers(
        now=_DAY, interval_overrides={WellnessTriggerType.BREAK: 2.0}
    )

    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.HYDRATION


def test_interval_overrides_does_not_affect_late_night(tracker):
    inside = datetime(2026, 8, 4, 23, 30, tzinfo=UTC)

    prompt = tracker.evaluate_triggers(
        now=inside, interval_overrides={WellnessTriggerType.LATE_NIGHT: 100.0}
    )

    assert prompt is not None
    assert prompt.trigger_type is WellnessTriggerType.LATE_NIGHT


def test_interval_overrides_applies_to_overwork(task_scheduler):
    config = _isolated_config(overwork_daily_seconds=100.0)
    tracker = WellnessTracker(task_scheduler, config)
    tracker._daily_active_seconds = 110.0

    assert tracker.evaluate_triggers(now=_DAY) is not None

    widened = tracker.evaluate_triggers(
        now=_DAY, interval_overrides={WellnessTriggerType.OVERWORK: 1.5}
    )
    assert widened is None


# --- static/AST: wellness/ imports nothing from voice/, ui/, device_control/ -------------


def test_wellness_package_import_boundaries():
    """AST-based, not a substring scan — the same precedent tests/unit/
    presentation/test_gesture_engine.py's own import-boundary check
    already established, so docstring prose (which legitimately names
    win32api/scheduler/emotion/learning to explain various independence
    decisions) is correctly not flagged, only real import statements are.

    Extended at Sprint 5.22 from a single-file check (wellness_tracker.py
    only) into a whole-package scan: every wellness/ module must still
    import nothing from voice/, ui/, or device_control/, and — new this
    sprint — nothing under wellness/ may import from learning/ EXCEPT
    wellness/adaptive_wellness.py, the one deliberate, disclosed exception
    bridging Wellness and Pattern Recognition (see that module's own
    docstring)."""
    wellness_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "wellness")
    forbidden_everywhere = ("voice", "ui", "device_control")
    allowed_learning_importer = "adaptive_wellness.py"

    for filename in sorted(os.listdir(wellness_dir)):
        if not filename.endswith(".py"):
            continue
        module_path = os.path.join(wellness_dir, filename)
        with open(module_path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=module_path)

        top_level_imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                top_level_imports.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level_imports.append(node.module.split(".")[0])

        for module_name in top_level_imports:
            assert module_name not in forbidden_everywhere, (filename, module_name)
            if module_name == "learning":
                assert filename == allowed_learning_importer, (filename, module_name)
