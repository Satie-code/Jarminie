"""Integration-level confirmation of Sprint 2.13's remaining hardened
failure scenarios (b, c, d, e) — scenarios (a) and (f) already have
integration-level coverage in test_communication_pipeline.py. Sprint
2.14's own Testing Checklist: "each of Sprint 2.13's six hardened failure
scenarios confirmed at the integration level, not just unit level." See
conftest.py for the shared harness and fake doubles.
"""

import time

from voice.microphone import MicrophoneMode
from voice.quiet_mode import OperatingMode

_WAIT_TIMEOUT = 5.0


def test_speech_to_text_failure_ends_session_and_returns_to_dormant(
    pipeline_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Scenario (b) at integration level: a Whisper failure during a live
    session must not crash anything — the session ends gracefully and the
    whole system returns to Quiet Mode."""
    h = pipeline_harness

    wait_for_active_capture(h.mic)
    h.stt.should_raise = True
    push_utterance(h.audio_backend)

    wait_for_dormant(h.quiet_mode_controller)
    assert h.mic.current_mode() is MicrophoneMode.PASSIVE_LISTENING
    assert not h.session_manager.is_active()
    assert h.tts.speak_calls == []  # never reached speaking


def test_text_to_speech_failure_ends_session_and_returns_to_dormant(
    pipeline_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Scenario (c) at integration level: a Coqui synthesis failure must
    not crash anything — VoiceSessionManager.speak_reply() already
    contains TextToSpeechError itself (Sprint 2.5), confirmed here
    through the real, full pipeline rather than VoiceSessionManager in
    isolation."""
    h = pipeline_harness

    wait_for_active_capture(h.mic)
    h.tts.should_raise = True
    h.stt.pending_transcripts.append("what time is it right now")
    push_utterance(h.audio_backend)

    wait_for_dormant(h.quiet_mode_controller)
    assert h.mic.current_mode() is MicrophoneMode.PASSIVE_LISTENING
    assert not h.session_manager.is_active()


def test_wake_word_thread_death_is_recoverable_via_restart(pipeline_harness):
    """Scenario (d) at integration level: a device failure while dormant
    (no session active) kills the wake-word thread; the exact stop()-
    then-start() sequence CoreManager.restart_module() performs relaunches
    it, and a real wake phrase works again afterward."""
    h = pipeline_harness

    h.audio_backend.raise_on_read = True
    deadline = time.monotonic() + _WAIT_TIMEOUT
    while time.monotonic() < deadline and h.wake_word_detector.health_check():
        time.sleep(0.02)
    assert h.wake_word_detector.health_check() is False

    # Recovery: mirrors CoreManager.restart_module()'s own stop()-then-start().
    h.wake_word_detector.stop()
    h.audio_backend.raise_on_read = False
    h.wake_engine.calls = 0  # let match_on_call=2 fire again on the fresh run
    h.wake_word_detector.start()

    deadline = time.monotonic() + _WAIT_TIMEOUT
    while time.monotonic() < deadline and h.mic.current_mode() is not MicrophoneMode.ACTIVE_CAPTURE:
        time.sleep(0.02)
    assert h.mic.current_mode() is MicrophoneMode.ACTIVE_CAPTURE
    assert h.quiet_mode_controller.current_mode() is OperatingMode.ACTIVE


def test_persona_compose_reply_failure_uses_a_safe_fallback_reply(
    pipeline_harness, wait_for_active_capture, push_utterance
):
    """Scenario (e) at integration level: unlike (b)/(c)/(f), a broken
    persona must NOT abort the turn — PersonaManager.compose_reply_safely()
    (Sprint 2.13) already catches it and returns a fallback, so the turn
    completes normally and the session stays live."""
    h = pipeline_harness
    wait_for_active_capture(h.mic)

    class _BrokenPersona:
        name = "jarvis"
        voice_id = "p340"

        def compose_reply(self, transcript, context):
            raise RuntimeError("persona logic exploded")

        def describe(self):
            return "Broken — for testing"

    h.persona_manager._personas["jarvis"] = _BrokenPersona()
    h.stt.pending_transcripts.append("hello there")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)
    reply_text, voice_id = h.tts.speak_calls[0]
    assert "hello there" not in reply_text  # the broken persona never actually ran
    assert reply_text  # a safe fallback was spoken, not silence
    assert voice_id == "p340"
    assert h.session_manager.is_active()  # turn completed normally, session still live
