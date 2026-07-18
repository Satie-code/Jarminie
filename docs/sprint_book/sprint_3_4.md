# Sprint 3.4 — Short-Term Memory

## Sprint ID

3.4

## Sprint Name

Short-Term Memory

## Purpose

Implement Part 2's final memory layer: *"Stores temporary context. Examples: Current conversation, recent searches, temporary tasks. Automatically expires according to the Dynamic Memory Formula."* This closes Phase 3.1 (Memory Engine).

## Engineering Rationale

Short-Term Memory is **not** a second copy of the conversation log — `ConversationSessionStore` (Sprint 2.7) already persists every turn verbatim, bounded by time-based retention. Duplicating that here would be redundant storage with no clear owner, exactly the kind of scope creep Sprint 2.7's own Engineering Rationale explicitly warned against ("if a future sprint is tempted to add a relevance/importance column here, that is Sprint 3.1/3.2's territory, not this one's" — this *is* that future sprint, and the boundary holds in the other direction too: Short-Term Memory does not re-persist raw turns).

Instead, Short-Term Memory **promotes salient items** out of the turn log into a real `MemoryRecord(memory_type=SHORT_TERM)` with a low starting confidence score (0–29, the "Temporary" band per the Dynamic Memory Formula) — something Sprint 3.5 can score properly and Sprint 3.6 can expire if it's never reinforced. What counts as "salient" genuinely requires language understanding, but Intent Detection and Context Analysis (Sprints 3.7/3.8) don't exist yet at this point in the build order. Consistent with this project's established pattern of shipping an honest, deliberately minimal placeholder rather than a fabricated "smart" heuristic pretending to be more capable than it is (`Persona.compose_reply()`, Sprint 2.9; `PersonaManager.detect_context_heuristic()`, Sprint 2.11 — both explicitly documented as replacement candidates for a later, real sprint), this sprint's salience detection is a small, config-driven trigger-phrase/pattern heuristic (e.g. "remind me", "don't forget", explicit date/time mentions), openly documented as a Sprint 3.8 replacement candidate.

## Objectives

- A `ShortTermMemory` wrapper that reads completed turns from `ConversationSessionStore` (2.7) and promotes salient ones into `MemoryStore(SHORT_TERM)` records.
- Promoted records start in the "Temporary" confidence band and carry `source_session_id`, linking them back to the originating conversation.
- No expiry logic here — that is Sprint 3.6's Memory Lifecycle Manager, consuming what this sprint creates.

## Dependencies

3.1 (Memory Store Foundation), 2.7 (Conversation Session Store)

## Files to Create

- `memory/short_term_memory.py` — `ShortTermMemory`.
- `tests/unit/memory/test_short_term_memory.py`

## Files to Modify

- `config/schema.py` — add to `MemoryConfig`: `short_term_default_confidence: float = 15.0` (mid-range of the 0–29 "Temporary" band), `short_term_salience_triggers: list[str] = ["remind me", "don't forget", "note that", "remember that"]` — config-driven, no hardcoded phrases, matching the `jarvis_trigger_phrases`/`wake_phrases` precedent (Sprints 2.11/1.2).

## Expected Classes

- `ShortTermMemory` — constructor DI: `(memory_store: MemoryStore, memory_config: MemoryConfig)`. Plain class (same reasoning as 3.2/3.3 — no owned resource beyond its dependencies).

## Expected Interfaces

None new.

## Expected Functions

- `ShortTermMemory.promote_from_turn(turn: ConversationTurn) -> str | None` — checks `turn.user_text` against `short_term_salience_triggers` (case-insensitive substring match, identical technique to `detect_explicit_selection()` in Sprint 2.11); if matched, stores a `MemoryRecord(memory_type=SHORT_TERM, confidence_score=short_term_default_confidence, source_session_id=turn.session_id, content=turn.user_text, ...)` and returns its id; returns `None` if nothing salient is detected — this is an expected, not exceptional, outcome for most turns.
- `ShortTermMemory.active_context_memories(session_id: str) -> list[MemoryRecord]` — all `SHORT_TERM` records for the given session that have not yet been removed by Sprint 3.6's cleanup (a live query against `MemoryStore`, not a cache — same "recomputed fresh every call" discipline as `ContextManager.current_context()`, Sprint 2.8).

## Data Flow

```
ConversationTurn (from ConversationSessionStore.get_recent_turns(), 2.7)
      ↓
ShortTermMemory.promote_from_turn(turn)
      ↓ (salience trigger matched)
MemoryStore.store(MemoryRecord(memory_type=SHORT_TERM, confidence_score=15.0, source_session_id=...))   (3.1)
      ↓
   (later) ConfidenceScorer.score()   (3.5)  →  MemoryLifecycleManager.run_cleanup_pass()   (3.6)
```

## Implementation Tasks

1. `config/schema.py` — `MemoryConfig` additions; `config/defaults.yaml` updated to match.
2. `memory/short_term_memory.py` — `ShortTermMemory`, `promote_from_turn()`, `active_context_memories()`.
3. Unit tests covering trigger-match/no-match cases and session scoping.

## Architecture Notes

`ShortTermMemory` is the first Level 3 module to depend on a Level 2 module (`ConversationSessionStore`) — a legitimate, intentional cross-level dependency (Short-Term Memory's entire job is deriving signal from conversation history that already exists), not a violation of level boundaries. It does not depend on `ContextManager` (2.8) — it needs the raw `ConversationTurn`, not the aggregated `ConversationContext` view.

This sprint closes **Phase 3.1 (Memory Engine)** — combined with Sprints 3.1–3.3, all five of Part 2's memory layers (Shared, Jarvis, Minie, Event, Short-Term) now exist with real storage and per-type retrieval, satisfying Phase 3.1's "Memory stored correctly" criterion in full and "Retrieval accurate" at the per-type level (cross-type, decision-ready retrieval is Sprint 3.9).

## Integration Considerations

- No live caller of `promote_from_turn()` exists yet — wired into the real turn-completion path by Sprint 3.12 (Decision Engine Integration), the same deferred-wiring discipline used throughout this Sprint Book.
- Sprint 3.9's Memory Retrieval Engine includes `active_context_memories()` results, session-scoped, in its cross-type composition.
- Sprint 3.6's Lifecycle Manager is the only code that removes `SHORT_TERM` records — this sprint creates them but never deletes them itself.

## Potential Risks

- **The salience trigger-phrase heuristic will under-detect** (most genuinely important short-term context won't contain a literal trigger phrase) — an accepted, explicitly documented limitation until Sprint 3.8's real Context Analysis replaces it, exactly like Sprint 2.11's context-detection heuristic was accepted for Level 2. Not a hidden permanent limitation.
- **Every session's turns are scanned per-turn**, not batched — acceptable at current conversation volume; revisit only if Sprint 3.14's real-world verification shows a performance problem (no premature optimization).

## Acceptance Criteria

- A turn containing a configured trigger phrase produces a `SHORT_TERM` record with `confidence_score == short_term_default_confidence` and the correct `source_session_id`.
- A turn without any trigger phrase produces no record and returns `None`.
- `active_context_memories(session_id)` only returns records for that session.
- Combined with Sprints 3.1–3.3, Phase 3.1's Acceptance Criteria ("Memory stored correctly. Retrieval accurate.") are met at the per-type level.

## Testing Checklist

- [ ] Unit: `promote_from_turn()` trigger match → record created with correct fields.
- [ ] Unit: `promote_from_turn()` no match → returns `None`, no record created.
- [ ] Unit: `active_context_memories()` session scoping (two sessions, no cross-contamination).
- [ ] Unit: `MemoryConfig` new fields load with correct defaults.

## Documentation Checklist

- [ ] `memory/short_term_memory.py` docstring: explicit "this is not a second conversation log" statement, and the placeholder-heuristic caveat cross-referencing Sprint 3.8.
- [ ] `docs/STATUS.md` — Phase 3.1 (Memory Engine) marked **Complete**.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md). This sprint also closes Phase 3.1 (Memory Engine).

## Estimated Complexity

Low-Medium.

## Estimated Development Time

1 day.

## Next Sprint

3.5 — Confidence Scoring Engine.

## Future Considerations

- Once Sprint 3.8 (Context Analysis) exists, `promote_from_turn()`'s trigger-phrase check should be replaced by a call into real salience detection — flagged explicitly, not built speculatively now.

---

## Sprint Completion Report (2026-07-18)

### Summary

Implemented `memory/short_term_memory.py`'s `ShortTermMemory` and the `MemoryConfig` additions this sprint's spec named. No gap against Sprint 3.1's shipped `MemoryRecord`/`MemoryStore` this time — `promote_from_turn()`/`active_context_memories()` both map cleanly onto what already exists, following the `EventMemory` (Sprint 3.3) precedent directly for the one place `MemoryStore` doesn't offer a purpose-built query (session-scoped filtering).

### Files Created

- `memory/short_term_memory.py` — `ShortTermMemory` (`promote_from_turn`, `active_context_memories`).
- `tests/unit/memory/test_short_term_memory.py` — 7 tests.

### Files Modified

- `config/schema.py` — `MemoryConfig.short_term_default_confidence: float = 15.0`, `short_term_salience_triggers: list[str]`; validation added to `_validate_memory()` (confidence in `[0, 100]`, non-empty trigger list, no blank entries).
- `config/defaults.yaml` — `memory:` section extended to match.
- `tests/unit/config/test_schema.py` — 4 new tests for the new fields' defaults and validation.
- `docs/STATUS.md` — Phase 3.1 (Memory Engine) marked **Complete**.

### Tests Added

11 new tests: 7 in `test_short_term_memory.py` (trigger match creates a correctly-scored, session-tagged record; case-insensitive matching; no-match returns `None` and creates nothing; session-scoped `active_context_memories()` with no cross-session leakage; empty result for an unknown session; default config values), 4 in `test_schema.py` (defaults, out-of-range confidence, empty/blank trigger list). 355/355 tests passing project-wide, `ruff check .` clean.

### Documentation Updated

This file (Sprint Completion Report). `docs/STATUS.md` — Phase 3.1 marked **Complete**.

### Acceptance Criteria Checklist

- ✔ A turn containing a configured trigger phrase produces a `SHORT_TERM` record with `confidence_score == short_term_default_confidence` and the correct `source_session_id` (`test_promote_from_turn_matches_trigger_and_creates_record`).
- ✔ A turn without any trigger phrase produces no record and returns `None` (`test_promote_from_turn_no_match_returns_none_and_creates_nothing`).
- ✔ `active_context_memories(session_id)` only returns records for that session (`test_active_context_memories_scoped_to_session`).
- ✔ Combined with Sprints 3.1–3.3, Phase 3.1's Acceptance Criteria ("Memory stored correctly. Retrieval accurate.") are met at the per-type level — all five `MemoryType`s now have real storage and retrieval.

### Engineering Decisions

- **`active_context_memories()` fetches via `MemoryStore.recent(SHORT_TERM, limit=_LARGE_LIMIT)` and filters by `source_session_id` in Python**, identical in shape to `EventMemory.list_milestones()`'s category filter (Sprint 3.3) — `MemoryStore` has no session-scoped query of its own. Consistent with that sprint's own reasoning: adding a session-filter parameter to `MemoryStore.recent()` for one caller's need isn't justified yet; revisit if a second caller needs the same filter.

### Remaining Risks

- **The Python-side session filter scans every live `SHORT_TERM` record**, not just one session's — acceptable now (no live caller exists yet, per this sprint's own Integration Considerations, so real volume is zero), but short-term memories accumulate faster than milestones would before Sprint 3.6's cleanup is wired (Sprint 3.12+). Flagged explicitly, not treated as solved — revisit if Sprint 3.12's real integration shows a measured problem, matching the "no premature optimization" principle already applied to `EventMemory`.
- The salience trigger-phrase heuristic remains a known-crude placeholder, unchanged from this sprint's own Potential Risks — still explicitly scheduled for replacement by Sprint 3.8, not a hidden permanent limitation.

### Technical Debt

None introduced.

### Recommendations

- **For Sprint 3.5 (Confidence Scoring Engine)**: if a second caller ever needs session- or category-scoped `MemoryStore` queries beyond what `EventMemory`/`ShortTermMemory` already needed in Python, that's the signal to add a real `MemoryStore`-level filter instead of a third copy of the same fetch-and-filter pattern — not urgent now, flagged for whoever notices it next.

**Phase 3.1 (Memory Engine) is now `Complete`** — all four sprints (3.1–3.4) done; all five of Part 2's memory layers exist with real storage and per-type retrieval. **Sprint 3.5 (Confidence Scoring Engine) is next**, beginning Phase 3.2 (Dynamic Memory).
