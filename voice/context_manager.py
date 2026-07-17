"""Context Manager — assembles the current conversation's working context
(active persona, recent turns, session timing) into one read shape other
subsystems can query.

This is a **pure aggregator, not a reasoning engine**: it performs no
inference, classification, sentiment analysis, or topic modeling. Real
context analysis belongs to Level 3's Decision Engine (Phase 3.3: Intent
Detection, Sprint 3.7; Context Analysis, Sprint 3.8) — this module must
never quietly grow into a second, competing implementation those sprints
would then have to reconcile with or replace. See
docs/sprint_book/sprint_2_8.md.

ContextManager is deliberately NOT a ManagedModule: it holds no
background thread, connection, or hardware resource of its own, only a
reference to ConversationSessionStore (Sprint 2.7), which already owns
persistence and its own lifecycle. current_context() recomputes its result
fresh from the store on every call — no internal caching to go stale.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from voice.conversation_store import ConversationSessionStore, ConversationTurn


@dataclass
class ConversationContext:
    """A snapshot of the current conversation's working context, valid at
    the moment it was assembled — callers needing a fresh view call
    ContextManager.current_context() again rather than holding onto one."""

    session_id: str
    active_persona_name: str
    recent_turns: list[ConversationTurn]
    session_started_at: datetime
    last_activity_at: datetime


class ContextManager:
    """Constructor DI per 03_Engineering_Standards.md: receives the
    ConversationSessionStore it reads from rather than constructing it
    itself. recent_turn_window (default 6) is a starting guess with no
    real usage data yet — trivially adjustable here if wrong; not
    promoted to VoiceConfig until a real need for tuning it is observed
    (avoids speculative configuration surface)."""

    def __init__(self, store: ConversationSessionStore, recent_turn_window: int = 6) -> None:
        self._store = store
        self._recent_turn_window = recent_turn_window

    def current_context(self, session_id: str, active_persona_name: str) -> ConversationContext:
        """Assemble a fresh ConversationContext from the store's current
        state.

        session_started_at/last_activity_at are derived from the returned
        recent_turns themselves (the earliest/latest timestamp in that
        bounded window) rather than from a live VoiceSessionManager
        reference — this sprint's only dependency is ConversationSessionStore
        (2.7), per its Dependencies/constructor signature. For a session
        with more turns than recent_turn_window, session_started_at
        reflects the start of the *visible window*, not necessarily the
        session's true first turn — an acceptable approximation for a
        working-context aggregator, not a historical record. For an empty
        session (no turns recorded yet), both fields default to the
        moment of this call.
        """
        recent_turns = self._store.get_recent_turns(session_id, limit=self._recent_turn_window)
        if recent_turns:
            session_started_at = recent_turns[0].timestamp
            last_activity_at = recent_turns[-1].timestamp
        else:
            now = datetime.now(UTC)
            session_started_at = now
            last_activity_at = now
        return ConversationContext(
            session_id=session_id,
            active_persona_name=active_persona_name,
            recent_turns=recent_turns,
            session_started_at=session_started_at,
            last_activity_at=last_activity_at,
        )
