"""Unit tests for internet.search_provider_registry (2026-08-01
provider-agnostic refactor)."""

from unittest.mock import MagicMock, patch

import pytest

from config.schema import InternetConfig
from internet.brave_search_provider import BraveSearchProvider
from internet.search_provider_registry import UnknownSearchProviderError, create_search_provider


def test_default_provider_resolves_to_brave():
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
