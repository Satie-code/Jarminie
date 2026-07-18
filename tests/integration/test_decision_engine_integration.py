"""Integration tests for Sprint 3.12 (Decision Engine Integration) — the
first real, end-to-end exercise of the Decision Engine pipeline
(Sprints 3.7-3.11) wired into the real Communication Pipeline (Sprint
2.12). See tests/integration/conftest.py for the shared harness: real
MemoryStore/Chroma/SQLite throughout, a fake LanguageModelClient only at
the Ollama boundary.
"""

import logging

from memory.models import MemoryType


def _reset_wake_detection(h) -> None:
    """FakeWakeWordEngine matches after a fixed number of calls,
    regardless of wall-clock time — pipeline_harness starts
    wake_word_detector as its own last setup step, so that background
    thread is already running (and may have already matched once) by the
    time a test's own body begins. Since VoiceSessionManager's inter-turn
    session_timeout_seconds watchdog starts counting from the moment
    begin_session() actually runs (voice/session_manager.py's own
    docstring: "a background watchdog thread... ends the session if no
    activity... within the window"), a wake match that happened during
    fixture setup — invisible to the test — can mean the session's own
    timeout clock has a head start the test never sees, concretely
    reproduced as a real, reliably-failing race once this sprint's extra
    Level 3 setup work (a real MemoryStore write) sat between activation
    and pushing an utterance. Resetting the call counter right before a
    test's own wait_for_active_capture() call makes the match happen
    relative to a known baseline instead — the same reset technique
    already used by test_wake_word_thread_death_is_recoverable_via_
    restart (test_voice_pipeline_integration.py) and by
    tests/system/test_level2_acceptance.py (Sprint 3.12)."""
    h.wake_engine.calls = 0


def test_full_turn_reply_measurably_differs_with_a_matching_stored_memory(
    pipeline_harness, wait_for_active_capture, push_utterance
):
    """Acceptance criterion (sprint_3_12.md): a real conversation turn
    produces a reply that measurably differs from the Level 2 templated
    placeholder for a fixture question with a matching stored memory —
    proving the Decision Engine's DecisionTrace actually reaches and
    influences compose_reply(), not just exists unused."""
    h = pipeline_harness
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    h.persona_scoped_memory.remember(MemoryType.JARVIS, "the project deadline is Friday")
    h.stt.pending_transcripts.append("what's my project deadline")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=5.0)

    reply_text, _ = h.tts.speak_calls[0]
    assert "what's my project deadline" in reply_text  # base acknowledgement still present
    assert "the project deadline is Friday" in reply_text  # the real memory, newly woven in


def test_full_turn_without_a_matching_memory_uses_the_plain_acknowledgement(
    pipeline_harness, wait_for_active_capture, push_utterance
):
    """Contrast case: with nothing stored, the reply is the plain
    acknowledgement — confirming the memory clause only appears when
    real retrieval actually found something, not unconditionally."""
    h = pipeline_harness
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    h.stt.pending_transcripts.append("what time is it right now")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=5.0)

    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text == 'Understood. You said: "what time is it right now".'


def test_persona_switches_via_context_analysis_suggested_persona(
    pipeline_harness, wait_for_active_capture, push_utterance
):
    """Acceptance criterion: persona switching driven by
    ContextAnalysis.suggested_persona (Sprint 3.8), not the Level 2
    keyword heuristic — the transcript deliberately has no overlap with
    either PersonaManager.detect_explicit_selection()'s trigger phrases
    or detect_context_heuristic()'s keyword lists, so only a real
    ContextAnalysis-driven switch could produce this result."""
    h = pipeline_harness
    h.llm_client.context_response = (
        "TOPIC: feelings\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: MINIE\nSENTIMENT: NEUTRAL"
    )
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    h.stt.pending_transcripts.append("just checking in")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=5.0)

    assert h.persona_manager.active_persona().name == "minie"


def test_explicit_selection_still_overrides_suggested_persona(
    pipeline_harness, wait_for_active_capture, push_utterance
):
    """Regression check for select_from_context()'s priority handling:
    an explicit "talk to jarvis" must still win even when the Decision
    Engine's own ContextAnalysis suggests the other persona — Sprint
    2.11's priority system (EXPLICIT_SELECTION > CONTEXT_DETECTION) must
    hold through this sprint's new call site, not just in isolation."""
    h = pipeline_harness
    h.llm_client.context_response = (
        "TOPIC: feelings\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: MINIE\nSENTIMENT: NEUTRAL"
    )
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    h.stt.pending_transcripts.append("talk to jarvis please")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=5.0)

    assert h.persona_manager.active_persona().name == "jarvis"


def test_memory_lifecycle_manager_start_runs_both_passes_and_logs_them(pipeline_harness, caplog):
    """Acceptance criterion: MemoryLifecycleManager.run_cleanup_pass()/
    run_monthly_review() are confirmed to execute once during startup,
    log-verified. Exercises the real mechanism start() itself calls
    (memory/lifecycle_manager.py's own docstring explains why start() is
    the correct, only-available hook for this at Level 3) directly,
    rather than depending on pytest fixture-initialization ordering to
    have already captured the harness's own internal startup call."""
    h = pipeline_harness

    with caplog.at_level(logging.INFO):
        h.memory_lifecycle_manager.start()

    assert any("Startup cleanup pass" in record.message for record in caplog.records)
    assert any("Startup monthly review" in record.message for record in caplog.records)
