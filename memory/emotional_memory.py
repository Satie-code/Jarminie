"""EmotionalMemory — Part 2's own "Remember: previous stress, celebrations,
important moments, long-term emotional context" (Sprint 5.3 — Level 5
Part A).

The narrowest possible wrapper over MemoryStore, mirroring EventMemory's
own established shape exactly (Sprint 3.3): constructor DI over MemoryStore
(plus MemoryConfig, for emotional_moment_recall_threshold — a small,
necessary extension beyond EventMemory's own single-dependency shape,
since this class's own recall behavior needs a config-driven threshold
EventMemory never did), not a ManagedModule, owns no resource of its own.

"Emotionally significant" is treated as an orthogonal property a record in
any of Part 2's five Memory Architecture layers can have — not a sixth
storage location. record_significant_moment() is deliberately restricted
to SHARED/JARVIS/MINIE: EVENT and SHORT_TERM already have their own
dedicated, narrower wrapper classes (EventMemory, ShortTermMemory) with
their own invariants, and this class must never become a second,
competing way to write into either.

No live caller yet — a real trigger (a detected stress spike, a
celebration) is Sprint 5.14's job. Sprint 5.13 (Companion Experience) is
recall_recent_moments()'s real intended consumer. See
docs/sprint_book/sprint_5/sprint_5_3.md.
"""

from datetime import datetime

from config.schema import MemoryConfig
from emotion.state_manager import EmotionalState
from memory.memory_store import MemoryStoreProtocol
from memory.models import MemoryRecord, MemoryType

_ALLOWED_MEMORY_TYPES = frozenset({MemoryType.SHARED, MemoryType.JARVIS, MemoryType.MINIE})

# Mirrors EventMemory's own _LARGE_LIMIT precedent — MemoryStore.recent()
# requires an explicit limit (no "all" sentinel); this pulls a generous
# internal candidate pool for recall_recent_moments() to filter/re-sort
# client-side (the identical technique EventMemory.list_milestones()
# already uses for its own category filter), not a real cap on how many
# moments a user could accumulate.
_CANDIDATE_POOL_LIMIT = 10_000

# emotional_significance's own [0.0, 1.0] range — see _score_significance().
_SIGNIFICANCE_DIMENSIONS: tuple[tuple[str, float, float], ...] = (
    ("mood", 0.0, 100.0),
    ("stress", 50.0, 50.0),
    ("comfort", 50.0, 50.0),
)


def _score_significance(state: EmotionalState) -> float:
    """The maximum absolute deviation of stress, mood, and comfort from
    their own neutral midpoints, normalized to 0.0-1.0 — a state sitting
    exactly at neutral scores 0.0; a state at any of the three dimensions'
    own extreme scores 1.0. A deliberately simple, explainable, first-pass
    formula: "significant" moments are, definitionally, ones where the
    state is far from baseline — a stress spike and a joy spike are both
    significant, an ordinary neutral exchange is not."""
    deviations = [
        abs(getattr(state, dimension) - midpoint) / half_range
        for dimension, midpoint, half_range in _SIGNIFICANCE_DIMENSIONS
    ]
    return max(0.0, min(1.0, max(deviations)))


class EmotionalMemory:
    """Constructor DI: receives the MemoryStore and MemoryConfig it
    depends on rather than constructing either. Not a ManagedModule —
    owns no resource of its own (same reasoning as EventMemory,
    PersonaScopedMemory, ShortTermMemory).

    Typed against MemoryStoreProtocol, not the concrete MemoryStore,
    since Runtime Phase 6 (Runtime Refactor Sprint) threads a
    LazyMemoryStore proxy through here in real operation."""

    def __init__(self, memory_store: MemoryStoreProtocol, memory_config: MemoryConfig) -> None:
        self._memory_store = memory_store
        self._memory_config = memory_config

    def record_significant_moment(
        self,
        content: str,
        memory_type: MemoryType,
        category: str,
        state: EmotionalState,
        occurred_at: datetime | None = None,
    ) -> str:
        """Persist a record whose emotional_significance is computed from
        state at write time — a real, derived number, never a
        caller-supplied guess. Raises ValueError for EVENT/SHORT_TERM —
        see this module's own docstring for why."""
        if memory_type not in _ALLOWED_MEMORY_TYPES:
            raise ValueError(
                "EmotionalMemory.record_significant_moment() does not accept "
                f"memory_type={memory_type.value!r}; only "
                f"{sorted(t.value for t in _ALLOWED_MEMORY_TYPES)} are allowed — "
                "EVENT/SHORT_TERM have their own dedicated wrapper classes with "
                "their own invariants."
            )
        record = MemoryRecord(
            memory_type=memory_type,
            content=content,
            category=category,
            emotional_significance=_score_significance(state),
            occurred_at=occurred_at,
        )
        return self._memory_store.store(record)

    def recall_recent_moments(self, memory_type: MemoryType, limit: int = 5) -> list[MemoryRecord]:
        """Records of memory_type whose emotional_significance meets
        MemoryConfig.emotional_moment_recall_threshold, most-significant
        first. Thin passthrough to MemoryStore.recent() plus client-side
        filter/sort — the identical technique EventMemory.list_milestones()
        already uses for its own category filter, not a new MemoryStore
        query capability."""
        candidates = self._memory_store.recent(memory_type, limit=_CANDIDATE_POOL_LIMIT)
        threshold = self._memory_config.emotional_moment_recall_threshold
        significant = [
            record for record in candidates if record.emotional_significance >= threshold
        ]
        significant.sort(key=lambda record: record.emotional_significance, reverse=True)
        return significant[:limit]
