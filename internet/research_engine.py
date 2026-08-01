"""Research Engine — orchestrates a query into a bounded, ranked set of
SearchResults. See docs/sprint_book/sprint_4_16.md and its Post-Sprint
Revision (2026-08-01 — provider-agnostic refactor).

Not a ManagedModule — no thread/connection/hardware of its own to
start/stop, the same "stateless-per-call aggregator" reasoning
sprint_2_8.md gave for ContextManager.

Depends only on the SearchProvider Protocol (internet/search_provider.py),
never on any concrete provider class — which provider is actually
active is entirely internet/search_provider_registry.py's own
composition-time decision, this class has no opinion on it. Degrades
to an empty list (never raises) on any SearchProvider failure — the
same fail-gracefully-by-default posture decision/intent_detector.py
already established for an external-service dependency, applied here
to the network as a whole (unreachable, timed out, rate-limited,
malformed response) rather than deferred entirely to Sprint 4.19's own
hardening pass, since a query that silently returns nothing is a far
safer default failure mode for a network-facing feature than one that
raises into a live conversation turn.
"""

from __future__ import annotations

from config.schema import InternetConfig
from core.logging_setup import get_logger
from internet.search_provider import SearchProvider, SearchResult

logger = get_logger(__name__)


class ResearchEngine:
    """Constructor DI: (search_provider, internet_config)."""

    def __init__(self, search_provider: SearchProvider, internet_config: InternetConfig) -> None:
        self._search_provider = search_provider
        self._config = internet_config

    def research(self, query: str) -> list[SearchResult]:
        try:
            results = self._search_provider.search(query, self._config.max_results_per_query)
        except Exception:
            logger.exception("Search failed for query %r; degrading to no results.", query)
            return []
        return results[: self._config.max_results_per_query]
