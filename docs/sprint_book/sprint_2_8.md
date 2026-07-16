# Sprint 2.8 — Context Manager

## Sprint ID

2.8

## Sprint Name

Context Manager

## Purpose

Complete Phase 2.2 (Conversation Engine) by assembling the current conversation's working context — active persona, recent turns, session metadata — into a single object other subsystems can query, per [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md)'s Phase 2.2 task: *"Context management."*

## Engineering Rationale

This module is a **pure aggregator**, not a reasoning engine. It assembles what Conversation Session Store (2.7) and Voice Session Manager (2.5) already know into one convenient read shape. It performs no inference, classification, sentiment analysis, or topic modeling — that is Level 3's Decision Engine responsibility (Phase 3.3: Intent Detection, Sprint 3.7; Context Analysis, Sprint 3.8), explicitly out of scope per this task's exclusion of any productivity/learning/decision functionality in Level 2. Keeping this distinction sharp now avoids Context Manager quietly growing into a second, competing Context Analysis implementation that Sprint 3.8 would then have to reconcile with or replace.

## Objectives

- A `ConversationContext` value object: current session id, active persona name, a bounded window of recent turns (read from 2.7), and session timing metadata (from 2.5).
- A `ContextManager` that assembles and refreshes this object as turns complete — no persistence of its own (it reads from 2.7, which already persists).
- No classification, scoring, or "meaning" is attached to the context — only structural aggregation.

## Dependencies

2.7 (Conversation Session Store)

## Files to Create

- `voice/context_manager.py` — `ConversationContext` (dataclass), `ContextManager`.
- `tests/unit/voice/test_context_manager.py`

## Files to Modify

None.

## Expected Classes

- `ConversationContext` (dataclass) — `session_id: str`, `active_persona_name: str`, `recent_turns: list[ConversationTurn]` (bounded, e.g. last 6), `session_started_at: datetime`, `last_activity_at: datetime`.
- `ContextManager` — constructor DI: `(store: ConversationSessionStore, recent_turn_window: int = 6)`. Not a `ManagedModule` — it holds no background thread, connection, or hardware resource of its own; it is a stateless-per-call aggregator over `store`, so a lifecycle interface would be an empty formality (avoids over-fitting `ManagedModule` to something that doesn't need it, the opposite mistake from the one flagged in Sprint 1.5's risk about Voice Engine).

## Expected Interfaces

None new — this module is a plain class, deliberately not implementing `ManagedModule` per the reasoning above.

## Expected Functions

- `ContextManager.current_context(session_id: str, active_persona_name: str) -> ConversationContext` — reads `store.get_recent_turns()`, assembles the value object fresh on each call (no internal caching to go stale — recomputed from the store's current state every time it's asked).

## Data Flow

```
ConversationSessionStore.get_recent_turns(session_id)  (2.7)
      ↓
ContextManager.current_context(session_id, active_persona_name)
      ↓
ConversationContext (session_id, active_persona_name, recent_turns, timing)
      ↓
Persona.compose_reply(context)  (2.9+)  /  Persona switching heuristics (2.11)
```

## Acceptance Criteria

- `current_context()` reflects exactly the most recent `recent_turn_window` turns from the store, oldest-first, no more and no fewer.
- No inference, scoring, or classification logic exists anywhere in this module — verifiable by inspection (no dependency on Ollama, no keyword classifiers) as part of code review (Development Guide Step 9).
- Calling `current_context()` twice in a row with an unchanged store returns equal (not necessarily identical-object) results — purely a function of current persisted state.

## Testing Checklist

- [ ] Unit: `current_context()` returns the correct bounded window of recent turns for a given session.
- [ ] Unit: an empty session (no turns yet) returns a `ConversationContext` with an empty `recent_turns` list, not an error.
- [ ] Unit: `recent_turn_window` boundary (exactly at the limit, one over).

## Documentation Checklist

- [ ] `voice/context_manager.py` docstring: explicit "aggregation only, no inference" statement, cross-referencing Sprint 3.7/3.8 as where real context analysis will live.
- [ ] `docs/STATUS.md` — Phase 2.2 (Conversation Engine) marked **Complete**.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md). This sprint also closes Phase 2.2 (Conversation Engine).

## Estimated Complexity

Low-Medium — the aggregation logic itself is simple; the discipline is in resisting scope creep toward Level 3's Decision Engine.

## Estimated Development Time

0.5–1 day.

## Risks

- **Temptation to add "lightweight" keyword-based intent hints here** to make Persona Switching (2.11) or a future Decision Engine "easier" — must be resisted; if Persona Switching needs a heuristic, it belongs in `personas/persona_manager.py` (2.11) reading `ConversationContext.recent_turns` itself, not baked into this aggregator. Flagged explicitly to keep the boundary with Sprint 2.11 clean.
- **`recent_turn_window` sizing** is a guess (6) with no real usage data yet — trivially config-driven if wrong; not worth promoting to `VoiceConfig` until a real need for tuning it is observed (avoids speculative configuration surface, per the Development Philosophy's preference against premature generality).

## Next Sprint

2.9 — Persona Base & Jarvis Persona.
