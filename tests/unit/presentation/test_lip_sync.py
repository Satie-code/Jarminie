"""Unit tests for presentation.lip_sync (Sprint 5.11).

No real audio hardware/model involved — synthetic float32 PCM fixtures
only, the same "component before integration, fakes only" discipline as
every other Part A sprint's own fast test suite. drive_from_audio()
spawns its own background thread (mirrors VoiceSessionManager.
begin_session()'s established pattern) and returns immediately; these
tests join that thread directly (the same "reach into a private
attribute from a test" precedent test_persona_manager.py's own
_active_flags corruption tests already established) rather than polling,
for fast, deterministic assertions.
"""

import numpy as np
import pytest

from config.schema import PresentationConfig
from presentation.lip_sync import LipSyncDriver

_SAMPLE_RATE_HZ = 16000
_JOIN_TIMEOUT_SECONDS = 5.0


class _FakeAvatarRenderer:
    def __init__(self, raise_after: int | None = None) -> None:
        self.calls: list[float] = []
        self._raise_after = raise_after

    def set_mouth_open(self, amount: float) -> None:
        self.calls.append(amount)
        if self._raise_after is not None and len(self.calls) > self._raise_after:
            raise RuntimeError("set_mouth_open() exploded")


def _pcm_bytes(samples: np.ndarray) -> bytes:
    return samples.astype(np.float32).tobytes()


def _silence(num_samples: int) -> bytes:
    return _pcm_bytes(np.zeros(num_samples, dtype=np.float32))


def _constant_tone(num_samples: int, amplitude: float = 1.0) -> bytes:
    return _pcm_bytes(np.full(num_samples, amplitude, dtype=np.float32))


@pytest.fixture
def fast_config() -> PresentationConfig:
    """A tiny sampling window so the driver's own real time.sleep() calls
    keep this test file fast."""
    return PresentationConfig(lip_sync_sample_window_ms=1.0)


@pytest.fixture
def driver(fast_config) -> LipSyncDriver:
    return LipSyncDriver(fast_config)


def _run_and_join(driver: LipSyncDriver, audio: bytes, avatar: _FakeAvatarRenderer) -> None:
    driver.drive_from_audio(audio, _SAMPLE_RATE_HZ, avatar)
    driver._thread.join(timeout=_JOIN_TIMEOUT_SECONDS)
    assert not driver._thread.is_alive()  # the join above must have genuinely completed


# --- empty/malformed audio degrades to a single set_mouth_open(0.0) ----------


def test_empty_audio_calls_set_mouth_open_zero_exactly_once(driver):
    avatar = _FakeAvatarRenderer()
    _run_and_join(driver, b"", avatar)
    assert avatar.calls == [0.0]


def test_malformed_audio_buffer_degrades_to_a_single_zero_call(driver):
    """A byte length not a multiple of 4 cannot be decoded as float32 —
    np.frombuffer() raises ValueError, caught and treated as silence."""
    avatar = _FakeAvatarRenderer()
    _run_and_join(driver, b"\x00\x01\x02", avatar)
    assert avatar.calls == [0.0]


def test_zero_sample_rate_degrades_to_a_single_zero_call(driver):
    avatar = _FakeAvatarRenderer()
    driver.drive_from_audio(_silence(100), 0, avatar)
    driver._thread.join(timeout=_JOIN_TIMEOUT_SECONDS)
    assert avatar.calls == [0.0]


# --- amplitude-to-mouth-open mapping (Testing Checklist) ----------------------


def test_silence_maps_to_zero_amplitude(driver):
    avatar = _FakeAvatarRenderer()
    audio = _silence(int(_SAMPLE_RATE_HZ * 0.05))  # 50ms

    _run_and_join(driver, audio, avatar)

    # Every sampled window is 0.0, plus the guaranteed final 0.0 call.
    assert all(value == 0.0 for value in avatar.calls)
    assert avatar.calls[-1] == 0.0
    assert len(avatar.calls) > 1


def test_a_full_amplitude_constant_tone_maps_to_the_maximum(driver):
    avatar = _FakeAvatarRenderer()
    audio = _constant_tone(int(_SAMPLE_RATE_HZ * 0.05), amplitude=1.0)

    _run_and_join(driver, audio, avatar)

    sampled_values = avatar.calls[:-1]  # exclude the guaranteed final 0.0 cleanup call
    assert sampled_values  # at least one real window was sampled
    assert all(value == pytest.approx(1.0, abs=1e-6) for value in sampled_values)


def test_varying_amplitude_produces_proportionally_varying_values(fast_config):
    """A quiet half followed by a loud half must map to a quiet-then-loud
    sequence of set_mouth_open() values."""
    driver = LipSyncDriver(fast_config)
    avatar = _FakeAvatarRenderer()
    window_samples = int(_SAMPLE_RATE_HZ * fast_config.lip_sync_sample_window_ms / 1000.0)
    quiet = np.full(window_samples * 3, 0.05, dtype=np.float32)
    loud = np.full(window_samples * 3, 0.9, dtype=np.float32)
    audio = _pcm_bytes(np.concatenate([quiet, loud]))

    _run_and_join(driver, audio, avatar)

    sampled_values = avatar.calls[:-1]
    first_half = sampled_values[: len(sampled_values) // 2]
    second_half = sampled_values[len(sampled_values) // 2 :]
    assert sum(first_half) / len(first_half) < sum(second_half) / len(second_half)


def test_mouth_open_values_are_always_within_zero_and_one(driver):
    avatar = _FakeAvatarRenderer()
    audio = _constant_tone(int(_SAMPLE_RATE_HZ * 0.05), amplitude=1.0)

    _run_and_join(driver, audio, avatar)

    assert all(0.0 <= value <= 1.0 for value in avatar.calls)


# --- guaranteed final set_mouth_open(0.0), even on exception (Acceptance Criteria) -


def test_final_zero_call_fires_even_when_set_mouth_open_raises_partway_through(driver):
    avatar = _FakeAvatarRenderer(raise_after=2)
    audio = _constant_tone(int(_SAMPLE_RATE_HZ * 0.1), amplitude=0.8)  # several windows

    _run_and_join(driver, audio, avatar)

    assert avatar.calls[-1] == 0.0
    # 3 real windowed calls (the 3rd one is what triggers the raise,
    # after recording itself), then the guaranteed final 0.0 cleanup.
    assert len(avatar.calls) == 4


def test_normal_playback_always_ends_with_a_final_zero_call(driver):
    avatar = _FakeAvatarRenderer()
    audio = _constant_tone(int(_SAMPLE_RATE_HZ * 0.05), amplitude=0.5)

    _run_and_join(driver, audio, avatar)

    assert avatar.calls[-1] == 0.0
    assert avatar.calls[0] != 0.0  # the real sampled value, not immediately the cleanup call


# --- drive_from_audio() never raises, spawns and returns (Acceptance Criteria) -


def test_drive_from_audio_returns_without_raising_and_without_blocking(driver):
    avatar = _FakeAvatarRenderer()
    audio = _constant_tone(int(_SAMPLE_RATE_HZ * 0.3), amplitude=0.5)  # a "long-ish" 300ms buffer

    driver.drive_from_audio(audio, _SAMPLE_RATE_HZ, avatar)  # must return immediately

    assert driver._thread is not None
    driver._thread.join(timeout=_JOIN_TIMEOUT_SECONDS)  # cleanup for the test itself


def test_drive_from_audio_never_raises_for_a_broken_avatar_renderer(driver):
    class _AlwaysBrokenAvatarRenderer:
        def set_mouth_open(self, amount: float) -> None:
            raise RuntimeError("always broken")

    driver.drive_from_audio(_constant_tone(1000), _SAMPLE_RATE_HZ, _AlwaysBrokenAvatarRenderer())
    driver._thread.join(timeout=_JOIN_TIMEOUT_SECONDS)  # must not raise into the test itself
