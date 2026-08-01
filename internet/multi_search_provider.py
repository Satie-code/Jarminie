"""Multi-provider fallback orchestration — the 2026-08-01 "Runtime
Stability & Internet Layer Refactor"'s own direct answer to "I do not
want JARMINEI to depend on a single commercial provider."

MultiSearchProvider itself implements the SearchProvider Protocol
(internet/search_provider.py) — structurally, the same duck-typed
"anything with a matching search() method" shape every other provider
already satisfies — specifically so ResearchEngine needs ZERO changes to
use it: internet/search_provider_registry.py's new
create_search_provider_with_fallback() hands main.py either a single
concrete provider (unchanged, existing behavior) or one of these
wrapping several, and ResearchEngine.research() cannot tell the
difference. This is the Protocol pattern doing exactly the job it was
built for — see search_provider.py's own docstring.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.logging_setup import get_logger
from internet.search_provider import SearchError, SearchProvider, SearchResult

logger = get_logger(__name__)


@dataclass
class ProviderAttempt:
    """One provider's own outcome within a single search() call — the
    structured record AllProvidersFailedError carries, per the user's
    own explicit request ("return a structured explanation rather than
    crashing")."""

    provider_name: str
    error: str


class AllProvidersFailedError(SearchError):
    """Raised only when EVERY provider in the fallback chain failed for
    this one query — a SearchError subclass, not a new exception
    hierarchy, so every existing caller's own `except SearchError`/
    `except Exception` handling (ResearchEngine.research()'s own
    broad catch, unchanged) already handles this correctly with zero
    code changes anywhere downstream. attempts carries the real,
    structured per-provider detail (name + own failure reason) the
    plain string message below is built from — a caller wanting the
    structured data directly (logging, diagnostics, a future richer UI)
    can read `.attempts` instead of re-parsing the message string."""

    def __init__(self, query: str, attempts: list[ProviderAttempt]) -> None:
        self.query = query
        self.attempts = attempts
        detail = "; ".join(f"{a.provider_name} ({a.error})" for a in attempts)
        super().__init__(
            f"All {len(attempts)} search provider(s) failed for {query!r}: {detail}"
        )


class MultiSearchProvider:
    """Tries each (name, SearchProvider) pair in order, returning the
    first successful non-empty-or-not result. A provider that raises
    (SearchError or any other exception — a provider breaking its own
    "never a raw exception" contract is defended against here too, the
    same defense-in-depth reasoning ResearchEngine.research()'s own
    broad except Exception already applies one layer up) is logged and
    skipped; the next provider in the chain is tried immediately. Only
    when EVERY provider has failed does this raise
    AllProvidersFailedError — ResearchEngine's own existing, unchanged
    except Exception then degrades that to an honest "I couldn't find
    anything" reply, exactly as it already does for a single provider's
    own failure today.

    A provider returning an EMPTY list (a real, successful call that
    genuinely found nothing) is treated as terminal, not a failure to
    fall back from — an empty result from a working provider is
    meaningfully different from a broken one, and silently trying every
    remaining provider after a real "no results" answer would waste
    real API quota/traffic for no benefit. Only a raised exception
    triggers fallback to the next provider."""

    def __init__(self, providers: list[tuple[str, SearchProvider]]) -> None:
        if not providers:
            raise ValueError("MultiSearchProvider requires at least one provider.")
        self._providers = providers

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        attempts: list[ProviderAttempt] = []
        for name, provider in self._providers:
            try:
                results = provider.search(query, max_results)
            except Exception as exc:
                logger.warning(
                    "Search provider %r failed for %r, trying next: %s", name, query, exc
                )
                attempts.append(ProviderAttempt(provider_name=name, error=str(exc)))
                continue
            if attempts:
                logger.info(
                    "Search provider %r succeeded for %r after %d earlier failure(s).",
                    name,
                    query,
                    len(attempts),
                )
            return results
        raise AllProvidersFailedError(query, attempts)
