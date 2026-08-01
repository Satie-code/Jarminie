"""SearXNG adapter — one SearchProvider implementation among several
(see internet/search_provider.py's own docstring for the Protocol every
provider implements identically).

Added as part of the 2026-08-01 "Runtime Stability & Internet Layer
Refactor." SearXNG is a self-hosted, federated metasearch engine (it
queries several underlying engines — Google, Bing, DuckDuckGo, and
others — and returns one merged result set) with no vendor API key and
no per-query cost, chosen second in the new fallback chain
(InternetConfig.search_providers) per the user's own explicit priority
order. Unlike every other provider in this codebase, SearXNG has no
single canonical hosted endpoint this class could default to — it is
either self-hosted or pointed at a trusted third-party public instance,
and InternetConfig.search_base_url (already reserved for exactly this
since the original 2026-08-01 provider-agnostic refactor, before any
SearXNG code existed) must name one explicitly. Deliberately NOT
defaulted to any specific public instance URL here: picking one on this
project's own behalf would be a real, unreviewed reliability/privacy
decision (a specific third party would see every query), the same class
of "don't silently pick something consequential" discipline this
project already applies to model/provider choices elsewhere (Sprint
4.16's own stop-and-ask gate for Brave).

Response field names below (results[].title/url/content) match SearXNG's
own published JSON API format (`?format=json`, only enabled if a given
instance's own settings.yml turns it on — most public instances do, by
convention) — NOT verified against a live instance in this session.
"""

from __future__ import annotations

from datetime import UTC, datetime

import requests

from config.schema import InternetConfig
from core.logging_setup import get_logger
from internet.search_provider import SearchError, SearchResult

logger = get_logger(__name__)


class SearXNGSearchProvider:
    """SearchProvider implementation against a real, configured SearXNG
    instance. Holds no persistent connection — each search() call is a
    single, independent HTTP request, the same "thin per-call HTTP
    wrapper" shape every other real HTTP-backed provider in this
    codebase already establishes."""

    def __init__(self, internet_config: InternetConfig) -> None:
        self._base_url = internet_config.search_base_url
        self._timeout_seconds = internet_config.request_timeout_seconds

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Raises SearchError on a missing base URL, connection failure,
        timeout, non-2xx response, or malformed payload — never a raw
        requests exception, the identical contract every other
        SearchProvider in this codebase already honors."""
        if not self._base_url:
            raise SearchError(
                "InternetConfig.search_base_url is not configured — SearXNG has no "
                "single canonical hosted endpoint; set search_base_url to a real, "
                "trusted self-hosted or public SearXNG instance (e.g. "
                "https://searx.example.org)."
            )
        try:
            response = requests.get(
                f"{self._base_url.rstrip('/')}/search",
                headers={"Accept": "application/json"},
                params={"q": query, "format": "json"},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            # Same "parse INSIDE the try block, never after it" discipline
            # brave_search_provider.py's own Sprint 4.20 fix established.
            raw_results = payload.get("results") or []
        except SearchError:
            raise
        except Exception as exc:
            raise SearchError(f"SearXNG request failed for {query!r}: {exc}") from exc

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
