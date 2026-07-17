"""Unit tests for voice.speech_to_text.

whisper.load_model() is mocked in every test — loading a real model would
be far too slow for the automated suite (Resource Protection). The real,
non-mocked model/inference path is verified manually, per this sprint's
own Testing Checklist (mirrors the Sprint 2.1/2.2 precedent for real
hardware/model verification).
"""

import math
from unittest.mock import MagicMock, patch

import pytest

from config.schema import ModelConfig
from voice.errors import SpeechToTextError
from voice.speech_to_text import WhisperSpeechToText


@pytest.fixture
def model_config() -> ModelConfig:
    return ModelConfig(whisper_model="base")


def test_start_loads_the_configured_model(model_config):
    stt = WhisperSpeechToText(model_config)

    with patch("whisper.load_model") as load_model:
        load_model.return_value = MagicMock()
        stt.start()

    load_model.assert_called_once_with("base")
    assert stt.health_check() is True


def test_start_is_idempotent_without_an_intervening_stop(model_config):
    stt = WhisperSpeechToText(model_config)

    with patch("whisper.load_model") as load_model:
        load_model.return_value = MagicMock()
        stt.start()
        stt.start()

    load_model.assert_called_once()


def test_start_wraps_load_failure_in_speech_to_text_error(model_config):
    stt = WhisperSpeechToText(model_config)

    with patch("whisper.load_model", side_effect=RuntimeError("no model file")):
        with pytest.raises(SpeechToTextError, match="Failed to load Whisper model"):
            stt.start()

    assert stt.health_check() is False


def test_stop_releases_the_model(model_config):
    stt = WhisperSpeechToText(model_config)
    with patch("whisper.load_model") as load_model:
        load_model.return_value = MagicMock()
        stt.start()

    stt.stop()

    assert stt.health_check() is False


def test_health_check_false_before_start(model_config):
    stt = WhisperSpeechToText(model_config)

    assert stt.health_check() is False


def test_transcribe_before_start_raises(model_config):
    stt = WhisperSpeechToText(model_config)

    with pytest.raises(SpeechToTextError, match="before start"):
        stt.transcribe(b"\x00\x00" * 100)


def test_transcribe_returns_expected_result(model_config):
    stt = WhisperSpeechToText(model_config)
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {
        "text": "  hello jarminei  ",
        "segments": [
            {"avg_logprob": -0.1, "no_speech_prob": 0.05},
            {"avg_logprob": -0.3, "no_speech_prob": 0.1},
        ],
    }
    with patch("whisper.load_model", return_value=fake_model):
        stt.start()

    result = stt.transcribe(b"\x00\x00" * 16000)

    assert result.text == "hello jarminei"
    assert result.average_confidence == pytest.approx(math.exp(-0.2), rel=1e-6)
    assert result.no_speech_probability == pytest.approx(0.075)
    assert result.duration_ms >= 0
    fake_model.transcribe.assert_called_once()


def test_transcribe_with_no_segments_returns_zero_confidence(model_config):
    stt = WhisperSpeechToText(model_config)
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {"text": "", "segments": []}
    with patch("whisper.load_model", return_value=fake_model):
        stt.start()

    result = stt.transcribe(b"\x00\x00" * 16000)

    assert result.average_confidence == 0.0
    assert result.no_speech_probability == 1.0


def test_transcribe_suppresses_likely_hallucinated_text(model_config):
    """Regression test: Whisper's own no-speech skip can be overridden
    internally when a hallucinated segment's avg_logprob looks confident
    (discovered via real ambient-noise testing in Sprint 2.5) — a high
    no_speech_prob must suppress the text here, unconditionally."""
    stt = WhisperSpeechToText(model_config)
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {
        "text": "What's wrong with you right now?",
        "segments": [{"avg_logprob": -0.05, "no_speech_prob": 0.85}],
    }
    with patch("whisper.load_model", return_value=fake_model):
        stt.start()

    result = stt.transcribe(b"\x00\x00" * 16000)

    assert result.text == ""
    assert result.no_speech_probability == pytest.approx(0.85)


def test_transcribe_keeps_text_when_no_speech_probability_is_low(model_config):
    stt = WhisperSpeechToText(model_config)
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {
        "text": "turn on the lights",
        "segments": [{"avg_logprob": -0.2, "no_speech_prob": 0.1}],
    }
    with patch("whisper.load_model", return_value=fake_model):
        stt.start()

    result = stt.transcribe(b"\x00\x00" * 16000)

    assert result.text == "turn on the lights"


def test_transcribe_respects_configured_no_speech_threshold(model_config):
    model_config.whisper_no_speech_threshold = 0.3
    stt = WhisperSpeechToText(model_config)
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {
        "text": "maybe something",
        "segments": [{"avg_logprob": -0.2, "no_speech_prob": 0.4}],
    }
    with patch("whisper.load_model", return_value=fake_model):
        stt.start()

    result = stt.transcribe(b"\x00\x00" * 16000)

    assert result.text == ""


def test_transcribe_wraps_inference_exception_in_speech_to_text_error(model_config):
    stt = WhisperSpeechToText(model_config)
    fake_model = MagicMock()
    fake_model.transcribe.side_effect = RuntimeError("inference blew up")
    with patch("whisper.load_model", return_value=fake_model):
        stt.start()

    with pytest.raises(SpeechToTextError, match="Failed to transcribe audio"):
        stt.transcribe(b"\x00\x00" * 16000)


def test_health_check_false_after_a_mid_inference_crash(model_config):
    """Sprint 2.13 hardening (scenario b): a crash during transcribe()
    leaves the loaded model object itself untouched, so health_check()
    must track the crash separately from "is a model loaded", or a
    genuinely broken engine would keep reporting healthy."""
    stt = WhisperSpeechToText(model_config)
    fake_model = MagicMock()
    fake_model.transcribe.side_effect = RuntimeError("inference blew up")
    with patch("whisper.load_model", return_value=fake_model):
        stt.start()
    assert stt.health_check() is True

    with pytest.raises(SpeechToTextError):
        stt.transcribe(b"\x00\x00" * 16000)

    assert stt.health_check() is False


def test_health_check_recovers_after_a_subsequent_successful_transcribe(model_config):
    stt = WhisperSpeechToText(model_config)
    fake_model = MagicMock()
    fake_model.transcribe.side_effect = [
        RuntimeError("inference blew up"),
        {"text": "ok now", "segments": [{"avg_logprob": -0.1, "no_speech_prob": 0.05}]},
    ]
    with patch("whisper.load_model", return_value=fake_model):
        stt.start()

    with pytest.raises(SpeechToTextError):
        stt.transcribe(b"\x00\x00" * 16000)
    assert stt.health_check() is False

    stt.transcribe(b"\x00\x00" * 16000)

    assert stt.health_check() is True


def test_restart_after_a_failed_load_retries_cleanly(model_config):
    """Confirms start() (already the correct start()-then-start()
    idempotency behavior) also works as the retry half of
    CoreManager.restart_module() after a genuine load failure."""
    stt = WhisperSpeechToText(model_config)

    with patch("whisper.load_model", side_effect=RuntimeError("disk full")):
        with pytest.raises(SpeechToTextError):
            stt.start()
    assert stt.health_check() is False

    with patch("whisper.load_model", return_value=MagicMock()) as load_model:
        stt.start()

    load_model.assert_called_once()
    assert stt.health_check() is True


def test_transcribe_passes_the_configured_initial_prompt(model_config):
    """Post-release fix: without a vocabulary hint, Whisper's "base" model
    misheard "talk to minie" as "talk to my knee" in real end-to-end
    testing — initial_prompt biases transcription toward JARMINEI's own
    vocabulary."""
    stt = WhisperSpeechToText(model_config)
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {"text": "", "segments": []}
    with patch("whisper.load_model", return_value=fake_model):
        stt.start()

    stt.transcribe(b"\x00\x00" * 16000)

    fake_model.transcribe.assert_called_once()
    prompt = fake_model.transcribe.call_args.kwargs["initial_prompt"]
    assert prompt == model_config.whisper_initial_prompt


def test_transcribe_passes_none_when_initial_prompt_is_configured_empty(model_config):
    model_config.whisper_initial_prompt = ""
    stt = WhisperSpeechToText(model_config)
    fake_model = MagicMock()
    fake_model.transcribe.return_value = {"text": "", "segments": []}
    with patch("whisper.load_model", return_value=fake_model):
        stt.start()

    stt.transcribe(b"\x00\x00" * 16000)

    assert fake_model.transcribe.call_args.kwargs["initial_prompt"] is None
