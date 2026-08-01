"""Unit tests for internet.research_engine."""

from datetime import UTC, datetime

import pytest

from config.schema import InternetConfig
from internet.research_engine import ResearchEngine
from internet.search_provider import SearchError, SearchResult


class FakeSearchProvider:
    """Local double implementing the SearchProvider Protocol — records
    every call it receives and returns/raises whatever the test
    configures."""

    def __init__(self, results: list[SearchResult] | None = None, error: Exception | None = None):
        self._results = results if results is not None else []
        self._error = error
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        self.calls.append((query, max_results))
        if self._error is not None:
            raise self._error
        return self._results


def make_results(count: int) -> list[SearchResult]:
    now = datetime.now(UTC)
    return [
        SearchResult(title=f"Result {i}", url=f"https://example.com/{i}", snippet=f"snippet {i}",
                     retrieved_at=now)
        for i in range(count)
    ]


# --- happy path -------------------------------------------------------------------


def test_research_passes_through_real_results_in_order():
    fake = FakeSearchProvider(results=make_results(3))
    engine = ResearchEngine(fake, InternetConfig(max_results_per_query=5))

    results = engine.research("test query")

    assert [r.title for r in results] == ["Result 0", "Result 1", "Result 2"]


def test_research_calls_search_provider_with_query_and_configured_bound():
    fake = FakeSearchProvider(results=[])
    engine = ResearchEngine(fake, InternetConfig(max_results_per_query=7))

    engine.research("what is the weather")

    assert fake.calls == [("what is the weather", 7)]


def test_research_bounds_results_even_if_search_provider_overreturns():
    fake = FakeSearchProvider(results=make_results(10))
    engine = ResearchEngine(fake, InternetConfig(max_results_per_query=3))

    results = engine.research("test query")

    assert len(results) == 3


# --- degradation on failure ---------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        SearchError("no API key"),
        ConnectionError("no route to host"),
        TimeoutError("too slow"),
        ValueError("malformed payload"),
    ],
)
def test_research_degrades_to_empty_list_on_any_search_provider_failure(error):
    fake = FakeSearchProvider(error=error)
    engine = ResearchEngine(fake, InternetConfig())

    results = engine.research("test query")

    assert results == []
