"""Unit tests for voice.wake_word.

All tests exercise WakeWordDetector against a FakeWakeWordEngine and a real
MicrophoneManager backed by FakeAudioBackend — no real audio hardware or
openwakeword model is loaded (OpenWakeWordEngine's real behavior is
manual/real-hardware verification only, per this sprint's own Testing
Checklist, mirroring the Whisper/Coqui precedent from the Sprint Book).
"""

import threading
import time

import pytest

from voice.errors import WakeWordError
from voice.microphone import MicrophoneManager, MicrophoneMode
from voice.wake_word import WakeWordDetector

_WAIT_TIMEOUT = 2.0
_PAUSE_OBSERVE_SECONDS = 0.3
"""Long enough to span several of the listen loop's _MODE_POLL_SECONDS
(0.1s) intervals, so a regression that resumes reading frames too eagerly
would show up as engine.calls increasing during this window."""


@pytest.fixture
def started_mic(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)
    manager.start()
    return manager


def test_on_detected_fires_exactly_once_on_a_genuine_match(
    started_mic, fake_wake_word_engine_factory
):
    engine = fake_wake_word_engine_factory(match_on_call=2, match_phrase="hey jarminei")
    detected = []
    detected_event = threading.Event()

    def on_detected(phrase: str) -> None:
        detected.append(phrase)
        detected_event.set()

    detector = WakeWordDetector(started_mic, engine, on_detected)
    detector.start()
    try:
        assert detected_event.wait(timeout=_WAIT_TIMEOUT)
    finally:
        detector.stop()

    assert detected == ["hey jarminei"]


def test_on_detected_not_called_when_engine_never_matches(
    started_mic, fake_wake_word_engine_factory
):
    engine = fake_wake_word_engine_factory(match_on_call=None)
    detected = []

    detector = WakeWordDetector(started_mic, engine, detected.append)
    detector.start()
    try:
        # Wait for the loop to actually run a few times, without asserting a match.
        for _ in range(5):
            engine.processed_event.wait(timeout=_WAIT_TIMEOUT)
            engine.processed_event.clear()
    finally:
        detector.stop()

    assert detected == []
    assert engine.calls > 0


def test_start_raises_if_microphone_not_in_passive_listening_mode(
    started_mic, fake_wake_word_engine_factory
):
    started_mic.set_mode(MicrophoneMode.ACTIVE_CAPTURE)
    engine = fake_wake_word_engine_factory()
    detector = WakeWordDetector(started_mic, engine, lambda phrase: None)

    with pytest.raises(WakeWordError, match="PASSIVE_LISTENING"):
        detector.start()


def test_stop_joins_the_background_thread(started_mic, fake_wake_word_engine_factory):
    engine = fake_wake_word_engine_factory()
    detector = WakeWordDetector(started_mic, engine, lambda phrase: None)
    detector.start()
    thread_ref = detector._thread
    assert thread_ref is not None and thread_ref.is_alive()

    detector.stop()

    assert not thread_ref.is_alive()
    assert detector._thread is None


def test_health_check_false_before_start(started_mic, fake_wake_word_engine_factory):
    engine = fake_wake_word_engine_factory()
    detector = WakeWordDetector(started_mic, engine, lambda phrase: None)

    assert detector.health_check() is False


def test_health_check_true_while_running(started_mic, fake_wake_word_engine_factory):
    engine = fake_wake_word_engine_factory()
    detector = WakeWordDetector(started_mic, engine, lambda phrase: None)
    detector.start()
    try:
        assert engine.processed_event.wait(timeout=_WAIT_TIMEOUT)
        assert detector.health_check() is True
    finally:
        detector.stop()


def test_microphone_error_mid_loop_ends_thread_and_marks_unhealthy(
    started_mic, fake_wake_word_engine_factory, fake_audio_backend
):
    engine = fake_wake_word_engine_factory()
    detector = WakeWordDetector(started_mic, engine, lambda phrase: None)
    detector.start()
    assert engine.processed_event.wait(timeout=_WAIT_TIMEOUT)

    fake_audio_backend.raise_on_read = True
    thread_ref = detector._thread
    thread_ref.join(timeout=_WAIT_TIMEOUT)

    assert not thread_ref.is_alive()
    assert detector.health_check() is False


def test_restart_after_thread_death_relaunches_and_recovers(
    started_mic, fake_wake_word_engine_factory, fake_audio_backend
):
    """Sprint 2.13 hardening (scenario d): mirrors the exact stop()-then-
    start() sequence CoreManager.restart_module() performs, proving a
    dead listen thread is recoverable when a restart is invoked —
    whether by a human via Debug Console, or a future automated driver
    (see docs/sprint_book/sprint_2_13.md's Sprint Completion Report on
    why this sprint doesn't build that driver itself)."""
    engine = fake_wake_word_engine_factory()
    detector = WakeWordDetector(started_mic, engine, lambda phrase: None)
    detector.start()
    assert engine.processed_event.wait(timeout=_WAIT_TIMEOUT)

    fake_audio_backend.raise_on_read = True
    detector._thread.join(timeout=_WAIT_TIMEOUT)
    assert detector.health_check() is False

    # restart_module()'s own sequence: stop() then start() again.
    detector.stop()
    fake_audio_backend.raise_on_read = False
    engine.processed_event.clear()
    detector.start()
    try:
        assert engine.processed_event.wait(timeout=_WAIT_TIMEOUT)
        assert detector.health_check() is True
    finally:
        detector.stop()


def test_engine_processing_failure_does_not_end_passive_listening(
    started_mic, fake_wake_word_engine_factory
):
    """An engine-side failure on a single frame must not end the listen
    loop — only a genuine MicrophoneError should (see this module's
    Engineering Rationale on the two different failure paths)."""
    engine = fake_wake_word_engine_factory()
    engine.should_raise = True
    detector = WakeWordDetector(started_mic, engine, lambda phrase: None)

    detector.start()
    try:
        assert engine.processed_event.wait(timeout=_WAIT_TIMEOUT)
        assert detector._thread.is_alive()
    finally:
        engine.should_raise = False
        detector.stop()


def test_listen_loop_pauses_while_mic_not_passive_listening(
    started_mic, fake_wake_word_engine_factory
):
    """Regression test for a real bug found during Sprint 2.12's real
    end-to-end integration testing (never caught by any of this file's
    other tests, since none of them ran the listen loop concurrently with
    an active session): the loop used to call mic.read_frame()
    unconditionally, stealing frames from VoiceSessionManager's own
    utterance capture once a session made the microphone ACTIVE_CAPTURE."""
    engine = fake_wake_word_engine_factory()
    detector = WakeWordDetector(started_mic, engine, lambda phrase: None)
    detector.start()
    try:
        assert engine.processed_event.wait(timeout=_WAIT_TIMEOUT)

        started_mic.set_mode(MicrophoneMode.ACTIVE_CAPTURE)
        # A single frame already mid-flight when set_mode() runs can still
        # land (the loop only checks mode at the top of each iteration) —
        # a brief settle window absorbs that one-frame race without
        # weakening what this test actually proves: no further frames
        # after the pause takes effect.
        time.sleep(0.05)
        calls_after_switch = engine.calls

        time.sleep(_PAUSE_OBSERVE_SECONDS)

        assert engine.calls == calls_after_switch
    finally:
        started_mic.set_mode(MicrophoneMode.PASSIVE_LISTENING)
        detector.stop()


def test_listen_loop_resumes_after_mic_returns_to_passive_listening(
    started_mic, fake_wake_word_engine_factory
):
    engine = fake_wake_word_engine_factory()
    detector = WakeWordDetector(started_mic, engine, lambda phrase: None)
    detector.start()
    try:
        assert engine.processed_event.wait(timeout=_WAIT_TIMEOUT)

        started_mic.set_mode(MicrophoneMode.ACTIVE_CAPTURE)
        time.sleep(_PAUSE_OBSERVE_SECONDS)
        calls_while_paused = engine.calls
        engine.processed_event.clear()

        started_mic.set_mode(MicrophoneMode.PASSIVE_LISTENING)

        assert engine.processed_event.wait(timeout=_WAIT_TIMEOUT)
        assert engine.calls > calls_while_paused
    finally:
        detector.stop()


def test_health_check_stays_true_while_paused_for_an_active_session(
    started_mic, fake_wake_word_engine_factory
):
    """Deliberately idle (session active) must not be reported the same
    as stuck-and-failing — see _listen_loop()'s own comment on why
    _last_processed_at is still updated during the pause."""
    engine = fake_wake_word_engine_factory()
    detector = WakeWordDetector(started_mic, engine, lambda phrase: None)
    detector.start()
    try:
        assert engine.processed_event.wait(timeout=_WAIT_TIMEOUT)

        started_mic.set_mode(MicrophoneMode.ACTIVE_CAPTURE)
        time.sleep(_PAUSE_OBSERVE_SECONDS)

        assert detector.health_check() is True
    finally:
        started_mic.set_mode(MicrophoneMode.PASSIVE_LISTENING)
        detector.stop()
