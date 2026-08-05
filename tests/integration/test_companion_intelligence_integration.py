"""Integration tests for Level 5 Part B's real, end-to-end wiring (Sprint
5.24 — Companion Intelligence Integration) — the first live exercise of
`EngineSelection.WELLNESS`, the widened `_check_and_announce_priority_item()`
three-source dispatcher, and real recurring `TaskScheduler` cadences for
`PatternRecognizer`/`RecommendationEngine`.

Mirrors tests/integration/test_scheduler_integration.py's own established
shape closely (Sprint 4.18's own identical "first live exercise of a new
proactive announcement source" precedent): WellnessPrompt/Recommendation
payloads are constructed directly and enqueued (mirroring that file's own
`_due_item()` — bypassing real detection to exercise the CONSUME/ANNOUNCE
half in isolation) wherever real detection isn't itself the thing under
test; fast_scheduler_harness (unmodified, Sprint 4.18's own fixture) is
enough for those cases, since WellnessTracker's/PatternRecognizer's own
detection jobs stay at their real, slow defaults and never interfere.
fast_level5_part_b_harness (this sprint's own new fixture) is used only
for the one test that needs PatternRecognizer/RecommendationEngine's own
real detection jobs to actually fire on a fast cadence.
"""

import uuid
from datetime import UTC, datetime, timedelta

from analytics.usage_model import AppFocusSample
from decision.priority_queue import PriorityLevel
from learning.recommendation import Recommendation
from voice.quiet_mode import OperatingMode
from wellness.wellness_model import WellnessPrompt, WellnessTriggerType

_TURN_TIMEOUT = 10.0


def _set_wellness_query(h, transcript_keyword_phrase: str) -> None:
    h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: wellness\nENTITIES: NONE\nREFERENCES_PAST: NO\nPERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    h.stt.pending_transcripts.append(transcript_keyword_phrase)


def _wellness_prompt(
    trigger_type: WellnessTriggerType = WellnessTriggerType.BREAK,
) -> WellnessPrompt:
    return WellnessPrompt(
        trigger_type=trigger_type,
        message="You've been active for a while — consider taking a short break.",
        triggered_at=datetime.now(UTC),
    )


def _recommendation(text: str = "You often use devenv.exe — want me to open it next time?"):
    return Recommendation(
        text=text, based_on_pattern_id=str(uuid.uuid4()), generated_at=datetime.now(UTC)
    )


# --- Real wellness announcement: forced Minie switch, spoken, resumed ---------


def test_real_wellness_announcement_force_switches_to_minie_and_resumes(
    fast_scheduler_harness, wait_until, wait_for_dormant
):
    """Acceptance Criteria: "A real, scripted wellness trigger... produces
    a real spoken announcement through Minie's own voice, with whatever
    persona was active before correctly restored immediately after."
    fast_scheduler_harness (not fast_level5_part_b_harness) is enough —
    the WellnessPrompt is enqueued directly, bypassing WellnessTracker's
    own detection entirely (mirroring test_scheduler_integration.py's own
    _due_item() precedent), so only scheduler_config.poll_interval_seconds
    (the announcement job's own cadence) needs to be fast."""
    h = fast_scheduler_harness
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    h.wake_engine.match_on_call = 10**9
    assert h.quiet_mode_controller.current_mode() is OperatingMode.DORMANT
    assert h.persona_manager.active_persona().name == "jarvis"
    jarvis_voice_id = h.persona_manager.active_persona().voice_id
    assert h.tts.speak_calls == []

    prompt = _wellness_prompt()
    h.priority_queue_manager.enqueue(prompt, PriorityLevel.WELLNESS, source="test")

    assert wait_until(
        lambda: len(h.tts.speak_calls) >= 1
        and h.persona_manager.active_persona().name == "jarvis",
        timeout=_TURN_TIMEOUT,
    ), "Wellness prompt was never proactively announced (or never resumed to jarvis)."

    reply_text, voice_id = h.tts.speak_calls[0]
    assert reply_text == prompt.message
    assert voice_id != jarvis_voice_id, "The announcement must be spoken through Minie's voice."

    # The item was genuinely popped (not left dangling).
    assert h.priority_queue_manager.peek_next() is None

    assert h.quiet_mode_controller.current_mode() is OperatingMode.ACTIVE
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


def test_wellness_announcement_registers_prompt_shown_with_escalation_manager(
    fast_scheduler_harness, wait_until, wait_for_dormant
):
    h = fast_scheduler_harness
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    h.wake_engine.match_on_call = 10**9

    prompt = _wellness_prompt(WellnessTriggerType.HYDRATION)
    h.priority_queue_manager.enqueue(prompt, PriorityLevel.WELLNESS, source="test")

    assert wait_until(lambda: len(h.tts.speak_calls) >= 1, timeout=_TURN_TIMEOUT)
    assert h.wellness_escalation_manager.current_level(WellnessTriggerType.HYDRATION) == 1

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


# --- Real live-turn wellness query ---------------------------------------------


def test_real_live_turn_wellness_query_is_routed_and_answered(
    pipeline_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Acceptance Criteria: "A real live turn asking a wellness-shaped
    question is routed to EngineSelection.WELLNESS and answered honestly
    from real WellnessTracker/AnalyticsDashboardService state."""
    h = pipeline_harness
    now = datetime.now(UTC)
    # Two samples, close enough together to merge into ONE real session
    # (analytics/usage_store.py's own grouping rule) — a single sample
    # alone has zero duration (started_at == ended_at), which would
    # itself trigger the "not enough information" fallback this test is
    # NOT exercising (see test_..._with_no_usage_data_degrades_honestly
    # below for that case).
    h.usage_store.record_sample(
        AppFocusSample(process_name="devenv.exe", window_title="Editor", sampled_at=now)
    )
    h.usage_store.record_sample(
        AppFocusSample(
            process_name="devenv.exe",
            window_title="Editor",
            # Well within AnalyticsConfig.session_gap_seconds' own
            # default (180s) — merges into ONE session with the sample
            # above rather than splitting into two separate zero/near-
            # zero-duration ones.
            sampled_at=now + timedelta(minutes=2),
        )
    )

    wait_for_active_capture(h.mic)
    _set_wellness_query(h, "how am I doing today?")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    reply_text, _ = h.tts.speak_calls[0]
    assert "active" in reply_text.lower()
    assert "minute" in reply_text.lower()

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


def test_real_live_turn_wellness_query_with_no_usage_data_degrades_honestly(
    pipeline_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """No fabricated statistic on a fresh install — see this Sprint's own
    Potential Risks: "a fresh install with an empty UsageStore will,
    correctly, report having nothing to say yet.\""""
    h = pipeline_harness

    wait_for_active_capture(h.mic)
    _set_wellness_query(h, "should I take a break?")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text == "I don't have enough information about today yet."

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


# --- GENERAL_SUGGESTION announcement: no persona switch ------------------------


def test_general_suggestion_announcement_through_active_persona_no_switch(
    fast_scheduler_harness, wait_until, wait_for_dormant
):
    """Acceptance Criteria's own implied contrast with WELLNESS: a
    suggestion is announced through whichever persona is already active,
    unchanged — the same SCHEDULED_REMINDER precedent, never a forced
    switch."""
    h = fast_scheduler_harness
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    h.wake_engine.match_on_call = 10**9
    assert h.persona_manager.active_persona().name == "jarvis"
    jarvis_voice_id = h.persona_manager.active_persona().voice_id

    recommendation = _recommendation()
    h.priority_queue_manager.enqueue(
        recommendation, PriorityLevel.GENERAL_SUGGESTION, source="test"
    )

    assert wait_until(lambda: len(h.tts.speak_calls) >= 1, timeout=_TURN_TIMEOUT), (
        "General suggestion was never proactively announced."
    )
    reply_text, voice_id = h.tts.speak_calls[0]
    assert reply_text == recommendation.text
    assert voice_id == jarvis_voice_id
    assert h.persona_manager.active_persona().name == "jarvis"

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


# --- Real recurring TaskScheduler cadences for PatternRecognizer/RecommendationEngine --


def test_pattern_recognizer_and_recommendation_engine_jobs_fire_on_configured_cadence(
    fast_level5_part_b_harness, wait_until
):
    """Testing Checklist: "TaskScheduler jobs for PatternRecognizer/
    RecommendationEngine genuinely fire on their own configured cadence."
    Seeds five real, distinct-day AppFocusSamples for the same process —
    each far enough apart to become its own one-sample UsageSession
    (analytics/usage_store.py's own grouping rule) — clearing both of
    LearningConfig's default gates (pattern_min_occurrences=5,
    pattern_min_days=3) so a real FREQUENT_APPLICATION pattern is
    genuinely detected, then a real Recommendation is genuinely composed
    from it and enqueued — proving both jobs actually ran, not merely
    that they were registered."""
    h = fast_level5_part_b_harness
    base = datetime.now(UTC) - timedelta(days=10)
    for day_offset in range(5):
        h.usage_store.record_sample(
            AppFocusSample(
                process_name="devenv.exe",
                window_title="Editor",
                sampled_at=base + timedelta(days=day_offset),
            )
        )

    assert wait_until(lambda: len(h.pattern_store.list_all()) >= 1, timeout=_TURN_TIMEOUT), (
        "PatternRecognizer.run_detection_pass() never fired on its own configured cadence."
    )

    assert wait_until(
        lambda: h.priority_queue_manager.peek_next() is not None
        and h.priority_queue_manager.peek_next().priority is PriorityLevel.GENERAL_SUGGESTION,
        timeout=_TURN_TIMEOUT,
    ), "RecommendationEngine.generate_recommendations() never fired on its own configured cadence."


# --- Level 5 Part B construction failure: full graceful degrade ---------------


def test_level5_part_b_unavailable_wellness_turn_degrades_honestly(
    pipeline_harness_without_level5_part_b,
    wait_for_active_capture,
    wait_for_dormant,
    push_utterance,
):
    h = pipeline_harness_without_level5_part_b

    wait_for_active_capture(h.mic)
    _set_wellness_query(h, "how am I doing today?")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text == "I don't have enough information about today yet."

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)


def test_level5_part_b_unavailable_start_and_stop_never_crash(
    pipeline_harness_without_level5_part_b,
):
    """start()/stop() already ran once as part of the fixture's own
    setup/teardown; this asserts the pipeline is genuinely wired and
    healthy despite every Level 5 Part B dependency being None — a
    silent construction-time crash would have failed fixture setup
    itself before this test body ever ran."""
    h = pipeline_harness_without_level5_part_b
    assert h.pipeline.health_check() is True


def test_level5_part_b_unavailable_proactive_check_never_crashes(
    pipeline_harness_without_level5_part_b,
):
    """_maybe_enqueue_wellness_prompt()/the pattern-detection and
    recommendation-generation jobs are simply never registered when
    their own dependency is None (see CommunicationPipeline.start()'s
    own None-guards) — calling the still-widened dispatcher directly
    proves it degrades to an honest, inert no-op rather than raising."""
    h = pipeline_harness_without_level5_part_b
    h.pipeline._check_and_announce_priority_item()
    assert h.priority_queue_manager.peek_next() is None


def test_scheduled_reminder_still_works_when_level5_part_b_is_unavailable(
    pipeline_harness_without_level5_part_b, wait_for_dormant
):
    """SCHEDULED_REMINDER's own announcement path is entirely independent
    of Level 5 Part B — confirmed directly through the null-fallback
    graph, not merely assumed from the None-guards' own code shape.
    Enqueued directly (mirroring test_scheduler_integration.py's own
    _due_item() precedent) rather than waiting on ReminderEngine's real
    poll — this harness intentionally keeps scheduler_config at its slow
    production default, so real detection would never fire within this
    test's own patience; only the CONSUME/ANNOUNCE half is under test
    here."""
    from scheduler.scheduler_model import ItemType, ScheduledItem

    h = pipeline_harness_without_level5_part_b
    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
    h.wake_engine.match_on_call = 10**9

    now = datetime.now(UTC)
    item = ScheduledItem(
        item_id=str(uuid.uuid4()),
        item_type=ItemType.EVENT,
        title="check the oven",
        scheduled_at=now - timedelta(seconds=1),
        created_at=now,
    )
    h.priority_queue_manager.enqueue(item, PriorityLevel.SCHEDULED_REMINDER, source="test")

    h.pipeline._check_and_announce_priority_item()

    assert h.tts.speak_calls, "Scheduled reminder was never announced."
    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text == "check the oven"

    wait_for_dormant(h.quiet_mode_controller, timeout=_TURN_TIMEOUT)
