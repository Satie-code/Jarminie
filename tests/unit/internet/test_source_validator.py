"""Unit tests for internet.source_validator."""

from datetime import UTC, datetime

from config.schema import InternetConfig
from internet.search_provider import SearchResult
from internet.source_validator import SourceValidator

_NOW = datetime.now(UTC)


def make_result(title: str, snippet: str, url: str = "https://example.com") -> SearchResult:
    return SearchResult(title=title, url=url, snippet=snippet, retrieved_at=_NOW)


# --- corroboration labeling ----------------------------------------------------------


def test_corroborated_when_terms_overlap_across_enough_sources():
    validator = SourceValidator(InternetConfig(min_sources_for_corroboration=2))
    results = [
        make_result("Python 3.13 released", "Python 3.13 introduces free threading support"),
        make_result(
            "Python update details",
            "The free threading feature removes the global interpreter lock in python",
        ),
        make_result("Weather forecast", "Expect rain and thunderstorms across the region tomorrow"),
    ]

    citations = validator.validate(results)

    assert citations[0].is_corroborated is True
    assert citations[1].is_corroborated is True
    assert citations[2].is_corroborated is False


def test_every_source_is_cited_regardless_of_corroboration():
    validator = SourceValidator(InternetConfig())
    results = [
        make_result("Alpha", "Zebra elephant giraffe rhinoceros hippopotamus"),
        make_result("Beta", "Quantum photon electron neutron proton"),
        make_result("Gamma", "Volcano earthquake tsunami avalanche wildfire"),
    ]

    citations = validator.validate(results)

    assert len(citations) == 3
    assert all(not c.is_corroborated for c in citations)


def test_citation_preserves_title_and_url():
    validator = SourceValidator(InternetConfig())
    result = make_result("A Title", "Some snippet text", url="https://example.com/page")

    citations = validator.validate([result])

    assert citations[0].title == "A Title"
    assert citations[0].url == "https://example.com/page"


def test_single_source_query_can_never_be_corroborated():
    validator = SourceValidator(InternetConfig(min_sources_for_corroboration=2))
    result = make_result("Solo result", "Only one source was found for this query")

    citations = validator.validate([result])

    assert citations[0].is_corroborated is False


def test_min_sources_for_corroboration_of_one_means_every_result_is_corroborated():
    validator = SourceValidator(InternetConfig(min_sources_for_corroboration=1))
    result = make_result("Solo result", "Only one source was found for this query")

    citations = validator.validate([result])

    assert citations[0].is_corroborated is True


def test_empty_results_returns_empty_citations():
    validator = SourceValidator(InternetConfig())
    assert validator.validate([]) == []
