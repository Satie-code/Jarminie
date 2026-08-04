"""Usage & Habit Tracking — the Analytics Engine's data model. See
docs/sprint_book/sprint_5/sprint_5_17.md.

AppFocusSample is deliberately immutable and per-poll (one row per real
observation), never a mutable "current session" object updated in place
across ticks. Sessions are derived at READ time by UsageStore.
list_sessions_since() grouping contiguous same-process samples instead
— simpler and more honest about what was actually observed: a gap in
samples (a missed poll, the process asleep) can never silently merge
two real, distinct sessions into one, the same "prefer a simpler, more
honest shape over a stateful one" reasoning scheduler/scheduler_model.py's
own single-ScheduledItem-shape decision already used (Sprint 4.14) for
a different problem. See usage_store.py's own module docstring for the
grouping rule itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4


@dataclass
class AppFocusSample:
    """One real, immutable observation of the foreground application at
    a point in time. sample_id is generated on construction (UUID4)
    unless supplied — matching memory/models.py's MemoryRecord.id
    precedent (Sprint 3.1)."""

    process_name: str
    window_title: str
    sampled_at: datetime
    sample_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class UsageSession:
    """A derived, contiguous run of AppFocusSamples sharing the same
    process_name — never stored directly, always computed by
    UsageStore.list_sessions_since() from real, persisted samples.

    category is resolved via AnalyticsConfig.category_map (a
    process_name -> category lookup), None when process_name has no
    configured mapping — never guessed.

    sample_count is a cheap, honest confidence signal: a session backed
    by one sample is far less certain to reflect real, sustained focus
    than one backed by twenty, the same "confidence as an honest
    scalar" discipline emotion/models.py's EmotionEstimate.confidence
    already established (Sprint 5.1)."""

    process_name: str
    category: str | None
    started_at: datetime
    ended_at: datetime
    sample_count: int
