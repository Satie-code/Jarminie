"""Integration tests for Sprint 3.13 (Error Handling & Recovery
Hardening) — the Level 3 analogue of Sprint 2.13, applying the Fail
Gracefully Rule across every new failure surface Level 3 introduced: an
external always-on AI runtime dependency (Ollama) and a dual-backend
persistence layer (SQLite + ChromaDB). See docs/sprint_book/sprint_3_13.md
for the six named scenarios (a)-(f); this file covers the ones that
genuinely need a real, wired end-to-end exercise (a, b, f) plus one
CoreManager-level startup check (a) — (c), (d), and (e) are pure
component-level concerns already covered by dedicated unit tests
(tests/unit/memory/test_confidence_scorer.py,
tests/unit/memory/test_lifecycle_manager.py,
tests/unit/decision/test_authority.py) and are not repeated here.

Uses tests/integration/conftest.py's shared pipeline_harness — fakes only
at the mic/wake-engine/STT/TTS/Ollama boundary, real MemoryStore/Chroma/
SQLite throughout, matching every other file in this directory.
"""

import logging

from config.loader import ConfigLoader
from config.schema import AppConfig, ModelConfig
from core.manager import CoreManager
from core.resource_monitor import ResourceMonitor, ResourceThresholds
from decision.context_analyzer import ContextAnalyzer
from decision.intent_detector import IntentDetector
from memory.models import MemoryType


def _reset_wake_detection(h) -> None:
    """See test_decision_engine_integration.py's own copy of this helper
    for the full rationale (a real, previously-reproduced timing race) —
    duplicated here rather than shared via conftest since it is a single
    line and tests/ has no cross-file plain-function imports (no
    __init__.py, by convention since Sprint 1.1)."""
    h.wake_engine.calls = 0


def _all_recorded_user_texts(h) -> list[str]:
    """Reaches into the real SqliteClient directly to confirm a turn was
    persisted — VoiceSessionManager generates session_id internally and
    doesn't expose it to the test, so querying by session_id (conversation_
    store.get_recent_turns()'s normal signature) isn't available here. The
    same "reach into a private collaborator for a real assertion"
    convention already used elsewhere in this suite (e.g.
    test_memory_store.py's own direct SQL probes)."""
    rows = h.conversation_store._sqlite_client.query(
        "SELECT user_text FROM conversation_turns ORDER BY timestamp DESC LIMIT 10"
    )
    return [row[0] for row in rows]


# --- Scenario (a): Ollama unreachable / model not pulled --------------------


def test_full_turn_completes_when_ollama_entirely_unreachable(
    pipeline_harness, wait_for_active_capture, push_utterance, caplog
):
    """A real conversation turn completes successfully (with a degraded-
    but-present reply) when Ollama is entirely unreachable — Intent
    Detection and Context Analysis already degrade internally to UNKNOWN/
    neutral defaults (Sprints 3.7/3.8) without raising, so the Decision
    Engine pipeline itself never even reaches Sprint 3.13's own new outer
    guard (scenario f) for this particular failure; this proves the
    already-built degrade holds under a genuinely raising client, not
    just a canned single-call mock. 0.4.2 addition: with Ollama entirely
    unreachable, ResponseGenerator.generate() (ALSO an LlmError, since
    should_raise makes every call fail regardless of prompt content) now
    falls back to the Level 2 templated reply too — the placeholder text
    below is this test's proof that the templated fallback, not real
    generation, is what actually shipped for this turn."""
    h = pipeline_harness
    h.llm_client.should_raise = True
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    with caplog.at_level(logging.WARNING):
        h.stt.pending_transcripts.append("what time is it right now")
        push_utterance(h.audio_backend)
        assert h.tts.spoken_event.wait(timeout=5.0)

    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text.replace("... ", "") == 'Understood. You said: "what time is it right now".'
    assert h.intent_detector.health_check() is False
    assert h.context_analyzer.health_check() is False
    assert any("Response Generator call failed" in r.message for r in caplog.records)


def test_startup_completes_successfully_when_ollama_entirely_unreachable(caplog):
    """Testing Checklist item: main.py's startup sequence must not abort
    when Ollama is unreachable — a clear warning is logged instead. This
    exercises the real mechanism (IntentDetector.start()/ContextAnalyzer.
    start() calling the injected client's optional is_reachable()
    capability, then CoreManager.startup()'s own per-module exception
    containment) directly at the CoreManager level, rather than building
    the full 15-module main.py graph, which the mic/wake/STT/TTS
    hardware/ML boundary would otherwise require faking anyway."""

    class _UnreachableClient:
        def is_reachable(self) -> bool:
            return False

        def generate(
            self, prompt: str, timeout_seconds: float, stop: list[str] | None = None
        ) -> str:
            raise AssertionError("generate() should never be called by this test")

    intent_detector = IntentDetector(_UnreachableClient(), ModelConfig())
    context_analyzer = ContextAnalyzer(_UnreachableClient(), ModelConfig())
    core_manager = CoreManager(
        AppConfig(), ResourceMonitor(ResourceThresholds()), ConfigLoader()
    )
    core_manager.register_module("intent_detector", intent_detector)
    core_manager.register_module("context_analyzer", context_analyzer)

    with caplog.at_level(logging.INFO):
        core_manager.startup()  # must not raise

    assert core_manager.module_states() == {
        "intent_detector": "running",
        "context_analyzer": "running",
    }
    assert core_manager.check_health("intent_detector") is False
    assert core_manager.check_health("context_analyzer") is False
    assert any("degraded state" in record.message for record in caplog.records)


# --- Scenario (b): ChromaDB unavailable or corrupted -------------------------


def test_full_turn_completes_when_chromadb_entirely_unreachable(
    pipeline_harness, wait_for_active_capture, push_utterance, monkeypatch
):
    """A real conversation turn completes successfully when ChromaDB is
    entirely unreachable: a previously-stored, genuinely relevant memory
    becomes invisible to retrieval (semantic_search() degrades to []
    rather than raising, memory/memory_store.py) rather than crashing the
    turn. Ollama itself is unaffected by this specific failure, so
    ResponseGenerator still produces a real, generated reply (0.4.2) —
    unlike the Ollama-unreachable scenario above, this degrade is scoped
    to memory retrieval only: the generation prompt simply has no
    memory-grounding block, since retrieval genuinely found nothing,
    exactly like the "no matching memory" contrast case in
    test_decision_engine_integration.py, but here because the search
    itself failed, not because nothing matched."""
    h = pipeline_harness
    h.persona_scoped_memory.remember(MemoryType.JARVIS, "the project deadline is Friday")

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated ChromaDB outage")

    monkeypatch.setattr(h.memory_store._chroma_client, "query", _raise)

    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    h.stt.pending_transcripts.append("what's my project deadline")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=5.0)

    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text.replace("... ", "") == h.llm_client.conversational_response

    generation_prompts = [c for c in h.llm_client.calls if "Reply to the user directly" in c]
    assert len(generation_prompts) == 1
    assert "Friday" not in generation_prompts[0]


# --- Scenario (f): the Decision Engine pipeline as a whole must not abort ---
# a turn ----------------------------------------------------------------------


def test_full_turn_completes_when_an_unexpected_decision_pipeline_exception_occurs(
    pipeline_harness, wait_for_active_capture, push_utterance, monkeypatch, caplog
):
    """An unexpected bug in any Decision Engine stage not already covered
    by its own fail-safe contract (simulated here as a raising
    MemoryRetrievalEngine.retrieve() — a stage with no internal try/
    except of its own, see memory/retrieval_engine.py) must not end the
    session; the turn still completes with a real, generated reply —
    ResponseGenerator tolerates decision_trace=None by design (0.4.2: it
    simply generates without trace-derived grounding), so
    voice/pipeline.py's own inner guard degrading decision_trace to None
    does not, on its own, degrade the reply to the Level 2 template
    too — that fallback is reserved for an actual LlmError."""
    h = pipeline_harness

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated unexpected Decision Engine bug")

    monkeypatch.setattr(h.memory_retrieval_engine, "retrieve", _raise)

    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)

    with caplog.at_level(logging.WARNING):
        h.stt.pending_transcripts.append("what time is it right now")
        push_utterance(h.audio_backend)
        assert h.tts.spoken_event.wait(timeout=5.0)

    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text.replace("... ", "") == h.llm_client.conversational_response
    assert any("Decision Engine pipeline failed" in r.message for r in caplog.records)
    assert not any(
        "Unexpected failure while handling a completed turn" in r.message
        for r in caplog.records
    )
    # the turn was still persisted despite the Decision Engine failure
    assert "what time is it right now" in _all_recorded_user_texts(h)
