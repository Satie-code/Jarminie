"""CompanionExperienceEngine (Sprint 5.13 — Level 5 Part A).

Assembles greetings, idle behavior, celebrations, context awareness, and
relationship continuity — the brief's own named companion-experience
list — from capability every prior Part A sprint already built. This
sprint is deliberately almost entirely **composition**, not new
mechanism:

- **Greetings** are keyed off real idle duration since the last session
  (`ConversationSessionStore`, Sprint 2.7 — already real, already
  persisted; this module reads a caller-supplied duration, adds nothing
  new to that store).
- **Idle behaviors** delegate entirely to `GestureEngine.
  maybe_roll_ambient_gesture()`/`GestureTrigger.AMBIENT_IDLE` (Sprint
  5.9) — this module does not build a second idle-gesture mechanism
  (explicitly named as a risk to avoid in Sprint 5.9's own Integration
  Considerations).
- **Celebrations** are triggered by `EmotionalMemory.
  recall_recent_moments()` (Sprint 5.3) surfacing a high-significance
  record, or by `EventMemory`'s own existing permanent milestones
  (Sprint 3.3) — both already real.
- **Relationship continuity** is a natural greeting referencing a past
  `EmotionalMemory` record ("last time we talked you mentioned X") —
  the brief's own explicit example.
- **Wellness reminders are explicitly named, not built** — Part B's own
  future Wellness Engine (sprints 5.17–5.19) owns that capability
  entirely; this module leaves no `WELLNESS`-shaped placeholder at all
  (see this module's own Integration Considerations reasoning, quoted
  from the Sprint Book: adding an unused reserved value now would repeat
  the same "reserved but never wired" confusion this project has had to
  correct after the fact before — `backlog/technical_debt.md` item 17's
  own history).

**Decide the moment, not the phrasing or rendering** — mirrors
`GestureEngine`'s own established when/how split exactly:
`CompanionExperienceEngine` decides *that* a greeting/celebration/
continuity-callback is warranted and *what content* it should
reference (a `CompanionMoment`), never *how* it's phrased or rendered.
`CompanionMoment.referenced_content` is deliberately a plain string
(the stored `MemoryRecord.content` verbatim), never a pre-formatted
greeting sentence — turning it into natural language is `Persona.
compose_reply()`'s own future job (Sprint 5.14 wires it), and rendering
goes through whichever `Renderer` is mounted (Sprint 5.6). This module
holds no reference to any `Persona`, `Renderer`, or `TextToSpeech`, and
adds no new phrasing-generation or rendering code of its own.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from config.schema import PresentationConfig
from memory.emotional_memory import EmotionalMemory
from memory.event_memory import EventMemory
from memory.models import MemoryRecord, MemoryType

_EMOTIONAL_MEMORY_TYPES: tuple[MemoryType, ...] = (
    MemoryType.SHARED,
    MemoryType.JARVIS,
    MemoryType.MINIE,
)
"""The three memory_types EmotionalMemory.recall_recent_moments() accepts
(EmotionalMemory.record_significant_moment()'s own allowed set) — a
companion moment is not persona-scoped at this engine's own level (no
persona_name parameter anywhere in this module), so all three are
queried and the single most significant result across them wins."""


class CompanionMomentType(Enum):
    """A plain Enum, trivially extended later — deliberately NOT
    pre-populated with a WELLNESS value (see this module's own
    docstring)."""

    GREETING = "greeting"
    CELEBRATION = "celebration"
    CONTINUITY_CALLBACK = "continuity_callback"


@dataclass
class CompanionMoment:
    """referenced_content is the stored MemoryRecord.content verbatim —
    never a pre-formatted sentence (Architecture Notes). None for a
    plain greeting with nothing specific to reference. referenced_at is
    when the referenced memory/event actually happened (occurred_at, or
    created_at if occurred_at was never given), for a natural "last
    time..." framing — distinct from detected_at, when this engine
    itself noticed the moment."""

    moment_type: CompanionMomentType
    referenced_content: str | None
    referenced_at: datetime | None
    detected_at: datetime


def _effective_occurred_at(record: MemoryRecord) -> datetime:
    """occurred_at if the record was given one, otherwise created_at —
    the same "when it happened, falling back to when it was written"
    reasoning EmotionalMemory/EventMemory's own docstrings already
    establish for occurred_at itself."""
    return record.occurred_at if record.occurred_at is not None else record.created_at


def _more_recent(a: MemoryRecord | None, b: MemoryRecord | None) -> MemoryRecord | None:
    """None-tolerant "prefer the more recent of the two" — Expected
    Functions' own check_for_celebration() wording."""
    if a is None:
        return b
    if b is None:
        return a
    return a if _effective_occurred_at(a) >= _effective_occurred_at(b) else b


class CompanionExperienceEngine:
    """Constructor DI per 03_Engineering_Standards.md: receives
    EmotionalMemory (5.3), EventMemory (3.3), and PresentationConfig
    only — no Persona/Renderer/TextToSpeech reference (Architecture
    Notes)."""

    def __init__(
        self,
        emotional_memory: EmotionalMemory,
        event_memory: EventMemory,
        presentation_config: PresentationConfig,
    ) -> None:
        self._emotional_memory = emotional_memory
        self._event_memory = event_memory
        self._config = presentation_config

    def check_for_greeting(self, idle_duration_seconds: float) -> CompanionMoment | None:
        """Never raises. None below greeting_idle_threshold_seconds.
        Otherwise a GREETING moment — check_for_continuity_callback() is
        consulted internally as a secondary check, and its own content
        (if any) is folded into the single returned GREETING moment
        rather than firing as a second, separate companion-experience
        moment on the same session start."""
        if idle_duration_seconds < self._config.greeting_idle_threshold_seconds:
            return None
        continuity = self.check_for_continuity_callback()
        return CompanionMoment(
            moment_type=CompanionMomentType.GREETING,
            referenced_content=continuity.referenced_content if continuity else None,
            referenced_at=continuity.referenced_at if continuity else None,
            detected_at=datetime.now(UTC),
        )

    def check_for_celebration(self) -> CompanionMoment | None:
        """Never raises. Combines the single most significant
        EmotionalMemory record clearing celebration_significance_threshold
        (across SHARED/JARVIS/MINIE) with EventMemory's own most recent
        milestone, preferring whichever of the two actually happened more
        recently. None if neither qualifies — an honest "nothing to
        celebrate right now" is the expected common case, not a
        failure."""
        emotional = self._best_emotional_record(self._config.celebration_significance_threshold)
        milestones = self._event_memory.list_milestones()
        milestone = milestones[0] if milestones else None

        chosen = _more_recent(emotional, milestone)
        if chosen is None:
            return None
        return CompanionMoment(
            moment_type=CompanionMomentType.CELEBRATION,
            referenced_content=chosen.content,
            referenced_at=_effective_occurred_at(chosen),
            detected_at=datetime.now(UTC),
        )

    def check_for_continuity_callback(self) -> CompanionMoment | None:
        """Never raises. A lighter-weight version of check_for_celebration()
        — the single most significant EmotionalMemory record at
        recall_recent_moments()'s own ordinary threshold (MemoryConfig.
        emotional_moment_recall_threshold), not the celebration-raised
        one; never consults EventMemory. None if EmotionalMemory has
        nothing to offer right now."""
        record = self._best_emotional_record()
        if record is None:
            return None
        return CompanionMoment(
            moment_type=CompanionMomentType.CONTINUITY_CALLBACK,
            referenced_content=record.content,
            referenced_at=_effective_occurred_at(record),
            detected_at=datetime.now(UTC),
        )

    def _best_emotional_record(self, min_significance: float = 0.0) -> MemoryRecord | None:
        """The single most significant record across all three
        EmotionalMemory-eligible types meeting min_significance (0.0 —
        the default — accepts anything recall_recent_moments() itself
        already returned, since that method's own internal threshold has
        already filtered out anything below MemoryConfig.
        emotional_moment_recall_threshold)."""
        candidates: list[MemoryRecord] = []
        for memory_type in _EMOTIONAL_MEMORY_TYPES:
            candidates.extend(self._emotional_memory.recall_recent_moments(memory_type, limit=1))
        qualifying = [r for r in candidates if r.emotional_significance >= min_significance]
        if not qualifying:
            return None
        qualifying.sort(key=lambda r: r.emotional_significance, reverse=True)
        return qualifying[0]
