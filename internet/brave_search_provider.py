"""Brave Search API adapter — one SearchProvider implementation among
potentially several. See docs/sprint_book/sprint_4_16.md (original
provider decision) and its Post-Sprint Revision (2026-08-01,
provider-agnostic refactor — this class was extracted from the
then-monolithic internet/search_client.py, renamed BraveSearchClient ->
BraveSearchProvider, with no behavior change).

Chosen as this project's first real provider via Sprint 4.16's own
explicit stop-and-ask gate (2026-07-31) — an independent index, a free
tier, and the simplest auth shape of the options considered. It is the
default (InternetConfig.search_provider = "brave") but not a required
dependency of the Internet Agent as a whole — see
internet/search_provider_registry.py for how a different or additional
provider gets selected/plugged in instead.

Response field names below (web.results[].title/url/description) match
Brave's own published Web Search API schema as of this file's own
implementation — NOT verified against a live call in this session (no
API key was available). The opt-in real test in
tests/unit/internet/test_brave_search_provider.py is what actually
proves this parsing is correct against a real response; it stays
skipped until a real JARMINEI_INTERNET_SEARCH_API_KEY is configured and
run for real. See backlog/technical_debt.md item 31.
"""

from __future__ import annotations

from datetime import UTC, datetime

import requests

from config.schema import InternetConfig
from core.logging_setup import get_logger
from internet.search_provider import SearchError, SearchResult

logger = get_logger(__name__)

_BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider:
    """SearchProvider implementation against the real Brave Search API.
    Holds no persistent connection — each search() call is a single,
    independent HTTP request, the same "thin per-call HTTP wrapper,
    nothing to open or close" shape OllamaClient already established."""

    def __init__(self, internet_config: InternetConfig) -> None:
        self._api_key = internet_config.search_api_key
        self._timeout_seconds = internet_config.request_timeout_seconds

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Raises SearchError on a missing API key, connection failure,
        timeout, non-2xx response, or malformed payload — never a raw
        requests exception. Callers (ResearchEngine) are responsible
        for deciding how to degrade on that error; this method's own
        job is only "get real results or fail honestly.\""""
        if not self._api_key:
            raise SearchError(
                "InternetConfig.search_api_key is not configured — set the "
                "JARMINEI_INTERNET_SEARCH_API_KEY environment variable."
            )
        try:
            response = requests.get(
                _BRAVE_SEARCH_ENDPOINT,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self._api_key,
                },
                params={"q": query, "count": max_results},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            # Sprint 4.20 adversarial re-read finding: parsing must live
            # INSIDE this same try block, not after it — payload.get(
            # "web", {}) only falls back to {} when the "web" key is
            # genuinely absent; a real (if malformed/degraded) response
            # shaped {"web": null, ...} makes it return None instead,
            # and .get("results", []) on None raises a raw AttributeError
            # this method's own docstring already promises never to leak.
            # ResearchEngine.research()'s own broad `except Exception`
            # already absorbed this in practice, but that's defense in
            # depth masking a real gap in this class's own contract, not
            # a reason to leave the gap itself unfixed.
            web = payload.get("web") or {}
            raw_results = web.get("results") or []
        except SearchError:
            raise
        except Exception as exc:
            raise SearchError(f"Brave Search request failed for {query!r}: {exc}") from exc

        retrieved_at = datetime.now(UTC)
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
                retrieved_at=retrieved_at,
            )
            for item in raw_results[:max_results]
        ]
