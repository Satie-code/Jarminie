"""Core data model shared by every Level 3 memory-type module.

MemoryType covers all five layers from 02_System_Architecture.md's Memory
Architecture (Shared, Jarvis, Minie, Event, Short-Term). MemoryRecord is the
one record shape MemoryStore persists for all of them — the type-specific
wrappers (PersonaScopedMemory, EventMemory, ShortTermMemory, Sprints 3.2-3.4)
constrain *which* MemoryType/flags they write, not the shape itself.

is_permanent and user_override exist here, unused by any logic in this
sprint, specifically so Sprint 3.3 (Event Memory) and Sprint 3.5 (Confidence
Scoring Engine) never need to modify this file's schema — see
docs/sprint_book/sprint_3_1.md's Potential Risks.

occurred_at (added in Sprint 3.1's Post-Sprint Fix, during Sprint 3.3) is
distinct from created_at: created_at is always "when this row was
written," occurred_at is "when the thing being remembered actually
happened" (e.g. a milestone recorded after the fact). None for every
memory type except Event Memory, where it's genuinely meaningful — see
docs/sprint_book/sprint_3_3.md's Potential Risks.

band_entered_at (added in Sprint 3.1's Post-Sprint Fix, during Sprint 3.6)
is when this record most recently transitioned into its CURRENT
ConfidenceBand (memory/confidence_scorer.py) — distinct from both
created_at (write time) and last_accessed_at (most recent read). Defaults
to "now" at construction (a fresh record's initial band is entered at
creation); MemoryLifecycleManager.run_cleanup_pass() (Sprint 3.6) is the
only code that ever advances it, and only on an actual band change. This
is what lets run_monthly_review() correctly distinguish "been sitting in
Monthly-review for a while" from "just decayed into it a moment ago" —
see docs/sprint_book/sprint_3_6.md's Engineering Decisions.

emotional_significance (added Sprint 5.3 — Emotional Memory, Level 5 Part
A) is a real, derived 0.0-1.0 signal replacing ConfidenceScorer.score()'s
own long-standing _NEUTRAL_EMOTIONAL_SIGNIFICANCE placeholder. Defaults to
0.0 (not the old placeholder's 0.5) — a real, disclosed behavior change
for every record NOT written through memory/emotional_memory.py's
EmotionalMemory.record_significant_moment(), documented in full in
docs/sprint_book/sprint_5/sprint_5_3.md's own Architecture Notes: 0.0
correctly states "not assessed as emotionally significant" for the
overwhelming majority of ordinary records, rather than 0.5's false claim
of moderate significance for content nobody ever actually assessed.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4


class MemoryType(Enum):
    SHARED = "shared"
    JARVIS = "jarvis"
    MINIE = "minie"
    EVENT = "event"
    SHORT_TERM = "short_term"


@dataclass
class MemoryRecord:
    """One stored memory. id is generated on construction (UUID4) unless
    the caller supplies one explicitly (e.g. when rehydrating a row read
    back from SQLite)."""

    memory_type: MemoryType
    content: str
    category: str | None = None
    confidence_score: float = 0.0
    emotional_significance: float = 0.0
    is_permanent: bool = False
    user_override: bool = False
    source_session_id: str | None = None
    occurred_at: datetime | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_accessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    band_entered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    access_count: int = 0
