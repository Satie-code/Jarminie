"""Unit tests for internet.search_provider_registry (2026-08-01
provider-agnostic refactor; extended 2026-08-01 "Runtime Stability &
Internet Layer Refactor" for the multi-provider fallback chain)."""

from unittest.mock import MagicMock, patch

import pytest

from config.schema import InternetConfig
from internet.brave_search_provider import BraveSearchProvider
from internet.multi_search_provider import MultiSearchProvider
from internet.search_provider_registry import (
    UnknownSearchProviderError,
    create_search_provider,
    create_search_provider_with_fallback,
)
from internet.searxng_search_provider import SearXNGSearchProvider
from internet.tavily_search_provider import TavilySearchProvider


def test_default_provider_resolves_to_brave():
    """create_search_provider() (the original, single-provider
    construction path) still resolves to Brave by default — unchanged
    by this refactor. Note InternetConfig's own new default IS a
    multi-provider chain now (search_providers=["tavily", "searxng",
    "brave"]) — that default only takes effect through create_search_
    provider_with_fallback() below, this function's own single-provider
    behavior is untouched."""
    provider = create_search_provider(InternetConfig())
    assert isinstance(provider, BraveSearchProvider)


def test_explicit_brave_provider_resolves_to_brave():
    provider = create_search_provider(InternetConfig(search_provider="brave"))
    assert isinstance(provider, BraveSearchProvider)


def test_constructed_provider_receives_the_real_config():
    """Confirms real DI wiring end-to-end (not just object identity) —
    the provider the registry constructs genuinely uses the InternetConfig
    it was given, verified via the one observable side effect a
    BraveSearchProvider has: the API key it sends on a real search()
    call."""
    config = InternetConfig(search_provider="brave", search_api_key="a-real-looking-key")
    provider = create_search_provider(config)

    response = MagicMock()
    response.json.return_value = {"web": {"results": []}}
    response.raise_for_status.return_value = None
    with patch("requests.get", return_value=response) as mock_get:
        provider.search("test query", max_results=1)

    assert mock_get.call_args.kwargs["headers"]["X-Subscription-Token"] == "a-real-looking-key"


def test_unknown_provider_raises_unknown_search_provider_error():
    config = InternetConfig(search_provider="does-not-exist")
    with pytest.raises(UnknownSearchProviderError, match="does-not-exist"):
        create_search_provider(config)


def test_unknown_provider_error_names_available_providers():
    config = InternetConfig(search_provider="does-not-exist")
    with pytest.raises(UnknownSearchProviderError, match="brave"):
        create_search_provider(config)


def test_tavily_provider_resolves_to_tavily():
    provider = create_search_provider(InternetConfig(search_provider="tavily"))
    assert isinstance(provider, TavilySearchProvider)


def test_searxng_provider_resolves_to_searxng():
    provider = create_search_provider(InternetConfig(search_provider="searxng"))
    assert isinstance(provider, SearXNGSearchProvider)


# --- create_search_provider_with_fallback() (Runtime Stability & Internet Layer Refactor) --


def test_default_config_builds_a_multi_provider_chain():
    """InternetConfig()'s own new default (search_providers=["tavily",
    "searxng", "brave"]) is what this function reads — the real,
    non-Brave-specific default behavior this refactor's whole point is."""
    provider = create_search_provider_with_fallback(InternetConfig())
    assert isinstance(provider, MultiSearchProvider)


def test_multi_provider_chain_tries_providers_in_the_configured_order():
    config = InternetConfig(
        search_providers=["tavily", "brave"],
        tavily_api_key=None,  # deliberately unconfigured — tavily fails, falls back
        search_api_key="a-real-looking-brave-key",
    )
    provider = create_search_provider_with_fallback(config)
    assert isinstance(provider, MultiSearchProvider)

    response = MagicMock()
    response.json.return_value = {"web": {"results": []}}
    response.raise_for_status.return_value = None
    with patch("requests.get", return_value=response) as mock_get:
        results = provider.search("test query", max_results=3)

    assert results == []
    # Only brave's own real HTTP call happened — tavily failed before
    # ever reaching the network (no API key configured).
    assert mock_get.call_args.kwargs["headers"]["X-Subscription-Token"] == (
        "a-real-looking-brave-key"
    )


def test_empty_search_providers_list_falls_back_to_single_provider_mode():
    """A caller explicitly clearing search_providers back to [] gets
    exactly create_search_provider()'s own single-provider behavior —
    no behavior change for any config that predates this refactor and
    still only sets search_provider (the original field)."""
    config = InternetConfig(search_providers=[], search_provider="brave")
    provider = create_search_provider_with_fallback(config)
    assert isinstance(provider, BraveSearchProvider)


def test_multi_provider_chain_with_an_unknown_provider_name_raises_immediately():
    config = InternetConfig(search_providers=["tavily", "does-not-exist"])
    with pytest.raises(UnknownSearchProviderError, match="does-not-exist"):
        create_search_provider_with_fallback(config)
