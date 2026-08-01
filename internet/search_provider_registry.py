"""Search Provider Registry — resolves InternetConfig.search_provider
into a real, concrete SearchProvider implementation. See
docs/sprint_book/sprint_4_16.md's Post-Sprint Revision (2026-08-01,
provider-agnostic refactor) for why this exists: the Internet Agent
must not require Brave specifically — this registry is the one place
that maps a config-driven provider name to a real class, so nothing
else (ResearchEngine, Summarizer, main.py's own future composition)
ever hardcodes which provider is active.

**Adding a new provider** (SerpAPI, or any future one) takes exactly two
steps, neither of which touches this docstring's own promise that
ResearchEngine/Summarizer stay provider-agnostic:
1. Write one new class implementing the SearchProvider Protocol
   (internet/search_provider.py) — its own file, mirroring
   brave_search_provider.py's shape (constructor DI on InternetConfig,
   a single search() method, SearchError on any failure).
2. Add one entry to _PROVIDERS below, keyed by the name users will set
   InternetConfig.search_provider (single-provider mode) or list in
   InternetConfig.search_providers (fallback-chain mode) to.

No change to InternetConfig's own shape is required for a simple
keyed-API provider (search_api_key/request_timeout_seconds already
generically serve one) — a provider needing something InternetConfig
doesn't yet have gets a new, equally generic field added to
InternetConfig, still without any of this file's own callers changing.
(DuckDuckGo is deliberately NOT registered here — see
backlog/technical_debt.md's own entry for the 2026-08-01 "Runtime
Stability & Internet Layer Refactor": its only real, keyless API is the
Instant Answer API, confirmed via a live call in this same session to
return just one general "Results" entry for a common, unambiguous query
— not a general web search API, and not a reliable foundation for this
project's own research use case. The unofficial scraping-based
workarounds several open-source libraries use are against DuckDuckGo's
own Terms of Service for automated use and were not built here, matching
this project's own "don't ship something we can't stand behind"
discipline.)

This is a plain function-based registry, not a stateful class —
deliberately simpler than device_control/action_engine.py's
ActionRegistry, since a single SearchProvider (or, since this refactor,
a small ordered chain of them) is what's active at a time, unlike
ActionRegistry's own many-executors-dispatched-by-type shape. Do not
generalize this into something heavier before a real, concrete need for
it exists.
"""

from __future__ import annotations

from collections.abc import Callable

from config.schema import InternetConfig
from internet.brave_search_provider import BraveSearchProvider
from internet.multi_search_provider import MultiSearchProvider
from internet.search_provider import SearchProvider
from internet.searxng_search_provider import SearXNGSearchProvider
from internet.tavily_search_provider import TavilySearchProvider


class UnknownSearchProviderError(Exception):
    """Raised when InternetConfig.search_provider (or an entry in
    InternetConfig.search_providers) names a provider with no registered
    implementation — a construction-time configuration error,
    deliberately loud (never caught/degraded), matching this project's
    own "fail fast on a broken composition, fail gracefully on a runtime
    operation" split (ConfigError vs. SearchError)."""


_PROVIDERS: dict[str, Callable[[InternetConfig], SearchProvider]] = {
    "brave": BraveSearchProvider,
    "tavily": TavilySearchProvider,
    "searxng": SearXNGSearchProvider,
}


def create_search_provider(internet_config: InternetConfig) -> SearchProvider:
    """Constructs the SINGLE SearchProvider implementation
    internet_config.search_provider names ("brave" by default) — the
    original, still-fully-supported single-provider construction path,
    unchanged by the 2026-08-01 multi-provider refactor below. Raises
    UnknownSearchProviderError (never a raw KeyError) for an
    unregistered name, naming every real, available option in the
    message so a typo/misconfiguration is immediately actionable."""
    return _construct(internet_config.search_provider, internet_config)


def create_search_provider_with_fallback(internet_config: InternetConfig) -> SearchProvider:
    """The new, preferred construction path (2026-08-01 "Runtime
    Stability & Internet Layer Refactor") — main.py's own composition
    root calls this instead of create_search_provider() now. Builds a
    real MultiSearchProvider trying every name in
    internet_config.search_providers, in order, falling back to the next
    on any real failure. When search_providers is empty (its own
    default is a real, non-empty chain — see InternetConfig's own
    docstring — but a caller may legitimately clear it back to `[]` to
    opt back into single-provider mode), this degrades to exactly
    create_search_provider()'s own single-provider behavior — no
    behavior change for any config that predates this refactor.

    Raises UnknownSearchProviderError immediately (never deferred to a
    real search call) if search_providers names anything unregistered —
    the same fail-fast-on-broken-composition posture
    create_search_provider() already established, applied per entry."""
    names = internet_config.search_providers
    if not names:
        return create_search_provider(internet_config)
    providers = [(name, _construct(name, internet_config)) for name in names]
    return MultiSearchProvider(providers)


def _construct(name: str, internet_config: InternetConfig) -> SearchProvider:
    try:
        provider_cls = _PROVIDERS[name]
    except KeyError:
        raise UnknownSearchProviderError(
            f"Unknown search provider {name!r}. Registered providers: {sorted(_PROVIDERS)}."
        ) from None
    return provider_cls(internet_config)
