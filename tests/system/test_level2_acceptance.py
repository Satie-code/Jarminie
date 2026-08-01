"""Level 2 — Communication formal Acceptance Pass (Sprint 2.14).

One continuous scripted multi-turn conversation — wake, listen,
transcribe, persona reply, speak, an explicit persona switch, then a
silence timeout back to Quiet Mode — asserting every Phase 2.1, 2.2, and
2.3 acceptance criterion from 04_Master_Implementation_Plan.md together,
in a single real run, through a real CoreManager.startup()/shutdown()
with the entire Level 2 module graph registered (see conftest.py).

Fakes stand in only at the audio-hardware/ML boundary; real Whisper/
Coqui/openWakeWord verification (including this same scripted
conversation shape) was performed separately via a one-off, non-committed
scratchpad smoke script, per the precedent established at Sprint 2.12.
"""

_WAIT_TIMEOUT = 5.0


def test_full_level2_acceptance_scripted_conversation(
    app_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    h = app_harness

    # Sprint 3.12: CoreManager.startup() now starts several more modules
    # (Level 3's memory/decision graph) before returning, giving the
    # wake-word background thread real, variable extra time to run
    # during fixture setup itself — FakeWakeWordEngine's match_on_call=2
    # could otherwise already be satisfied before this test body even
    # starts, making the wake moment (and its downstream session/
    # utterance timing) non-deterministic relative to what this test
    # observes. Resetting the call counter here, right before this
    # test's own polling begins, makes the match happen relative to a
    # known baseline instead — the same reset technique already used by
    # test_wake_word_thread_death_is_recoverable_via_restart
    # (tests/integration/test_voice_pipeline_integration.py).
    h.wake_engine.calls = 0

    # Phase 2.1: "Wake phrase activates JARMINEI."
    wait_for_active_capture(h.mic)
    assert h.quiet_mode_controller.current_mode().value == "active"
    session_id = h.session_manager._session.session_id

    # Phase 2.1: "Speech recognition functions." / "Voice responses function."
    h.stt.pending_transcripts.append("what time is it right now")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)
    first_reply, first_voice_id = h.tts.speak_calls[0]
    assert first_reply == h.llm_client.conversational_response  # a real generated reply
    assert h.persona_manager.active_persona().name == "jarvis"

    # Phase 2.2: "Natural conversation maintained during session" — a
    # second turn in the SAME session (not a new wake-up).
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("what's the weather like")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)
    assert h.session_manager.is_active()
    assert h.session_manager._session.session_id == session_id  # still the same session
    assert len(h.tts.speak_calls) == 2

    # Phase 2.3: "Correct persona selected. Correct voice selected." — an
    # explicit selection switches both, mid-session.
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("talk to minie please")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)
    assert h.persona_manager.active_persona().name == "minie"
    _, third_voice_id = h.tts.speak_calls[2]
    assert third_voice_id == h.persona_manager.active_persona().voice_id
    assert third_voice_id != first_voice_id

    # Phase 2.3: "No simultaneous personas" — exactly one active flag,
    # checkable at any point (PersonaManager.health_check()'s own
    # invariant, Sprint 2.11).
    assert h.persona_manager.health_check() is True

    # All three turns were actually persisted (Phase 2.2's Conversation
    # Session Store, Sprint 2.7).
    recent_turns = h.conversation_store.get_recent_turns(session_id, limit=10)
    assert len(recent_turns) == 3
    assert [t.persona_name for t in recent_turns] == ["jarvis", "jarvis", "minie"]

    # Silence timeout ends the session and returns cleanly to Quiet Mode —
    # the full cycle back to where JARMINEI started.
    wait_for_dormant(h.quiet_mode_controller)
    assert h.mic.current_mode().value == "passive_listening"
    assert not h.session_manager.is_active()

    # Every Level 2 AND Level 3 module is registered, was actually
    # running, and is visible via the same module_states() Status Panel
    # already renders generically — zero ui/status_panel.py changes
    # needed (Sprint 2.12's own Acceptance Criteria, re-confirmed here
    # through a real CoreManager rather than assumed; the six Level 3
    # additions are Sprint 3.12's own Decision Engine Integration; the
    # two Level 4 additions are Sprint 4.11's own Workflow & Device
    # Control Integration; the two Level 4 Part B additions are Sprint
    # 4.18's own Scheduler & Internet Agent Integration, registered
    # early per that sprint's own ordering requirement).
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
    }
    assert all(state == "running" for state in states.values())
