"""EventMemory — Part 2's Event Memory layer: "Stores permanent milestones
... Never automatically deleted."

The narrowest wrapper in this Sprint Book, deliberately so: it exists only
to make "an event record is always permanent" true by construction.
record_milestone()'s signature has no parameter through which a caller
could pass is_permanent or confidence_score — the mistake is closed off at
the type level, not validated at runtime. This class exposes no delete/
forget/expire method at all; only MemoryStore.delete() (Sprint 3.1) can
remove an event record, and nothing in Level 3 calls it — see this
module's own class docstring.
"""

from datetime import datetime

from memory.memory_store import MemoryStore
from memory.models import MemoryRecord, MemoryType


class EventMemory:
    """Constructor DI: receives the MemoryStore it depends on rather than
    constructing it. Not a ManagedModule — owns no resource of its own
    (same reasoning as PersonaScopedMemory, Sprint 3.2).

    Never automatically deleted: every record this class creates has
    is_permanent=True, which Sprint 3.6's MemoryLifecycleManager must
    check before any deletion/rescoring — enforced structurally here by
    never exposing a delete method at all, not merely by convention."""

    def __init__(self, memory_store: MemoryStore) -> None:
        self._memory_store = memory_store

    def record_milestone(
        self, content: str, category: str, occurred_at: datetime | None = None
    ) -> str:
        """Persist a permanent milestone. is_permanent and confidence_score
        are not caller-settable — always True and 100.0 respectively,
        regardless of input. occurred_at is when the milestone actually
        happened (may be well after created_at, e.g. "I finished my degree
        last month") — distinct from created_at, the write timestamp."""
        record = MemoryRecord(
            memory_type=MemoryType.EVENT,
            content=content,
            category=category,
            confidence_score=100.0,
            is_permanent=True,
            occurred_at=occurred_at,
        )
        return self._memory_store.store(record)

    def list_milestones(self, category: str | None = None) -> list[MemoryRecord]:
        """All EVENT records, newest-created first. category=None returns
        every milestone regardless of category."""
        records = self._memory_store.recent(MemoryType.EVENT, limit=_LARGE_LIMIT)
        if category is None:
            return records
        return [record for record in records if record.category == category]

    def search_milestones(self, query_text: str, n_results: int = 5) -> list[MemoryRecord]:
        """Semantic search scoped to MemoryType.EVENT only. Thin wrapper
        over search_milestones_scored() that discards distance."""
        scored = self.search_milestones_scored(query_text, n_results)
        return [record for record, _distance in scored]

    def search_milestones_scored(
        self, query_text: str, n_results: int = 5
    ) -> list[tuple[MemoryRecord, float]]:
        """Same query as search_milestones(), but keeps each result's
        Chroma distance — added during Sprint 3.9 (MemoryRetrievalEngine),
        which needs a genuine similarity score to blend with confidence.
        Additive: search_milestones() itself is unchanged."""
        return self._memory_store.semantic_search(MemoryType.EVENT, query_text, n_results)


# MemoryStore.recent() requires an explicit limit (no "all" sentinel) —
# this is large enough that no realistic number of milestones a single
# user could accumulate would be truncated by it, while still being a
# real, finite bound rather than an unbounded query.
_LARGE_LIMIT = 10_000
