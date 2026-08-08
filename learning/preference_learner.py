"""Preference Learning — the Learning Engine's own real, disclosed
dependency widening beyond Sprint 5.21's Pattern Recognition. See
docs/sprint_book/sprint_5/sprint_5_23.md.

**PreferenceLearner.detect_conversation_style() is the one place in this
entire Part that reads memory/memory_store.py's MemoryStore directly**,
rather than analytics/usage_store.py's UsageStore/AnalyticsDashboardService
— a deliberate, narrow, disclosed exception to this Part's own otherwise-
consistent "Analytics data in, patterns out" data flow (5.17→5.20/5.21),
justified specifically because "Preferred conversation style" (Part 2's
own named Learning Engine capability) has no other real signal anywhere
in this codebase. MemoryRecord.memory_type (JARVIS/MINIE/SHARED, already
real and persisted since Sprint 3.1) is the one genuinely available proxy
for "which persona's own conversational style the user actually engages
with more" — a real, already-stored signal, not a fabricated one, and not
a new tracking mechanism invented for this sprint alone.

**A real, disclosed layering choice**: MemoryStore's own public interface
has no direct "count records of this type" primitive (only recent(),
which takes a bounded limit) — this sprint's own Files to Modify
deliberately excludes memory/memory_store.py, so rather than adding a new
method to Level 3's own frozen store, detect_conversation_style() reuses
recent() exactly as designed, sampling up to _SAMPLE_LIMIT most recent
records of each type. This is the same "defensive bound against an
unbounded historical scan" discipline LearningConfig.lookback_days
already established elsewhere in this Part, applied here to a record
count instead of a time window.

SHARED-typed records are excluded from the count structurally, not via a
filter — detect_conversation_style() only ever queries MemoryType.JARVIS/
MemoryType.MINIE, since SHARED names no persona preference by
construction.
"""

from __future__ import annotations

from datetime import UTC, datetime

from config.schema import LearningConfig
from core.logging_setup import get_logger
from learning.pattern_model import LearnedPattern, PatternType
from learning.pattern_store import PatternStore
from memory.memory_store import MemoryStoreProtocol
from memory.models import MemoryType

logger = get_logger(__name__)

# A defensive bound on how many of each persona's most recent memory
# records detect_conversation_style() samples — see this module's own
# docstring for why MemoryStore's own recent() (not a new count-by-type
# method) is reused as-is.
_SAMPLE_LIMIT = 1000


class PreferenceLearner:
    """Constructor DI: (memory_store, pattern_store, learning_config).

    memory_store is typed against MemoryStoreProtocol, not the concrete
    MemoryStore, since Runtime Phase 6 (Runtime Refactor Sprint) threads
    a LazyMemoryStore proxy through here in real operation."""

    def __init__(
        self,
        memory_store: MemoryStoreProtocol,
        pattern_store: PatternStore,
        learning_config: LearningConfig,
    ) -> None:
        self._memory_store = memory_store
        self._pattern_store = pattern_store
        self._config = learning_config

    def detect_conversation_style(self) -> LearnedPattern | None:
        """Returns None (never a forced 50/50 guess) until the combined
        JARVIS+MINIE record count clears conversation_style_min_records;
        otherwise upserts and returns a CONVERSATION_STYLE pattern whose
        subject is whichever persona has the higher count, confidence
        scaled by how lopsided the real split is (0.0 at an even split,
        approaching 1.0 the more one-sided it is) — a near-even split
        correctly produces low confidence, not a confident guess."""
        jarvis_count = len(self._memory_store.recent(MemoryType.JARVIS, _SAMPLE_LIMIT))
        minie_count = len(self._memory_store.recent(MemoryType.MINIE, _SAMPLE_LIMIT))
        combined = jarvis_count + minie_count
        if combined < self._config.conversation_style_min_records:
            return None

        if jarvis_count >= minie_count:
            subject, majority, minority = "jarvis", jarvis_count, minie_count
        else:
            subject, majority, minority = "minie", minie_count, jarvis_count
        confidence = (majority - minority) / combined

        now = datetime.now(UTC)
        pattern = LearnedPattern(
            pattern_type=PatternType.CONVERSATION_STYLE,
            description=f"Engages more often with {subject.capitalize()}'s conversational style",
            subject=subject,
            confidence=confidence,
            evidence_count=combined,
            first_observed_at=now,
            last_updated_at=now,
        )
        self._pattern_store.upsert(pattern)
        return pattern
