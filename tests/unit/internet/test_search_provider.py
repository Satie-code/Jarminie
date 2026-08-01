"""Unit tests for internet.search_provider — the shared SearchResult/
SearchError/SearchProvider contract itself (2026-08-01 provider-
agnostic refactor). See internet/brave_search_provider.py's own test
file for a concrete provider's behavior, and
tests/unit/internet/test_search_provider_registry.py for provider
selection."""

from datetime import UTC, datetime

from internet.search_provider import SearchResult


def test_search_result_holds_every_field():
    now = datetime.now(UTC)
    result = SearchResult(
        title="A title", url="https://example.com", snippet="A snippet", retrieved_at=now
    )

    assert result.title == "A title"
    assert result.url == "https://example.com"
    assert result.snippet == "A snippet"
    assert result.retrieved_at == now
