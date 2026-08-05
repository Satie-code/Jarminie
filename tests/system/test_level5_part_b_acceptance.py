"""Level 5 Part B — Companion Intelligence formal Acceptance Pass (Sprint
5.26), closing Level 5 Part B and, with Sprint 5.16's own Part A freeze,
all of Level 5 (Companion) as a whole. Mirrors Sprint 2.14/3.14/4.13/
4.20/5.16's own identical closing role for their own Levels/Parts.

One continuous scripted scenario (`test_level5_part_b_full_acceptance_
scenario` below) through the real, complete Level 1-5 (Part A + Part B)
`CoreManager` graph (`app_harness`, tests/system/conftest.py — the same
harness `test_level5_part_a_acceptance.py`/`test_level4_part_b_
acceptance.py` already use, now also carrying every Level 5 Part B
object). Covers, in order: a real `AnalyticsDashboardService.
daily_summary()` computed from fixture `AppFocusSample`s; a real,
directly-advanced `WellnessTracker` state crossing `BREAK`, producing a
real spoken announcement through Minie with Jarvis correctly restored
immediately after; three postponements engaging the Hard Limit; a real
`PatternRecognizer`/`RecommendationEngine` detection-and-recommendation
pass; and a real live turn routed to `EngineSelection.WELLNESS`.

**Deliberately uses `app_harness` (realistic, slow `SchedulerConfig`/
`WellnessConfig`/`LearningConfig`/`AnalyticsConfig` defaults), not a fast
variant, for this whole scripted scenario** — every wellness/pattern/
recommendation step below directly advances state and calls the real job
bodies (`_maybe_enqueue_wellness_prompt()`, `_generate_and_enqueue_
recommendations()`, `_check_and_announce_priority_item()`) synchronously,
the same `_due_item()`-style "persist the end state directly rather than
wait a real interval" technique `test_level4_part_b_acceptance.py`
already established for `ReminderEngine` and `test_level5_part_a_
acceptance.py` for `CompanionExperienceEngine`'s own greeting — matching
this sprint's own Scripted Acceptance Scenario text exactly. This is also
a genuine, disclosed correctness choice, not just a style preference:
`WellnessTracker._on_tick()` reads the real machine's own win32api idle
time and can reset `_continuous_active_seconds` on real, environment-
dependent inactivity — at `WellnessConfig.idle_check_interval_seconds`'s
own realistic 60s default this job never fires within this file's own
short runtime, so a directly-set counter stays stable throughout; at Sprint
5.25's own fast 0.3s interval it could race and reset it, a real hazard
found and avoided while designing this file, not assumed safe. The one
place this scenario genuinely needs real recurrence — confirming all four
Level 5 Part B `TaskScheduler` jobs actually fire more than once, per this
sprint's own Testing Checklist — is therefore a SEPARATE, dedicated test
(`test_all_four_level5_part_b_jobs_genuinely_recur` below) using a new
`fast_level5_part_b_app_harness` fixture, which only counts real calls and
never depends on any hand-set counter surviving multiple ticks.

**Sprint 5.25 hardening re-confirmation** (Objective 3/Testing Checklist),
applying the same "only where a system-level repeat adds real confidence"
judgment Sprint 3.14/4.13/4.20/5.16 each already used for their own six
scenarios:
- **(a)/(b)/(c)** are purely component-level, already exhaustively
  covered by Sprint 5.25's own dedicated integration tests against real
  (if narrowly faked) OS/SQLite failures (`tests/integration/test_
  companion_intelligence_resilience.py`) — a full-system repeat would add
  ceremony, not confidence.
- **(d)** is naturally re-exercised by `test_all_four_level5_part_b_jobs_
  genuinely_recur` below (four real jobs, one continuous run) rather than
  needing a separate dedicated repeat.
- **(e)/(f)** are genuinely composition-dependent on the real, full graph
  and are re-confirmed below as dedicated functions, the same treatment
  `sprint_5_16.md` gave its own scenarios (b)/(e).

The one remaining Acceptance Criterion — a supervised, real-machine,
human-observed pass (a real wellness prompt genuinely heard and correctly
handed to Minie's own voice and back; real application-usage data
genuinely reflecting what the machine actually ran; a real recommendation
genuinely making sense to the person hearing it) — is explicitly NOT
performed by this automated suite, matching every prior Level-freeze
sprint's own precedent of naming a manual step rather than silently
assuming it happened; see this sprint's own completion report.
"""

from datetime import UTC, datetime, timedelta

import pytest

from analytics.usage_model import AppFocusSample
from analytics.usage_tracker import UsageTracker
from decision.priority_queue import PriorityLevel
from learning.pattern_model import PatternType
from learning.pattern_recognizer import PatternRecognizer
from learning.recommendation import RecommendationEngine
from wellness.wellness_model import WellnessPrompt, WellnessTriggerType
from wellness.wellness_tracker import WellnessTracker

_TURN_TIMEOUT = 10.0
"""Matches test_level4_part_b_acceptance.py's/test_level5_part_a_
acceptance.py's own more generous timeout — this file's own scenario is
similarly long/composite."""

# The three WellnessTriggerTypes that share WellnessTracker's own single
# _continuous_active_seconds accumulator (see wellness/wellness_tracker.py's
# own module docstring) plus LATE_NIGHT (hard-limited defensively below so
# step 5's own assertion is deterministic regardless of the real wall-clock
# hour this file happens to run at, not because a LATE_NIGHT prompt was
# ever actually shown) — OVERWORK alone is left out, since it uses a
# separate _daily_active_seconds accumulator this scenario never sets, so
# it is never crossed and needs no hard-limiting to stay silent.
_TRIGGERS_TO_HARD_LIMIT = (
    WellnessTriggerType.BREAK,
    WellnessTriggerType.EYE_PROTECTION,
    WellnessTriggerType.HYDRATION,
    WellnessTriggerType.LATE_NIGHT,
)


def _reset_wake_detection(h) -> None:
    """See test_level3/4/5_part_a_acceptance.py's own identical helper
    for the full rationale (a real, previously-reproduced timing race,
    Sprint 3.12)."""
    h.wake_engine.calls = 0


def test_level5_part_b_full_acceptance_scenario(
    app_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    h = app_harness

    # --- Step 1: a sequence of simulated AppFocusSamples produces a
    # real, non-empty AnalyticsDashboardService.daily_summary() — every
    # field verified against the known fixture, not merely "did not
    # raise". Two samples 2 minutes apart merge into ONE real UsageSession
    # (analytics/usage_store.py's own grouping rule; well within
    # AnalyticsConfig.session_gap_seconds' own 180s default). -----------
    now = datetime.now(UTC)
    h.usage_store.record_sample(
        AppFocusSample(process_name="devenv.exe", window_title="Editor", sampled_at=now)
    )
    h.usage_store.record_sample(
        AppFocusSample(
            process_name="devenv.exe", window_title="Editor", sampled_at=now + timedelta(minutes=2)
        )
    )
    summary = h.dashboard_service.daily_summary(now.date())
    assert summary.total_active_seconds == 120.0
    assert summary.top_applications == [("devenv.exe", 120.0)]
    assert summary.focus_session_count == 1
    assert summary.longest_focus_session_seconds == 120.0

    # --- Step 2: a real, live-switched Jarvis session first (so
    # "whichever persona was active immediately before" is a genuine
    # prior turn, not just the default), then WellnessTracker's own
    # continuous-active-time counter is directly advanced past
    # break_interval_seconds — producing a real WellnessPrompt via a
    # real evaluate_triggers() call, enqueued and announced through the
    # real, complete graph: forced switch to Minie, spoken, and Jarvis
    # restored immediately after (checked directly via active_persona()
    # both before advancing state and after the announcement). ---------
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)
    h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: general question\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    h.stt.pending_transcripts.append("what time is it")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    assert h.persona_manager.active_persona().name == "jarvis"
    jarvis_voice_id = h.persona_manager.active_persona().voice_id
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    # Disables the real background WakeWordDetector thread for the
    # remainder of steps 2-4 below — a real, concretely reproduced race
    # found writing this test: that thread keeps sampling FakeAudioBackend
    # continuously even with no further push_utterance() call, and can
    # spuriously re-match and activate() a session via ActivationReason.
    # WAKE_WORD at any moment, racing the direct _check_and_announce_
    # priority_item() calls below and silently absorbing the wellness
    # announcement's own activate() call into QuietModeController's
    # documented "activations cannot stack" no-op — restored (via
    # _reset_wake_detection()) immediately before step 5's own live turn.
    h.wake_engine.match_on_call = 10**9

    h.wellness_tracker._continuous_active_seconds = (
        h.wellness_tracker._config.break_interval_seconds
    )
    speak_calls_before = len(h.tts.speak_calls)
    h.pipeline._maybe_enqueue_wellness_prompt()
    h.pipeline._check_and_announce_priority_item()

    assert len(h.tts.speak_calls) > speak_calls_before, "The wellness prompt was never announced."
    announced_text, announced_voice_id = h.tts.speak_calls[-1]
    assert announced_text == "You've been active for a while — consider taking a short break."
    assert announced_voice_id != jarvis_voice_id, "Must be spoken through Minie's own voice."
    assert h.persona_manager.active_persona().name == "jarvis"  # correctly resumed
    # The announcement's own session (begin_session(announce_first=...))
    # is still ACTIVE at this point — waited out here so step 4's own
    # direct _check_and_announce_priority_item() call below sees the
    # real DORMANT precondition it requires, rather than silently
    # skipping (found while writing this test).
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    # --- Step 3: three simulated postponements against every trigger
    # that BREAK's own counter value also crosses (see this module's own
    # docstring/_TRIGGERS_TO_HARD_LIMIT comment for why BREAK alone isn't
    # enough) correctly engage the Hard Limit — a further crossing
    # produces no further prompt at all, verified directly. -------------
    for trigger_type in _TRIGGERS_TO_HARD_LIMIT:
        for _ in range(3):
            h.wellness_escalation_manager.register_postponed(trigger_type)
        assert h.wellness_escalation_manager.is_hard_limited(trigger_type)

    assert h.wellness_tracker.evaluate_triggers() is None

    # --- Step 4: PatternRecognizer.run_detection_pass() over fixture
    # UsageStore data crossing both gates (pattern_min_occurrences=5,
    # pattern_min_days=3 by default — five distinct-day samples for the
    # same process clears both) produces a real, persisted LearnedPattern;
    # RecommendationEngine.generate_recommendations(), via the real
    # CommunicationPipeline._generate_and_enqueue_recommendations() job
    # body, produces a real, templated Recommendation, correctly surfaced
    # at PriorityLevel.GENERAL_SUGGESTION and announced without any
    # persona switch. Spread across a DIFFERENT preferred_time_bucket_
    # hours-sized bucket (2h default) each day — deliberately, not
    # incidentally: five same-time-of-day samples would ALSO clear
    # detect_preferred_times()'s own identical two-gate check, producing
    # a second, competing PREFERRED_TIME recommendation and making which
    # one peek_next() returns first order-dependent rather than a clean,
    # singular proof of this step's own FREQUENT_APPLICATION path (found
    # while writing this test — an earlier draft used the same hour every
    # day and got a PREFERRED_TIME recommendation at the front instead). -
    base = datetime.now(UTC) - timedelta(days=10)
    for day_offset in range(5):
        h.usage_store.record_sample(
            AppFocusSample(
                process_name="devenv.exe",
                window_title="Editor",
                sampled_at=(base + timedelta(days=day_offset)).replace(hour=day_offset * 4),
            )
        )
    detected = h.pattern_recognizer.run_detection_pass()
    assert any(
        p.pattern_type is PatternType.FREQUENT_APPLICATION and p.subject == "devenv.exe"
        for p in detected
    )
    stored = h.pattern_store.list_by_type(PatternType.FREQUENT_APPLICATION)
    assert any(p.subject == "devenv.exe" for p in stored)

    speak_calls_before = len(h.tts.speak_calls)
    h.pipeline._generate_and_enqueue_recommendations()
    peeked = h.priority_queue_manager.peek_next()
    assert peeked is not None
    assert peeked.priority is PriorityLevel.GENERAL_SUGGESTION
    recommendation = peeked.payload
    assert recommendation.text == (
        "You often use devenv.exe around this time — want me to open it for you next time?"
    )

    h.pipeline._check_and_announce_priority_item()
    assert len(h.tts.speak_calls) > speak_calls_before
    announced_text, announced_voice_id = h.tts.speak_calls[-1]
    assert announced_text == recommendation.text
    assert announced_voice_id == jarvis_voice_id  # no persona switch for GENERAL_SUGGESTION
    assert h.persona_manager.active_persona().name == "jarvis"
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    # --- Step 5: a real live turn ("how am I doing today?") is routed to
    # EngineSelection.WELLNESS and answered honestly from the same real,
    # fixture-seeded state steps 1-3 produced: 2 real active minutes
    # (step 1), no further wellness prompt due (every trigger that could
    # possibly fire is hard-limited or never crossed, per step 3 — this
    # assertion is deterministic regardless of the real wall-clock hour
    # this file happens to run at). ---------------------------------------
    h.wake_engine.match_on_call = 2  # restore real wake detection for this turn
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)
    h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: wellness\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("how am I doing today?")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    reply_text, _ = h.tts.speak_calls[-1]
    # VoicePersonalityModulator.shape_pacing() (Sprint 5.11) inserts its
    # own per-persona pacing marker into the raw reply — stripped here
    # the same way test_level5_part_a_acceptance.py's own jarvis_reply/
    # minie_reply comparison already does, since this assertion cares
    # about the honest wellness content, not voice pacing.
    assert reply_text.replace("... ", "") == (
        "You've been active for about 2 minute(s) today. No wellness reminders are due right now."
    )
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)

    # --- Every Level 1-5 (Part A + Part B) module is registered and
    # running through the real, complete CoreManager graph. ---------------
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
        "usage_store",
        "usage_tracker",
        "pattern_store",
        "pattern_recognizer",
        "wellness_tracker",
    }
    assert all(state == "running" for state in states.values())


# --- Testing Checklist: fast_scheduler_app_harness-style confirmation of
# all four new recurring jobs -----------------------------------------------


@pytest.fixture
def level5_part_b_job_call_counts(monkeypatch):
    """Same class-level counting-wrapper technique as test_level4_part_b_
    acceptance.py's own maintenance_call_counts fixture — must be
    requested BEFORE fast_level5_part_b_app_harness in a test's own
    parameter list, since each job captures its own bound method the
    instant its own add_job() call runs during harness setup. Counts
    calls only — never depends on any counter VALUE, so this is immune
    to the real-machine-idle-time hazard this module's own docstring
    names for the main scripted scenario above."""
    counts = {
        "usage_tracker": 0,
        "wellness_tracker": 0,
        "pattern_recognizer": 0,
        "recommendation_engine": 0,
    }

    original_usage_tick = UsageTracker._on_tick
    original_wellness_tick = WellnessTracker._on_tick
    original_pattern_pass = PatternRecognizer.run_detection_pass
    original_recommend = RecommendationEngine.generate_recommendations

    def counting_usage_tick(self):
        counts["usage_tracker"] += 1
        return original_usage_tick(self)

    def counting_wellness_tick(self):
        counts["wellness_tracker"] += 1
        return original_wellness_tick(self)

    def counting_pattern_pass(self):
        counts["pattern_recognizer"] += 1
        return original_pattern_pass(self)

    def counting_recommend(self):
        counts["recommendation_engine"] += 1
        return original_recommend(self)

    monkeypatch.setattr(UsageTracker, "_on_tick", counting_usage_tick)
    monkeypatch.setattr(WellnessTracker, "_on_tick", counting_wellness_tick)
    monkeypatch.setattr(PatternRecognizer, "run_detection_pass", counting_pattern_pass)
    monkeypatch.setattr(RecommendationEngine, "generate_recommendations", counting_recommend)

    return counts


def test_all_four_level5_part_b_jobs_genuinely_recur(
    level5_part_b_job_call_counts, fast_level5_part_b_app_harness, wait_until
):
    """Testing Checklist item 3: UsageTracker's, WellnessTracker's,
    PatternRecognizer's, and RecommendationEngine's own TaskScheduler
    jobs each genuinely fire more than once, through the real, complete
    CoreManager graph — not just registered once."""
    _ = fast_level5_part_b_app_harness

    def _all_fired_at_least_twice() -> bool:
        return all(count >= 2 for count in level5_part_b_job_call_counts.values())

    assert wait_until(_all_fired_at_least_twice, timeout=_TURN_TIMEOUT), (
        f"Not every Level 5 Part B job fired twice within the test's own bounded "
        f"window: {level5_part_b_job_call_counts}"
    )


# --- Sprint 5.25 hardening scenarios (e)/(f), re-confirmed at the system
# level -- see this module's own docstring for why (a)/(b)/(c)/(d) are not
# re-tested a third time as dedicated functions here. ------------------------


def test_wellness_announcement_failure_never_leaves_persona_stuck_through_the_full_graph(
    app_harness, wait_for_dormant
):
    """Scenario (e), system level: a real induced PersonaManager.select()
    failure during a WELLNESS announcement must not leave PersonaManager
    stuck on Minie or corrupt PriorityQueueManager's own queue state,
    through the real, fully-wired Level 1-5 CoreManager graph — not just
    a hand-assembled pipeline_harness (tests/integration/conftest.py)."""
    h = app_harness
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    h.wake_engine.match_on_call = 10**9
    assert h.persona_manager.active_persona().name == "jarvis"

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated PersonaManager.select() failure")

    original_select = h.persona_manager.select
    h.persona_manager.select = _raise
    try:
        prompt = WellnessPrompt(
            trigger_type=WellnessTriggerType.BREAK,
            message="You've been active for a while — consider taking a short break.",
            triggered_at=datetime.now(UTC),
        )
        h.priority_queue_manager.enqueue(prompt, PriorityLevel.WELLNESS, source="test")
        h.pipeline._check_and_announce_priority_item()  # must not raise
    finally:
        h.persona_manager.select = original_select

    assert h.persona_manager.active_persona().name == "jarvis"
    assert h.priority_queue_manager.peek_next() is None


def test_wellness_turn_and_recommendation_pass_degrade_honestly_through_a_broken_store(
    app_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Scenario (f), system level: a real, genuine SQLite failure in
    UsageStore/PatternStore degrades honestly at both real call sites —
    _handle_wellness_turn() and _generate_and_enqueue_recommendations() —
    through the real, complete CoreManager graph, rather than crashing
    the turn or the job."""
    h = app_harness

    def _raise(*args, **kwargs):
        raise Exception("simulated SQLite failure")

    original_usage_query = h.usage_store._sqlite_client.query
    h.usage_store._sqlite_client.query = _raise
    try:
        wait_for_active_capture(h.mic)
        h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
        h.llm_client.context_response = (
            "TOPIC: wellness\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
            "PERSONA: NONE\nSENTIMENT: NEUTRAL"
        )
        h.stt.pending_transcripts.append("how am I doing today?")
        push_utterance(h.audio_backend)
        assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
        reply_text, _ = h.tts.speak_calls[-1]
        assert reply_text == "I don't have enough information about today yet."
        wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    finally:
        h.usage_store._sqlite_client.query = original_usage_query

    original_pattern_query = h.pattern_store._sqlite_client.query
    h.pattern_store._sqlite_client.query = _raise
    try:
        h.pipeline._generate_and_enqueue_recommendations()  # must not raise
    finally:
        h.pattern_store._sqlite_client.query = original_pattern_query
    assert h.priority_queue_manager.peek_next() is None
