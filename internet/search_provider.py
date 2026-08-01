"""Internet Agent — the shared Search Provider contract. See
docs/sprint_book/sprint_4_16.md and its Post-Sprint Revision
(2026-08-01 — provider-agnostic refactor).

SearchProvider is a Protocol (not an ABC), mirroring
decision/llm_client.py's LanguageModelClient precedent — the same
"the architecture must remain model-independent" discipline
03_Engineering_Standards.md states for the AI Runtime, applied here to
search backends: adding or swapping a provider means writing one new
class implementing this Protocol plus one registry entry
(internet/search_provider_registry.py), never touching ResearchEngine,
Summarizer, or this file itself. See that registry's own docstring for
exactly how a new provider (Tavily, SerpAPI, SearXNG, or any future
one) gets plugged in.

Deliberately named "Provider," departing from LanguageModelClient's own
"Client" naming convention — this abstraction's whole purpose is
genuinely interchangeable backends selected by configuration (Brave
today, potentially several more later), not one runtime with a thin
wrapper around it. This was an explicit, direct user request (the
2026-08-01 provider-agnostic architecture revision), not a silent
rename of an already-reviewed convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class SearchError(Exception):
    """Raised for any search call failure — missing/invalid
    credentials, connection, timeout, or a non-2xx response. Never a
    raw provider-specific exception, per Interface First Design keeping
    implementation-specific errors out of caller code (mirrors
    decision/llm_client.py's LlmError precedent exactly)."""


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    retrieved_at: datetime


class SearchProvider(Protocol):
    """A single-method contract, deliberately minimal — the same "kept
    deliberately minimal" precedent ManagedModule/LanguageModelClient
    both already established."""

    def search(self, query: str, max_results: int) -> list[SearchResult]: ...
