"""Unit tests for internet.tavily_search_provider.

requests.post is mocked in every fast test — matching this project's own
established "mock the external library call at the boundary" precedent
(tests/unit/internet/test_brave_search_provider.py's own identical
approach). No opt-in/real test exists for Tavily in this file — no
JARMINEI_INTERNET_TAVILY_API_KEY was available in this development
session to write one against; see backlog/technical_debt.md's own entry
for the 2026-08-01 "Runtime Stability & Internet Layer Refactor."
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from config.schema import InternetConfig
from internet.search_provider import SearchError
from internet.tavily_search_provider import TavilySearchProvider


def _fake_response(json_payload: dict, status_ok: bool = True) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_payload
    if status_ok:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
    return response


_TAVILY_PAYLOAD = {
    "query": "test query",
    "results": [
        {
            "title": "Example Result One",
            "url": "https://example.com/one",
            "content": "The first snippet.",
            "score": 0.9,
        },
        {
            "title": "Example Result Two",
            "url": "https://example.com/two",
            "content": "The second snippet.",
            "score": 0.8,
        },
        {
            "title": "Example Result Three",
            "url": "https://example.com/three",
            "content": "The third snippet.",
            "score": 0.7,
        },
    ],
}


@pytest.fixture
def config() -> InternetConfig:
    return InternetConfig(tavily_api_key="test-key-123", request_timeout_seconds=5.0)


# --- search() happy path -------------------------------------------------------------


def test_search_parses_results_from_a_real_shaped_response(config):
    provider = TavilySearchProvider(config)

    with patch("requests.post") as mock_post:
        mock_post.return_value = _fake_response(_TAVILY_PAYLOAD)
        results = provider.search("test query", max_results=5)

    assert [r.title for r in results] == [
        "Example Result One",
        "Example Result Two",
        "Example Result Three",
    ]
    assert results[0].url == "https://example.com/one"
    assert results[0].snippet == "The first snippet."
    assert results[0].retrieved_at is not None


def test_search_bounds_to_max_results(config):
    provider = TavilySearchProvider(config)

    with patch("requests.post") as mock_post:
        mock_post.return_value = _fake_response(_TAVILY_PAYLOAD)
        results = provider.search("test query", max_results=2)

    assert len(results) == 2


def test_search_sends_the_correct_request_shape(config):
    provider = TavilySearchProvider(config)

    with patch("requests.post") as mock_post:
        mock_post.return_value = _fake_response(_TAVILY_PAYLOAD)
        provider.search("test query", max_results=3)

    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.tavily.com/search"
    assert kwargs["json"]["api_key"] == "test-key-123"
    assert kwargs["json"]["query"] == "test query"
    assert kwargs["json"]["max_results"] == 3
    assert kwargs["timeout"] == 5.0


# --- search() failure handling ---------------------------------------------------------


def test_search_without_api_key_raises_search_error():
    provider = TavilySearchProvider(InternetConfig(tavily_api_key=None))
    with pytest.raises(SearchError, match="not configured"):
        provider.search("test query", max_results=5)


def test_search_raises_search_error_on_connection_error(config):
    provider = TavilySearchProvider(config)
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError("no route")):
        with pytest.raises(SearchError):
            provider.search("test query", max_results=5)


def test_search_raises_search_error_on_timeout(config):
    provider = TavilySearchProvider(config)
    with patch("requests.post", side_effect=requests.exceptions.Timeout("too slow")):
        with pytest.raises(SearchError):
            provider.search("test query", max_results=5)


def test_search_raises_search_error_on_non_2xx_response(config):
    provider = TavilySearchProvider(config)
    with patch("requests.post") as mock_post:
        mock_post.return_value = _fake_response({}, status_ok=False)
        with pytest.raises(SearchError):
            provider.search("test query", max_results=5)


def test_search_handles_missing_results_key_gracefully(config):
    provider = TavilySearchProvider(config)
    with patch("requests.post") as mock_post:
        mock_post.return_value = _fake_response({"unexpected": "shape"})
        results = provider.search("test query", max_results=5)
    assert results == []


def test_search_handles_a_null_results_value_gracefully(config):
    """Same class of gap test_brave_search_provider.py's own Sprint 4.20
    finding fixed there — {"results": null} is a genuinely different
    shape from a missing "results" key; parsing lives inside the same
    try block that wraps the HTTP call specifically so this degrades to
    SearchError rather than leaking a raw AttributeError."""
    provider = TavilySearchProvider(config)
    with patch("requests.post") as mock_post:
        mock_post.return_value = _fake_response({"results": None})
        results = provider.search("test query", max_results=5)
    assert results == []
