# Sprint 3.3 — Event Memory

## Sprint ID

3.3

## Sprint Name

Event Memory

## Purpose

Implement Part 2's Event Memory layer: *"Stores permanent milestones. Examples: Major projects, career milestones, important achievements. Never automatically deleted."*

## Engineering Rationale

Event Memory is structurally different from Shared/Jarvis/Minie Memory (Sprint 3.2): it needs a **hard, unconditional** survival guarantee, not just a high confidence score. Scoring a milestone 100/100 at creation would still leave it *theoretically* subject to Sprint 3.5's recompute logic if that logic ever regresses — a fragile guarantee resting on a number never being wrong. Sprint 3.1 instead added a dedicated `MemoryRecord.is_permanent: bool` field, structurally independent of `confidence_score`, specifically so this sprint can set it unconditionally and Sprint 3.6's Lifecycle Manager can check one unambiguous flag rather than inferring intent from a score threshold that other code might legitimately recompute. This is the same reasoning already applied to `SwitchReason`/`is_permanent`-style flags elsewhere in this project: a guarantee should be checkable by inspection, not by trusting a derived value stays correct forever.

Because deletion here would violate Part 2's explicit "never automatically deleted," this sprint deliberately does **not** expose a `delete()` method on its own wrapper class at all — only `MemoryStore.delete()` (Sprint 3.1) can remove an event record, and no code in Levels 3 calls it. A future explicit user "forget this" command (out of this Level's scope) would be the only legitimate caller, and would call `MemoryStore.delete()` directly with clear justification, not through a convenience method that makes deletion look routine.

## Objectives

- An `EventMemory` wrapper over `MemoryStore` that always writes `memory_type=EVENT, is_permanent=True`, regardless of caller input.
- No deletion or expiry path exposed by this class.
- Milestones are queryable both by recency and by category (e.g. "career", "project").

## Dependencies

3.1 (Memory Store Foundation)

## Files to Create

- `memory/event_memory.py` — `EventMemory`.
- `tests/unit/memory/test_event_memory.py`

## Files to Modify

None.

## Expected Classes

- `EventMemory` — constructor DI: `(memory_store: MemoryStore)`. Plain class, same reasoning as `PersonaScopedMemory` (3.2) for not implementing `ManagedModule`.

## Expected Interfaces

None new.

## Expected Functions

- `EventMemory.record_milestone(content: str, category: str, occurred_at: datetime | None = None) -> str` — always constructs `MemoryRecord(memory_type=MemoryType.EVENT, is_permanent=True, confidence_score=100.0, ...)`; `is_permanent` and `confidence_score` are **not** caller-settable parameters — the signature has no way to pass a lower value, closing off the mistake at the type level rather than validating it at runtime.
- `EventMemory.list_milestones(category: str | None = None) -> list[MemoryRecord]` — recency-ordered; `category=None` returns all.
- `EventMemory.search_milestones(query_text: str, n_results: int = 5) -> list[MemoryRecord]` — semantic search scoped to `MemoryType.EVENT` only.

## Data Flow

```
content + category (+ optional occurred_at)
      ↓
EventMemory.record_milestone(...)
      ↓
MemoryStore.store(MemoryRecord(memory_type=EVENT, is_permanent=True, confidence_score=100.0, ...))   (3.1)
      ↓
   (never reachable from) MemoryLifecycleManager.run_cleanup_pass()   (3.6 — excludes is_permanent=True records)
```

## Implementation Tasks

1. `memory/event_memory.py` — `EventMemory`, `record_milestone()`, `list_milestones()`, `search_milestones()`.
2. Unit tests confirming `is_permanent=True` and `confidence_score=100.0` are set on every record regardless of any attempt to influence them, and that no deletion method exists on the class (verified by `hasattr` assertion, a defensive test against a bug class the same way Sprint 2.11 tested `health_check()`'s invariant).

## Architecture Notes

`EventMemory` is the narrowest wrapper in this Sprint Book — deliberately so. It exists only to make "an event record is always permanent" true by construction. It has no dependency on `PersonaScopedMemory` (3.2) — events are not persona-scoped by Part 2's definition (a "career milestone" belongs to the user, not to Jarvis or Minie specifically), so it depends directly on `MemoryStore`.

## Integration Considerations

- No live caller exists yet — a future workflow (e.g. Level 4's Workflow Engine completing a large project) or a direct user statement ("remember that I finished my degree today") would call `record_milestone()`. Wiring a real caller is out of this sprint's and this Level's scope; flagged as a candidate for whichever future sprint first has a concrete need (same discipline as `ConversationSessionStore.purge_older_than()`, `backlog/technical_debt.md` item 11).
- Sprint 3.9's Memory Retrieval Engine includes `EventMemory.search_milestones()` results in its cross-type composition.
- Sprint 3.6's `MemoryLifecycleManager` must never call `MemoryStore.delete()` or `update_confidence()` on any record with `is_permanent=True` — this sprint's Acceptance Criteria requires that guarantee be independently testable from Sprint 3.6's side too.

## Potential Risks

- **No real caller means this sprint's correctness can only be verified in isolation**, not through a realistic end-to-end scenario, until Sprint 3.14's acceptance pass or a later Level provides one. Acceptable — the same was true of Sprint 2.7's `purge_older_than()` at the time it shipped.
- **`occurred_at` vs `created_at` distinction**: a milestone can be recorded well after it happened ("I finished my degree last month"). `occurred_at` is stored as a separate field from `MemoryRecord.created_at` (the write timestamp) to keep that distinction honest — confirmed explicitly here so it isn't silently conflated during implementation.

## Acceptance Criteria

- Every record created via `record_milestone()` has `is_permanent=True` and `confidence_score=100.0`, with no code path able to override either.
- `EventMemory` exposes no method capable of deleting or lowering the confidence of a record it created.
- `list_milestones(category=...)` and `search_milestones()` only ever return `MemoryType.EVENT` records.

## Testing Checklist

- [ ] Unit: `record_milestone()` always sets `is_permanent=True`, `confidence_score=100.0`.
- [ ] Unit: `list_milestones()` category filter and unfiltered recency order.
- [ ] Unit: `search_milestones()` scoped exclusively to `EVENT`.
- [ ] Unit: defensive check — `EventMemory` has no `delete`/`forget`/`expire` method.

## Documentation Checklist

- [ ] `memory/event_memory.py` docstring: explicit "never automatically deleted" guarantee and how `is_permanent` enforces it, cross-referencing Sprint 3.6's obligation to respect the flag.
- [ ] `docs/STATUS.md` — Phase 3.1 (Memory Engine) row remains `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Low-Medium.

## Estimated Development Time

0.5–1 day.

## Next Sprint

3.4 — Short-Term Memory.

## Future Considerations

- A genuine "forget this permanently" user command (Human First Rule — the user's decision always overrides) would need a deliberately separate, harder-to-reach code path than any of this sprint's methods — explicitly not designed here, flagged for whichever future sprint introduces user-driven memory deletion as a first-class feature.
