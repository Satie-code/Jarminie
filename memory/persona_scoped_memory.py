"""PersonaScopedMemory — Shared, Jarvis, and Minie Memory (Part 2's three
owner-scoped memory layers), built as one wrapper over MemoryStore rather
than three near-identical classes (Single Responsibility: the mechanics of
"store/retrieve scoped by owner" are identical across all three; only the
read-scoping rule differs).

Read-scoping is enforced STRUCTURALLY: recall_for_persona() never
constructs a query against the other persona's collection at all, the same
"structurally impossible to leak" discipline PersonaManager (Sprint 2.11)
established for "no simultaneous personas" — see this module's own tests
for the defensive proof.
"""

from core.logging_setup import get_logger
from memory.memory_store import MemoryStoreProtocol
from memory.models import MemoryRecord, MemoryType

logger = get_logger(__name__)

_OWNER_TYPES = (MemoryType.SHARED, MemoryType.JARVIS, MemoryType.MINIE)
_PERSONA_TYPES = {"jarvis": MemoryType.JARVIS, "minie": MemoryType.MINIE}


class PersonaScopedMemory:
    """Constructor DI: receives the MemoryStore it depends on rather than
    constructing it. Not a ManagedModule — owns no resource of its own
    beyond memory_store (same reasoning as ContextManager, Sprint 2.8).

    Typed against MemoryStoreProtocol, not the concrete MemoryStore,
    since Runtime Phase 6 (Runtime Refactor Sprint) threads a
    LazyMemoryStore proxy through here in real operation — see
    memory/memory_store.py's own docstrings for both."""

    def __init__(self, memory_store: MemoryStoreProtocol) -> None:
        self._memory_store = memory_store

    def remember(
        self,
        owner: MemoryType,
        content: str,
        category: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """Persist content under SHARED, JARVIS, or MINIE. Any other
        MemoryType raises ValueError immediately — a programmer error
        caught at the call site, not a runtime condition to degrade from.
        EVENT/SHORT_TERM have their own dedicated wrappers (Sprints 3.3,
        3.4) and must never be written through this class."""
        if owner not in _OWNER_TYPES:
            raise ValueError(
                f"PersonaScopedMemory.remember() only accepts {_OWNER_TYPES}, got {owner}"
            )
        record = MemoryRecord(
            memory_type=owner,
            content=content,
            category=category,
            source_session_id=session_id,
        )
        return self._memory_store.store(record)

    def recall_for_persona(
        self, persona_name: str, query_text: str, n_results: int = 5
    ) -> list[MemoryRecord]:
        """Query SHARED and the matching persona-specific collection only.
        persona_name must be "jarvis" or "minie". The persona-specific
        MemoryType is selected via a literal lookup, not a post-hoc filter
        over a combined query — the Jarvis code path never constructs a
        query against MemoryType.MINIE, or vice versa.

        Thin wrapper over recall_for_persona_scored() that discards
        distance, kept for every caller that only needs records — see
        that method for the merge details."""
        scored = self.recall_for_persona_scored(persona_name, query_text, n_results)
        return [record for record, _distance in scored]

    def recall_for_persona_scored(
        self, persona_name: str, query_text: str, n_results: int = 5
    ) -> list[tuple[MemoryRecord, float]]:
        """Same query as recall_for_persona(), but keeps each result's
        Chroma distance. Added during Sprint 3.9 (MemoryRetrievalEngine),
        which needs a genuine similarity score to blend with confidence —
        recall_for_persona() itself predates that need and always
        discarded distance, so this is additive, not a breaking change to
        an already-shipped method. See docs/sprint_book/sprint_3_1.md's
        Post-Sprint Fix, which exposed distance at the MemoryStore layer
        specifically so this composition could eventually happen.

        Both source lists come back from MemoryStore.semantic_search() as
        (record, distance) pairs; this method merges them by genuinely
        re-sorting on Chroma distance (lowest = most similar first), per
        this sprint's own spec — not by interleaving two separately-sorted
        lists."""
        if persona_name not in _PERSONA_TYPES:
            raise ValueError(
                f"PersonaScopedMemory.recall_for_persona_scored() only accepts "
                f"{sorted(_PERSONA_TYPES)}, got {persona_name!r}"
            )
        persona_type = _PERSONA_TYPES[persona_name]
        shared_results = self._memory_store.semantic_search(
            MemoryType.SHARED, query_text, n_results
        )
        persona_results = self._memory_store.semantic_search(persona_type, query_text, n_results)
        merged = _merge_by_distance_scored(shared_results, persona_results)
        return merged[:n_results]

    def recall_shared_only(self, query_text: str, n_results: int = 5) -> list[MemoryRecord]:
        """For contexts with no persona attribution yet (used later by
        Sprint 3.9's cross-type retrieval)."""
        results = self._memory_store.semantic_search(MemoryType.SHARED, query_text, n_results)
        return [record for record, _distance in results]


def _merge_by_distance_scored(
    first: list[tuple[MemoryRecord, float]], second: list[tuple[MemoryRecord, float]]
) -> list[tuple[MemoryRecord, float]]:
    """Combine two (record, distance) lists into one, sorted by ascending
    distance (most similar first), keeping distance intact — added
    alongside recall_for_persona_scored() (Sprint 3.9). Both source lists
    only ever contain a given id once (they come from different Chroma
    collections), so no dedup is needed here."""
    return sorted(first + second, key=lambda pair: pair[1])


def _merge_by_distance(
    first: list[tuple[MemoryRecord, float]], second: list[tuple[MemoryRecord, float]]
) -> list[MemoryRecord]:
    """Combine two (record, distance) lists into one MemoryRecord list,
    sorted by ascending distance (most similar first), discarding
    distance. Thin wrapper over _merge_by_distance_scored()."""
    return [record for record, _distance in _merge_by_distance_scored(first, second)]
