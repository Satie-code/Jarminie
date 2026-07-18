"""Memory Retrieval Engine — the Decision Engine pipeline's third stage,
per 02_System_Architecture.md: "Intent Detection -> Context Analysis ->
**Memory Retrieval** -> Priority Evaluation -> Authority Evaluation ->
Engine Selection." This sprint fills a real gap between
sprint_book/INDEX.md's original roadmap (which listed only Intent
Detection, Context Analysis, Priority Queue, Authority Evaluation) and
Part 2's own five-stage diagram — see this file's own sprint spec.

Composes Sprints 3.1-3.6 into one ranked, explainable query. Introduces
no new storage and no new confidence logic — only retrieval composition
and ranking, always through the existing type-specific wrappers
(PersonaScopedMemory, EventMemory, ShortTermMemory), never MemoryStore
directly, so every scoping/permanence guarantee those sprints already
built is preserved rather than re-implemented or bypassed.

Ranking formula: combined_rank_score = (similarity_score *
retrieval_similarity_weight) + (confidence_score / 100 *
retrieval_confidence_weight). similarity_score is Chroma distance
normalized into (0, 1] via 1 / (1 + distance) — chosen over a linear
min-max normalization because Chroma's distance metric has no fixed
upper bound to normalize against; empirically (measured against the
real embedding model while implementing this sprint) related content
scored roughly 0.55-0.65 and unrelated content roughly 0.30-0.40 under
this formula, which is what informs _MIN_EVENT_SIMILARITY below.

Two implementation-time decisions not spelled out by this sprint's own
spec, both needed to satisfy its Acceptance Criteria ("Event and
Short-Term results only appear when actually relevant to query_text"):
1. Event Memory results are dropped below _MIN_EVENT_SIMILARITY — a
   semantic search always returns its nearest neighbors regardless of
   whether any of them are genuinely relevant, so a cutoff is required
   for an unrelated query to ever yield an empty Event result set.
2. Short-Term Memory has no semantic search of its own at all
   (active_context_memories() is a plain per-session recency query, not
   a Chroma query) — relevance is instead approximated by a crude
   keyword-overlap fraction between query_text and each candidate's
   content, the same "keyword heuristic, real NLU not available at this
   point in the build order" discipline PersonaManager.detect_context_
   heuristic() (2.11) and ShortTermMemory.promote_from_turn()'s own
   salience triggers (3.4) already established. Persona-scoped (Shared/
   Jarvis/Minie) results are NOT filtered by either mechanism — they are
   core conversational background, not a "bonus" recall that should
   vanish for an off-topic query, per this sprint's own Acceptance
   Criteria naming only Event and Short-Term.
"""

import re
from dataclasses import dataclass

from config.schema import MemoryConfig
from memory.confidence_scorer import ConfidenceBand, ConfidenceScorer
from memory.event_memory import EventMemory
from memory.models import MemoryRecord
from memory.persona_scoped_memory import PersonaScopedMemory
from memory.short_term_memory import ShortTermMemory

_MIN_EVENT_SIMILARITY = 0.4
"""Below this, an Event Memory nearest-neighbor result is treated as
"not actually relevant" rather than merely "less relevant" — see this
module's own docstring for the empirical basis."""

_BAND_LABELS: dict[ConfidenceBand, str] = {
    ConfidenceBand.TEMPORARY: "Temporary",
    ConfidenceBand.SHORT_TERM: "Short-term",
    ConfidenceBand.MONTHLY_REVIEW: "Monthly-review",
    ConfidenceBand.LONG_TERM: "Long-term",
    ConfidenceBand.PERMANENT: "Permanent",
}

_STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
        "i", "you", "he", "she", "it", "we", "they", "my", "your", "his",
        "her", "its", "our", "their", "to", "of", "in", "on", "at", "for",
        "and", "or", "but", "with", "about", "what", "when", "where", "how",
        "can", "could", "would", "should", "me", "us", "them", "this", "that",
    }
)
_WORD_PATTERN = re.compile(r"[a-z0-9']+")


@dataclass
class RetrievedMemory:
    """One ranked retrieval result. confidence_score is read from
    record.confidence_score at query time — this sprint recomputes
    nothing (that's Sprint 3.5's ConfidenceScorer.score()'s own job, and
    only band() is used here, to label the reason string)."""

    record: MemoryRecord
    similarity_score: float
    confidence_score: float
    combined_rank_score: float
    retrieval_reason: str


class MemoryRetrievalEngine:
    """Constructor DI per 03_Engineering_Standards.md: receives every
    Sprint 3.1-3.6 collaborator it composes rather than constructing any
    of them. Plain class, not a ManagedModule — owns no resource of its
    own beyond those already-managed collaborators, same reasoning as
    ContextManager (2.8)."""

    def __init__(
        self,
        persona_scoped_memory: PersonaScopedMemory,
        event_memory: EventMemory,
        short_term_memory: ShortTermMemory,
        confidence_scorer: ConfidenceScorer,
        memory_config: MemoryConfig,
    ) -> None:
        self._persona_scoped_memory = persona_scoped_memory
        self._event_memory = event_memory
        self._short_term_memory = short_term_memory
        self._confidence_scorer = confidence_scorer
        self._memory_config = memory_config

    def retrieve(
        self,
        query_text: str,
        persona_name: str,
        session_id: str,
        max_results: int | None = None,
    ) -> list[RetrievedMemory]:
        """Query Shared+Persona memory, Event memory, and session-scoped
        Short-Term memory in one call, rank by combined_rank_score
        (descending), truncate to max_results (defaulting to
        memory_config.max_retrieval_results). An empty/whitespace-only
        query_text returns an empty list without querying anything."""
        if not query_text or not query_text.strip():
            return []
        limit = (
            max_results if max_results is not None else self._memory_config.max_retrieval_results
        )

        persona_scoped = self._persona_scoped_memory.recall_for_persona_scored(
            persona_name, query_text
        )
        event_results = self._event_memory.search_milestones_scored(query_text)

        candidates: list[tuple[MemoryRecord, float]] = []
        candidates.extend(_as_similarity_candidates(persona_scoped))
        candidates.extend(
            (record, similarity)
            for record, similarity in _as_similarity_candidates(event_results)
            if similarity >= _MIN_EVENT_SIMILARITY
        )
        candidates.extend(self._relevant_short_term_candidates(query_text, session_id))

        results = [self._to_retrieved_memory(record, score) for record, score in candidates]
        results.sort(key=lambda r: r.combined_rank_score, reverse=True)
        return results[:limit]

    def _relevant_short_term_candidates(
        self, query_text: str, session_id: str
    ) -> list[tuple[MemoryRecord, float]]:
        records = self._short_term_memory.active_context_memories(session_id)
        candidates = []
        for record in records:
            relevance = _keyword_overlap_relevance(query_text, record.content)
            if relevance > 0.0:
                candidates.append((record, relevance))
        return candidates

    def _to_retrieved_memory(
        self, record: MemoryRecord, similarity_score: float
    ) -> RetrievedMemory:
        confidence_score = record.confidence_score
        combined_rank_score = (
            similarity_score * self._memory_config.retrieval_similarity_weight
            + (confidence_score / 100) * self._memory_config.retrieval_confidence_weight
        )
        band = self._confidence_scorer.band(confidence_score)
        reason = _build_retrieval_reason(similarity_score, confidence_score, band)
        return RetrievedMemory(
            record=record,
            similarity_score=similarity_score,
            confidence_score=confidence_score,
            combined_rank_score=combined_rank_score,
            retrieval_reason=reason,
        )


def _as_similarity_candidates(
    scored: list[tuple[MemoryRecord, float]],
) -> list[tuple[MemoryRecord, float]]:
    """Convert a list of (record, Chroma distance) pairs into
    (record, similarity) pairs via _chroma_distance_to_similarity()."""
    return [(record, _chroma_distance_to_similarity(distance)) for record, distance in scored]


def _chroma_distance_to_similarity(distance: float) -> float:
    """Normalize an unbounded Chroma distance into (0, 1] — see this
    module's own docstring for why 1/(1+distance) was chosen over a
    linear min-max normalization."""
    return 1.0 / (1.0 + distance)


def _build_retrieval_reason(similarity: float, confidence: float, band: ConfidenceBand) -> str:
    """ASCII-only separator ("-", not a Unicode middle dot): a non-ASCII
    character in a runtime string mojibakes on the Windows console's
    default codepage — the same failure mode already found and fixed for
    an em-dash in Sprint 1.6 (docs/sprint_book/sprint_1_6.md), which
    established sticking to ASCII in every runtime log/display string."""
    label = _BAND_LABELS[band]
    return f"{similarity * 100:.0f}% similar - {label} confidence ({confidence:.0f}/100)"


def _keyword_overlap_relevance(query_text: str, content: str) -> float:
    """Crude token-overlap relevance proxy for Short-Term Memory, which
    has no Chroma embedding of its own (active_context_memories() is a
    plain recency query, not a semantic search) — see this module's own
    docstring. Returns the fraction of query_text's meaningful words also
    present in content, in [0, 1]."""
    query_words = _meaningful_words(query_text)
    if not query_words:
        return 0.0
    content_words = _meaningful_words(content)
    overlap = query_words & content_words
    return len(overlap) / len(query_words)


def _meaningful_words(text: str) -> set[str]:
    return {w for w in _WORD_PATTERN.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2}
