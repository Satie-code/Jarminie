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
