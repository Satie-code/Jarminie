"""Unit tests for internet.multi_search_provider.

Uses simple local test-double SearchProvider implementations (matching
this project's own "real double, not a mock, for a Protocol implementer"
convention already established for FakeSearchProvider in tests/
integration/conftest.py) rather than mocking requests — this file's own
job is proving the fallback ORCHESTRATION logic, not any one real
provider's HTTP behavior, which each provider's own dedicated test file
already covers.
"""

from datetime import UTC, datetime

import pytest

from internet.multi_search_provider import (
    AllProvidersFailedError,
    MultiSearchProvider,
    ProviderAttempt,
)
from internet.search_provider import SearchError, SearchResult


def _result(title: str) -> SearchResult:
    return SearchResult(
        title=title, url="https://example.com", snippet="s", retrieved_at=datetime.now(UTC)
    )


class _StubProvider:
    def __init__(
        self, *, results: list[SearchResult] | None = None, raises: Exception | None = None
    ) -> None:
        self._results = results
        self._raises = raises
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        self.calls.append((query, max_results))
        if self._raises is not None:
            raise self._raises
        return self._results if self._results is not None else []


# --- fallback happy paths --------------------------------------------------------------


def test_first_provider_success_never_calls_the_second():
    first = _StubProvider(results=[_result("from first")])
    second = _StubProvider(results=[_result("from second")])
    multi = MultiSearchProvider([("first", first), ("second", second)])

    results = multi.search("query", max_results=5)

    assert [r.title for r in results] == ["from first"]
    assert first.calls == [("query", 5)]
    assert second.calls == []


def test_first_provider_failure_falls_back_to_second():
    first = _StubProvider(raises=SearchError("first is down"))
    second = _StubProvider(results=[_result("from second")])
    multi = MultiSearchProvider([("first", first), ("second", second)])

    results = multi.search("query", max_results=5)

    assert [r.title for r in results] == ["from second"]
    assert first.calls == [("query", 5)]
    assert second.calls == [("query", 5)]


def test_falls_back_across_more_than_two_providers():
    first = _StubProvider(raises=SearchError("first is down"))
    second = _StubProvider(raises=SearchError("second is down"))
    third = _StubProvider(results=[_result("from third")])
    multi = MultiSearchProvider([("first", first), ("second", second), ("third", third)])

    results = multi.search("query", max_results=5)

    assert [r.title for r in results] == ["from third"]
    assert first.calls and second.calls and third.calls


def test_a_provider_raising_a_non_search_error_still_falls_back():
    """A provider breaking its own "never a raw exception" contract is
    defended against here too — the same defense-in-depth reasoning
    ResearchEngine.research()'s own broad except Exception already
    applies one layer up, applied here between providers."""
    first = _StubProvider(raises=RuntimeError("a provider's own internal bug"))
    second = _StubProvider(results=[_result("from second")])
    multi = MultiSearchProvider([("first", first), ("second", second)])

    results = multi.search("query", max_results=5)

    assert [r.title for r in results] == ["from second"]


def test_a_real_successful_empty_result_is_not_a_failure_to_fall_back_from():
    """A provider that genuinely, successfully found nothing must not
    trigger a fallback to the next provider — an empty list from a
    working provider is a real, honest answer, not a failure."""
    first = _StubProvider(results=[])
    second = _StubProvider(results=[_result("from second")])
    multi = MultiSearchProvider([("first", first), ("second", second)])

    results = multi.search("query", max_results=5)

    assert results == []
    assert first.calls == [("query", 5)]
    assert second.calls == []


# --- all providers failed: structured explanation ---------------------------------------


def test_all_providers_failing_raises_all_providers_failed_error_with_structured_attempts():
    first = _StubProvider(raises=SearchError("no api key"))
    second = _StubProvider(raises=SearchError("connection refused"))
    multi = MultiSearchProvider([("first", first), ("second", second)])

    with pytest.raises(AllProvidersFailedError) as excinfo:
        multi.search("query", max_results=5)

    error = excinfo.value
    assert isinstance(error, SearchError)  # every existing caller's except SearchError still works
    assert error.query == "query"
    assert error.attempts == [
        ProviderAttempt(provider_name="first", error="no api key"),
        ProviderAttempt(provider_name="second", error="connection refused"),
    ]
    assert "first" in str(error)
    assert "no api key" in str(error)
    assert "second" in str(error)
    assert "connection refused" in str(error)


def test_all_providers_failed_error_is_caught_by_a_plain_except_exception():
    """Confirms ResearchEngine.research()'s own existing, unmodified
    `except Exception: return []` handles this new exception type
    correctly with zero code changes there."""
    first = _StubProvider(raises=SearchError("down"))
    multi = MultiSearchProvider([("first", first)])

    try:
        multi.search("query", max_results=5)
        caught = None
    except Exception as exc:  # the exact shape ResearchEngine.research() uses
        caught = exc

    assert isinstance(caught, AllProvidersFailedError)


# --- construction -----------------------------------------------------------------------


def test_construction_with_no_providers_raises_value_error():
    with pytest.raises(ValueError):
        MultiSearchProvider([])
