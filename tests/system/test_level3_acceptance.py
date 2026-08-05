"""Level 3 — Intelligence formal Acceptance Pass (Sprint 3.14).

One continuous scripted multi-turn conversation exercising memory
storage/recall, the User Override Rule, confidence scoring, persona
switching via real Context Analysis, and the full Decision Engine
pipeline together — asserting every Phase 3.1 ("Memory stored correctly.
Retrieval accurate."), 3.2 ("Scores update correctly. Memory lifecycle
functions."), and 3.3 ("Correct subsystem selected. Explainability
preserved.") acceptance criterion from 04_Master_Implementation_Plan.md
together, in a single real run, through a real CoreManager.startup()/
shutdown() with the entire Level 1+2+3 module graph registered (see
conftest.py's app_harness).

Fakes stand in only at the audio-hardware/ML boundary (mic, wake engine,
STT, TTS, and the Ollama-backed LanguageModelClient) — real MemoryStore/
Chroma/SQLite throughout, the same convention as tests/integration/ and
every Level 3 unit test. Real Ollama + real ChromaDB embedding model
verification is a separate, opt-in pass — see
test_level3_real_model_verification.py.

PriorityQueueManager.classify_resource_alert() has no live caller
anywhere in the real turn-processing path (see
docs/backlog/technical_debt.md item 17, found during this sprint's own
adversarial re-read) — the simulated critical ResourceMonitor alert
below is therefore exercised directly against the harness's real
PriorityQueueManager/ResourceMonitor, not through a spoken conversation
turn, consistent with that finding rather than pretending a live wiring
exists.
"""

import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from decision.priority_queue import PriorityLevel
from memory.confidence_scorer import ConfidenceBand
from memory.models import MemoryRecord, MemoryType

_WAIT_TIMEOUT = 5.0

_OVERRIDE_TRANSCRIPT = "remember that the project deadline is Friday, this is important"


def _reset_wake_detection(h) -> None:
    """See tests/integration/test_decision_engine_integration.py's own
    copy of this helper for the full rationale (a real, previously-
    reproduced timing race, Sprint 3.12) — duplicated here rather than
    shared via conftest since tests/ has no cross-file plain-function
    imports (no __init__.py, by convention since Sprint 1.1)."""
    h.wake_engine.calls = 0


def test_full_level3_acceptance_scripted_conversation(
    app_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    h = app_harness

    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)
    session_id = h.session_manager._session.session_id

    # --- Turn 1: a fact worth remembering, triggering the User Override
    # Rule (Phase 3.2: "Scores update correctly.") -------------------------
    # _OVERRIDE_TRANSCRIPT deliberately contains a phrase from BOTH
    # MemoryConfig.short_term_salience_triggers ("remember that") AND
    # override_trigger_phrases ("this is important") — the two lists are
    # independent (voice/pipeline.py's own Engineering Decision, Sprint
    # 3.12), so a real override requires both to fire on the same turn.
    h.stt.pending_transcripts.append(_OVERRIDE_TRANSCRIPT)
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)
    assert h.persona_manager.active_persona().name == "jarvis"

    promoted = [
        r
        for r in h.short_term_memory.active_context_memories(session_id)
        if r.content == _OVERRIDE_TRANSCRIPT
    ]
    assert len(promoted) == 1
    overridden_record_id = promoted[0].id
    overridden = h.memory_store.get_by_id(overridden_record_id)
    assert overridden.confidence_score == 100.0
    assert overridden.user_override is True
    assert h.confidence_scorer.band(overridden.confidence_score) is ConfidenceBand.PERMANENT

    # --- Turn 2: a casual question — Minie selected via real Context
    # Analysis, not the Level 2 keyword heuristic (Phase 3.3: "Correct
    # subsystem selected.") ------------------------------------------------
    h.tts.spoken_event.clear()
    h.llm_client.context_response = (
        "TOPIC: feelings\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: MINIE\nSENTIMENT: NEUTRAL"
    )
    h.stt.pending_transcripts.append("just checking in, how are things")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)
    assert h.persona_manager.active_persona().name == "minie"

    # --- Turn 3: a technical question referencing turn 1's fact —
    # MemoryRetrievalEngine surfaces the overridden memory via Short-Term
    # Memory's session-scoped keyword-overlap path (deterministic,
    # independent of real embedding-model behavior — see this module's
    # own docstring), and it genuinely reaches the Response Generation
    # prompt (Phase 3.1: "Retrieval accurate."; 0.4.2 replaces the old
    # Level 2 templated placeholder with real generation — see
    # docs/changelog/0.4.2-conversational-response-generation.md).
    # PERSONA: JARVIS switches back so the reply's persona is known for
    # the assertion below. -----------------------------------------------
    h.tts.spoken_event.clear()
    h.llm_client.context_response = (
        "TOPIC: project deadline\nENTITIES: NONE\nREFERENCES_PAST: YES\n"
        "PERSONA: JARVIS\nSENTIMENT: NEUTRAL"
    )
    h.stt.pending_transcripts.append("what's the project deadline again")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)
    assert h.persona_manager.active_persona().name == "jarvis"
    third_reply, _ = h.tts.speak_calls[2]
    assert third_reply.replace("... ", "") == h.llm_client.conversational_response

    generation_prompts = [c for c in h.llm_client.calls if "Reply to the user directly" in c]
    assert len(generation_prompts) == 3  # one real generation call per turn so far
    assert _OVERRIDE_TRANSCRIPT in generation_prompts[2]  # the real, retrieved memory content

    # --- Simulated critical ResourceMonitor alert (Phase 3.3's Priority
    # Evaluation stage) — exercised directly; see this module's own
    # docstring for why no live conversation turn can reach this path
    # today. ------------------------------------------------------------
    critical_snapshot = replace(
        h.resource_monitor.sample(), cpu_percent=99.9, timestamp=datetime.now(UTC)
    )
    alerts = h.resource_monitor.critical_alerts(critical_snapshot)
    assert any(alert.resource == "cpu" for alert in alerts)
    priority = h.priority_queue_manager.classify_resource_alert(alerts[0])
    assert priority is PriorityLevel.IMPORTANT_ALERT

    # --- MemoryLifecycleManager.run_cleanup_pass() invoked directly
    # (Phase 3.2: "Memory lifecycle functions.") — the turn-1 memory is
    # excluded (user_override=True), while an unrelated low-confidence
    # fixture record is correctly removed. A genuinely stale
    # last_accessed_at/created_at (365 days) is required to actually
    # land in the Temporary band (0-29) under the real Dynamic Memory
    # Formula — PersonaScopedMemory.remember() has no way to backdate a
    # record, so this stores one directly via MemoryStore, the same
    # "construct MemoryRecord by hand for a specific band" technique
    # tests/unit/memory/test_lifecycle_manager.py's own fixtures use. ----
    h.confidence_scorer._memory_config.cleanup_grace_period_days = 0
    stale_timestamp = datetime.now(UTC) - timedelta(days=365)
    stale_record_id = h.memory_store.store(
        MemoryRecord(
            memory_type=MemoryType.SHARED,
            content="an unrelated, low-confidence fixture record",
            category="not_in_the_importance_table",
            created_at=stale_timestamp,
            last_accessed_at=stale_timestamp,
        )
    )
    report = h.memory_lifecycle_manager.run_cleanup_pass()

    assert stale_record_id in report.deleted_record_ids
    assert h.memory_store.get_by_id(stale_record_id) is None
    assert overridden_record_id not in report.deleted_record_ids
    assert h.memory_store.get_by_id(overridden_record_id) is not None

    # --- Silence timeout ends the session, back to Quiet Mode — the full
    # cycle back to where JARMINEI started (same closing shape as the
    # Level 2 acceptance test). -------------------------------------------
    wait_for_dormant(h.quiet_mode_controller)
    assert h.mic.current_mode().value == "passive_listening"
    assert not h.session_manager.is_active()

    # Every Level 1+2+3 module is registered, was actually running, and
    # is visible via the same module_states() Status Panel already
    # renders generically. The two Level 4 additions ("action_audit_log",
    # "workflow_store") are Sprint 4.11's own Workflow & Device Control
    # Integration; the two Level 4 Part B additions ("task_scheduler",
    # "calendar_store") are Sprint 4.18's own Scheduler & Internet Agent
    # Integration — all part of the same shared app_harness object graph.
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
    }
    assert all(state == "running" for state in states.values())


# --- Sprint 3.13 hardening scenarios, re-confirmed at the system level -----
# (Objective 2: "Re-confirmation of all six of Sprint 3.13's hardening
# scenarios at the system level.") Scenarios (c) confidence-scoring edge
# cases, (d) lifecycle cleanup partial failure, and (e) AuthorityEvaluator's
# internal safe-default are pure component-level concerns with no
# composition-dependent behavior — already covered thoroughly by dedicated
# unit tests (tests/unit/memory/test_confidence_scorer.py,
# tests/unit/memory/test_lifecycle_manager.py,
# tests/unit/decision/test_authority.py) and re-confirmed again at the
# integration level (tests/integration/test_decision_engine_hardening.py);
# re-testing them a third time through the full CoreManager graph would add
# no new coverage. Scenarios (a), (b), and (f) genuinely benefit from a
# system-level re-confirmation, since each is about the full conversation
# continuing successfully end to end, which only a real CoreManager-driven
# run can demonstrate.


def test_full_conversation_continues_when_ollama_entirely_unreachable(
    app_harness, wait_for_active_capture, push_utterance, caplog
):
    """Scenario (a), system level: a full conversation turn through the
    real CoreManager-started graph completes with a degraded-but-present
    reply when Ollama is entirely unreachable. 0.4.2: ResponseGenerator's
    own call ALSO fails (should_raise makes every call raise), so the
    reply is genuinely the Level 2 templated fallback, not real
    generation — confirmed via the log message its own fallback emits,
    not just the reply text."""
    h = app_harness
    h.llm_client.should_raise = True
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    with caplog.at_level(logging.WARNING):
        h.stt.pending_transcripts.append("what time is it right now")
        push_utterance(h.audio_backend)
        assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)

    reply_text, _ = h.tts.speak_calls[0]
    # .replace("... ", ""): Sprint 5.14's VoicePersonalityModulator.shape_pacing()
    # now really runs on every spoken reply, inserting pacing markers at
    # existing sentence/clause boundaries — stripping them reconstructs
    # the original text exactly (that module's own structural guarantee).
    assert reply_text.replace("... ", "") == 'Understood. You said: "what time is it right now".'
    assert h.intent_detector.health_check() is False
    assert h.context_analyzer.health_check() is False
    assert any("Response Generator call failed" in r.message for r in caplog.records)


def test_full_conversation_continues_when_chromadb_entirely_unreachable(
    app_harness, wait_for_active_capture, push_utterance, monkeypatch
):
    """Scenario (b), system level: a previously-stored, genuinely
    relevant memory becomes invisible to retrieval rather than crashing
    the turn, when ChromaDB is entirely unreachable. Ollama itself is
    unaffected, so ResponseGenerator still produces a real, generated
    reply (0.4.2) — the generation prompt simply carries no
    memory-grounding block."""
    h = app_harness
    h.persona_scoped_memory.remember(MemoryType.JARVIS, "the project deadline is Friday")

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated ChromaDB outage")

    monkeypatch.setattr(h.memory_store._chroma_client, "query", _raise)

    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    h.stt.pending_transcripts.append("what's my project deadline")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)

    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text.replace("... ", "") == h.llm_client.conversational_response

    generation_prompts = [c for c in h.llm_client.calls if "Reply to the user directly" in c]
    assert len(generation_prompts) == 1
    assert "Friday" not in generation_prompts[0]


def test_unexpected_decision_pipeline_exception_does_not_end_the_session(
    app_harness, wait_for_active_capture, push_utterance, monkeypatch
):
    """Scenario (f), system level: an unexpected bug in a Decision Engine
    stage with no fail-safe contract of its own (simulated here as a
    raising MemoryRetrievalEngine.retrieve()) degrades the turn rather
    than ending the session — the conversation continues (a second turn
    in the SAME session succeeds normally). 0.4.2: ResponseGenerator
    tolerates decision_trace=None by design, so the reply is still a
    real, generated one — only the trace-derived grounding was lost, not
    the reply's realness."""
    h = app_harness

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated unexpected Decision Engine bug")

    monkeypatch.setattr(h.memory_retrieval_engine, "retrieve", _raise)

    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)
    session_id = h.session_manager._session.session_id

    h.stt.pending_transcripts.append("what time is it right now")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)

    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text.replace("... ", "") == h.llm_client.conversational_response
    assert h.session_manager.is_active()  # NOT ended — still the same session
    assert h.session_manager._session.session_id == session_id
