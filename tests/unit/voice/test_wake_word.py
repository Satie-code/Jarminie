"""Unit tests for voice.wake_word.

All tests exercise WakeWordDetector against a FakeWakeWordEngine and a real
MicrophoneManager backed by FakeAudioBackend — no real audio hardware or
openwakeword model is loaded (OpenWakeWordEngine's real behavior is
manual/real-hardware verification only, per this sprint's own Testing
Checklist, mirroring the Whisper/Coqui precedent from the Sprint Book).
"""

import threading

import pytest

from voice.errors import WakeWordError
from voice.microphone import MicrophoneManager, MicrophoneMode
from voice.wake_word import WakeWordDetector

_WAIT_TIMEOUT = 2.0


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
