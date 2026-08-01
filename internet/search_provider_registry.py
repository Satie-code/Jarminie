"""Search Provider Registry — resolves InternetConfig.search_provider
into a real, concrete SearchProvider implementation. See
docs/sprint_book/sprint_4_16.md's Post-Sprint Revision (2026-08-01,
provider-agnostic refactor) for why this exists: the Internet Agent
must not require Brave specifically — this registry is the one place
that maps a config-driven provider name to a real class, so nothing
else (ResearchEngine, Summarizer, main.py's own future composition)
ever hardcodes which provider is active.

**Adding a new provider** (Tavily, SerpAPI, SearXNG, or any future one)
takes exactly two steps, neither of which touches this docstring's own
promise that ResearchEngine/Summarizer stay provider-agnostic:
1. Write one new class implementing the SearchProvider Protocol
   (internet/search_provider.py) — its own file, mirroring
   brave_search_provider.py's shape (constructor DI on InternetConfig,
   a single search() method, SearchError on any failure).
2. Add one entry to _PROVIDERS below, keyed by the name users will set
   InternetConfig.search_provider to.

No change to InternetConfig's own shape is required for a simple
keyed-API provider (search_api_key/request_timeout_seconds already
generically serve one) — a provider needing something InternetConfig
doesn't yet have (e.g. SearXNG's own self-hosted instance URL,
search_base_url) gets a new, equally generic field added to
InternetConfig, still without any of this file's own callers changing.

This is a plain function-based registry, not a stateful class —
deliberately simpler than device_control/action_engine.py's
ActionRegistry, since exactly one SearchProvider is ever active at a
time (config-selected), unlike ActionRegistry's own many-executors-
dispatched-by-type shape. Do not generalize this into something
heavier before a real, concrete need for it exists.
"""

from __future__ import annotations

from collections.abc import Callable

from config.schema import InternetConfig
from internet.brave_search_provider import BraveSearchProvider
from internet.search_provider import SearchProvider


class UnknownSearchProviderError(Exception):
    """Raised when InternetConfig.search_provider names a provider with
    no registered implementation — a construction-time configuration
    error, deliberately loud (never caught/degraded), matching this
    project's own "fail fast on a broken composition, fail gracefully
    on a runtime operation" split (ConfigError vs. SearchError)."""


_PROVIDERS: dict[str, Callable[[InternetConfig], SearchProvider]] = {
    "brave": BraveSearchProvider,
}


def create_search_provider(internet_config: InternetConfig) -> SearchProvider:
    """Constructs the SearchProvider implementation
    internet_config.search_provider names ("brave" by default). Raises
    UnknownSearchProviderError (never a raw KeyError) for an
    unregistered name, naming every real, available option in the
    message so a typo/misconfiguration is immediately actionable."""
    name = internet_config.search_provider
    try:
        provider_cls = _PROVIDERS[name]
    except KeyError:
        raise UnknownSearchProviderError(
            f"Unknown search_provider {name!r}. Registered providers: {sorted(_PROVIDERS)}."
        ) from None
    return provider_cls(internet_config)
