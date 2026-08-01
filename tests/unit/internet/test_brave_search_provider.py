"""Unit tests for internet.brave_search_provider.

requests.get is mocked in every fast test — matching this project's own
established "mock the external library call at the boundary" precedent
(tests/unit/voice/test_text_to_speech.py's own TTS.api.TTS mocking).
The real, non-mocked Brave Search API call is verified only by the
opt-in test at the bottom of this file, which skips cleanly unless a
real JARMINEI_INTERNET_SEARCH_API_KEY is configured — see
docs/backlog/technical_debt.md item 31 for why that real verification
could not be performed in this session.

Renamed from test_search_client.py (2026-08-01 provider-agnostic
refactor) — BraveSearchClient -> BraveSearchProvider, no behavior
change to the tests themselves.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from config.schema import InternetConfig
from internet.brave_search_provider import BraveSearchProvider
from internet.search_provider import SearchError


def _fake_response(json_payload: dict, status_ok: bool = True) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_payload
    if status_ok:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
    return response


_BRAVE_PAYLOAD = {
    "web": {
        "results": [
            {
                "title": "Example Result One",
                "url": "https://example.com/one",
                "description": "The first snippet.",
            },
            {
                "title": "Example Result Two",
                "url": "https://example.com/two",
                "description": "The second snippet.",
            },
            {
                "title": "Example Result Three",
                "url": "https://example.com/three",
                "description": "The third snippet.",
            },
        ]
    }
}


@pytest.fixture
def config() -> InternetConfig:
    return InternetConfig(search_api_key="test-key-123", request_timeout_seconds=5.0)


# --- search() happy path -------------------------------------------------------------


def test_search_parses_results_from_a_real_shaped_response(config):
    provider = BraveSearchProvider(config)

    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response(_BRAVE_PAYLOAD)
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
    provider = BraveSearchProvider(config)

    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response(_BRAVE_PAYLOAD)
        results = provider.search("test query", max_results=2)

    assert len(results) == 2


def test_search_sends_the_correct_request_shape(config):
    provider = BraveSearchProvider(config)

    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response(_BRAVE_PAYLOAD)
        provider.search("test query", max_results=3)

    args, kwargs = mock_get.call_args
    assert args[0] == "https://api.search.brave.com/res/v1/web/search"
    assert kwargs["headers"]["X-Subscription-Token"] == "test-key-123"
    assert kwargs["headers"]["Accept"] == "application/json"
    assert kwargs["params"] == {"q": "test query", "count": 3}
    assert kwargs["timeout"] == 5.0


# --- search() failure handling ---------------------------------------------------------


def test_search_without_api_key_raises_search_error():
    provider = BraveSearchProvider(InternetConfig(search_api_key=None))
    with pytest.raises(SearchError, match="not configured"):
        provider.search("test query", max_results=5)


def test_search_raises_search_error_on_connection_error(config):
    provider = BraveSearchProvider(config)
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("no route")):
        with pytest.raises(SearchError):
            provider.search("test query", max_results=5)


def test_search_raises_search_error_on_timeout(config):
    provider = BraveSearchProvider(config)
    with patch("requests.get", side_effect=requests.exceptions.Timeout("too slow")):
        with pytest.raises(SearchError):
            provider.search("test query", max_results=5)


def test_search_raises_search_error_on_non_2xx_response(config):
    provider = BraveSearchProvider(config)
    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response({}, status_ok=False)
        with pytest.raises(SearchError):
            provider.search("test query", max_results=5)


def test_search_handles_missing_web_key_gracefully(config):
    """A malformed/unexpected payload shape (no "web" key at all)
    degrades to an empty list rather than raising — the response was
    still a valid 2xx JSON reply, just not the shape expected."""
    provider = BraveSearchProvider(config)
    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response({"unexpected": "shape"})
        results = provider.search("test query", max_results=5)
    assert results == []


def test_search_handles_a_null_web_value_gracefully(config):
    """Sprint 4.20 adversarial re-read finding: {"web": null} is a
    genuinely different shape from a missing "web" key — payload.get(
    "web", {}) only falls back to {} when the key is absent; here the
    key is present with value None, so the old code's un-guarded
    `.get("results", [])` on that None raised a raw, un-promised
    AttributeError instead of degrading. Confirmed as a real gap before
    fixing it (not assumed): ResearchEngine.research()'s own broad
    `except Exception` was already absorbing it in practice, masking a
    real violation of this method's own "never a raw requests
    exception" docstring promise."""
    provider = BraveSearchProvider(config)
    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response({"web": None})
        results = provider.search("test query", max_results=5)
    assert results == []


def test_search_handles_a_null_results_value_gracefully(config):
    """The same class of gap as test_search_handles_a_null_web_value_
    gracefully above, one level deeper: {"web": {"results": null}}."""
    provider = BraveSearchProvider(config)
    with patch("requests.get") as mock_get:
        mock_get.return_value = _fake_response({"web": {"results": None}})
        results = provider.search("test query", max_results=5)
    assert results == []


# --- opt-in/real: the actual Brave Search API -------------------------------------------


@pytest.fixture(autouse=True)
def _skip_if_no_real_api_key(request):
    """Only applies to the one test below marked with the
    real_search_api marker — every other test in this file uses a fake
    key and never reaches the network, so this fixture is a no-op for
    them (checked via the test's own marker, the same pattern
    test_level3_real_model_verification.py established for an
    autouse-fixture-scoped skip)."""
    if "real_search_api" not in request.keywords:
        return
    if not os.environ.get("JARMINEI_INTERNET_SEARCH_API_KEY"):
        pytest.skip(
            "JARMINEI_INTERNET_SEARCH_API_KEY is not set — real Brave Search API "
            "verification skipped. Set it to a real key and re-run to actually "
            "exercise this test against the live provider."
        )


@pytest.mark.real_search_api
def test_real_brave_search_returns_plausible_results_for_a_known_query():
    real_config = InternetConfig(search_api_key=os.environ.get("JARMINEI_INTERNET_SEARCH_API_KEY"))
    provider = BraveSearchProvider(real_config)

    results = provider.search("Python programming language", max_results=3)

    assert len(results) > 0
    for result in results:
        assert result.title
        assert result.url.startswith("http")
        assert result.snippet
