"""Level 4 Part B — Scheduler & Internet Agent formal Acceptance Pass
(Sprint 4.20), closing Level 4 (Productivity) as a whole.

One continuous scripted scenario spanning BOTH Part A and Part B
capability through the real, complete Level 1-4 `CoreManager` graph —
`v0.4`'s own definition ("Complete productivity assistant") spans both
parts, and this is the first sprint with the standing and the full,
fully-composed graph to actually confirm that together. Part A coverage
here is deliberately REPRESENTATIVE (one device-control action, one
workflow run), not exhaustive — Sprint 4.13's own `test_level4_part_a_
acceptance.py` already exhaustively covers file operations, window
management, command execution, recycle-bin recovery, and workflow
confirmation semantics in detail; re-deriving all of that a second time
here would add no new coverage while slowing this already-composite
suite, per this sprint's own Engineering Rationale.

Uses fast_scheduler_app_harness (tests/system/conftest.py), NOT the
widely-shared app_harness — every other tests/system/ file uses
SchedulerConfig()'s realistic 30s/3600s defaults specifically so none of
Level 4 Part B's background jobs ever fire during a normal test; this
file is the one place that needs them to, so it opts into short
poll_interval_seconds/maintenance_interval_seconds instead (0.3s),
through the real, complete CoreManager graph (see that fixture's own
docstring for why this is now safe even with CoreManager's plain
reverse-registration-order shutdown, verified directly rather than
assumed).

**Reminder creation vs. reminder announcement are deliberately split**,
not chained into one 60+-second wait: `_parse_relative_time()` (voice/
pipeline.py) only resolves "in N minutes"/"in N hours" phrasing — no
sub-minute granularity exists — so a reminder actually CREATED via a
live turn is always genuinely ~1+ minute out. Waiting a real 60+ seconds
inside an already-composite system test to observe it become due would
be an honest but needlessly slow way to prove "genuinely announced when
due while idle" — the identical capability is already proven, fast and
for real, by directly persisting a second, already-due ScheduledItem
(the same `_due_item()`-shaped technique tests/integration/test_
scheduler_integration.py already established at Sprint 4.18/4.19) and
observing ReminderEngine's own real poll -> the real proactive-
announcement job pick it up. The live-turn-created reminder still proves
"created via a live turn" for real; the directly-persisted one proves
"genuinely announced when due" for real; between them, both halves of
this sprint's own Objectives are covered, just not needlessly serialized
into one slow wait.

**Sprint 4.19 hardening re-confirmation** (Objective 3), following the
same judgment Sprint 3.14/4.13 both already applied to their own six
scenarios: scenarios (a) SearchClient failure, (b) LanguageModelClient
failure, and (c) TaskScheduler job isolation are NOT re-tested as
dedicated functions here — (a)/(b) are purely component-level (Research
Engine/Summarizer's own degrade behavior has no CoreManager-dependent
behavior at all, already proven for real through a full live turn at
Sprint 4.19's own integration tests) and (c)'s own job-isolation
guarantee comes from APScheduler itself, not from anything CoreManager
adds; this file's own maintenance-recurrence check below already
re-confirms real jobs keep firing through the complete graph as a
natural side effect of Testing Checklist item 3, without needing a
second, artificial induced-failure repeat. Scenario (d) (the reminder/
session-transition race) is naturally re-exercised by this scenario's
own reminder-announcement step (a real session ending, a real idle
transition) without needing a dedicated adversarial function. Scenarios
(e) (CalendarStore SQLite failure) and (f) (TTS failure mid-proactive-
announcement) ARE genuinely composition-dependent (real interaction with
the full, multi-store, multi-job graph) and are re-confirmed below as
dedicated functions, mirroring test_level4_part_a_acceptance.py's own
precedent for its own three "genuinely benefits" scenarios.

The one remaining Acceptance Criterion — a supervised, real-machine,
human-observed verification pass (a real spoken research question
producing a sensible cited answer; a real scheduled reminder genuinely
spoken aloud at the right time, unprompted, while the system is idle) —
is explicitly NOT performed by this automated suite, matching every
prior Level-freeze sprint's own precedent of naming a manual step rather
than silently assuming it happened; see this sprint's own completion
report.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from device_control.action_engine import ActionContext, ActionType
from device_control.action_log import ActionAuditLog
from internet.search_provider import SearchResult
from memory.lifecycle_manager import MemoryLifecycleManager
from scheduler.scheduler_model import ItemType, ScheduledItem
from voice.conversation_store import ConversationSessionStore
from voice.quiet_mode import OperatingMode
from voice.text_to_speech import TextToSpeechError
from workflow.workflow_model import WorkflowDefinition, WorkflowStep

_TURN_TIMEOUT = 10.0
"""More generous than every other tests/system/ file's own 5.0s — this
file's own background jobs create real, if usually small, scheduling
contention across a whole run, matching tests/integration/test_
scheduler_integration.py's own identical reasoning."""


def _reset_wake_detection(h) -> None:
    """See test_level3_acceptance.py's/test_level4_part_a_acceptance.py's
    own identical copy of this helper for the full rationale (a real,
    previously-reproduced timing race, Sprint 3.12)."""
    h.wake_engine.calls = 0


def _due_item(title: str) -> ScheduledItem:
    """A ScheduledItem already due (scheduled_at one second in the past)
    — see this module's own docstring for why reminder creation and
    reminder announcement are tested via two separate items rather than
    one slow end-to-end wait."""
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
    """Same class-level monkeypatch technique as tests/integration/
    test_scheduler_integration.py's own identical fixture — see that
    file's own docstring for the full rationale (must be requested
    BEFORE fast_scheduler_app_harness in a test's own parameter list,
    since CommunicationPipeline.start() captures each as a bound method
    the instant task_scheduler.add_job() runs during harness setup)."""
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


def test_level4_part_b_full_acceptance_scenario(
    maintenance_call_counts,
    fast_scheduler_app_harness,
    wait_for_active_capture,
    wait_for_dormant,
    push_utterance,
    wait_until,
    tmp_path,
):
    h = fast_scheduler_app_harness

    # --- 1. Representative Part A: a live voice turn routes to
    # DEVICE_CONTROL and genuinely launches hostname.exe. -----------------
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)
    h.llm_client.intent_response = "CATEGORY: ACTION_REQUEST\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: launch an application\nENTITIES: hostname\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    h.stt.pending_transcripts.append("open hostname")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text == "Done — I've opened hostname.exe."
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    # --- 2. Representative Part A: a simple, low-risk workflow (no
    # confirmation needed — well under large_workflow_step_threshold,
    # no HIGH-risk step) run directly, the same "direct call, not a
    # second live voice turn" reasoning test_level4_part_a_acceptance.py
    # already established (voice-triggered workflow routing is already
    # proven at tests/integration/test_workflow_integration.py). --------
    workflow_folder = str(tmp_path / "wf_folder")
    definition = WorkflowDefinition(
        workflow_id="wf-part-b-acceptance",
        name="Representative Setup",
        steps=[
            WorkflowStep(
                step_index=0,
                action_type=ActionType.FOLDER_CREATE,
                parameters={"path": workflow_folder},
                description="Create the working folder",
            ),
            WorkflowStep(
                step_index=1,
                action_type=ActionType.LAUNCH_APPLICATION,
                parameters={"operation": "launch", "executable_path": "hostname.exe"},
                description="Launch hostname",
            ),
        ],
        created_by="test",
        created_at=datetime.now(UTC),
        is_enabled=True,
    )
    h.workflow_store.save(definition)
    workflow_context = ActionContext(requested_by="acceptance_test")
    workflow_result = h.workflow_executor.run("wf-part-b-acceptance", workflow_context)
    assert workflow_result.aborted_early is False
    assert all(
        r.action_result.status.value == "succeeded" for r in workflow_result.step_results
    )

    # --- 3. Part B: a scheduled reminder created via a real live voice
    # turn (SCHEDULER routing), persisted for real via CalendarStore. ----
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)
    h.llm_client.intent_response = "CATEGORY: ACTION_REQUEST\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: check the oven\nENTITIES: oven\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("remind me in 5 minutes to check the oven")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    reply_text, _ = h.tts.speak_calls[-1]
    assert reply_text.startswith("Done — I'll remind you about check the oven at ")
    saved_items = h.calendar_store.list_all()
    assert any(item.title == "check the oven" for item in saved_items)
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    # --- 4. Part B: a SECOND, already-due reminder is genuinely,
    # proactively announced while idle — see this module's own docstring
    # for why this is a separate item from step 3's live-turn creation. -
    speak_calls_before_announcement = len(h.tts.speak_calls)
    due_item = _due_item("pick up the dry cleaning")
    h.calendar_store.save(due_item)
    assert wait_until(
        lambda: len(h.tts.speak_calls) > speak_calls_before_announcement, timeout=_TURN_TIMEOUT
    ), "The due reminder was never proactively announced."
    announced_text, _ = h.tts.speak_calls[speak_calls_before_announcement]
    assert announced_text == "pick up the dry cleaning"
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    # --- 5. Part B: a live research query, routed through
    # EngineSelection.INTERNET_AGENT, produces a real cited summary
    # (network faked at the SearchProvider boundary — a real, opt-in
    # network pass is tests/system/test_level4_part_b_real_
    # verification.py's own separate job, per this sprint's own
    # Potential Risks). --------------------------------------------------
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)
    h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: JARMINEI project news\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    h.fake_search_provider.queued_results = [
        SearchResult(
            title="JARMINEI Project Overview",
            url="https://example.com/jarminei",
            snippet="JARMINEI is a modular, privacy-conscious voice assistant project.",
            retrieved_at=datetime.now(UTC),
        )
    ]
    h.llm_client.summary_response = "JARMINEI is a modular voice assistant project."
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("what's the latest news on the jarminei project")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    reply_text, _ = h.tts.speak_calls[-1]
    assert reply_text.startswith("JARMINEI is a modular voice assistant project.")
    assert "1 source(s)" in reply_text
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    # --- 6. The three periodic-maintenance passes each genuinely fire
    # more than once within this test's own bounded window, through the
    # real, complete CoreManager graph — not just registered once. ------
    def _all_fired_at_least_twice() -> bool:
        return all(count >= 2 for count in maintenance_call_counts.values())

    assert wait_until(_all_fired_at_least_twice, timeout=_TURN_TIMEOUT), (
        f"Not every maintenance job fired twice within the test's own bounded "
        f"window: {maintenance_call_counts}"
    )

    # --- Every Level 1-4 (Part A + Part B) module is registered and
    # running through the real, complete CoreManager graph. -------------
    states = h.core_manager.module_states()
    assert set(states) == {
        "task_scheduler",
        "calendar_store",
        "microphone",
        "speech_to_text",
        "text_to_speech",
        "conversation_store",
        "persona_manager",
        "voice_session_manager",
        "quiet_mode_controller",
        "wake_word_detector",
        "communication_pipeline",
        "memory_store",
        "memory_lifecycle_manager",
        "intent_detector",
        "context_analyzer",
        "priority_queue_manager",
        "authority_evaluator",
        "action_audit_log",
        "workflow_store",
        "emotion_detection_engine",
        "emotional_state_manager",
        "presentation_controller",
        # Sprint 5.24 (Level 5 Part B — Companion Intelligence).
        "usage_store",
        "usage_tracker",
        "pattern_store",
        "pattern_recognizer",
        "wellness_tracker",
        # Sprint 6.13 (Level 6 Part A — Autonomous Intelligence).
        "task_graph_store",
        "knowledge_graph_store",
        "proactive_assistant",
    }
    assert all(state == "running" for state in states.values())


# --- Sprint 4.19 hardening scenarios (e)/(f), re-confirmed at the system
# level -- see this module's own docstring for why (a)/(b)/(c)/(d) are not
# re-tested a third time as dedicated functions here. ----------------------


def test_calendar_store_sqlite_failure_degrades_gracefully_through_the_full_graph(
    app_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Scenario (e), system level: a real CalendarStore SQLite failure
    degrades gracefully at both real call sites, through the real,
    fully-wired Level 1-4 CoreManager graph — not just CalendarStore or
    ReminderEngine in isolation (tests/unit/scheduler/test_calendar_
    store.py, tests/unit/scheduler/test_reminder_engine.py) or a
    hand-assembled pipeline_harness (tests/integration/conftest.py).
    Uses the plain (slow-interval) app_harness — this scenario doesn't
    need real recurrence, only a single real poll/turn to reach each
    call site."""
    h = app_harness

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated CalendarStore SQLite failure")

    # ReminderEngine's own poll call site: must not raise.
    original_query = h.calendar_store._sqlite_client.query
    h.calendar_store._sqlite_client.query = _raise
    try:
        h.reminder_engine._poll_due_items()
    finally:
        h.calendar_store._sqlite_client.query = original_query

    # CommunicationPipeline._handle_scheduler_turn()'s own call site:
    # degrades to an honest reply instead of a false "Done" claim or a
    # silent session-ending no-reply.
    original_save = h.calendar_store.save
    h.calendar_store.save = _raise
    try:
        _reset_wake_detection(h)
        wait_for_active_capture(h.mic)
        h.llm_client.intent_response = "CATEGORY: ACTION_REQUEST\nCONFIDENCE: 0.9"
        h.llm_client.context_response = (
            "TOPIC: call mom\nENTITIES: mom\nREFERENCES_PAST: NO\n"
            "PERSONA: NONE\nSENTIMENT: NEUTRAL"
        )
        h.stt.pending_transcripts.append("remind me to call mom in 20 minutes")
        push_utterance(h.audio_backend)

        assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
        reply_text, _ = h.tts.speak_calls[-1]
        expected = "I'm sorry, I couldn't save that reminder right now."
        assert reply_text.replace("... ", "") == expected
    finally:
        h.calendar_store.save = original_save
        wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


def test_tts_failure_during_proactive_announcement_cleanly_returns_to_dormant(
    fast_scheduler_app_harness, wait_until, wait_for_dormant
):
    """Scenario (f), system level: a real induced TTS failure during the
    proactive-announcement job's own speak-first-then-listen sequence
    cleanly rolls QuietModeController back to DORMANT, through the real,
    fully-wired Level 1-4 CoreManager graph — re-confirming tests/
    integration/test_scheduler_integration.py's own identical finding
    (QuietModeController.activate()'s existing broad try/except already
    handles this) now holds when the complete graph, not just Level 4
    Part B's own pieces, is running."""
    h = fast_scheduler_app_harness
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    h.wake_engine.match_on_call = 10**9

    original_speak = h.tts.speak

    def _raise(text, voice_id):
        raise TextToSpeechError("simulated TTS failure during proactive announcement")

    h.tts.speak = _raise

    item = _due_item("check the oven")
    h.calendar_store.save(item)

    assert wait_until(
        lambda: h.priority_queue_manager.peek_next() is None, timeout=_TURN_TIMEOUT
    ), "The due reminder was never even attempted."

    h.tts.speak = original_speak
    assert h.quiet_mode_controller.current_mode() is OperatingMode.DORMANT
    assert h.quiet_mode_controller.health_check() is True
    assert h.session_manager.health_check() is True
