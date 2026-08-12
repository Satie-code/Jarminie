"""Level 6 Part A — Autonomous Intelligence & Cognitive Architecture formal
Acceptance Pass (Sprint 6.15), closing Level 6 Part A. Mirrors Sprint
2.14/3.14/4.13/4.20/5.16/5.26's own identical closing role for their own
Levels/Parts.

One continuous scripted scenario (`test_level6_part_a_full_acceptance_
scenario` below) through the real, complete Level 1-6 Part A `CoreManager`
graph (`app_harness`, tests/system/conftest.py — the same harness every
other tests/system/ acceptance file already uses, now also carrying every
Level 6 Part A object). Covers, in order: a real goal proposal reviewed by
the user before any persistence; an explicit accept (the Human-First gate);
running the accepted plan — the default fake planning task classifies as an
unapproved SYSTEM_COMMAND (HIGH risk per device_control/action_engine.py's
own default risk table), so WorkflowExecutor's own whole-workflow
confirmation gate fires for real; a live-voice-triggered confirmation reply
can never actually be answered (backlog/technical_debt.md item 26's own
disclosed, unfixed single-thread reentrancy limitation), so it honestly
times out and denies the step — exactly the "empty-by-default
approved_commands allowlist... honestly blocked, not silently skipped"
behavior this sprint's own Objectives names explicitly, deliberately NOT
routed around the way tests/integration/test_autonomous_intelligence_
integration.py's own identical scenario does (that test's own job is
proving the wiring; this one's is proving the real, complete graph's honest
denial behavior); a live "why did you suggest that?" follow-up producing a
real, sourced Explanation; a real ProactiveAssistant-sourced item announced
only while DORMANT and only per AdaptivePrioritizer's own SURFACE_NOW
judgment; and confirmation that the completed (here: aborted) workflow
run's own outcome reached SelfEvaluator.

**A real, disclosed correction to this sprint's own Objectives text**: "the
completed workflow's outcome reaches SelfEvaluator and is retrievable via
TaskGraphStore.list_evaluations_for_goal()" repeats a premise already found
false at Sprint 6.13/6.14 — list_evaluations_for_goal() JOINs
evaluation_records.subject_id against tasks.task_id, but
SelfEvaluator.evaluate_workflow_run() (6.10) always keys subject_id on the
WorkflowRunResult's own run_id, so it can never surface a workflow-run
evaluation (planning/task_graph_store.py's own docstring already discloses
this). Verified instead by reading the raw evaluation_records table
directly, the only honest way to observe it — the identical technique
already established at tests/integration/test_autonomous_intelligence_
integration.py.

Sprint 6.14 hardening re-confirmation (Objective 2/Testing Checklist),
applying the same "only where a system-level repeat adds real confidence"
judgment Sprint 3.14/4.13/4.20/5.16/5.26 each already used for their own six
scenarios:
- **(a)** (LlmError mid-planning/explanation turn) and **(b)** (TaskGraphStore/
  KnowledgeGraphStore SQLite failures) are purely component-level, already
  exhaustively covered by Sprint 6.14's own dedicated unit tests against
  real (if narrowly faked) SQLite/LLM failures — a full-system repeat would
  add ceremony, not confidence.
- **(c)** (ProactiveAssistant tick isolation) is naturally re-exercised by
  `test_proactive_assistant_genuinely_recurs_at_system_level` below (a real,
  recurring TaskScheduler job, one continuous run) rather than needing a
  separate dedicated repeat — if a raising tick ever killed the job, genuine
  recurrence would fail to observe.
- **(d)** (PriorityQueueManager concurrency) is a pure data-structure
  property with no dependency on the real graph's own composition — Sprint
  6.14's own real 8-thread stress test already proves it conclusively;
  nothing about a real CoreManager adds confidence here.
- **(e)** (CyclicDependencyError reachability) was proven via a real,
  repo-wide AST scan (a static analysis, not runtime-composition-dependent)
  — the proof holds regardless of which harness runs it; nothing to repeat.
- **(f)** (SelfEvaluator failure never blocks/reverses TaskGraph bookkeeping)
  is genuinely composition-dependent on the real graph and is re-confirmed
  below as a dedicated function, the same treatment sprint_5_16.md gave its
  own scenarios (b)/(e).

**Outstanding, disclosed, not performed by this automated suite** (matching
every prior Level-freeze sprint's own precedent of naming a real,
unautomatable gap rather than glossing over it, starting with Sprint 2.14's
wake-word round trip): a supervised, human-observed real-machine
verification pass for Level 6 Part A's own conversational surfaces (a
planning proposal's own spoken wording actually sounding natural, a real
"why did you suggest that?" follow-up actually answering what a real user
meant, a real proactive announcement actually landing at a sensible moment)
— see this sprint's own completion report.
"""

from datetime import UTC, datetime, timedelta

from device_control.action_engine import (
    ActionContext,
    ActionRequest,
    ActionResult,
    ActionStatus,
    ActionType,
)
from planning.planning_model import Goal, Milestone, PlanningStatus, Task
from planning.task_graph import TaskGraph
from scheduler.scheduler_model import ItemType, ScheduledItem
from workflow.workflow_executor import WorkflowRunResult, WorkflowStepResult

_TURN_TIMEOUT = 10.0


def _reset_wake_detection(h) -> None:
    """See test_level3/4/5_part_a/part_b_acceptance.py's own identical
    helper for the full rationale (a real, previously-reproduced timing
    race, Sprint 3.12)."""
    h.wake_engine.calls = 0


def test_level6_part_a_full_acceptance_scenario(
    app_harness, wait_for_active_capture, wait_for_dormant, push_utterance, wait_until
):
    h = app_harness
    # Mirrors test_level5_part_b_acceptance.py's own identical poke —
    # AdaptivePrioritizer would otherwise correctly DEFER_BRIEFLY the
    # proactive announcement below given how recently a real turn just
    # happened; genuinely intended behavior, just not what step 5 tests.
    h.adaptive_prioritizer._config.conversation_active_threshold_seconds = 0.0
    # Hard-limits MISSED_MEAL the same way test_level5_part_b_acceptance.py's
    # own _TRIGGERS_TO_HARD_LIMIT keeps WellnessTracker's wall-clock-hour-
    # dependent triggers silent — a window that can never contain "now"
    # (0 <= now.hour < 0 is always false) keeps step 5 below deterministic
    # regardless of the real hour this suite happens to run at, rather than
    # depending on the current moment falling outside the default
    # noon-to-2pm window.
    h.proactive_assistant._config.missed_meal_window_start_hour = 0
    h.proactive_assistant._config.missed_meal_window_end_hour = 0

    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    # --- Turn 1: propose a fresh goal — never persisted before
    # acceptance, a real Human-First review step. -----------------------
    h.stt.pending_transcripts.append("help me plan a small project")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    proposal_reply, _ = h.tts.speak_calls[-1]
    assert "milestone" in proposal_reply.lower()
    assert h.task_graph_store.list_goals() == []

    # --- Turn 2: accept it — the real enforcement point for the
    # Human-First gate; only the Goal's own status is bumped, each Task
    # stays PROPOSED until it actually runs. -----------------------------
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("yes")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    accepted_goals = h.task_graph_store.list_goals(status=PlanningStatus.ACCEPTED)
    assert len(accepted_goals) == 1
    goal = accepted_goals[0]
    assert goal.milestones[0].tasks[0].status is PlanningStatus.PROPOSED

    # --- Turn 3: run it. The default fake planning task ("Do the first
    # concrete thing") classifies as an unapproved SYSTEM_COMMAND (HIGH
    # risk) — WorkflowExecutor's own real, unmodified whole-workflow
    # confirmation gate fires and speaks a confirmation prompt FIRST (its
    # own separate speak() call, which would satisfy a single
    # tts.spoken_event.wait() before this turn's own final reply does —
    # the identical race tests/integration/test_autonomous_intelligence_
    # integration.py's own docstring names, handled here by polling for
    # the final reply's own content instead). A live-voice-triggered
    # confirmation reply can never actually be answered (backlog/
    # technical_debt.md item 26's own disclosed limitation), so it
    # honestly times out after SecurityConfig.confirmation_timeout_seconds
    # (2.0s in this harness) and denies the step — exactly the
    # "empty-by-default approved_commands... honestly blocked" outcome
    # this sprint's own Objectives names (even had the confirmation been
    # answered, the empty allowlist would deny the step at dispatch too —
    # this scenario observes the confirmation-timeout gate, the one
    # actually reached first). ------------------------------------------
    h.stt.pending_transcripts.append("run my plan")
    push_utterance(h.audio_backend)
    assert wait_until(
        lambda: any("wasn't confirmed" in text for text, _ in h.tts.speak_calls),
        timeout=_TURN_TIMEOUT,
    ), "The workflow's own confirmation-timeout denial was never spoken."
    run_reply, _ = h.tts.speak_calls[-1]
    assert "wasn't confirmed" in run_reply

    # The originating Task was never dispatched at all — an honest "never
    # attempted" state, not a fabricated success or failure.
    updated_goal = h.task_graph_store.get_goal(goal.goal_id)
    assert updated_goal.milestones[0].tasks[0].status is PlanningStatus.PROPOSED

    # SelfEvaluator still ran for the real (if empty-stepped)
    # WorkflowRunResult — see this module's own docstring for why
    # list_evaluations_for_goal() itself can never surface it.
    rows = h.task_graph_store._sqlite_client.query(
        "SELECT subject_id, outcome FROM evaluation_records"
    )
    assert len(rows) == 1
    assert rows[0][1] == "failure"

    # --- Turn 4: "why did you suggest that?" — a real, sourced
    # Explanation composed from the "run my plan" turn's own
    # DecisionTrace.reasoning_text — no fresh ReasoningEngine.explain_why()
    # fallback call needed. This turn's own Intent/Context detection
    # still calls the LLM as usual (every turn does, regardless of engine
    # selection) — the claim under test is narrower: ExplainabilityLayer
    # itself never falls through to a fresh LLM call, verified by
    # confirming none of THIS turn's new prompts match reasoning/
    # reasoning_engine.py's own literal "reasoning engine" opening phrase
    # (the same substring FakeLanguageModelClient's own dispatch uses). --
    h.tts.spoken_event.clear()
    calls_before_explanation = len(h.llm_client.calls)
    h.stt.pending_transcripts.append("why did you suggest that")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    explanation_reply, _ = h.tts.speak_calls[-1]
    assert explanation_reply.strip() != ""
    assert explanation_reply != "I can't explain my reasoning right now."
    new_calls = h.llm_client.calls[calls_before_explanation:]
    assert not any("reasoning engine" in prompt for prompt in new_calls)

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    # Disables the real background WakeWordDetector thread for step 5
    # below — see test_level5_part_b_acceptance.py's own identical
    # comment for the full, concretely reproduced rationale.
    h.wake_engine.match_on_call = 10**9

    # --- Step 5: a real, overdue ScheduledItem's own FORGOTTEN_REMINDER
    # trigger (IMPORTANT_ALERT — always resolves SURFACE_NOW in
    # AdaptivePrioritizer's own rules) is announced only while DORMANT,
    # driven through a direct ProactiveAssistant._on_tick() +
    # CommunicationPipeline._check_and_announce_priority_item() call
    # pair — the same synchronous, direct-call technique
    # test_level5_part_b_acceptance.py's own step 2 already established
    # for this file's own realistic (slow) SchedulerConfig/ProactiveConfig
    # defaults; genuine real-recurrence proof is this file's own separate,
    # dedicated test below, matching that same file's own precedent. ----
    overdue_item = ScheduledItem(
        item_id="overdue-1",
        item_type=ItemType.EVENT,
        title="renew the domain registration",
        scheduled_at=datetime.now(UTC) - timedelta(hours=1),
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    h.calendar_store.save(overdue_item)
    speak_calls_before = len(h.tts.speak_calls)
    h.proactive_assistant._on_tick()
    h.pipeline._check_and_announce_priority_item()

    assert len(h.tts.speak_calls) > speak_calls_before, "The proactive item was never announced."
    announcement_reply, _ = h.tts.speak_calls[-1]
    assert "renew the domain registration" in announcement_reply
    assert h.priority_queue_manager.peek_next() is None  # genuinely popped, not left dangling


def test_proactive_assistant_genuinely_recurs_at_system_level(
    fast_level6_part_a_app_harness, wait_until, wait_for_dormant
):
    """Sprint 6.14 hardening scenario (c) re-confirmed at the system
    level, naturally, via genuine recurrence rather than a dedicated
    repeat: if a raising tick ever killed ProactiveAssistant's own
    TaskScheduler job, this real second announcement would never arrive.
    Mirrors tests/integration/test_autonomous_intelligence_integration.py's
    own test_proactive_assistant_job_genuinely_recurs precedent, now
    through the real, complete Level 1-6 Part A CoreManager graph."""
    h = fast_level6_part_a_app_harness
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


def test_self_evaluator_failure_never_blocks_or_reverses_task_bookkeeping(
    app_harness, monkeypatch
):
    """Sprint 6.14 hardening scenario (f) re-confirmed at the system
    level — genuinely composition-dependent on the real TaskGraphStore/
    SelfEvaluator graph, unlike (a)/(b)/(d)/(e) above. Drives
    _finalize_workflow_run() directly (the same, real method the main
    scripted scenario above already calls indirectly) against a real,
    persisted Goal/Task and a genuinely-succeeded WorkflowRunResult, with
    SelfEvaluator.evaluate_workflow_run() monkeypatched to raise —
    confirms the Task's own real status commit (via the real
    TaskGraphStore, a genuine SQLite write) already happened before the
    evaluator is ever reached, matching voice/pipeline.py's own
    _finalize_workflow_run() docstring (two independent try/except
    blocks)."""
    h = app_harness
    now = datetime.now(UTC)
    task = Task(task_id="t1", title="Do the thing", description="A real task")
    goal = Goal(
        goal_id="g1",
        statement="A real accepted goal",
        milestones=[Milestone(milestone_id="m1", title="M1", tasks=[task])],
        created_at=now,
        status=PlanningStatus.ACCEPTED,
    )
    h.task_graph_store.save_goal(goal)
    task_graph = TaskGraph(goal)

    request = ActionRequest(
        action_type=ActionType.LAUNCH_APPLICATION,
        parameters={},
        context=ActionContext(requested_by="test"),
        requested_at=now,
    )
    step_result = WorkflowStepResult(
        step_index=0,
        action_result=ActionResult(
            request=request, status=ActionStatus.SUCCEEDED, completed_at=now
        ),
        skipped=False,
    )
    run_result = WorkflowRunResult(
        workflow_id="wf-1",
        run_id="run-1",
        step_results=[step_result],
        aborted_early=False,
        whole_workflow_confirmation=None,
        started_at=now,
        completed_at=now,
    )

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(h.self_evaluator, "evaluate_workflow_run", _raise)

    h.pipeline._finalize_workflow_run(run_result, task_graph, [task], goal)  # must not raise

    assert task.status is PlanningStatus.COMPLETED
    persisted_goal = h.task_graph_store.get_goal(goal.goal_id)
    assert persisted_goal.milestones[0].tasks[0].status is PlanningStatus.COMPLETED
