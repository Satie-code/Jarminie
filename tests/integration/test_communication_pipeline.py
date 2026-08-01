"""Integration tests for voice.pipeline.CommunicationPipeline — the first
real, end-to-end exercise of every Level 2 (Communication) module wired
together (Sprint 2.12), plus two of Sprint 2.13's hardened failure
scenarios (a: microphone disconnect, f: SQLite write failure) confirmed
at this same real, non-mocked integration level. See conftest.py for the
shared harness and fake doubles this file (and
test_voice_pipeline_integration.py) both use. The remaining hardened
scenarios (b, c, d, e) are covered in test_voice_pipeline_integration.py
(Sprint 2.14).
"""

from voice.microphone import MicrophoneMode
from voice.quiet_mode import OperatingMode


def test_full_wake_to_reply_round_trip(
    pipeline_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Demonstrates Phase 2.1/2.2/2.3's acceptance criteria together in
    one real run: wake phrase activates JARMINEI, speech recognition
    functions, a persona composes and speaks a reply, the turn is
    persisted, and the session returns cleanly to Quiet Mode afterward."""
    h = pipeline_harness

    # Wake phrase activates JARMINEI.
    wait_for_active_capture(h.mic)
    assert h.quiet_mode_controller.current_mode() is OperatingMode.ACTIVE
    assert h.session_manager.is_active()
    session_id = h.session_manager._session.session_id

    # Speech recognition + persona reply + voice response. Deliberately a
    # transcript with no overlap with either of PersonaManager's crude
    # context-heuristic keyword lists (voice/persona_manager.py) — this
    # test is about the basic round trip, not persona-switching, which
    # test_explicit_minie_selection_switches_voice_for_next_reply covers.
    h.stt.pending_transcripts.append("what time is it right now")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=5.0)

    reply_text, voice_id = h.tts.speak_calls[0]
    assert reply_text == h.llm_client.conversational_response  # a real generated reply
    assert h.persona_manager.active_persona().name == "jarvis"  # default, unswitched
    assert voice_id == h.persona_manager.active_persona().voice_id
    assert h.persona_manager.health_check() is True  # exactly one persona active

    # The turn was actually persisted through the real Conversation
    # Session Store (2.7), not just spoken.
    recent_turns = h.conversation_store.get_recent_turns(session_id, limit=10)
    assert len(recent_turns) == 1
    assert recent_turns[0].user_text == "what time is it right now"
    assert recent_turns[0].persona_name == "jarvis"

    # Silence timeout ends the session and returns to Quiet Mode.
    wait_for_dormant(h.quiet_mode_controller)
    assert h.mic.current_mode() is MicrophoneMode.PASSIVE_LISTENING
    assert not h.session_manager.is_active()


def test_explicit_minie_selection_switches_voice_for_next_reply(
    pipeline_harness, wait_for_active_capture, push_utterance
):
    """Testing Checklist: 'an explicit "talk to Minie" utterance
    mid-conversation actually switches the active voice for the next
    reply.'"""
    h = pipeline_harness

    wait_for_active_capture(h.mic)
    assert h.persona_manager.active_persona().name == "jarvis"

    # Turn 1: ordinary utterance, default Jarvis persona replies.
    h.stt.pending_transcripts.append("what's the weather like")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=5.0)
    _, first_voice_id = h.tts.speak_calls[0]
    assert h.persona_manager.active_persona().name == "jarvis"
    assert first_voice_id == h.persona_manager.active_persona().voice_id

    # Turn 2: an explicit selection utterance switches persona and voice.
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append("talk to minie please")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=5.0)

    assert h.persona_manager.active_persona().name == "minie"
    _, second_voice_id = h.tts.speak_calls[1]
    assert second_voice_id == h.persona_manager.active_persona().voice_id
    assert second_voice_id != first_voice_id
    assert h.persona_manager.health_check() is True


def test_microphone_disconnect_mid_session_ends_session_and_returns_to_dormant(
    pipeline_harness, wait_for_active_capture, wait_for_dormant
):
    """Sprint 2.13 hardening (scenario a): a mid-session device failure
    must not crash anything — the session ends with SessionEndReason.ERROR
    and the whole system returns cleanly to Quiet Mode, ready for the next
    wake phrase."""
    h = pipeline_harness

    wait_for_active_capture(h.mic)
    assert h.quiet_mode_controller.current_mode() is OperatingMode.ACTIVE

    h.audio_backend.raise_on_read = True  # simulated device disconnect

    wait_for_dormant(h.quiet_mode_controller)
    assert h.mic.current_mode() is MicrophoneMode.PASSIVE_LISTENING
    assert not h.session_manager.is_active()


def test_conversation_store_write_failure_does_not_interrupt_the_live_session(
    pipeline_harness, wait_for_active_capture, push_utterance
):
    """Sprint 2.13 hardening (scenario f), under adversarial conditions
    within the full real pipeline rather than ConversationSessionStore in
    isolation (already covered by Sprint 2.7's own tests): a broken
    persistence layer must not stop the persona from actually replying."""
    h = pipeline_harness

    wait_for_active_capture(h.mic)
    h.conversation_store._sqlite_client.close()  # simulated persistence failure

    h.stt.pending_transcripts.append("what time is it right now")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=5.0)
    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text == h.llm_client.conversational_response  # a real generated reply
    assert h.session_manager.is_active()  # the turn completed, session still live
