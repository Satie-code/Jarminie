"""Unit tests for internet.searxng_search_provider.

requests.get is mocked in every fast test — matching this project's own
established "mock the external library call at the boundary" precedent.
No opt-in/real test exists for SearXNG in this file: every real public
instance tried directly in this same development session (5 different,
well-known ones) returned either a bot-detection challenge page, HTTP
429 (rate limited), or was unreachable — see backlog/technical_debt.md's
own entry for the 2026-08-01 "Runtime Stability & Internet Layer
Refactor" for the full, concrete finding. A real verification pass needs
a genuinely self-hosted or pre-vetted instance, which this session has
neither.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from config.schema import InternetConfig
from internet.search_provider import SearchError
from internet.searxng_search_provider import SearXNGSearchProvider


def _fake_response(json_payload: dict, status_ok: bool = True) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_payload
    if status_ok:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
    return response


_SEARXNG_PAYLOAD = {
    "query": "test query",
    "results": [
        {
            "title": "Example Result One",
            "url": "https://example.com/one",
            "content": "The first snippet.",
            "engine": "google",
        },
        {
            "title": "Example Result Two",
            "url": "https://example.com/two",
            "content": "The second snippet.",
            "engine": "bing",
        },
        {
            "title": "Example Result Three",
            "url": "https://example.com/three",
            "content": "The third snippet.",
            "engine": "duckduckgo",
        },
    ],
}


@pytest.fixture
def config() -> InternetConfig:
    return InternetConfig(search_base_url="https://searx.example.org", request_timeout_seconds=5.0)


# --- search() happy path -------------------------------------------------------------


def test_search_parses_results_from_a_real_shaped_response(config):
    provider = SearXNGSearchProvider(config)

    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response(_SEARXNG_PAYLOAD)
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
    provider = SearXNGSearchProvider(config)

    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response(_SEARXNG_PAYLOAD)
        results = provider.search("test query", max_results=2)

    assert len(results) == 2


def test_search_sends_the_correct_request_shape(config):
    provider = SearXNGSearchProvider(config)

    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response(_SEARXNG_PAYLOAD)
        provider.search("test query", max_results=3)

    args, kwargs = mock_get.call_args
    assert args[0] == "https://searx.example.org/search"
    assert kwargs["params"] == {"q": "test query", "format": "json"}
    assert kwargs["timeout"] == 5.0


def test_search_strips_a_trailing_slash_from_base_url():
    provider = SearXNGSearchProvider(
        InternetConfig(search_base_url="https://searx.example.org/", request_timeout_seconds=5.0)
    )
    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response(_SEARXNG_PAYLOAD)
        provider.search("test query", max_results=3)

    args, _ = mock_get.call_args
    assert args[0] == "https://searx.example.org/search"


# --- search() failure handling ---------------------------------------------------------


def test_search_without_base_url_raises_search_error():
    provider = SearXNGSearchProvider(InternetConfig(search_base_url=None))
    with pytest.raises(SearchError, match="not configured"):
        provider.search("test query", max_results=5)


def test_search_raises_search_error_on_connection_error(config):
    provider = SearXNGSearchProvider(config)
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("no route")):
        with pytest.raises(SearchError):
            provider.search("test query", max_results=5)


def test_search_raises_search_error_on_timeout(config):
    provider = SearXNGSearchProvider(config)
    with patch("requests.get", side_effect=requests.exceptions.Timeout("too slow")):
        with pytest.raises(SearchError):
            provider.search("test query", max_results=5)


def test_search_raises_search_error_on_non_2xx_response(config):
    provider = SearXNGSearchProvider(config)
    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response({}, status_ok=False)
        with pytest.raises(SearchError):
            provider.search("test query", max_results=5)


def test_search_handles_missing_results_key_gracefully(config):
    provider = SearXNGSearchProvider(config)
    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response({"unexpected": "shape"})
        results = provider.search("test query", max_results=5)
    assert results == []


def test_search_handles_a_null_results_value_gracefully(config):
    """Same class of gap test_brave_search_provider.py's own Sprint 4.20
    finding fixed there — parsing lives inside the same try block that
    wraps the HTTP call specifically so a {"results": null} response
    degrades to SearchError rather than leaking a raw AttributeError."""
    provider = SearXNGSearchProvider(config)
    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response({"results": None})
        results = provider.search("test query", max_results=5)
    assert results == []
