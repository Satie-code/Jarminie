"""Unit tests for voice.microphone."""

import pytest

from voice.errors import MicrophoneError
from voice.microphone import MicrophoneManager, MicrophoneMode


def test_start_opens_backend_and_enters_passive_listening(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)

    manager.start()

    assert fake_audio_backend.is_open
    assert fake_audio_backend.opened_with == (None, 16000)
    assert manager.current_mode() is MicrophoneMode.PASSIVE_LISTENING


def test_stop_closes_backend(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)
    manager.start()

    manager.stop()

    assert not fake_audio_backend.is_open


def test_health_check_false_before_start(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)

    assert manager.health_check() is False


def test_health_check_true_after_start(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)

    manager.start()

    assert manager.health_check() is True


def test_health_check_false_after_stop(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)
    manager.start()

    manager.stop()

    assert manager.health_check() is False


def test_read_frame_delegates_to_backend_with_frame_size_derived_from_sample_rate(
    fake_audio_backend, voice_config_factory
):
    manager = MicrophoneManager(voice_config_factory(mic_sample_rate_hz=16000), fake_audio_backend)
    manager.start()

    frame = manager.read_frame()

    # 30ms at 16000Hz = 480 samples; FakeAudioBackend returns 2 bytes/sample.
    assert fake_audio_backend.read_calls == [480]
    assert frame == b"\x00\x00" * 480


def test_read_frame_scales_with_a_different_sample_rate(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(mic_sample_rate_hz=8000), fake_audio_backend)
    manager.start()

    manager.read_frame()

    assert fake_audio_backend.read_calls == [240]


def test_read_frame_raises_before_start(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)

    with pytest.raises(MicrophoneError, match="before start"):
        manager.read_frame()


def test_read_frame_raises_while_muted(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)
    manager.start()
    manager.set_mode(MicrophoneMode.MUTED)

    with pytest.raises(MicrophoneError, match="MUTED"):
        manager.read_frame()

    assert fake_audio_backend.read_calls == []


def test_read_frame_works_in_active_capture_mode(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)
    manager.start()
    manager.set_mode(MicrophoneMode.ACTIVE_CAPTURE)

    manager.read_frame()

    assert fake_audio_backend.read_calls == [480]


def test_read_frame_backend_failure_raises_microphone_error_and_marks_unhealthy(
    fake_audio_backend, voice_config_factory
):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)
    manager.start()
    fake_audio_backend.raise_on_read = True

    with pytest.raises(MicrophoneError):
        manager.read_frame()

    assert manager.health_check() is False


def test_set_mode_raises_before_start(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)

    with pytest.raises(MicrophoneError, match="before start"):
        manager.set_mode(MicrophoneMode.ACTIVE_CAPTURE)


def test_set_mode_raises_after_stop(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)
    manager.start()
    manager.stop()

    with pytest.raises(MicrophoneError, match="after stop"):
        manager.set_mode(MicrophoneMode.ACTIVE_CAPTURE)


@pytest.mark.parametrize(
    "mode", [MicrophoneMode.PASSIVE_LISTENING, MicrophoneMode.ACTIVE_CAPTURE, MicrophoneMode.MUTED]
)
def test_set_mode_accepts_every_mode_while_open(mode, fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)
    manager.start()

    manager.set_mode(mode)

    assert manager.current_mode() is mode


def test_only_one_mode_is_current_at_a_time(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)
    manager.start()

    manager.set_mode(MicrophoneMode.ACTIVE_CAPTURE)
    assert manager.current_mode() is MicrophoneMode.ACTIVE_CAPTURE

    manager.set_mode(MicrophoneMode.MUTED)
    assert manager.current_mode() is MicrophoneMode.MUTED


def test_stop_resets_internal_state_even_if_backend_close_raises(
    fake_audio_backend, voice_config_factory
):
    """Sprint 2.13 hardening (scenario a): a real disconnected device can
    make close() itself raise — is_open/mode must still reset (try/finally)
    so a later call doesn't incorrectly believe the device is still open."""
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)
    manager.start()
    fake_audio_backend.raise_on_close = True

    manager.stop()  # must not raise

    assert manager.health_check() is False
    with pytest.raises(MicrophoneError, match="before start"):
        manager.read_frame()


def test_restart_after_a_failed_close_reopens_cleanly(fake_audio_backend, voice_config_factory):
    """Confirms stop() (even when its own close() failed) leaves the
    manager in a state where start() can be called again — the same
    stop()-then-start() sequence CoreManager.restart_module() performs."""
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)
    manager.start()
    fake_audio_backend.raise_on_close = True
    manager.stop()
    fake_audio_backend.raise_on_close = False

    manager.start()

    assert manager.health_check() is True
    assert manager.current_mode() is MicrophoneMode.PASSIVE_LISTENING


def test_flush_stale_audio_delegates_to_the_backend(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)
    manager.start()

    manager.flush_stale_audio()

    assert fake_audio_backend.flush_calls == 1


class _DiscardingAudioBackend:
    """Local double (not the shared fake_audio_backend fixture, whose
    frame_queue also has to double as scripted test content elsewhere and
    so can't safely be cleared by flush()): a minimal backend where
    flush() genuinely discards whatever's queued, mirroring
    SoundDeviceAudioBackend's real read_available-draining behavior."""

    def __init__(self) -> None:
        self.is_open = False
        self.frame_queue: list[bytes] = []

    def open(self, device_index: int | None, sample_rate_hz: int) -> None:
        self.is_open = True

    def read(self, num_frames: int) -> bytes:
        if self.frame_queue:
            return self.frame_queue.pop(0)
        return b"\x00\x00" * num_frames

    def flush(self) -> None:
        self.frame_queue.clear()

    def close(self) -> None:
        self.is_open = False


def test_flush_stale_audio_discards_buffered_frames_before_any_read(voice_config_factory):
    """Post-release fix: a frame already sitting in the backend's buffer
    (e.g. the tail end of a just-spoken wake phrase) must never reach a
    caller of read_frame() once flushed."""
    backend = _DiscardingAudioBackend()
    manager = MicrophoneManager(voice_config_factory(), backend)
    manager.start()
    backend.frame_queue = [b"\xff\x7f" * 480]  # simulated stale backlog

    manager.flush_stale_audio()
    frame = manager.read_frame()

    assert frame == b"\x00\x00" * 480  # fresh silent frame, not the stale one


def test_flush_stale_audio_raises_before_start(fake_audio_backend, voice_config_factory):
    manager = MicrophoneManager(voice_config_factory(), fake_audio_backend)

    with pytest.raises(MicrophoneError, match="before start"):
        manager.flush_stale_audio()
