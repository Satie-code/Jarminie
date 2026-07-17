"""Shared test fixtures for voice/ unit tests.

Plain helper functions can't be imported across files here (tests/ has no
__init__.py, by convention since Sprint 1.1 — see docs/sprint_book/
sprint_1_1.md), so shared helpers are exposed as fixtures instead, same
pattern as tests/unit/ui/conftest.py.
"""

import threading

import pytest

from config.schema import VoiceConfig
from voice.errors import SpeechToTextError, TextToSpeechError
from voice.speech_to_text import TranscriptionResult

LOUD_FRAME = b"\xff\x7f" * 480
"""A frame of near-max-amplitude int16 samples (0x7fff), well above any
sensible utterance_silence_threshold — simulates a frame of speech."""

QUIET_FRAME = b"\x00\x00" * 480
"""A frame of digital silence — simulates a non-speech frame."""


@pytest.fixture
def loud_frame() -> bytes:
    return LOUD_FRAME


@pytest.fixture
def quiet_frame() -> bytes:
    return QUIET_FRAME


class FakeAudioBackend:
    """In-memory AudioBackend double — never touches real hardware.

    Returns synthetic silent frames and records every call so tests can
    assert on interaction, plus toggles to simulate open/read failures
    (a disconnected or unavailable device). frame_queue, if non-empty, is
    popped from first (letting tests script a loud-then-quiet sequence for
    VAD/utterance-boundary tests) before falling back to silent frames.
    """

    def __init__(self) -> None:
        self.is_open = False
        self.opened_with: tuple[int | None, int] | None = None
        self.read_calls: list[int] = []
        self.raise_on_open = False
        self.raise_on_read = False
        self.frame_queue: list[bytes] = []

    def open(self, device_index: int | None, sample_rate_hz: int) -> None:
        if self.raise_on_open:
            raise RuntimeError("simulated device open failure")
        self.is_open = True
        self.opened_with = (device_index, sample_rate_hz)

    def read(self, num_frames: int) -> bytes:
        self.read_calls.append(num_frames)
        if self.raise_on_read:
            raise RuntimeError("simulated device disconnect")
        if self.frame_queue:
            return self.frame_queue.pop(0)
        return b"\x00\x00" * num_frames

    def close(self) -> None:
        self.is_open = False


@pytest.fixture
def fake_audio_backend() -> FakeAudioBackend:
    return FakeAudioBackend()


class FakeAudioOutput:
    """In-memory AudioOutput double — never touches real hardware.

    Records every play() call so tests can assert on the audio/sample
    rate passed through, plus a toggle to simulate a playback failure.
    """

    def __init__(self) -> None:
        self.play_calls: list[tuple[bytes, int]] = []
        self.raise_on_play = False

    def play(self, audio: bytes, sample_rate_hz: int) -> None:
        self.play_calls.append((audio, sample_rate_hz))
        if self.raise_on_play:
            raise RuntimeError("simulated playback failure")


@pytest.fixture
def fake_audio_output() -> FakeAudioOutput:
    return FakeAudioOutput()


class FakeWakeWordEngine:
    """In-memory WakeWordEngine double — never loads a real model.

    process() counts calls and sets processed_event on every call (so
    tests can wait deterministically for "the loop ran" instead of
    sleeping and hoping); returns match_phrase on the configured
    match_on_call index, None otherwise. should_raise simulates an
    engine-side processing failure.
    """

    def __init__(
        self, match_on_call: int | None = None, match_phrase: str = "hey jarminei"
    ) -> None:
        self.calls = 0
        self.match_on_call = match_on_call
        self.match_phrase = match_phrase
        self.should_raise = False
        self.processed_event = threading.Event()

    def process(self, frame: bytes) -> str | None:
        call_index = self.calls
        self.calls += 1
        self.processed_event.set()
        if self.should_raise:
            raise RuntimeError("simulated wake word engine failure")
        if self.match_on_call is not None and call_index == self.match_on_call:
            return self.match_phrase
        return None


@pytest.fixture
def fake_wake_word_engine_factory():
    """Factory fixture: build a FakeWakeWordEngine, overridable per test."""

    def _make(**overrides):
        return FakeWakeWordEngine(**overrides)

    return _make


class FakeSpeechToText:
    """In-memory SpeechToText double — never loads a real model."""

    def __init__(self, text: str = "hello jarminei") -> None:
        self.text = text
        self.calls: list[bytes] = []
        self.should_raise = False

    def transcribe(self, audio: bytes) -> TranscriptionResult:
        self.calls.append(audio)
        if self.should_raise:
            raise SpeechToTextError("simulated transcription failure")
        return TranscriptionResult(text=self.text, average_confidence=0.9, duration_ms=1)


@pytest.fixture
def fake_stt() -> FakeSpeechToText:
    return FakeSpeechToText()


class FakeTextToSpeech:
    """In-memory TextToSpeech double — never loads a real model."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.should_raise = False

    def speak(self, text: str, voice_id: str) -> None:
        self.calls.append((text, voice_id))
        if self.should_raise:
            raise TextToSpeechError("simulated speech synthesis failure")


@pytest.fixture
def fake_tts() -> FakeTextToSpeech:
    return FakeTextToSpeech()


class FakeVoiceSessionManager:
    """In-memory VoiceSessionManager double — never touches a real
    microphone, STT, or TTS. begin_session() just records that it was
    called and flips is_active(); a test controls is_active() directly via
    set_active() to simulate the real session lifecycle for health_check()
    consistency checks."""

    def __init__(self) -> None:
        self.begin_session_calls = 0
        self._active = False

    def begin_session(self):
        self.begin_session_calls += 1
        self._active = True
        return None

    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = active


@pytest.fixture
def fake_session_manager() -> FakeVoiceSessionManager:
    return FakeVoiceSessionManager()


@pytest.fixture
def voice_config_factory():
    """Factory fixture: build a VoiceConfig with sensible defaults,
    overridable per test via keyword arguments."""

    def _make(**overrides):
        defaults = dict(
            wake_phrases=["hey jarminei"],
            jarvis_voice_id="p340",
            minie_voice_id="p243",
            mic_device_index=None,
            mic_sample_rate_hz=16000,
        )
        defaults.update(overrides)
        return VoiceConfig(**defaults)

    return _make
