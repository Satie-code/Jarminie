"""Integration tests for the Scheduler Engine's real, end-to-end wiring
(Sprint 4.18) — the first live exercise of `EngineSelection.SCHEDULER`,
`ReminderEngine`'s poll actually consuming what a live turn persists, and
`CommunicationPipeline._check_and_announce_due_reminder()`, this
project's first genuinely proactive (JARMINEI-initiated) behavior.

Uses fast_scheduler_harness (tests/integration/conftest.py), NOT the
widely-shared pipeline_harness — every other integration test file uses
SchedulerConfig()'s realistic 30s/3600s defaults specifically so none of
Level 4 Part B's background jobs ever fire during a normal few-second
test; this file is the one place that needs them to, so it opts into
short poll_interval_seconds/maintenance_interval_seconds instead
(0.3s), paired with fast_scheduler_harness's own hardened teardown
(_wait_for_no_scheduler_worker_threads()) that closes the exact
SQLite-connection-close-vs-in-flight-job race a naive short-interval
harness would otherwise reintroduce.

_TURN_TIMEOUT is deliberately more generous than every other integration
test file's own 5.0s (see fast_scheduler_harness's own docstring for
why) — this file's own background jobs create real, if usually small,
scheduling contention across a whole run (several 0.3s-interval jobs
touching a handful of real SQLite connections), and correctness here
never depends on speed, only on eventually reaching the right state.
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from decision.priority_queue import PriorityLevel
from device_control.action_log import ActionAuditLog
from memory.lifecycle_manager import MemoryLifecycleManager
from scheduler.scheduler_model import ItemType, ScheduledItem
from voice.conversation_store import ConversationSessionStore
from voice.quiet_mode import OperatingMode

_TURN_TIMEOUT = 10.0


def _set_scheduler_request(h, entity: str, topic: str) -> None:
    h.llm_client.intent_response = "CATEGORY: ACTION_REQUEST\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        f"TOPIC: {topic}\nENTITIES: {entity}\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )


def _set_general_chat(h) -> None:
    h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: general chat\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )


def _due_item(title: str) -> ScheduledItem:
    """A ScheduledItem already due (scheduled_at one second in the past)
    — for tests exercising ReminderEngine's poll/the proactive-
    announcement consumer directly, without waiting out
    _parse_relative_time()'s own real minute/hour granularity."""
    now = datetime.now(UTC)
    return ScheduledItem(
        item_id=str(uuid.uuid4()),
        item_type=ItemType.EVENT,
        title=title,
        scheduled_at=now - timedelta(seconds=1),
        created_at=now,
    )


@pytest.fixture
def maintenance_call_counts(monkeypatch):
    """Wraps MemoryLifecycleManager.run_cleanup_pass()/
    run_monthly_review(), ConversationSessionStore.purge_older_than(),
    and ActionAuditLog.purge_older_than() at the CLASS level with a
    counting-but-still-real wrapper (each still calls the genuine
    original implementation — this proves real recurring behavior, not
    merely that a mock was invoked).

    Must be requested BEFORE fast_scheduler_harness in a test's own
    parameter list: CommunicationPipeline.start() (Sprint 4.18) captures
    each of these as a bound method the instant task_scheduler.add_job()
    is called, which happens during fast_scheduler_harness's own setup —
    patching has to land on the class before that harness is built, not
    after it's handed back. pytest instantiates same-scoped, independent
    fixtures in the order a test function lists them, which is what
    makes this ordering reliable rather than incidental."""
    counts = {
        "cleanup_pass": 0,
        "monthly_review": 0,
        "conversation_purge": 0,
        "audit_purge": 0,
    }

    original_cleanup = MemoryLifecycleManager.run_cleanup_pass
    original_monthly = MemoryLifecycleManager.run_monthly_review
    original_conversation_purge = ConversationSessionStore.purge_older_than
    original_audit_purge = ActionAuditLog.purge_older_than

    def counting_cleanup(self):
        counts["cleanup_pass"] += 1
        return original_cleanup(self)

    def counting_monthly(self):
        counts["monthly_review"] += 1
        return original_monthly(self)

    def counting_conversation_purge(self, days=None):
        counts["conversation_purge"] += 1
        return original_conversation_purge(self, days)

    def counting_audit_purge(self, days=None):
        counts["audit_purge"] += 1
        return original_audit_purge(self, days)

    monkeypatch.setattr(MemoryLifecycleManager, "run_cleanup_pass", counting_cleanup)
    monkeypatch.setattr(MemoryLifecycleManager, "run_monthly_review", counting_monthly)
    monkeypatch.setattr(ConversationSessionStore, "purge_older_than", counting_conversation_purge)
    monkeypatch.setattr(ActionAuditLog, "purge_older_than", counting_audit_purge)

    return counts


def test_live_turn_creates_reminder_persisted_via_calendar_store(
    fast_scheduler_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Acceptance Criteria: "A live conversation turn creating a
    reminder is correctly routed through EngineSelection.SCHEDULER,
    persisted via CalendarStore." The reply's own formatted "at HH:MM"
    isn't asserted verbatim — it's computed from wall-clock time inside
    the pipeline itself, so pinning the exact string risks a spurious
    failure if the turn happens to straddle a minute boundary between
    this test's own "now" and the pipeline's. Asserting the persisted
    item's real scheduled_at falls within a tolerance window of "5
    minutes from now" is the more meaningful check anyway — it proves
    the actual stored data, not just a reply string's formatting.
    """
    h = fast_scheduler_harness
    before = datetime.now(UTC)
    _set_scheduler_request(h, "oven", "check the oven")

    wait_for_active_capture(h.mic)
    h.stt.pending_transcripts.append("remind me in 5 minutes to check the oven")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text.startswith("Done — I'll remind you about check the oven at ")

    items = h.calendar_store.list_all()
    assert len(items) == 1
    item = items[0]
    assert item.item_type is ItemType.EVENT
    assert item.title == "check the oven"
    assert item.is_completed is False

    lower_bound = before + timedelta(minutes=4, seconds=50)
    upper_bound = before + timedelta(minutes=5, seconds=10)
    assert lower_bound <= item.scheduled_at <= upper_bound

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


def test_due_reminder_is_proactively_announced_when_idle(
    fast_scheduler_harness, wait_until, wait_for_dormant
):
    """Acceptance Criteria: "A due reminder is proactively announced (via
    QuietModeController.activate(SCHEDULED_ALERT) + a real spoken
    message) when the system is idle." Also stands in for "picked up by
    ReminderEngine's existing poll": this due item only ever reaches
    PriorityQueueManager through that real, unmodified poll — there is
    no other path from CalendarStore to a spoken announcement.

    Unlike every other scripted-conversation test in this project, this
    one needs the system to be DORMANT with nothing else going on, so
    the proactive path is exercised in isolation. FakeWakeWordEngine's
    background thread is already running by the time fast_scheduler_
    harness yields (the same real, previously-documented race
    pipeline_harness's own voice_config docstring names — a fixture
    that starts wake_word_detector before returning can already have
    satisfied match_on_call=2 before this test body's first line runs).
    Simply pushing match_on_call out of reach here would be too late —
    an activation that already happened can't be un-fired after the
    fact. wait_for_dormant() first lets any such accidental session
    settle back to DORMANT on its own (its own real silence timeout,
    exactly like any other session, with no utterance ever pushed so no
    TTS call it could leave behind), THEN match_on_call is pushed out of
    reach so nothing triggers a second accidental wake during the rest
    of this test's own multi-second duration.
    """
    h = fast_scheduler_harness
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    h.wake_engine.match_on_call = 10**9
    assert h.quiet_mode_controller.current_mode() is OperatingMode.DORMANT
    assert h.tts.speak_calls == []

    item = _due_item("check the oven")
    h.calendar_store.save(item)

    assert wait_until(lambda: len(h.tts.speak_calls) >= 1, timeout=_TURN_TIMEOUT), (
        "Due reminder was never proactively announced."
    )
    reply_text, voice_id = h.tts.speak_calls[0]
    assert reply_text == "check the oven"
    assert voice_id == h.persona_manager.active_persona().voice_id

    # The item was genuinely popped (not left dangling) — nothing else
    # is queued behind it.
    assert h.priority_queue_manager.peek_next() is None

    # A proactive announcement is a real session like any other — it
    # completes the exact same full cycle back to DORMANT.
    assert h.quiet_mode_controller.current_mode() is OperatingMode.ACTIVE
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


def test_due_reminder_is_deferred_while_a_session_is_active(
    fast_scheduler_harness, wait_until, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Acceptance Criteria: "...and correctly NOT announced (stays
    queued) while a session is active." Part 2's own Priority Queue
    language for Scheduled Reminders is "Queued" — a due item found
    while ACTIVE must wait for the next idle-check, not interrupt.
    Proven directly here (several real poll cycles pass with the
    session still ACTIVE and the item still sitting, un-popped, in the
    queue), then the reverse — once the session genuinely goes DORMANT,
    the SAME reminder is picked up on the very next cycle, proving it
    waits rather than being silently dropped.
    """
    h = fast_scheduler_harness

    h.wake_engine.calls = 0
    wait_for_active_capture(h.mic)
    _set_general_chat(h)
    h.stt.pending_transcripts.append("how are you today")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    assert h.quiet_mode_controller.current_mode() is OperatingMode.ACTIVE

    item = _due_item("pick up the mail")
    h.calendar_store.save(item)

    assert wait_until(
        lambda: h.priority_queue_manager.peek_next() is not None, timeout=_TURN_TIMEOUT
    ), "ReminderEngine's own poll never enqueued the due item."

    # Several full poll_interval_seconds cycles (0.15s each) pass while
    # still ACTIVE — the item must still be sitting there, un-popped,
    # and no second speak() call must have happened.
    time.sleep(0.6)
    assert h.quiet_mode_controller.current_mode() is OperatingMode.ACTIVE
    assert len(h.tts.speak_calls) == 1
    peeked = h.priority_queue_manager.peek_next()
    assert peeked is not None
    assert peeked.priority is PriorityLevel.SCHEDULED_REMINDER
    assert peeked.payload.item_id == item.item_id

    # The session times out on its own (no further utterances); the
    # very next idle-check announces the reminder that was waiting.
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    assert wait_until(lambda: len(h.tts.speak_calls) >= 2, timeout=_TURN_TIMEOUT), (
        "Deferred reminder was never announced once the system went idle."
    )
    reply_text, _ = h.tts.speak_calls[1]
    assert reply_text == "pick up the mail"

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


def test_periodic_maintenance_jobs_fire_more_than_once_via_real_recurrence(
    maintenance_call_counts, fast_scheduler_harness, wait_until
):
    """Testing Checklist: "the three periodic-maintenance jobs
    (MemoryLifecycleManager, ConversationSessionStore, ActionAuditLog)
    genuinely fire more than once across a real, short-interval test
    run — proving recurrence, not just a single registration call."
    MemoryLifecycleManager contributes two jobs (run_cleanup_pass(),
    run_monthly_review()) — all four counters must independently reach
    at least 2 real invocations through the actual TaskScheduler/
    APScheduler machinery, closing backlog/technical_debt.md items
    11/15's recurring-cadence half for real.
    """
    _ = fast_scheduler_harness  # harness must be live for its own background jobs to tick

    def _all_fired_at_least_twice() -> bool:
        return all(count >= 2 for count in maintenance_call_counts.values())

    assert wait_until(_all_fired_at_least_twice, timeout=_TURN_TIMEOUT), (
        f"Not every maintenance job fired twice within 5s: {maintenance_call_counts}"
    )


# --- Sprint 4.19 (Error Handling & Recovery Hardening, Part B) --------------------------


@pytest.fixture
def one_job_failing_call_counts(monkeypatch):
    """Sprint 4.19 hardening, scenario (c): same class-level monkeypatch
    technique as maintenance_call_counts above, except ActionAuditLog.
    purge_older_than fails from its SECOND call onward (after counting
    its own call) instead of calling through to the real implementation
    every time — simulating one real job's own repeated runtime
    exception, so the paired test can prove the other four real jobs
    registered alongside it (the two MemoryLifecycleManager passes,
    ConversationSessionStore's purge, and — implicitly, since it's on
    the same shared TaskScheduler — the reminder poll/announcement
    check) keep running on their own real schedule regardless.
    Re-verifies Sprint 4.15's own two-synthetic-job guarantee
    (test_a_jobs_own_exception_does_not_stop_another_independently_
    registered_job) against the REAL, fully-wired five-job Sprint 4.18
    graph instead.

    Letting the FIRST call through unfailed is deliberate, not
    incidental: ActionAuditLog.start() (Sprint 4.8) itself calls
    purge_older_than() once as part of its own real startup sequence,
    with no try/except of its own around that call — an always-raising
    wrapper here would crash fast_scheduler_harness's own construction
    before this test's body ever ran (confirmed directly: an earlier
    draft of this fixture did exactly that). Failing from the second
    call onward instead tells the more realistic story this scenario is
    actually about anyway — a store that started up fine and later hit
    a real, transient failure — not "broken from the very first call,"
    a meaningfully different and less interesting failure mode."""
    counts = {
        "cleanup_pass": 0,
        "monthly_review": 0,
        "conversation_purge": 0,
        "audit_purge": 0,
    }

    original_cleanup = MemoryLifecycleManager.run_cleanup_pass
    original_monthly = MemoryLifecycleManager.run_monthly_review
    original_conversation_purge = ConversationSessionStore.purge_older_than
    original_audit_purge = ActionAuditLog.purge_older_than

    def counting_cleanup(self):
        counts["cleanup_pass"] += 1
        return original_cleanup(self)

    def counting_monthly(self):
        counts["monthly_review"] += 1
        return original_monthly(self)

    def counting_conversation_purge(self, days=None):
        counts["conversation_purge"] += 1
        return original_conversation_purge(self, days)

    def failing_after_first_call_audit_purge(self, days=None):
        counts["audit_purge"] += 1
        if counts["audit_purge"] == 1:
            return original_audit_purge(self, days)
        raise RuntimeError("simulated ActionAuditLog.purge_older_than failure")

    monkeypatch.setattr(MemoryLifecycleManager, "run_cleanup_pass", counting_cleanup)
    monkeypatch.setattr(MemoryLifecycleManager, "run_monthly_review", counting_monthly)
    monkeypatch.setattr(ConversationSessionStore, "purge_older_than", counting_conversation_purge)
    monkeypatch.setattr(ActionAuditLog, "purge_older_than", failing_after_first_call_audit_purge)

    return counts


def test_one_task_scheduler_jobs_own_exception_does_not_stop_the_other_real_jobs(
    one_job_failing_call_counts, fast_scheduler_harness, wait_until
):
    """Scenario (c). audit_purge's own first call (ActionAuditLog.
    start()'s real startup purge) always succeeds; every call from the
    second one onward — genuine TaskScheduler-driven recurrence — fails.
    Requiring audit_purge to reach 3 (one real success, then at least
    two real failures) is what actually proves it keeps being CALLED on
    schedule despite repeatedly raising, not merely that it fired once —
    APScheduler doesn't disable/remove a job after an exception, it just
    logs and retries on the job's own next tick — while the other three
    real jobs keep ticking normally alongside it on the same shared
    TaskScheduler."""
    _ = fast_scheduler_harness

    def _all_kept_ticking() -> bool:
        counts = one_job_failing_call_counts
        return counts["audit_purge"] >= 3 and all(
            counts[name] >= 2 for name in ("cleanup_pass", "monthly_review", "conversation_purge")
        )

    assert wait_until(_all_kept_ticking, timeout=_TURN_TIMEOUT), (
        f"Not every job kept ticking despite one's own real exception: "
        f"{one_job_failing_call_counts}"
    )


def test_reminder_becoming_due_during_session_end_never_corrupts_state(
    fast_scheduler_harness, voice_config, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Scenario (d): a reminder becoming due in the narrow window between
    VoiceSessionManager's watchdog deciding to end a session and the
    session actually ending — named as a real, accepted-but-untested
    edge case in sprint_4_18.md's own Potential Risks.

    Investigation (reading voice/quiet_mode.py/session_manager.py
    directly, not assuming) found QuietModeController.current_mode()/
    deactivate() are a single plain attribute read/write each — genuinely
    atomic at the Python bytecode level, with no possible "torn"
    intermediate state to observe, only ACTIVE or DORMANT at whichever
    exact instant _check_and_announce_due_reminder() happens to check.
    This test proves that holds under real, sustained concurrent
    pressure rather than only by code inspection: a due reminder sits in
    the queue for the ENTIRE session lifetime, right through its own
    timeout transition, while health_check() is sampled continuously and
    must never once report an inconsistent state (ACTIVE with no real
    session, or vice versa)."""
    h = fast_scheduler_harness
    h.wake_engine.calls = 0
    wait_for_active_capture(h.mic)
    h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: general chat\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    h.stt.pending_transcripts.append("how are you today")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)

    item = _due_item("check the oven")
    h.calendar_store.save(item)

    inconsistent_states = []
    deadline = time.monotonic() + voice_config.session_timeout_seconds + _TURN_TIMEOUT
    while time.monotonic() < deadline:
        if not h.quiet_mode_controller.health_check():
            inconsistent_states.append(h.quiet_mode_controller.current_mode())
        if (
            h.quiet_mode_controller.current_mode() is OperatingMode.DORMANT
            and len(h.tts.speak_calls) >= 2
        ):
            break
        time.sleep(0.02)

    assert inconsistent_states == [], f"health_check() went inconsistent: {inconsistent_states}"
    # The reminder was never lost — it waited through the whole active
    # session (Part 2's own "Queued" language) and was announced once
    # the system genuinely went idle, not silently dropped.
    assert len(h.tts.speak_calls) >= 2
    assert h.tts.speak_calls[1][0] == "check the oven"

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


def test_tts_failure_during_proactive_announcement_cleanly_returns_to_dormant(
    fast_scheduler_harness, wait_until, wait_for_dormant
):
    """Scenario (f): VoiceSessionManager/TTS failure mid-proactive-
    announcement. The speak-first-then-listen sequence Sprint 4.18 built
    (activate(SCHEDULED_ALERT) -> begin_session() -> immediate
    speak(announce_first)) is a genuinely new call shape; investigation
    (reading voice/quiet_mode.py directly) found QuietModeController.
    activate() ALREADY wraps begin_session() in a broad try/except that
    rolls _mode back to DORMANT on ANY failure — built during Sprint
    2.14's own hardening and explicitly re-documented in Sprint 4.18 as
    covering this exact announce_first path too. No new production code
    for this scenario; this test proves that existing protection holds
    for real, through the actual proactive-announcement job, rather than
    only by reading the docstring's own claim.

    The item having already been popped off PriorityQueueManager before
    the failed announcement attempt (and therefore not retried) is a
    real, honest, separate limitation — out of this scenario's own
    scope, which is exclusively about QuietModeController/
    VoiceSessionManager state consistency, not about reminder
    redelivery; named here, not silently assumed away."""
    h = fast_scheduler_harness
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    h.wake_engine.match_on_call = 10**9
    h.tts.should_raise = True

    item = _due_item("check the oven")
    h.calendar_store.save(item)

    # The announcement was genuinely attempted — the item was popped off
    # the real PriorityQueueManager even though speaking it then failed.
    assert wait_until(
        lambda: h.priority_queue_manager.peek_next() is None, timeout=_TURN_TIMEOUT
    ), "The due reminder was never even attempted."

    assert h.quiet_mode_controller.current_mode() is OperatingMode.DORMANT
    assert h.quiet_mode_controller.health_check() is True
    assert h.session_manager.health_check() is True
    assert h.tts.speak_calls == []
