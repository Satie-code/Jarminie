"""Unit tests for decision.llm_client.

ollama.Client is mocked in every test — no real network call is made
from the committed suite (this sprint's own Testing Checklist explicitly
defers real-Ollama verification to Sprint 3.14, mirroring the
Whisper/Coqui/openWakeWord real-model verification precedent throughout
Level 2). The wrapped-exception behavior asserted here (ResponseError,
ConnectionError, timeout) was confirmed to match the real ollama package
(0.6.2) empirically while implementing this sprint.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from config.schema import ModelConfig
from decision.llm_client import LlmError, OllamaClient


@pytest.fixture
def model_config() -> ModelConfig:
    return ModelConfig(ollama_model="llama3", ollama_host="http://localhost:11434")


def test_generate_returns_the_response_text(model_config):
    client = OllamaClient(model_config)
    fake_response = SimpleNamespace(response="CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9")
    with patch("ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.generate.return_value = fake_response

        result = client.generate("some prompt", timeout_seconds=5.0)

    assert result == "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    mock_client_cls.assert_called_once_with(host="http://localhost:11434", timeout=5.0)
    mock_client_cls.return_value.generate.assert_called_once_with(
        model="llama3", prompt="some prompt", stream=False, options=None
    )


def test_generate_passes_a_stop_sequence_as_ollama_options(model_config):
    """0.4.3 latency fix: a real, measured finding — without a real
    stop sequence, a real model reliably keeps generating well past a
    prompt's own "respond with exactly N lines" instruction (see this
    module's own LanguageModelClient docstring). Confirms stop is
    genuinely forwarded to Ollama's own options={"stop": [...]}
    mechanism, not just accepted and silently dropped."""
    client = OllamaClient(model_config)
    with patch("ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.generate.return_value = SimpleNamespace(response="ok")

        client.generate("prompt", timeout_seconds=5.0, stop=["\n\n"])

    mock_client_cls.return_value.generate.assert_called_once_with(
        model="llama3", prompt="prompt", stream=False, options={"stop": ["\n\n"]}
    )


def test_generate_omits_options_when_no_stop_sequence_given(model_config):
    """The default (stop=None) must stay a true no-op — every caller
    that existed before 0.4.3 (ResponseGenerator, Summarizer) must see
    identical behavior to before this change."""
    client = OllamaClient(model_config)
    with patch("ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.generate.return_value = SimpleNamespace(response="ok")

        client.generate("prompt", timeout_seconds=5.0)

    mock_client_cls.return_value.generate.assert_called_once_with(
        model="llama3", prompt="prompt", stream=False, options=None
    )


def test_generate_wraps_a_malformed_response_object_in_llm_error(model_config):
    """Sprint 6.19 hardening (backlog item 33): a response object
    missing its own .response attribute (a malformed/unexpected shape,
    the identical class of gap item 32 already fixed for
    BraveSearchProvider.search()) must raise LlmError, not a raw
    AttributeError this method's own docstring already promises never
    to leak."""
    client = OllamaClient(model_config)
    with patch("ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.generate.return_value = SimpleNamespace()

        with pytest.raises(LlmError, match="Ollama generate\\(\\) failed"):
            client.generate("prompt", timeout_seconds=5.0)


def test_generate_wraps_an_unpulled_model_response_error_in_llm_error(model_config):
    client = OllamaClient(model_config)
    with patch("ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.generate.side_effect = RuntimeError(
            "model 'llama3' not found (status code: 404)"
        )

        with pytest.raises(LlmError, match="Ollama generate\\(\\) failed"):
            client.generate("prompt", timeout_seconds=5.0)


def test_generate_wraps_connection_failure_in_llm_error(model_config):
    client = OllamaClient(model_config)
    with patch("ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.generate.side_effect = ConnectionError(
            "Failed to connect to Ollama."
        )

        with pytest.raises(LlmError):
            client.generate("prompt", timeout_seconds=5.0)


def test_generate_wraps_timeout_in_llm_error(model_config):
    client = OllamaClient(model_config)
    with patch("ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.generate.side_effect = TimeoutError("timed out")

        with pytest.raises(LlmError):
            client.generate("prompt", timeout_seconds=5.0)


def test_generate_constructs_a_client_with_the_given_timeout_each_call(model_config):
    """A fresh ollama.Client is built per call so timeout_seconds is a
    genuine per-call parameter — ollama.Client.generate() itself has no
    per-call timeout, only a constructor-level one."""
    client = OllamaClient(model_config)
    with patch("ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.generate.return_value = SimpleNamespace(response="ok")

        client.generate("prompt", timeout_seconds=2.5)
        client.generate("prompt", timeout_seconds=30.0)

    assert mock_client_cls.call_args_list[0].kwargs["timeout"] == 2.5
    assert mock_client_cls.call_args_list[1].kwargs["timeout"] == 30.0


def test_is_reachable_true_when_list_succeeds(model_config):
    client = OllamaClient(model_config)
    with patch("ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.list.return_value = MagicMock()

        assert client.is_reachable() is True


def test_is_reachable_false_when_list_raises(model_config):
    client = OllamaClient(model_config)
    with patch("ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.list.side_effect = ConnectionError("down")

        assert client.is_reachable() is False
