"""Integration tests for Level 6 Part A's real, end-to-end wiring (Sprint
6.13 — Autonomous Intelligence Integration) — the first live exercise of
`EngineSelection.PLANNING`/`EXPLANATION`, the propose/accept/run planning
flow through `PlanningEngine` -> `TaskGraph` -> `TaskGraphWorkflowAdapter`
-> the real, unmodified `WorkflowExecutor`, `_finalize_workflow_run()`'s
own `TaskGraph.mark_completed()`/`mark_failed()` -> `SelfEvaluator` wiring,
`ExplainabilityLayer`'s own live "why?" follow-up, `AdaptivePrioritizer`-
informed proactive dispatch, and `ProactiveAssistant`'s own real
`TaskScheduler` cadence.

Mirrors tests/integration/test_companion_intelligence_integration.py's own
established shape closely (Sprint 5.24's own identical "first live
exercise of a new Level's own wiring" precedent).
"""

from datetime import UTC, datetime, timedelta

from planning.planning_model import PlanningStatus
from scheduler.scheduler_model import ItemType, ScheduledItem

_TURN_TIMEOUT = 10.0


# --- Full plan: propose -> accept -> run -> evaluate --------------------------------------


def test_full_plan_propose_accept_run_evaluate_flow(
    pipeline_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Acceptance Criteria: "A full 'plan a goal -> review -> accept ->
    run -> evaluate' flow completes end-to-end through the real
    CoreManager graph, with a human-reviewable proposal step that is
    never silently auto-accepted." Asserts on the real, observable store
    state after each turn — never a fabricated "Done" reply, since a
    Task-Graph-derived SYSTEM_COMMAND/LAUNCH_APPLICATION step's own real
    dispatch outcome through the unmodified ActionRegistry/PermissionGate
    stack is honestly unpredictable here (already covered by
    tests/integration/test_action_engine_integration.py) — this test's
    own job is proving the WIRING, not re-proving device-control
    dispatch semantics.

    A real, concretely reproduced race found writing this test: the
    default fake planning_response's own task title ("Do the first
    concrete thing") classifies as SYSTEM_COMMAND (workflow/
    task_graph_adapter.py's own _classify(), no "open"/"launch" keyword
    match) — an unapproved command is HIGH risk, which makes the real,
    unmodified WorkflowExecutor request a genuine whole-workflow spoken
    confirmation before running anything at all. This test never drives
    a confirmation reply, so that prompt (not the eventual result) is
    what actually satisfies tts.spoken_event first, racing this test's
    own teardown against the confirmation's still-pending 2s timeout in
    the background. Using an "open ..." task title instead classifies as
    LAUNCH_APPLICATION (LOW risk, device_control/action_engine.py's own
    default risk table) — no confirmation gate, so WorkflowExecutor
    proceeds straight to a real (here, cleanly failing — "notepad" is
    not on this harness's own restricted allowlist) dispatch attempt,
    exactly the honest, unpredictable-only-in-outcome path this test's
    own docstring above already expects."""
    h = pipeline_harness
    h.llm_client.planning_response = (
        "MILESTONE: Get started\nTASK: open notepad | Launch the text editor | 5 minutes"
    )
    wait_for_active_capture(h.mic)

    # Turn 1: propose a fresh goal — never persisted before acceptance.
    h.stt.pending_transcripts.append("help me plan a small project")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    proposal_reply, _ = h.tts.speak_calls[0]
    assert "milestone" in proposal_reply.lower()
    assert h.task_graph_store.list_goals() == []

    # Turn 2: accept it — a real Human-First gate, not a formality.
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("yes")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    accepted_goals = h.task_graph_store.list_goals(status=PlanningStatus.ACCEPTED)
    assert len(accepted_goals) == 1
    goal = accepted_goals[0]
    # Only the Goal's own status is bumped to ACCEPTED — the real
    # enforcement point for the Human-First gate is _run_accepted_plan()'s
    # own goal.status check, not each Task's individually; a Task stays
    # PROPOSED (still "ready", per planning/task_graph.py's own
    # _NON_TERMINAL_STATUSES) until it actually runs.
    assert goal.milestones[0].tasks[0].status is PlanningStatus.PROPOSED

    # Turn 3: run it — real TaskGraphWorkflowAdapter -> the existing,
    # completely unmodified WorkflowExecutor.
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("run my plan")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)

    # _finalize_workflow_run() mechanically settled the originating
    # Task's own status (never left PROPOSED/ACCEPTED).
    updated_goal = h.task_graph_store.get_goal(goal.goal_id)
    task = updated_goal.milestones[0].tasks[0]
    assert task.status in (PlanningStatus.COMPLETED, PlanningStatus.ABANDONED)

    # A real SelfEvaluator.EvaluationRecord now exists for the workflow
    # run itself — but NOT one list_evaluations_for_goal(goal.goal_id)
    # can ever surface. SelfEvaluator.evaluate_workflow_run() (Sprint
    # 6.10) keys the record's subject_id on the WorkflowRunResult's own
    # run_id, while list_evaluations_for_goal()'s own query JOINs
    # evaluation_records.subject_id against tasks.task_id (planning/
    # task_graph_store.py's own docstring: "an evaluation of a
    # WorkflowRunResult is never returned by this method" — a real,
    # disclosed Sprint 6.10 scope limit, not a bug). Verified instead by
    # reading the raw table directly, the only honest way to observe it
    # from outside the store.
    rows = h.task_graph_store._sqlite_client.query(
        "SELECT subject_id, outcome FROM evaluation_records"
    )
    assert len(rows) == 1
    assert rows[0][0] != task.task_id

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


def test_rejecting_a_proposed_goal_discards_it(
    pipeline_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    h = pipeline_harness
    wait_for_active_capture(h.mic)

    h.stt.pending_transcripts.append("help me plan a small project")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)

    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("no")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)

    reply, _ = h.tts.speak_calls[1]
    # VoicePersonalityModulator.shape_pacing() (Sprint 5.11) may insert
    # "... " pacing pauses depending on the active presentation state's
    # own voice_warmth — normalized away here, the same
    # test_level2_acceptance.py's own established precedent.
    assert reply.replace("... ", "") == "Okay, I've discarded that plan."
    assert h.task_graph_store.list_goals() == []

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


# --- Explanation follow-up -----------------------------------------------------------------


def test_explanation_follow_up_after_a_planning_turn(
    pipeline_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Acceptance Criteria: "A 'why did you...?' follow-up question after
    a planning or workflow turn produces a real, sourced Explanation."
    The prior turn's own real DecisionTrace.reasoning_text (produced by
    decision/authority.py's own _build_reasoning() PLANNING branch) is
    what ExplainabilityLayer composes from — no fresh LLM call needed,
    the same "compose before calling the LLM again" discipline Sprint
    6.11 established."""
    h = pipeline_harness
    wait_for_active_capture(h.mic)

    h.stt.pending_transcripts.append("help me plan a small project")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)

    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("why did you say that")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)

    explanation_reply, _ = h.tts.speak_calls[1]
    assert explanation_reply
    assert explanation_reply != "I can't explain my reasoning right now."
    assert "planning" in explanation_reply.lower()

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


# --- Real ProactiveAssistant cadence -> AdaptivePrioritizer -> announcement ----------------


def test_real_upcoming_deadline_is_detected_and_announced_when_idle(
    fast_level6_part_a_harness, wait_until, wait_for_dormant
):
    """Acceptance Criteria: "ProactiveAssistant's own enqueued items are
    announced only when DORMANT and only when AdaptivePrioritizer
    resolves SURFACE_NOW, verified via real TaskScheduler cadence (not a
    synthetic direct call)." A real ScheduledItem is saved directly to
    CalendarStore (bypassing any detection heuristics, mirroring
    test_scheduler_integration.py's own _due_item() precedent) —
    ProactiveAssistant's own real, recurring _on_tick() (0.3s, via
    fast_level6_part_a_harness) is what discovers and enqueues it for
    real, through ContextEngine.build() -> _check_upcoming_deadline().
    IMPORTANT_ALERT always resolves SURFACE_NOW in AdaptivePrioritizer's
    own rules (decision/adaptive_prioritizer.py), so this exercises that
    real decision, not just a bare peek_next().

    Sprint 6.15 fix: MISSED_MEAL is wall-clock-hour-dependent (fires
    whenever "now" falls inside the default noon-to-2pm window and this
    fixture's own empty recent_applications never supplies a qualifying
    break) — a real, previously-unnoticed flake found while writing
    tests/system/test_level6_part_a_acceptance.py's own identical
    scenario. Unlike that system-level scenario (which drives
    ProactiveAssistant via a single, direct _on_tick() call after its own
    config is already poked), this test's whole point is real,
    fixture-setup-time-onward TaskScheduler recurrence (0.3s) — a config
    poke inside the test body cannot reliably win the race against a
    tick that already fired during fixture setup itself, before the test
    body's first statement even runs. Fixed by polling for the specific
    deadline reply instead of assuming it is necessarily the first
    speak() call — an earlier, unrelated MISSED_MEAL announcement is a
    real, tolerable possibility this test doesn't otherwise care about."""
    h = fast_level6_part_a_harness
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    h.wake_engine.match_on_call = 10**9

    deadline_item = ScheduledItem(
        item_id="deadline-1",
        item_type=ItemType.DEADLINE,
        title="Submit the report",
        scheduled_at=datetime.now(UTC) + timedelta(hours=1),
        created_at=datetime.now(UTC),
    )
    h.calendar_store.save(deadline_item)

    assert wait_until(
        lambda: any("Submit the report" in text for text, _ in h.tts.speak_calls),
        timeout=_TURN_TIMEOUT,
    ), "Upcoming-deadline prompt was never proactively announced."

    # The deadline item was genuinely popped (not left dangling in the
    # queue) — checked by content, not by queue-emptiness, since an
    # unrelated, independently wall-clock-triggered MISSED_MEAL item may
    # also legitimately be queued or already announced (see this test's
    # own docstring).
    queued = h.priority_queue_manager.peek_next()
    assert queued is None or getattr(queued.payload, "title", None) != "Submit the report"
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


def test_proactive_assistant_job_genuinely_recurs(
    fast_level6_part_a_harness, wait_until, wait_for_dormant
):
    """A real, recurring TaskScheduler job, not a one-shot — mirrors
    tests/integration/test_companion_intelligence_integration.py's own
    established job-recurrence proof shape. An overdue, incomplete
    ScheduledItem stays a real FORGOTTEN_REMINDER candidate on every tick
    indefinitely (unlike a deadline, which ages out of its own warning
    window), so a second real announcement — once trigger_cooldown_seconds
    (shortened here) has elapsed — is a genuine, non-flaky recurrence
    signal, not a one-shot artifact of fixture setup."""
    h = fast_level6_part_a_harness
    h.proactive_assistant._config.trigger_cooldown_seconds = 0.1
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    h.wake_engine.match_on_call = 10**9

    overdue_item = ScheduledItem(
        item_id="overdue-1",
        item_type=ItemType.EVENT,
        title="Call the dentist",
        scheduled_at=datetime.now(UTC) - timedelta(hours=1),
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    h.calendar_store.save(overdue_item)

    assert wait_until(
        lambda: len(h.tts.speak_calls) >= 1, timeout=_TURN_TIMEOUT
    ), "ProactiveAssistant's own job never fired at all."
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    assert wait_until(
        lambda: len(h.tts.speak_calls) >= 2, timeout=_TURN_TIMEOUT
    ), "ProactiveAssistant's own job did not genuinely recur a second time."


# --- Entire Level 6 Part A bundle absent: graceful degrade sweep --------------------------


def test_level6_part_a_absent_every_new_turn_type_degrades_honestly(
    pipeline_harness_without_level6_part_a, wait_for_active_capture, wait_for_dormant,
    push_utterance,
):
    """Acceptance Criteria: "With the entire Level 6 Part A module bundle
    absent (None), every pre-existing turn type (Level 1-5) continues to
    function exactly as before, and any Level-6-Part-A-shaped request
    degrades to an honest, spoken 'not currently available' — never a
    crash, never a silent no-op." """
    h = pipeline_harness_without_level6_part_a
    wait_for_active_capture(h.mic)

    h.stt.pending_transcripts.append("help me plan a small project")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    planning_reply, _ = h.tts.speak_calls[0]
    assert planning_reply.replace("... ", "") == "Planning isn't currently available."

    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("why did you say that")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    explanation_reply, _ = h.tts.speak_calls[1]
    assert explanation_reply.replace("... ", "") == "I can't explain my reasoning right now."

    # A pre-existing (Level 1-5) turn type still functions exactly as
    # before — Level 6 Part A's own absence never narrows anything else.
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("what time is it right now")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    conversational_reply, _ = h.tts.speak_calls[2]
    assert conversational_reply.replace("... ", "") == h.llm_client.conversational_response

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
