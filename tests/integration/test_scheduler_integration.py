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
