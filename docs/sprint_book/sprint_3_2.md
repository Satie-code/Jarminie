# Sprint 3.2 — Shared Memory & Persona Memory

## Sprint ID

3.2

## Sprint Name

Shared Memory & Persona Memory

## Purpose

Implement three of Part 2's five memory layers — Shared Memory, Jarvis Memory, Minie Memory — per [02_System_Architecture.md](../02_System_Architecture.md)'s Memory Architecture: Shared stores "projects, goals, skills, important routines, important life events, long-term preferences"; Jarvis Memory stores "technical discussions, project workflows, programming context, research, automation history"; Minie Memory stores "casual conversations, comfort topics, humor preferences, wellness history, emotional context."

## Engineering Rationale

These three layers share identical mechanics — store content scoped to an owner, retrieve scoped to a reader — differing only in *who may read what*. Building three near-identical classes (`SharedMemory`, `JarvisMemory`, `MinieMemory`) would violate Single Responsibility by triplicating the same logic; this sprint instead builds one `PersonaScopedMemory` over Sprint 3.1's `MemoryStore`, constrained to `MemoryType.SHARED`/`JARVIS`/`MINIE`, that enforces the read-scoping rule **structurally** — a Jarvis-scoped query never issues a Chroma/SQLite query against the Minie collection at all, rather than fetching everything and filtering results afterward. This mirrors the exact discipline `PersonaManager` (Sprint 2.11) already established for "no simultaneous personas": the Sprint Completion Report there deliberately chose a design that made the violation *structurally impossible to express*, not just prevented by convention, specifically so a defensive test could exist. The same principle applies here — memory leaking across personas would be a privacy/trust failure the Human First and Single Responsibility rules both implicitly guard against.

## Objectives

- A `PersonaScopedMemory` wrapping `MemoryStore` (3.1), exposing `remember()`/`recall_for_persona()` for all three owner-scoped layers.
- `recall_for_persona("jarvis", ...)` only ever queries `SHARED` + `JARVIS` collections; `recall_for_persona("minie", ...)` only ever queries `SHARED` + `MINIE`. Neither can reach the other persona's private layer under any input.
- Shared memory content is visible to both personas' recall calls.

## Dependencies

3.1 (Memory Store Foundation)

## Files to Create

- `memory/persona_scoped_memory.py` — `PersonaScopedMemory`.
- `tests/unit/memory/test_persona_scoped_memory.py`

## Files to Modify

None.

## Expected Classes

- `PersonaScopedMemory` — constructor DI: `(memory_store: MemoryStore)`. Not a `ManagedModule` — it owns no resource of its own beyond `memory_store`, the same "plain class, not over-fitted to a lifecycle it doesn't need" reasoning as `ContextManager` (Sprint 2.8).

## Expected Interfaces

None new — depends only on `MemoryStore`'s existing interface.

## Expected Functions

- `PersonaScopedMemory.remember(owner: MemoryType, content: str, category: str | None = None, session_id: str | None = None) -> str` — `owner` must be `SHARED`, `JARVIS`, or `MINIE`; any other value raises `ValueError` immediately (a programmer error caught at the call site, not a runtime condition to degrade from — `EVENT`/`SHORT_TERM` have their own dedicated wrappers, Sprints 3.3/3.4, and must never be written through this class).
- `PersonaScopedMemory.recall_for_persona(persona_name: str, query_text: str, n_results: int = 5) -> list[MemoryRecord]` — `persona_name` must be `"jarvis"` or `"minie"`. Internally issues exactly two `MemoryStore.semantic_search()` calls — `SHARED` and the matching persona type — merges the two result lists, and re-sorts by Chroma distance. At no point does the Jarvis code path construct a query against `MemoryType.MINIE`, or vice versa; this is enforced by a literal `if/elif` over `persona_name` selecting the second `MemoryType`, not a post-hoc filter over a combined query.
- `PersonaScopedMemory.recall_shared_only(query_text: str, n_results: int = 5) -> list[MemoryRecord]` — for contexts with no persona attribution yet (used later by Sprint 3.9's cross-type retrieval).

## Data Flow

```
content + owner (SHARED | JARVIS | MINIE)
      ↓
PersonaScopedMemory.remember(owner, content, ...)
      ↓
MemoryStore.store(MemoryRecord(memory_type=owner, ...))   (3.1)

query_text + persona_name
      ↓
PersonaScopedMemory.recall_for_persona(persona_name, query_text)
      ↓                              ↓
MemoryStore.semantic_search(SHARED)  MemoryStore.semantic_search(JARVIS | MINIE)
      ↓                              ↓
            merged, re-sorted MemoryRecord[]
      ↓
Sprint 3.9's Memory Retrieval Engine / Sprint 3.12's Decision Engine Integration
```

## Implementation Tasks

1. `memory/persona_scoped_memory.py` — `PersonaScopedMemory`, `remember()`, `recall_for_persona()`, `recall_shared_only()`.
2. Unit tests including a structural leak test: with both Jarvis-only and Minie-only content stored, assert `recall_for_persona("jarvis", ...)` cannot return the Minie-only record under any query text, and vice versa.

## Architecture Notes

`PersonaScopedMemory` sits directly on top of `MemoryStore` with no SQLite/Chroma knowledge of its own — the same layering discipline as `ContextManager` sitting on `ConversationSessionStore`. It has no awareness of `PersonaManager` (2.11) or `Persona` (2.9/2.10) — it takes `persona_name: str`, not a `Persona` object, keeping `memory/` decoupled from `personas/` (cross-module dependencies stay minimal, per [03_Engineering_Standards.md](../03_Engineering_Standards.md)'s Project Organization Rules).

## Integration Considerations

- This sprint has no live caller yet — `Persona.compose_reply()` does not call `recall_for_persona()` until Sprint 3.12 (Decision Engine Integration), the same deferred-wiring pattern used throughout this project (`ConversationSessionStore.purge_older_than()`, Sprint 2.7, had no caller until later; `PersonaManager`'s reserved `SwitchReason` values, Sprint 2.11, likewise).
- Sprint 3.9's Memory Retrieval Engine composes over `PersonaScopedMemory` (plus `EventMemory`, `ShortTermMemory`) rather than duplicating its scoping logic.

## Potential Risks

- **Merging two already-sorted-by-distance lists (Shared + persona-specific) with a simple re-sort is a naive rank fusion** — legitimate for now (no confidence weighting exists until Sprint 3.5), but should not be mistaken for Sprint 3.9's real combined-ranking logic, which additionally weighs confidence. Documented in this class's own docstring to prevent confusion later.
- **`category` is stored but never validated against a fixed vocabulary** — matches Part 2's own examples ("Projects", "Goals", "Skills"...) being descriptive, not prescriptive; a fixed enum would be premature generality before real usage shows what categories are actually needed.

## Acceptance Criteria

- `recall_for_persona("jarvis", ...)` never returns a `MINIE`-owned record for any query text; `recall_for_persona("minie", ...)` never returns a `JARVIS`-owned record — verified structurally, not just by a passing example.
- A `SHARED` record stored via `remember(MemoryType.SHARED, ...)` is returned by both `recall_for_persona("jarvis", ...)` and `recall_for_persona("minie", ...)` for a matching query.
- `remember()` raises `ValueError` for `owner=MemoryType.EVENT` or `owner=MemoryType.SHORT_TERM`.

## Testing Checklist

- [ ] Unit: `remember()` accepts `SHARED`/`JARVIS`/`MINIE`, rejects `EVENT`/`SHORT_TERM`.
- [ ] Unit: cross-persona leak test (structural, both directions).
- [ ] Unit: shared-memory visibility to both personas.
- [ ] Unit: `recall_shared_only()` never includes persona-specific records.

## Documentation Checklist

- [ ] `memory/persona_scoped_memory.py` docstring: explicit statement of the structural (not filter-based) scoping guarantee, and the naive-rank-fusion caveat relative to Sprint 3.9.
- [ ] `docs/STATUS.md` — Phase 3.1 (Memory Engine) row remains `Designing` (3.3/3.4 still pending).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1–1.5 days.

## Next Sprint

3.3 — Event Memory.

## Future Considerations

- If a third or fourth persona is ever introduced (outside current scope — Part 1 is explicit that JARMINEI is "one intelligence, two personas"), `recall_for_persona`'s `if/elif` would need to generalize to a lookup table. Not built speculatively now.
