"""Unit tests for voice.text_to_speech.

TTS.api.TTS is mocked in every test — loading a real Coqui model would be
far too slow for the automated suite (Resource Protection), same pattern
as Sprint 2.3's Whisper tests. The real, non-mocked model/audio path is
verified manually, per this sprint's own Testing Checklist.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from config.schema import ModelConfig
from voice.errors import TextToSpeechError
from voice.text_to_speech import CoquiTextToSpeech


@pytest.fixture
def model_config() -> ModelConfig:
    return ModelConfig(tts_model="tts_models/en/vctk/vits")


def _fake_tts(speakers=("p225", "p226")):
    fake = MagicMock()
    fake.speakers = list(speakers) if speakers is not None else None
    fake.tts.return_value = [0.1, -0.2, 0.3]
    fake.synthesizer.output_sample_rate = 22050
    return fake


def test_start_loads_the_configured_model(model_config, fake_audio_output):
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)

    with patch("TTS.api.TTS") as tts_cls:
        tts_cls.return_value = _fake_tts()
        tts_engine.start()

    tts_cls.assert_called_once_with(model_name="tts_models/en/vctk/vits")
    assert tts_engine.health_check() is True


def test_start_is_idempotent_without_an_intervening_stop(model_config, fake_audio_output):
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)

    with patch("TTS.api.TTS") as tts_cls:
        tts_cls.return_value = _fake_tts()
        tts_engine.start()
        tts_engine.start()

    tts_cls.assert_called_once()


def test_start_wraps_load_failure_in_text_to_speech_error(model_config, fake_audio_output):
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)

    with patch("TTS.api.TTS", side_effect=RuntimeError("no model file")):
        with pytest.raises(TextToSpeechError, match="Failed to load Coqui TTS model"):
            tts_engine.start()

    assert tts_engine.health_check() is False


def test_stop_releases_the_model(model_config, fake_audio_output):
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)
    with patch("TTS.api.TTS") as tts_cls:
        tts_cls.return_value = _fake_tts()
        tts_engine.start()

    tts_engine.stop()

    assert tts_engine.health_check() is False


def test_health_check_false_before_start(model_config, fake_audio_output):
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)

    assert tts_engine.health_check() is False


def test_speak_before_start_raises(model_config, fake_audio_output):
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)

    with pytest.raises(TextToSpeechError, match="before start"):
        tts_engine.speak("hello", "p225")


def test_speak_with_unrecognized_voice_id_raises(model_config, fake_audio_output):
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)
    with patch("TTS.api.TTS") as tts_cls:
        tts_cls.return_value = _fake_tts(speakers=("p225", "p226"))
        tts_engine.start()

    with pytest.raises(TextToSpeechError, match="Unrecognized voice_id"):
        tts_engine.speak("hello", "not_a_real_speaker")

    assert fake_audio_output.play_calls == []


@pytest.mark.parametrize("voice_id", ["p225", "p226"])
def test_speak_routes_to_the_correct_voice_and_plays_through_the_same_model(
    voice_id, model_config, fake_audio_output
):
    fake_tts = _fake_tts(speakers=("p225", "p226"))
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)
    with patch("TTS.api.TTS", return_value=fake_tts) as tts_cls:
        tts_engine.start()
        tts_engine.speak("hello there", voice_id)

    fake_tts.tts.assert_called_once_with(text="hello there", speaker=voice_id)
    tts_cls.assert_called_once()  # same running model instance, no reload
    assert len(fake_audio_output.play_calls) == 1
    audio, sample_rate = fake_audio_output.play_calls[0]
    assert sample_rate == 22050
    assert audio == np.asarray([0.1, -0.2, 0.3], dtype=np.float32).tobytes()


def test_speak_accepts_any_voice_id_when_model_has_no_known_speakers(
    model_config, fake_audio_output
):
    """A single-speaker model has no .speakers list to validate against."""
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)
    with patch("TTS.api.TTS") as tts_cls:
        tts_cls.return_value = _fake_tts(speakers=None)
        tts_engine.start()

    tts_engine.speak("hello", "anything")

    assert len(fake_audio_output.play_calls) == 1


def test_speak_wraps_synthesis_exception_in_text_to_speech_error(model_config, fake_audio_output):
    fake_tts = _fake_tts(speakers=("p225",))
    fake_tts.tts.side_effect = RuntimeError("synthesis blew up")
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)
    with patch("TTS.api.TTS", return_value=fake_tts):
        tts_engine.start()

    with pytest.raises(TextToSpeechError, match="Failed to synthesize speech"):
        tts_engine.speak("hello", "p225")


def test_speak_wraps_playback_exception_in_text_to_speech_error(model_config, fake_audio_output):
    fake_tts = _fake_tts(speakers=("p225",))
    fake_audio_output.raise_on_play = True
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)
    with patch("TTS.api.TTS", return_value=fake_tts):
        tts_engine.start()

    with pytest.raises(TextToSpeechError, match="Failed to play synthesized speech"):
        tts_engine.speak("hello", "p225")


def test_health_check_false_after_a_synthesis_failure(model_config, fake_audio_output):
    """Sprint 2.13 hardening (scenario c): a crashed speak() call leaves
    the loaded model object itself untouched, so health_check() must
    track the crash separately from "is a model loaded"."""
    fake_tts = _fake_tts(speakers=("p225",))
    fake_tts.tts.side_effect = RuntimeError("synthesis blew up")
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)
    with patch("TTS.api.TTS", return_value=fake_tts):
        tts_engine.start()
    assert tts_engine.health_check() is True

    with pytest.raises(TextToSpeechError):
        tts_engine.speak("hello", "p225")

    assert tts_engine.health_check() is False


def test_health_check_false_after_a_playback_failure(model_config, fake_audio_output):
    fake_tts = _fake_tts(speakers=("p225",))
    fake_audio_output.raise_on_play = True
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)
    with patch("TTS.api.TTS", return_value=fake_tts):
        tts_engine.start()

    with pytest.raises(TextToSpeechError):
        tts_engine.speak("hello", "p225")

    assert tts_engine.health_check() is False


def test_health_check_recovers_after_a_subsequent_successful_speak(model_config, fake_audio_output):
    fake_tts = _fake_tts(speakers=("p225",))
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)
    with patch("TTS.api.TTS", return_value=fake_tts):
        tts_engine.start()
    fake_audio_output.raise_on_play = True
    with pytest.raises(TextToSpeechError):
        tts_engine.speak("hello", "p225")
    assert tts_engine.health_check() is False

    fake_audio_output.raise_on_play = False
    tts_engine.speak("hello again", "p225")

    assert tts_engine.health_check() is True


def test_unrecognized_voice_id_does_not_affect_health(model_config, fake_audio_output):
    """A bad voice_id is a caller usage error, not evidence the engine
    itself is broken — health_check() must stay unaffected by it."""
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)
    with patch("TTS.api.TTS") as tts_cls:
        tts_cls.return_value = _fake_tts(speakers=("p225", "p226"))
        tts_engine.start()

    with pytest.raises(TextToSpeechError, match="Unrecognized voice_id"):
        tts_engine.speak("hello", "not_a_real_speaker")

    assert tts_engine.health_check() is True


def test_restart_after_a_failed_load_retries_cleanly(model_config, fake_audio_output):
    """Confirms start() also works as the retry half of
    CoreManager.restart_module() after a genuine load failure."""
    tts_engine = CoquiTextToSpeech(model_config, fake_audio_output)

    with patch("TTS.api.TTS", side_effect=RuntimeError("disk full")):
        with pytest.raises(TextToSpeechError):
            tts_engine.start()
    assert tts_engine.health_check() is False

    with patch("TTS.api.TTS") as tts_cls:
        tts_cls.return_value = _fake_tts()
        tts_engine.start()

    tts_cls.assert_called_once()
    assert tts_engine.health_check() is True
