"""Integration tests for Sprint 5.25 (Error Handling & Recovery
Hardening, Part B — Companion Intelligence) — the six named scenarios
that specifically need the real, fully-wired Sprint 5.24 graph to
manifest at all (this sprint's own Engineering Rationale). Mirrors
tests/integration/test_presentation_layer_resilience.py's own Sprint
5.15 shape.

(a) UsageTracker._sample_foreground_window()'s own psutil race — already
    correctly handled at the unit level (tests/unit/analytics/
    test_usage_tracker.py, Sprint 5.17); this file adds the INTEGRATION-
    level confirmation through a real, registered TaskScheduler job.
(b) UsageStore/PatternStore read-path SQLite failure degrade (analytics/
    usage_store.py, learning/pattern_store.py — new this sprint).
(c) WellnessTracker._sample_idle_seconds()'s own win32api failure degrade
    (wellness/wellness_tracker.py — new this sprint).
(d) One job's exception never stops another's — confirmed already
    correct (TaskScheduler's own Sprint 4.15 per-job isolation), extended
    from test_scheduler_integration.py's own Sprint 4.19 five-job
    precedent to a real six-job graph.
(e) _announce_wellness()'s force-switch/announce/resume sequence
    (voice/pipeline.py — new this sprint's try/except/finally).
(f) _handle_wellness_turn()/RecommendationEngine.generate_recommendations()
    against a broken PatternStore/UsageStore — confirmed already correct
    through scenario (b)'s own hardening, exercised here through the
    real live-turn/TaskScheduler call sites specifically.
"""

import uuid
from datetime import UTC, datetime, timedelta

import psutil
import pytest
import pywintypes

from analytics.usage_tracker import UsageTracker
from decision.priority_queue import PriorityLevel
from learning.pattern_model import PatternType
from learning.pattern_recognizer import PatternRecognizer
from learning.recommendation import RecommendationEngine
from scheduler.reminder_engine import ReminderEngine
from scheduler.scheduler_model import ItemType, ScheduledItem
from voice.pipeline import CommunicationPipeline
from wellness.wellness_model import WellnessPrompt, WellnessTriggerType
from wellness.wellness_tracker import WellnessTracker

_TURN_TIMEOUT = 10.0


def _wellness_prompt(
    trigger_type: WellnessTriggerType = WellnessTriggerType.BREAK,
) -> WellnessPrompt:
    return WellnessPrompt(
        trigger_type=trigger_type,
        message="You've been active for a while — consider taking a short break.",
        triggered_at=datetime.now(UTC),
    )


# --- scenario (a): UsageTracker's own psutil race, via a real registered job ----------


def test_psutil_no_such_process_during_a_real_tick_records_no_sample_and_never_raises(
    fast_scheduler_harness, monkeypatch
):
    """Calls the real, registered _on_tick() directly (AnalyticsConfig's
    own 60s production default is too slow to wait out here — the same
    "call the job body directly" precedent test_scheduled_reminder_
    still_works_when_level5_part_b_is_unavailable already established),
    rather than waiting for TaskScheduler's own real timer — the thing
    under test is _on_tick()'s own exception handling, not recurrence
    (scenario (d) below already covers recurrence)."""
    h = fast_scheduler_harness
    monkeypatch.setattr(
        "analytics.usage_tracker.win32gui.GetForegroundWindow", lambda: 42
    )
    monkeypatch.setattr(
        "analytics.usage_tracker.win32process.GetWindowThreadProcessId",
        lambda hwnd: (0, 4242),
    )
    monkeypatch.setattr(
        "analytics.usage_tracker.win32gui.GetWindowText", lambda hwnd: "Some Window"
    )

    def _raise_no_such_process(pid):
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr("analytics.usage_tracker.psutil.Process", _raise_no_such_process)

    since = datetime.now(UTC) - timedelta(minutes=1)
    before = h.usage_store.list_samples_since(since)

    h.usage_tracker._on_tick()  # must not raise

    after = h.usage_store.list_samples_since(since)
    assert after == before, "A psutil.NoSuchProcess race must record no sample this tick."


def test_psutil_access_denied_during_a_real_tick_records_no_sample_and_never_raises(
    fast_scheduler_harness, monkeypatch
):
    h = fast_scheduler_harness
    monkeypatch.setattr(
        "analytics.usage_tracker.win32gui.GetForegroundWindow", lambda: 42
    )
    monkeypatch.setattr(
        "analytics.usage_tracker.win32process.GetWindowThreadProcessId",
        lambda hwnd: (0, 4242),
    )
    monkeypatch.setattr(
        "analytics.usage_tracker.win32gui.GetWindowText", lambda hwnd: "Some Window"
    )

    def _raise_access_denied(pid):
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr("analytics.usage_tracker.psutil.Process", _raise_access_denied)

    since = datetime.now(UTC) - timedelta(minutes=1)
    before = h.usage_store.list_samples_since(since)

    h.usage_tracker._on_tick()  # must not raise

    after = h.usage_store.list_samples_since(since)
    assert after == before, "A psutil.AccessDenied race must record no sample this tick."


def test_the_very_next_tick_after_a_psutil_race_records_normally(
    fast_scheduler_harness, monkeypatch
):
    """The race is a one-tick miss, not a lasting failure mode — the
    very next successful tick records a real sample."""
    h = fast_scheduler_harness
    monkeypatch.setattr(
        "analytics.usage_tracker.win32gui.GetForegroundWindow", lambda: 42
    )
    monkeypatch.setattr(
        "analytics.usage_tracker.win32process.GetWindowThreadProcessId",
        lambda hwnd: (0, 4242),
    )
    monkeypatch.setattr(
        "analytics.usage_tracker.win32gui.GetWindowText", lambda hwnd: "Some Window"
    )

    def _raise_no_such_process(pid):
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr("analytics.usage_tracker.psutil.Process", _raise_no_such_process)
    since = datetime.now(UTC) - timedelta(minutes=1)
    h.usage_tracker._on_tick()
    assert h.usage_store.list_samples_since(since) == []

    class _FakeProcess:
        def name(self) -> str:
            return "devenv.exe"

    monkeypatch.setattr(
        "analytics.usage_tracker.psutil.Process", lambda pid: _FakeProcess()
    )
    h.usage_tracker._on_tick()

    recorded = h.usage_store.list_samples_since(since)
    assert len(recorded) == 1
    assert recorded[0].process_name == "devenv.exe"


# --- scenario (b): UsageStore/PatternStore read-path SQLite failure -------------------


def test_usage_store_list_samples_since_degrades_to_empty_on_sqlite_failure(
    fast_scheduler_harness, monkeypatch
):
    h = fast_scheduler_harness

    def _raise(*args, **kwargs):
        raise Exception("simulated SQLite failure")

    monkeypatch.setattr(h.usage_store._sqlite_client, "query", _raise)

    since = datetime.now(UTC) - timedelta(days=1)
    assert h.usage_store.list_samples_since(since) == []
    assert h.usage_store.list_sessions_since(since) == []


def test_pattern_store_list_by_type_and_list_all_degrade_to_empty_on_sqlite_failure(
    fast_scheduler_harness, monkeypatch
):
    h = fast_scheduler_harness

    def _raise(*args, **kwargs):
        raise Exception("simulated SQLite failure")

    monkeypatch.setattr(h.pattern_store._sqlite_client, "query", _raise)

    assert h.pattern_store.list_by_type(PatternType.FREQUENT_APPLICATION) == []
    assert h.pattern_store.list_all() == []


# --- scenario (c): WellnessTracker's own win32api idle-check failure ------------------


def test_win32api_failure_degrades_a_tick_to_not_significantly_inactive(
    fast_scheduler_harness, monkeypatch
):
    h = fast_scheduler_harness
    tracker = h.wellness_tracker
    tracker._continuous_active_seconds = 10.0
    tracker._daily_active_seconds = 10.0

    def _raise():
        raise pywintypes.error(0, "GetLastInputInfo", "simulated failure")

    monkeypatch.setattr("wellness.wellness_tracker.win32api.GetLastInputInfo", _raise)

    assert tracker._sample_idle_seconds() == 0.0

    interval = tracker._config.idle_check_interval_seconds
    tracker._on_tick()  # must not raise, and must NOT reset the counters
    assert tracker._continuous_active_seconds == 10.0 + interval
    assert tracker._daily_active_seconds == 10.0 + interval


def test_win32api_failure_is_logged_once_per_streak_not_per_tick(
    fast_scheduler_harness, monkeypatch, caplog
):
    h = fast_scheduler_harness
    tracker = h.wellness_tracker

    def _raise():
        raise pywintypes.error(0, "GetLastInputInfo", "simulated failure")

    monkeypatch.setattr("wellness.wellness_tracker.win32api.GetLastInputInfo", _raise)

    with caplog.at_level("DEBUG", logger="wellness.wellness_tracker"):
        tracker._sample_idle_seconds()
        tracker._sample_idle_seconds()
        tracker._sample_idle_seconds()

    failure_logs = [r for r in caplog.records if "idle-time query failed" in r.message]
    assert len(failure_logs) == 1, "A repeated failure streak must log only once."


def test_win32api_recovery_resets_the_failure_streak_and_logs_once(
    fast_scheduler_harness, monkeypatch, caplog
):
    h = fast_scheduler_harness
    tracker = h.wellness_tracker

    def _raise():
        raise pywintypes.error(0, "GetLastInputInfo", "simulated failure")

    monkeypatch.setattr("wellness.wellness_tracker.win32api.GetLastInputInfo", _raise)
    tracker._sample_idle_seconds()
    assert tracker._win32_failure_active is True

    monkeypatch.setattr(
        "wellness.wellness_tracker.win32api.GetLastInputInfo", lambda: 0
    )
    monkeypatch.setattr(
        "wellness.wellness_tracker.win32api.GetTickCount", lambda: 5000
    )

    with caplog.at_level("DEBUG", logger="wellness.wellness_tracker"):
        idle_seconds = tracker._sample_idle_seconds()

    assert tracker._win32_failure_active is False
    assert idle_seconds == 5.0
    recovery_logs = [r for r in caplog.records if "recovered" in r.message]
    assert len(recovery_logs) == 1


# --- scenario (d): one job's exception never stops the other five real jobs -----------


@pytest.fixture
def six_job_failing_call_counts(monkeypatch):
    """Extends test_scheduler_integration.py's own Sprint 4.19
    one_job_failing_call_counts fixture (class-level counting-wrapper
    technique) from five real jobs to a real six-job graph: Level 5 Part
    B's own four new recurring jobs (UsageTracker, WellnessTracker,
    PatternRecognizer, RecommendationEngine) plus two pre-existing
    Sprint 4.18/5.24 jobs (ReminderEngine's own due-item poll,
    CommunicationPipeline's widened _check_and_announce_priority_item).
    UsageTracker._on_tick fails on EVERY call — unlike ActionAuditLog.
    purge_older_than's own "let the first call through" precedent,
    UsageTracker.start() never calls _on_tick() synchronously during its
    own startup, so there is no real first call that must succeed."""
    counts = {
        "usage_tracker": 0,
        "wellness_tracker": 0,
        "pattern_recognizer": 0,
        "recommendation_engine": 0,
        "reminder_engine": 0,
        "priority_item_announcement": 0,
    }

    original_wellness_tick = WellnessTracker._on_tick
    original_pattern_pass = PatternRecognizer.run_detection_pass
    original_recommend = RecommendationEngine.generate_recommendations
    original_reminder_poll = ReminderEngine._poll_due_items
    original_priority_check = CommunicationPipeline._check_and_announce_priority_item

    def always_failing_usage_tick(self):
        counts["usage_tracker"] += 1
        raise RuntimeError("simulated UsageTracker._on_tick failure")

    def counting_wellness_tick(self):
        counts["wellness_tracker"] += 1
        return original_wellness_tick(self)

    def counting_pattern_pass(self):
        counts["pattern_recognizer"] += 1
        return original_pattern_pass(self)

    def counting_recommend(self):
        counts["recommendation_engine"] += 1
        return original_recommend(self)

    def counting_reminder_poll(self):
        counts["reminder_engine"] += 1
        return original_reminder_poll(self)

    def counting_priority_check(self):
        counts["priority_item_announcement"] += 1
        return original_priority_check(self)

    monkeypatch.setattr(UsageTracker, "_on_tick", always_failing_usage_tick)
    monkeypatch.setattr(WellnessTracker, "_on_tick", counting_wellness_tick)
    monkeypatch.setattr(PatternRecognizer, "run_detection_pass", counting_pattern_pass)
    monkeypatch.setattr(RecommendationEngine, "generate_recommendations", counting_recommend)
    monkeypatch.setattr(ReminderEngine, "_poll_due_items", counting_reminder_poll)
    monkeypatch.setattr(
        CommunicationPipeline, "_check_and_announce_priority_item", counting_priority_check
    )

    return counts


def test_six_real_jobs_one_failing_repeatedly_never_stops_the_other_five(
    six_job_failing_call_counts, fast_level5_part_b_harness, wait_until
):
    """Re-verifies TaskScheduler's own Sprint 4.15 per-job isolation
    guarantee against the REAL, fully-wired Level 5 Part B six-job graph
    — APScheduler doesn't disable/remove a job after an exception, it
    just logs and retries on the job's own next tick, while the other
    five real jobs keep ticking normally alongside it on the same shared
    TaskScheduler."""
    _ = fast_level5_part_b_harness

    def _all_kept_ticking() -> bool:
        counts = six_job_failing_call_counts
        return counts["usage_tracker"] >= 2 and all(
            counts[name] >= 2
            for name in (
                "wellness_tracker",
                "pattern_recognizer",
                "recommendation_engine",
                "reminder_engine",
                "priority_item_announcement",
            )
        )

    assert wait_until(_all_kept_ticking, timeout=_TURN_TIMEOUT), (
        f"Not every job kept ticking despite UsageTracker's own repeated exception: "
        f"{six_job_failing_call_counts}"
    )


# --- scenario (e): _announce_wellness()'s force-switch/announce/resume sequence -------


def test_persona_select_raising_never_leaves_persona_manager_stuck_and_never_crashes(
    fast_scheduler_harness, monkeypatch, wait_for_dormant, wait_until
):
    """Waits for the REAL, already-registered TaskScheduler job to
    consume the item (rather than also calling
    _check_and_announce_priority_item() directly) — a Post-Sprint-Fix-
    worthy lesson learned writing this very test: fast_scheduler_harness's
    own background job (poll_interval_seconds=0.3) is already ticking
    concurrently, and APScheduler's own max_instances=1 only prevents
    that job from overlapping ITSELF; it has no idea about an
    out-of-band direct call racing it from the test's own thread. Only
    one caller (the real scheduled job) ever invokes the dispatcher
    here, eliminating that race entirely."""
    h = fast_scheduler_harness
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    h.wake_engine.match_on_call = 10**9
    assert h.persona_manager.active_persona().name == "jarvis"

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated PersonaManager.select() failure")

    monkeypatch.setattr(h.persona_manager, "select", _raise)

    prompt = _wellness_prompt()
    h.priority_queue_manager.enqueue(prompt, PriorityLevel.WELLNESS, source="test")

    assert wait_until(
        lambda: h.priority_queue_manager.peek_next() is None, timeout=_TURN_TIMEOUT
    ), "The item must still be popped, not left dangling to corrupt future polls."

    assert h.persona_manager.active_persona().name == "jarvis", (
        "select() itself failing must mean the switch was never attempted."
    )


def test_announce_step_raising_after_a_real_switch_still_resumes_the_previous_persona(
    fast_scheduler_harness, monkeypatch, wait_for_dormant, wait_until
):
    """A later step (the announcement itself) fails AFTER select()
    genuinely applied — the finally block must still call
    resume_previous(), proving PersonaManager is never left stuck on
    Minie. Waits for the real background job rather than also calling
    the dispatcher directly — see the previous test's own docstring for
    the race that direct-call approach genuinely produced.

    The wait predicate checks BOTH peek_next() is None AND active_
    persona() is back to jarvis, not queue-emptiness alone — pop_next()
    empties the queue BEFORE the handler even starts running, so a
    predicate checking only "queue empty" can observe the real, genuine
    transient window where select() has already applied (switched to
    minie) but the handler's own finally block hasn't yet called
    resume_previous() — a real, concretely reproduced flake found
    writing this very test, not a hypothetical one."""
    h = fast_scheduler_harness
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    h.wake_engine.match_on_call = 10**9
    assert h.persona_manager.active_persona().name == "jarvis"

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated QuietModeController.activate() failure")

    monkeypatch.setattr(h.quiet_mode_controller, "activate", _raise)

    prompt = _wellness_prompt(WellnessTriggerType.HYDRATION)
    h.priority_queue_manager.enqueue(prompt, PriorityLevel.WELLNESS, source="test")

    assert wait_until(
        lambda: h.priority_queue_manager.peek_next() is None
        and h.persona_manager.active_persona().name == "jarvis",
        timeout=_TURN_TIMEOUT,
    ), (
        "resume_previous() must have run in the finally block despite the "
        "announcement step itself raising."
    )


def test_a_wellness_announcement_failure_does_not_contaminate_a_later_reminder(
    fast_scheduler_harness, wait_for_dormant, wait_until
):
    """The spec's own explicit cross-source non-contamination requirement:
    a WELLNESS announcement failing must not affect a SCHEDULED_REMINDER
    queued behind it. Induces the failure, confirms PersonaManager
    recovered (previous test's own guarantee), then enqueues and
    processes a real SCHEDULED_REMINDER, confirming it announces
    normally through jarvis. Restores the real activate() explicitly
    before enqueueing the reminder, and — see the two tests above's own
    docstring — waits for the real background job to consume each item
    rather than also calling the dispatcher directly."""
    h = fast_scheduler_harness
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    h.wake_engine.match_on_call = 10**9

    original_activate = h.quiet_mode_controller.activate

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated QuietModeController.activate() failure")

    h.quiet_mode_controller.activate = _raise
    prompt = _wellness_prompt(WellnessTriggerType.EYE_PROTECTION)
    h.priority_queue_manager.enqueue(prompt, PriorityLevel.WELLNESS, source="test")

    # See test_announce_step_raising_after_a_real_switch_still_resumes_the_
    # previous_persona's own docstring: the predicate must wait for BOTH
    # queue-emptiness AND the persona actually settling back to jarvis,
    # not queue-emptiness alone (a real, concretely reproduced transient
    # race between pop_next() and the handler's own finally block).
    assert wait_until(
        lambda: h.priority_queue_manager.peek_next() is None
        and h.persona_manager.active_persona().name == "jarvis",
        timeout=_TURN_TIMEOUT,
    ), "The wellness item was never fully processed and resumed to jarvis."

    h.quiet_mode_controller.activate = original_activate

    now = datetime.now(UTC)
    item = ScheduledItem(
        item_id=str(uuid.uuid4()),
        item_type=ItemType.EVENT,
        title="check the oven",
        scheduled_at=now - timedelta(seconds=1),
        created_at=now,
    )
    h.priority_queue_manager.enqueue(item, PriorityLevel.SCHEDULED_REMINDER, source="test")

    assert wait_until(lambda: len(h.tts.speak_calls) >= 1, timeout=_TURN_TIMEOUT), (
        "Scheduled reminder was never announced after the wellness failure."
    )
    reply_text, _ = h.tts.speak_calls[-1]
    assert reply_text == "check the oven"

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


# --- scenario (f): live-turn/TaskScheduler regression confirmation through a broken store --


def test_live_wellness_turn_degrades_honestly_when_usage_store_sqlite_is_broken(
    pipeline_harness, monkeypatch, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Not the empty-data case Sprint 5.24's own test already covers — a
    genuine SQLite failure, proving _handle_wellness_turn() degrades
    honestly through scenario (b)'s own new UsageStore hardening rather
    than raising mid-turn."""
    h = pipeline_harness

    def _raise(*args, **kwargs):
        raise Exception("simulated SQLite failure")

    monkeypatch.setattr(h.usage_store._sqlite_client, "query", _raise)

    h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: wellness\nENTITIES: NONE\nREFERENCES_PAST: NO\nPERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    wait_for_active_capture(h.mic)
    h.stt.pending_transcripts.append("how am I doing today?")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text == "I don't have enough information about today yet."

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


def test_recommendation_generation_job_degrades_honestly_when_pattern_store_is_broken(
    fast_level5_part_b_harness, monkeypatch, wait_until
):
    """A real TaskScheduler-driven recommendation pass against a broken
    PatternStore — RecommendationEngine.generate_recommendations() reads
    pattern_store.list_all(), now hardened by scenario (b), so this job
    keeps ticking (never crashing, never enqueuing a fabricated
    GENERAL_SUGGESTION) despite every read failing."""
    h = fast_level5_part_b_harness

    def _raise(*args, **kwargs):
        raise Exception("simulated SQLite failure")

    monkeypatch.setattr(h.pattern_store._sqlite_client, "query", _raise)

    call_count = {"n": 0}
    original = RecommendationEngine.generate_recommendations

    def counting(self):
        call_count["n"] += 1
        return original(self)

    monkeypatch.setattr(RecommendationEngine, "generate_recommendations", counting)

    assert wait_until(lambda: call_count["n"] >= 2, timeout=_TURN_TIMEOUT), (
        "RecommendationEngine's own job never kept ticking against a broken PatternStore."
    )
    assert h.priority_queue_manager.peek_next() is None, (
        "A broken PatternStore must never produce a fabricated GENERAL_SUGGESTION."
    )
    assert h.pipeline.health_check() is True
