"""Source Validation — the Internet Agent's honest corroboration
signal. See docs/sprint_book/sprint_4_17.md.

SourceValidator.validate() is a mechanical, checkable corroboration
signal, NOT a fabricated "verified" badge — no external fact-checking
API exists in this project's technology stack, and Part 2's own
"clearly distinguish between verified facts and uncertain information"
language does not claim JARMINEI can independently verify truth, only
that it should label honestly. A result is is_corroborated=True only
when its own significant terms genuinely overlap with at least
min_sources_for_corroboration - 1 OTHER SearchResults (a simple,
domain-independent term-overlap check, not semantic entailment) — the
same "report what can actually be measured, never a confident-sounding
number with nothing real behind it" discipline
voice/speech_to_text.py's no_speech_probability and
memory/confidence_scorer.py's Dynamic Memory Formula already establish
elsewhere in this codebase. Every source is included in the output
regardless of its corroboration status — an uncorroborated single
source is still cited, just honestly labeled, never silently dropped
(Part 2 asks for *distinguishing* uncertain information, not hiding
it).

A real semantic-similarity approach (e.g. reusing memory/'s own
ChromaDB embedding machinery) is a plausible future improvement,
deliberately not built here — see sprint_4_17.md's own Future
Considerations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from config.schema import InternetConfig
from internet.search_provider import SearchResult

_MIN_SHARED_TERMS = 2
_MIN_WORD_LENGTH = 4
_STOPWORDS = frozenset(
    {
        "that",
        "this",
        "these",
        "those",
        "with",
        "from",
        "into",
        "about",
        "have",
        "has",
        "had",
        "will",
        "would",
        "could",
        "should",
        "there",
        "their",
        "they",
        "them",
        "than",
        "then",
        "when",
        "where",
        "which",
        "what",
        "your",
        "some",
        "more",
        "most",
        "such",
        "over",
        "also",
        "were",
        "been",
        "being",
        "does",
        "doing",
        "each",
        "many",
        "much",
    }
)


def _significant_terms(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return {w for w in words if len(w) >= _MIN_WORD_LENGTH and w not in _STOPWORDS}


@dataclass
class Citation:
    title: str
    url: str
    is_corroborated: bool


class SourceValidator:
    """Constructor DI: (internet_config,). Stateless per call — no
    lifecycle of its own, the same shape ContextManager (2.8) already
    established for a pure aggregator with nothing to start/stop."""

    def __init__(self, internet_config: InternetConfig) -> None:
        self._config = internet_config

    def validate(self, results: list[SearchResult]) -> list[Citation]:
        """Every result in `results` gets exactly one Citation back, in
        the same order — this never drops or reorders a source."""
        term_sets = [_significant_terms(f"{r.title} {r.snippet}") for r in results]
        citations = []
        for i, result in enumerate(results):
            supporting_count = 1  # a result always "supports" itself
            for j, other_terms in enumerate(term_sets):
                if i == j:
                    continue
                if len(term_sets[i] & other_terms) >= _MIN_SHARED_TERMS:
                    supporting_count += 1
            citations.append(
                Citation(
                    title=result.title,
                    url=result.url,
                    is_corroborated=(
                        supporting_count >= self._config.min_sources_for_corroboration
                    ),
                )
            )
        return citations
