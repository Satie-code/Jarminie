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

## Sprint Completion Report (2026-07-17)

Delivered exactly the files this sprint's spec named, nothing else:

- `voice/context_manager.py` — `ConversationContext` (dataclass), `ContextManager` (plain class, not a `ManagedModule`, per spec).
- `tests/unit/voice/test_context_manager.py` — 10 tests, all against a real `ConversationSessionStore` backed by a real SQLite file under `tmp_path` (Sprint 2.7's own established pattern — `ContextManager`'s job is aggregating exactly what the store returns, so exercising the real store's bounded-window/ordering contract together with this module's logic is the most faithful test of "reflects exactly... from the store").

No files were modified — `voice/conversation_store.py` is untouched, per the spec's own "Files to Modify: None." 207/207 tests passing project-wide (197 prior + 10 new), `ruff check .` clean.

**All Acceptance Criteria met**: `current_context()` returns exactly the configured `recent_turn_window` most recent turns oldest-first (tested at the boundary — exactly 6, and one over at 7, confirming the oldest turn is the one dropped); an empty session returns an empty `recent_turns` list rather than erroring; calling `current_context()` twice with an unchanged store returns equal (dataclass `==`, not identity) results, and a newly recorded turn is picked up on the very next call (no internal caching). No inference/scoring/classification dependency exists anywhere in the module — its only imports are `dataclasses`, `datetime`, and `voice.conversation_store`.

**One real spec gap resolved during implementation, worth recording**: the spec's `ConversationContext` wants `session_started_at`/`last_activity_at` fields, and its Objectives line describes them as "session timing metadata (from 2.5)" — but this sprint's Dependencies list only 2.7, and `ContextManager`'s Expected Classes constructor signature is explicitly `(store: ConversationSessionStore, recent_turn_window: int = 6)`, with no `VoiceSessionManager` parameter to read live session timing from. Files to Modify is also "None," ruling out adding a new timing-query method to `ConversationSessionStore`. Resolved by deriving both timestamps purely from the bounded `recent_turns` window `get_recent_turns()` already returns: `session_started_at` = earliest turn's timestamp, `last_activity_at` = latest turn's timestamp, both within the same window — meaning for a session with more history than `recent_turn_window`, `session_started_at` reflects the start of the *visible window*, not the session's true first turn. This is documented as a deliberate approximation in `current_context()`'s own docstring (a working-context aggregator, not a historical record). For a session with zero turns, both fields fall back to the moment of the call (`datetime.now(UTC)`), covered by `test_empty_session_timing_metadata_defaults_to_now`. If a future sprint (2.9+, or Sprint 2.12 integration) needs the *true* session start rather than the visible window's start, that would mean either widening the query in `ConversationSessionStore` or injecting `VoiceSessionManager` directly — flagged here rather than guessed at, since it wasn't needed by anything in this sprint's own Acceptance Criteria.

Phase 2.2 (Conversation Engine) is now **Complete** — `docs/STATUS.md` updated accordingly. **Sprint 2.9 (Persona Base & Jarvis Persona) is next.**
