"""Unit tests for voice.session_manager.

Uses small timing values (session_timeout_seconds, utterance_silence_ms,
max_utterance_seconds) so these tests run fast — synchronization on actual
events (threading.Event) rather than sleeping-and-hoping wherever possible.
"""

import threading

import pytest

from voice.errors import SessionError
from voice.microphone import MicrophoneManager, MicrophoneMode
from voice.session_manager import SessionEndReason, VoiceSessionManager

_WAIT_TIMEOUT = 2.0


@pytest.fixture
def started_mic(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)
    manager.start()
    return manager


@pytest.fixture
def turn_complete_event():
    return threading.Event()


@pytest.fixture
def session_ended_event():
    return threading.Event()


@pytest.fixture
def manager_factory(
    started_mic, fake_stt, fake_tts, voice_config_factory, turn_complete_event, session_ended_event
):
    """Factory fixture: build a VoiceSessionManager wired to the shared
    fakes, recording turns/end-reasons into caller-provided lists and
    setting the shared events so tests can wait deterministically."""

    def _make(turns: list | None = None, end_reasons: list | None = None, **overrides):
        turns = turns if turns is not None else []
        end_reasons = end_reasons if end_reasons is not None else []
        overrides.setdefault("utterance_silence_ms", 30)
        overrides.setdefault("utterance_silence_threshold", 0.02)
        overrides.setdefault("max_utterance_seconds", 1.0)
        overrides.setdefault("session_timeout_seconds", 30.0)
        config = voice_config_factory(**overrides)

        def on_turn_complete(transcript, session_id):
            turns.append((transcript, session_id))
            turn_complete_event.set()

        def on_session_ended(reason):
            end_reasons.append(reason)
            session_ended_event.set()

        return VoiceSessionManager(
            started_mic, fake_stt, fake_tts, config, on_turn_complete, on_session_ended
        )

    return _make


def test_begin_session_switches_mic_to_active_capture(started_mic, manager_factory):
    manager = manager_factory()

    manager.begin_session()

    assert started_mic.current_mode() is MicrophoneMode.ACTIVE_CAPTURE
    assert manager.is_active() is True
    manager.end_session(SessionEndReason.EXPLICIT_END)


def test_end_session_returns_mic_to_passive(started_mic, manager_factory):
    manager = manager_factory()
    manager.begin_session()

    manager.end_session(SessionEndReason.EXPLICIT_END)

    assert started_mic.current_mode() is MicrophoneMode.PASSIVE_LISTENING
    assert manager.is_active() is False


def test_begin_session_flushes_stale_buffered_audio(
    started_mic, manager_factory, fake_audio_backend
):
    """Post-release fix: begin_session() must flush whatever's already
    buffered (typically the just-spoken wake phrase itself, since
    wake-word detection has inherent lag) before listening for the real
    command. The actual discard behavior (not just that flush() gets
    called) is verified directly, non-racily, in test_microphone.py's
    own test_flush_stale_audio_discards_buffered_frames_before_any_read —
    this fake's flush() is a pure call-counter, since frame_queue here is
    also how every test in this file scripts utterance content, often
    pre-loaded before begin_session() runs."""
    manager = manager_factory()

    manager.begin_session()

    assert fake_audio_backend.flush_calls == 1
    manager.end_session(SessionEndReason.EXPLICIT_END)


def test_end_session_is_idempotent(manager_factory):
    end_reasons = []
    manager = manager_factory(end_reasons=end_reasons)
    manager.begin_session()

    manager.end_session(SessionEndReason.EXPLICIT_END)
    manager.end_session(SessionEndReason.ERROR)  # second call must be a no-op

    assert end_reasons == [SessionEndReason.EXPLICIT_END]


def test_utterance_boundary_detected_after_trailing_silence(
    manager_factory, turn_complete_event, fake_stt, fake_audio_backend, loud_frame
):
    fake_audio_backend.frame_queue = [loud_frame, loud_frame, loud_frame]
    turns = []
    manager = manager_factory(turns=turns)

    manager.begin_session()
    try:
        assert turn_complete_event.wait(timeout=_WAIT_TIMEOUT)
    finally:
        manager.end_session(SessionEndReason.EXPLICIT_END)

    assert len(turns) == 1
    assert turns[0][0] == fake_stt.text
    assert len(fake_stt.calls) == 1
    # the buffered audio includes the 3 loud frames plus trailing silence
    assert fake_stt.calls[0].startswith(loud_frame * 3)


def test_speak_reply_calls_tts_and_rearms_listening_for_next_turn(
    manager_factory, turn_complete_event, fake_tts, fake_audio_backend, loud_frame
):
    fake_audio_backend.frame_queue = [loud_frame]
    turns = []
    manager = manager_factory(turns=turns)
    manager.begin_session()
    assert turn_complete_event.wait(timeout=_WAIT_TIMEOUT)
    turn_complete_event.clear()

    # queue a second utterance for the next turn, then speak the reply
    fake_audio_backend.frame_queue = [loud_frame]
    manager.speak_reply("hello back", "p340")

    assert fake_tts.calls == [("hello back", "p340")]
    try:
        assert turn_complete_event.wait(timeout=_WAIT_TIMEOUT)
    finally:
        manager.end_session(SessionEndReason.EXPLICIT_END)
    assert len(turns) == 2


def test_speak_reply_outside_session_raises(manager_factory):
    manager = manager_factory()

    with pytest.raises(SessionError, match="outside an active session"):
        manager.speak_reply("hello", "p340")


def test_stt_failure_ends_session_with_error(
    manager_factory, session_ended_event, fake_stt, started_mic, fake_audio_backend, loud_frame
):
    fake_audio_backend.frame_queue = [loud_frame]
    fake_stt.should_raise = True
    end_reasons = []
    manager = manager_factory(end_reasons=end_reasons)

    manager.begin_session()

    assert session_ended_event.wait(timeout=_WAIT_TIMEOUT)
    assert end_reasons == [SessionEndReason.ERROR]
    assert started_mic.current_mode() is MicrophoneMode.PASSIVE_LISTENING


def test_microphone_disconnect_mid_capture_ends_session_with_error(
    manager_factory, session_ended_event, started_mic, fake_audio_backend
):
    """Sprint 2.13 hardening (scenario a), isolated at the
    VoiceSessionManager level: a device disconnect during utterance
    capture (not just a transcription failure) must also end the session
    gracefully and return the microphone to passive listening."""
    end_reasons = []
    manager = manager_factory(end_reasons=end_reasons)

    manager.begin_session()
    fake_audio_backend.raise_on_read = True

    assert session_ended_event.wait(timeout=_WAIT_TIMEOUT)
    assert end_reasons == [SessionEndReason.ERROR]
    assert started_mic.current_mode() is MicrophoneMode.PASSIVE_LISTENING


def test_silence_timeout_ends_session_when_no_activity(manager_factory, session_ended_event):
    end_reasons = []
    manager = manager_factory(
        end_reasons=end_reasons, session_timeout_seconds=0.2, max_utterance_seconds=10.0
    )
    manager.start()

    manager.begin_session()

    assert session_ended_event.wait(timeout=_WAIT_TIMEOUT)
    assert end_reasons == [SessionEndReason.SILENCE_TIMEOUT]
    manager.stop()


def test_completed_turn_resets_the_timeout_window(
    manager_factory, turn_complete_event, fake_audio_backend, loud_frame
):
    """A turn completing shortly before the timeout would otherwise fire
    must reset the window — the session should still be alive well past
    the original deadline."""
    fake_audio_backend.frame_queue = [loud_frame]
    end_reasons = []
    manager = manager_factory(
        end_reasons=end_reasons,
        session_timeout_seconds=0.3,
        utterance_silence_ms=30,
        max_utterance_seconds=10.0,
    )
    manager.start()

    manager.begin_session()
    assert turn_complete_event.wait(timeout=_WAIT_TIMEOUT)

    # The turn completed well within the 0.3s window, resetting last_activity_at.
    # Confirm the session is still alive immediately after (not already ended).
    assert manager.is_active() is True
    assert end_reasons == []

    manager.stop()


def test_max_utterance_seconds_caps_unbounded_buffering(
    manager_factory, turn_complete_event, fake_audio_backend, loud_frame
):
    """If speech never pauses long enough to trigger silence detection,
    the safety cap still ends the utterance."""
    fake_audio_backend.frame_queue = [loud_frame] * 200  # never runs out mid-test
    turns = []
    manager = manager_factory(turns=turns, utterance_silence_ms=5000, max_utterance_seconds=0.1)

    manager.begin_session()
    try:
        assert turn_complete_event.wait(timeout=_WAIT_TIMEOUT)
    finally:
        manager.end_session(SessionEndReason.EXPLICIT_END)

    assert len(turns) == 1
