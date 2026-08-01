"""Tavily Search API adapter — one SearchProvider implementation among
several (see internet/search_provider.py's own docstring for the
Protocol every provider implements identically).

Added as part of the 2026-08-01 "Runtime Stability & Internet Layer
Refactor" — the user's own explicit, direct request that JARMINEI not
depend on any single commercial search provider. Tavily is the first
entry in the new multi-provider fallback chain
(InternetConfig.search_providers, internet/multi_search_provider.py),
chosen first per that request's own stated priority order: a real free
development tier, a clean single-key REST API, and (unlike Brave) an
index purpose-built for LLM/agent consumption rather than general human
browsing — a reasonable fit for this project's own summarization-
grounded use case.

Response field names below (results[].title/url/content) match Tavily's
own published REST API schema as of this file's own implementation —
NOT verified against a live call in this session (no API key is
available in this development environment). Mirrors brave_search_
provider.py's own "log this as a real, named gap rather than silently
present it as verified" precedent — see backlog/technical_debt.md's own
entry for this refactor.
"""

from __future__ import annotations

from datetime import UTC, datetime

import requests

from config.schema import InternetConfig
from core.logging_setup import get_logger
from internet.search_provider import SearchError, SearchResult

logger = get_logger(__name__)

_TAVILY_SEARCH_ENDPOINT = "https://api.tavily.com/search"


class TavilySearchProvider:
    """SearchProvider implementation against the real Tavily Search API.
    Holds no persistent connection — each search() call is a single,
    independent HTTP request, the same "thin per-call HTTP wrapper,
    nothing to open or close" shape every other real HTTP-backed
    provider in this codebase already establishes (BraveSearchProvider,
    OllamaClient)."""

    def __init__(self, internet_config: InternetConfig) -> None:
        self._api_key = internet_config.tavily_api_key
        self._timeout_seconds = internet_config.request_timeout_seconds

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Raises SearchError on a missing API key, connection failure,
        timeout, non-2xx response, or malformed payload — never a raw
        requests exception, the identical contract every other
        SearchProvider in this codebase already honors."""
        if not self._api_key:
            raise SearchError(
                "InternetConfig.tavily_api_key is not configured — set the "
                "JARMINEI_INTERNET_TAVILY_API_KEY environment variable."
            )
        try:
            response = requests.post(
                _TAVILY_SEARCH_ENDPOINT,
                headers={"Content-Type": "application/json"},
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                },
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            # Same "parse INSIDE the try block, never after it" discipline
            # brave_search_provider.py's own Sprint 4.20 fix established —
            # payload.get("results") returning None (a real, if malformed,
            # response shape) must degrade to SearchError, not leak a raw
            # AttributeError from indexing/iterating None.
            raw_results = payload.get("results") or []
        except SearchError:
            raise
        except Exception as exc:
            raise SearchError(f"Tavily Search request failed for {query!r}: {exc}") from exc

        retrieved_at = datetime.now(UTC)
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                retrieved_at=retrieved_at,
            )
            for item in raw_results[:max_results]
        ]
