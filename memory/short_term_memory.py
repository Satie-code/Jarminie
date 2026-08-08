"""ShortTermMemory — Part 2's final memory layer: "Stores temporary
context... Automatically expires according to the Dynamic Memory Formula."

This is NOT a second conversation log. ConversationSessionStore (Sprint
2.7) already persists every turn verbatim, bounded by time-based
retention. Short-Term Memory instead promotes salient items out of that
log into a real MemoryRecord(memory_type=SHORT_TERM) with a low starting
confidence score — something Sprint 3.5's ConfidenceScorer can score
properly and Sprint 3.6's MemoryLifecycleManager can expire if never
reinforced. This module creates SHORT_TERM records; it never deletes them
— only Sprint 3.6 does.

Salience detection is a small, deliberately crude keyword-trigger
heuristic (MemoryConfig.short_term_salience_triggers), openly documented
as a Sprint 3.8 (Context Analysis) replacement candidate — the same
placeholder discipline as PersonaManager.detect_context_heuristic()
(Sprint 2.11) and Persona.compose_reply() (Sprint 2.9). Real salience
detection genuinely requires language understanding that doesn't exist
yet at this point in the build order.
"""

from config.schema import MemoryConfig
from memory.memory_store import MemoryStoreProtocol
from memory.models import MemoryRecord, MemoryType
from voice.conversation_store import ConversationTurn

# MemoryStore.recent() requires an explicit limit — large enough that no
# realistic number of live (not-yet-cleaned-up) short-term memories across
# all sessions would be truncated, same reasoning as EventMemory's
# _LARGE_LIMIT (Sprint 3.3).
_LARGE_LIMIT = 10_000


class ShortTermMemory:
    """Constructor DI: receives the MemoryStore and MemoryConfig it
    depends on rather than constructing either. Not a ManagedModule — owns
    no resource of its own (same reasoning as PersonaScopedMemory/
    EventMemory, Sprints 3.2/3.3).

    Typed against MemoryStoreProtocol, not the concrete MemoryStore,
    since Runtime Phase 6 (Runtime Refactor Sprint) threads a
    LazyMemoryStore proxy through here in real operation."""

    def __init__(self, memory_store: MemoryStoreProtocol, memory_config: MemoryConfig) -> None:
        self._memory_store = memory_store
        self._memory_config = memory_config

    def promote_from_turn(self, turn: ConversationTurn) -> str | None:
        """Check turn.user_text against the configured salience triggers
        (case-insensitive substring match, identical technique to
        PersonaManager.detect_explicit_selection()). If matched, stores a
        SHORT_TERM record at the configured default confidence and
        returns its id. Returns None if nothing salient is detected — an
        expected, not exceptional, outcome for most turns."""
        lowered = turn.user_text.lower()
        matched = any(
            trigger.lower() in lowered
            for trigger in self._memory_config.short_term_salience_triggers
        )
        if not matched:
            return None
        record = MemoryRecord(
            memory_type=MemoryType.SHORT_TERM,
            content=turn.user_text,
            confidence_score=self._memory_config.short_term_default_confidence,
            source_session_id=turn.session_id,
        )
        return self._memory_store.store(record)

    def active_context_memories(self, session_id: str) -> list[MemoryRecord]:
        """All SHORT_TERM records for session_id that haven't yet been
        removed by Sprint 3.6's cleanup. A live query against MemoryStore,
        recomputed fresh every call — no caching, same discipline as
        ContextManager.current_context() (Sprint 2.8).

        MemoryStore has no session_id filter of its own (Sprint 3.1) —
        this fetches every live SHORT_TERM record via recent() and filters
        in Python, the same approach EventMemory.list_milestones() (Sprint
        3.3) already established for its own category filter."""
        records = self._memory_store.recent(MemoryType.SHORT_TERM, limit=_LARGE_LIMIT)
        return [record for record in records if record.source_session_id == session_id]
