# Sprint 6.3 — Context Engine

## Sprint ID

6.3

## Sprint Name

Context Engine

## Purpose

Give every later Level 6 Part A sprint (Reasoning, Proactive Assistant, Decision Engine v2, Adaptive Prioritization) one place to ask "what's actually going on right now?" — combining conversation, memory, current applications, projects, calendar, time, and system status into a single, read-only working-context object, per the brief's own literal list. This is a composition layer, not a new source of truth: every field in its output is read from an already-existing store built at an earlier Level.

## Engineering Rationale

**A real, deliberate naming decision, made explicitly because two existing classes already occupy adjacent name-space**: `voice/context_manager.py`'s `ContextManager`/`ConversationContext` (Sprint 2.8) already assembles *conversation-level* context (recent turns, active persona, session timing), and `decision/context_analyzer.py`'s `ContextAnalyzer` (Sprint 3.8) already classifies *per-turn* sentiment/topic/urgency. Neither is being replaced or duplicated. The new `ContextEngine` sits **above** both — it is the cross-subsystem aggregator the brief describes ("Conversation. Memory. Current apps. Projects. Calendar. Time. Location (future). System status."), and it treats `ContextManager.current_context()`'s own output as exactly one of its several inputs, not something it recomputes. This boundary is stated explicitly in the new module's own docstring, the same treatment `presentation/presentation_controller.py` got at Sprint 5.6 when it needed to avoid colliding with the pre-existing `PersonaManager`.

A new top-level `context/` package is introduced, for the same one-engine-one-folder reason `planning/` was introduced at Sprint 6.1 — recorded here as the point of decision, `backlog/technical_debt.md` entry deferred to implementation.

**Deliberately stateless and read-only**: `ContextEngine` is not a `ManagedModule` — it owns no storage and no lifecycle, matching `analytics/dashboard_data.py`'s `AnalyticsDashboardService`'s identical "compose already-persisted data on demand" shape. Every collaborator it reads from is independently already lifecycle-managed by `CoreManager`.

## Objectives

- `WorkingContext` — the unified, point-in-time snapshot dataclass.
- `ContextEngine`: composes `ConversationContext` (existing), recent `MemoryRecord`s (existing), recent `UsageSession`s (existing, Sprint 5.17/5.20), upcoming `ScheduledItem`s (existing, Sprint 4.14), `ResourceMonitor` readings (existing, Sprint 1.4), and the current wall-clock time into one `WorkingContext.build()` call.
- `ContextEngineConfig` (new `config/schema.py` section) — lookback windows for each composed source.

## Dependencies

2.8 (`ContextManager`), 3.1–3.9 (`MemoryStore`, `MemoryRetrievalEngine`), 5.17/5.20 (`UsageStore`/`AnalyticsDashboardService`), 4.14 (`CalendarStore`), 1.4 (`ResourceMonitor`). No dependency on 6.1/6.2/6.6 — `WorkingContext` has an optional, softly-typed slot for "active goals"/"known projects" that stays empty until Sprint 6.6 (Knowledge Graph) exists, rather than blocking this sprint on a later one.

## Files to Create

- `context/context_model.py` — `WorkingContext`.
- `context/context_engine.py` — `ContextEngine`.
- `tests/unit/context/test_context_model.py`
- `tests/unit/context/test_context_engine.py`

## Files to Modify

- `config/schema.py` — new `ContextEngineConfig` dataclass: `memory_lookback_count: int = 10` (how many recent `MemoryRecord`s to include, mirroring `ContextManager`'s own `recent_turn_window` shape), `usage_lookback_hours: float = 4.0` (how far back to look for "current apps"), `calendar_lookahead_hours: float = 24.0` (how far ahead counts as "upcoming").
- `config/defaults.yaml` — matching `context_engine:` section.
- `config/loader.py` — `_SECTION_SCHEMAS` entry.

## Expected Classes

- `WorkingContext` (dataclass, frozen — a snapshot, never mutated in place once built) — `built_at: datetime`, `conversation: ConversationContext` (existing type, `voice/context_manager.py`), `recent_memories: list[MemoryRecord]`, `recent_applications: list[UsageSession]`, `upcoming_scheduled_items: list[ScheduledItem]` (existing type, `scheduler/scheduler_model.py`), `resource_status: ResourceReading` (existing type, `core/resource_monitor.py`), `known_projects: list[object] = field(default_factory=list)` (placeholder slot, typed loosely on purpose — becomes `list[Entity]` once Sprint 6.6 exists; documented as a deliberate forward-compatible gap, not a vague design).
- `ContextEngine` — constructor DI: `(context_manager: ContextManager, memory_store: MemoryStore, usage_store: UsageStore, calendar_store: CalendarStore, resource_monitor: ResourceMonitor, context_engine_config: ContextEngineConfig)`. Every dependency is optional (`X | None = None`) except `context_engine_config` — a `WorkingContext` built with some collaborators absent simply leaves the corresponding field empty (`[]`, not `None`, so callers never need a null-check per field), matching the Fail Gracefully Rule applied to composition rather than a live call failure.

## Expected Interfaces

None new.

## Expected Functions

- `ContextEngine.build(session_id: str, active_persona_name: str) -> WorkingContext` — calls each present collaborator's own existing read method (`context_manager.current_context()`, `memory_store.recent(MemoryType.SHARED, ...)`, `usage_store.list_sessions_since(...)`, `calendar_store.list_due_within(...)` or equivalent upcoming-items query, `resource_monitor.sample()`), catching and logging any individual collaborator failure without aborting the whole build — a `WorkingContext` with a missing/empty field is always returned rather than the whole method raising, since a caller needing "as much context as is currently available" should never be blocked by one degraded source.

## Data Flow

```
Caller (Reasoning Engine 6.4, Proactive Assistant 6.8, Adaptive Prioritization 6.12 — all wired at 6.13)
      ↓
ContextEngine.build(session_id, active_persona_name)
      ↓
   ┌─────────────┬───────────────┬────────────────┬───────────────────┬──────────────────┐
   ↓             ↓               ↓                ↓                   ↓                  ↓
ContextManager  MemoryStore   UsageStore     CalendarStore     ResourceMonitor      (known_projects:
.current_       .recent()     .list_         .list_due_        .sample()            empty until 6.6)
context()                     sessions_      within()
                               since()
   └─────────────┴───────────────┴────────────────┴───────────────────┴──────────────────┘
      ↓
WorkingContext (frozen snapshot)
      ↓
returned to caller — never persisted, never mutated after construction
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml`/`config/loader.py` — `ContextEngineConfig`.
2. `context/context_model.py` — `WorkingContext`.
3. `context/context_engine.py` — `ContextEngine.build()`, per-collaborator try/except-and-log, optional-collaborator handling.
4. Unit tests: full build against fakes for every collaborator; each collaborator individually absent (`None`) produces an empty-but-valid field, not a raised exception; each collaborator individually raising is caught and logged, not propagated; `built_at` reflects real call time.

## Architecture Notes

`ContextEngine` never writes anything — no store, no cache, no side effect on any collaborator. Every call to `build()` is a fresh read; this sprint deliberately does not add caching (a `WorkingContext` that silently goes stale would be a worse failure mode than the small, real cost of re-querying a handful of already-fast local stores on each call — this is the same "prefer a simpler, more honest shape" reasoning `sprint_5_17.md`'s own immutable-sample design already used for a different problem). If a future profiling pass finds this genuinely too slow on the target hardware, caching is a Future Consideration, not a default assumption.

`known_projects` is the one field with no real producer until Sprint 6.6 — included now, empty, rather than added later as a breaking dataclass change, the same "declare the field early, populate it once its owning sprint exists" precedent `device_control/action_engine.py`'s own `ActionStatus.RECOVERED` member already established at Sprint 4.1 (populated for real only at Sprint 4.8).

## Integration Considerations

- No live caller yet. Sprints 6.4/6.8/6.12 are this Sprint Book's own real consumers; Sprint 6.13 (Integration) is where `ContextEngine` is constructed for real in `main.py` and wired into a live turn's own processing.
- Sprint 6.6 (Knowledge Graph) is expected to populate `known_projects` for real — this sprint's own `ContextEngine.build()` signature does not need to change for that; only the field's content does, since `KnowledgeGraphStore` will be injected as one more optional constructor collaborator at that later sprint.

## Potential Risks

- **A `WorkingContext` can be built from entirely stale reads if two collaborators are queried microseconds apart but the underlying system state changes between them** (e.g. `resource_monitor.sample()` reads a battery level that changes the instant after) — an inherent property of any point-in-time snapshot, not a bug; documented as a real limitation rather than solved (perfect consistency across independent live subsystems is out of scope).
- **`known_projects` staying an untyped placeholder (`list[object]`) until Sprint 6.6** is a real, if narrow, type-safety gap for any code written against this sprint's own `WorkingContext` before 6.6 lands — disclosed rather than worked around with a premature type that would just be guessed.
- **No access control/filtering on `recent_memories`** — `ContextEngine.build()` reads `MemoryType.SHARED` only (never persona-scoped Jarvis/Minie memories), preserving `PersonaScopedMemory`'s own existing read-scoping rule by construction rather than needing its own enforcement logic; worth restating explicitly in code, since a future careless change adding a persona-scoped read here would be a real privacy regression against Sprint 3.2's own established boundary.

## Acceptance Criteria

- `build()` returns a `WorkingContext` with every source's real, current data when every collaborator is present and healthy.
- Any single absent (`None`) collaborator produces an empty, well-typed field — never `None` itself, never a raised exception.
- Any single collaborator raising during `build()` is caught, logged, and produces an empty field for that source only — the rest of the `WorkingContext` is still fully populated.
- `recent_memories` never includes a `MemoryType.JARVIS`/`MemoryType.MINIE` record, regardless of `active_persona_name`.

## Testing Checklist

- [ ] Unit: `WorkingContext` construction, frozen/immutability check.
- [ ] Unit: `build()` — full success path against fakes for all five collaborators.
- [ ] Unit: `build()` — each collaborator individually `None`; each collaborator individually raising; both cases confirmed non-fatal to the overall call.
- [ ] Unit: `recent_memories` scoping — confirms only `MemoryType.SHARED` is ever requested, via a call-arguments assertion against the fake `MemoryStore`, not just output inspection.
- [ ] Unit: `ContextEngineConfig` validation.

## Documentation Checklist

- [ ] `context/context_engine.py` docstring: the explicit `ContextManager`/`ContextAnalyzer` boundary (composes, never replaces or duplicates), stated per Engineering Rationale above.
- [ ] `docs/STATUS.md` — Level 6 Part A narrative extended.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

6.4 — Reasoning Engine.

## Future Considerations

- Location as a context source — the brief itself names it "(future)"; no sensor/API exists anywhere in this codebase to supply it, not built speculatively.
- Caching/invalidation for `WorkingContext` if profiling later shows the per-call composition cost is real — no evidence of that yet, not solved preemptively (see Architecture Notes).
- A push/subscribe model (collaborators notifying `ContextEngine` of changes rather than being polled on each `build()`) — a real architectural alternative, but a bigger change than this sprint's own scope; not adopted without evidence the polling model is actually insufficient.

## Sprint Completion Report (2026-08-06)

Implemented as specified, authorized directly ("continue with the sprint 6.3") right after Sprint 6.2 closed in the same conversation.

Delivered `context/context_model.py` (`WorkingContext`, a frozen dataclass) and `context/context_engine.py` (`ContextEngine.build()`, composing five collaborators into one snapshot) — a new `context/` package, and `ContextEngineConfig` (`config/schema.py`/`config/defaults.yaml`/`config/loader.py`).

**Two real, disclosed corrections from this sprint file's own text, both caught by checking the real, current source of each composed collaborator before implementing:**

1. **`resource_status` is typed `ResourceSnapshot | None`, not `ResourceReading`** — the sprint file's own Expected Classes named a type, `ResourceReading`, that does not exist anywhere in `core/resource_monitor.py` or the rest of this codebase; the real class `ResourceMonitor.sample()` actually returns is `ResourceSnapshot` (built at Sprint 1.4). Confirmed by reading the real file before writing the model, not assumed from the sprint file's own guessed name.
2. **The "empty ([], not None)" degrade rule is applied only to the four collection-typed fields** (`recent_memories`, `recent_applications`, `upcoming_scheduled_items`, `known_projects`); `conversation`/`resource_status` degrade to `None` instead. The sprint file's own Expected Classes text states the empty/never-`None` rule without carving out an exception for the two singular fields, but no honest "empty" `ConversationContext`/`ResourceSnapshot` object exists without inventing fake data (a fabricated zero-battery/zero-CPU reading, or a session with a fabricated ID) — which the Human First Rule and this codebase's own "never fabricate what wasn't actually observed" discipline (e.g. `UsageSession.sample_count` as an honest confidence signal, Sprint 5.17) both rule out. A `None` for a genuinely-absent single object is the honest signal; an empty list for a genuinely-empty collection is the honest signal — they are not the same shape, and the sprint file's own single blanket rule didn't need to distinguish them until this sprint's own model actually mixed both field shapes for the first time.

**A real design question resolved directly, not left ambiguous**: which store method to call for "current apps" and "upcoming" scheduled items, since neither collaborator has a method literally named to match the sprint file's own Data Flow diagram text. `UsageStore.list_sessions_since(since)` (real signature, Sprint 5.17) is called with `since = now - usage_lookback_hours`; `CalendarStore.list_due_within(window_end)` (real signature, Sprint 4.14 — takes an absolute end timestamp, not an hours delta, and separately enforces its own `SchedulerConfig.max_lookahead_days=365` upper bound, which `calendar_lookahead_hours=24.0`'s default is nowhere close to) is called with `window_end = now + calendar_lookahead_hours`.

15 new tests: `tests/unit/context/test_context_model.py` (2 — default `known_projects`, frozen/immutability), `tests/unit/context/test_context_engine.py` (9 — full success path against fakes for all five collaborators; every collaborator absent simultaneously; a single collaborator absent while the rest populate; every collaborator raising simultaneously, confirmed non-fatal to the whole call via a real induced `RuntimeError` on three collaborators at once; a raising conversation read and a raising resource read each individually confirmed to degrade to `None`; a call-arguments assertion proving `recent_memories` only ever requests `MemoryType.SHARED`, never `JARVIS`/`MINIE`, regardless of `active_persona_name`; `memory_lookback_count` passed through from config; `built_at` bounded by real call time) plus 4 more `ContextEngineConfig` validation tests in `test_schema.py`.

Full suite verification: `tests/unit/context/` (11/11) and the widened `test_schema.py` run individually first; then the complete `tests/unit` + `tests/integration` suite (opt-in real-model marker excluded, `test_text_to_speech.py` deselected) — 1874 passing (1859 + 15 new), zero failures, zero new flakiness. `ruff check .` clean repository-wide.

`docs/STATUS.md` (Level 6 Part A narrative extended, Part A header → "3/15 implemented," Context & Knowledge phase notes → "6.3 Complete"), `docs/sprint_book/INDEX.md` (6.3 row → `Complete`), and `docs/backlog/technical_debt.md` (new item 43, `context/` top-level package addition, same treatment as items 2/40/42) all updated.

**No git commit made** — per this project's own "only commit when explicitly asked" rule; changes left in the working tree alongside Sprints 6.1/6.2's own still-uncommitted work, the user not yet asked whether to commit. **Sprint 6.4 (Reasoning Engine) is next.**
