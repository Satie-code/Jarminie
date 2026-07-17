"""Shared test fixtures for voice/ unit tests.

Plain helper functions can't be imported across files here (tests/ has no
__init__.py, by convention since Sprint 1.1 — see docs/sprint_book/
sprint_1_1.md), so shared helpers are exposed as fixtures instead, same
pattern as tests/unit/ui/conftest.py.
"""

import threading

import pytest

from config.schema import VoiceConfig


class FakeAudioBackend:
    """In-memory AudioBackend double — never touches real hardware.

    Returns synthetic silent frames and records every call so tests can
    assert on interaction, plus toggles to simulate open/read failures
    (a disconnected or unavailable device).
    """

    def __init__(self) -> None:
        self.is_open = False
        self.opened_with: tuple[int | None, int] | None = None
        self.read_calls: list[int] = []
        self.raise_on_open = False
        self.raise_on_read = False

    def open(self, device_index: int | None, sample_rate_hz: int) -> None:
        if self.raise_on_open:
            raise RuntimeError("simulated device open failure")
        self.is_open = True
        self.opened_with = (device_index, sample_rate_hz)

    def read(self, num_frames: int) -> bytes:
        self.read_calls.append(num_frames)
        if self.raise_on_read:
            raise RuntimeError("simulated device disconnect")
        return b"\x00\x00" * num_frames

    def close(self) -> None:
        self.is_open = False


@pytest.fixture
def fake_audio_backend() -> FakeAudioBackend:
    return FakeAudioBackend()


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


@pytest.fixture
def voice_config_factory():
    """Factory fixture: build a VoiceConfig with sensible defaults,
    overridable per test via keyword arguments."""

    def _make(**overrides):
        defaults = dict(
            wake_phrases=["hey jarminei"],
            jarvis_voice_id="jarvis_default",
            minie_voice_id="minie_default",
            mic_device_index=None,
            mic_sample_rate_hz=16000,
        )
        defaults.update(overrides)
        return VoiceConfig(**defaults)

    return _make
