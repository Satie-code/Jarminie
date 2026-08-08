# Sprint 6.6 — Knowledge Graph

## Sprint ID

6.6

## Sprint Name

Knowledge Graph

## Purpose

Give JARMINEI durable, queryable long-term context about the *entities* in the user's life — projects, people, goals, files, topics — and the relationships between them, per the brief's own list ("Projects. People. Goals. Relationships. Files. Topics. Dependencies. Long-term context."). This is what lets Sprint 6.3's `ContextEngine.known_projects` field stop being an empty placeholder, and what gives Sprint 6.8's Proactive Assistant a real basis for "project inactivity" detection.

## Engineering Rationale

A new top-level `knowledge/` package, for the same reason `planning/`/`context/`/`reasoning/` were each introduced — recorded here, `backlog/technical_debt.md` entry deferred to implementation.

**A real, deliberate boundary against `memory/`**: `MemoryStore`'s five `MemoryType`s (Sprint 3.1) are locked — "the existing enum's scoring/scoping rules are written specifically around its locked 5 members," per `docs/sprint_book/INDEX.md`'s own Level 5 Part B breakdown note, which already made the identical call for `LearnedPattern` (a new `PatternStore` rather than a 6th `MemoryType`). The Knowledge Graph follows that exact precedent: entities and relationships get their own store, never a 6th `MemoryType`. The two systems answer different questions — `MemoryStore` answers "what was said or observed, and how confident/permanent is it" (the Dynamic Memory Formula); `KnowledgeGraphStore` answers "what things exist, and how do they relate" (a structural map, no confidence decay, no lifecycle band). A `MemoryRecord` can *reference* an `Entity` by ID (e.g. a memory about "the JARMINEI project"), but neither system reads the other's table directly.

**Reused, not reinvented**: persistence follows the exact `SqliteClient`-via-`ManagedModule`, caller-owns-its-own-DDL pattern every prior store already established.

## Objectives

- `Entity`/`Relationship`/`EntityType` — the graph's own data model.
- `KnowledgeGraphStore(ManagedModule)`: persistent entity/relationship storage plus traversal queries (an entity's direct relationships, and — bounded — its transitive neighborhood).
- `KnowledgeGraphConfig` (new `config/schema.py` section).

## Dependencies

3.1 (`database/sqlite_client.py`'s `SqliteClient`), 6.1 (`Goal` — a `Goal` becomes an `Entity` once accepted, giving Planning a real long-term anchor point).

## Files to Create

- `knowledge/knowledge_model.py` — `EntityType`, `Entity`, `RelationshipType`, `Relationship`.
- `knowledge/knowledge_graph_store.py` — `KnowledgeGraphStore`.
- `tests/unit/knowledge/test_knowledge_model.py`
- `tests/unit/knowledge/test_knowledge_graph_store.py`

## Files to Modify

- `config/schema.py` — new `KnowledgeGraphConfig` dataclass: `max_traversal_depth: int = 3` (a defensive bound on transitive-neighborhood queries — an unbounded graph walk over user-authored data is a real, if unlikely, performance/DoS-shaped risk even locally; mirrors `PlanningConfig.max_task_dependencies`'s identical "defensive bound, not a product requirement" reasoning), `max_relationships_per_entity: int = 50`.
- `config/defaults.yaml` — matching `knowledge_graph:` section.
- `config/loader.py` — `_SECTION_SCHEMAS` entry.

## Expected Classes

- `EntityType` (Enum) — `PROJECT`, `PERSON`, `GOAL`, `FILE`, `TOPIC` (exactly the five nouns the brief names, in that order — no speculative sixth member added without textual basis).
- `Entity` (dataclass) — `entity_id: str`, `entity_type: EntityType`, `name: str`, `description: str = ""`, `created_at: datetime`, `last_referenced_at: datetime` (updated whenever any relationship or lookup touches this entity — the field Sprint 6.8's project-inactivity trigger reads).
- `RelationshipType` (Enum) — `DEPENDS_ON`, `RELATES_TO`, `OWNS`, `PART_OF`, `MENTIONED_IN` (five general-purpose relationship shapes covering the brief's own "Relationships... Dependencies" language without over-fitting to one imagined use case; a narrower or richer taxonomy has no textual basis yet).
- `Relationship` (dataclass) — `from_entity_id: str`, `to_entity_id: str`, `relationship_type: RelationshipType`, `created_at: datetime`.
- `KnowledgeGraphStore(ManagedModule)` — constructor DI: `(sqlite_client: SqliteClient, knowledge_graph_config: KnowledgeGraphConfig)`. Owns its own DDL: `entities`, `relationships` tables.

## Expected Interfaces

None new.

## Expected Functions

- `KnowledgeGraphStore.save_entity(entity: Entity) -> None` — upsert by `entity_id`, matching `learning/pattern_store.py`'s own established `INSERT ... ON CONFLICT DO UPDATE` idiom (Sprint 5.21) where an update should refresh mutable fields (`description`, `last_referenced_at`) while preserving `created_at`.
- `KnowledgeGraphStore.get_entity(entity_id: str) -> Entity | None`
- `KnowledgeGraphStore.find_entities(entity_type: EntityType | None = None, name_contains: str | None = None) -> list[Entity]` — the lookup path Sprint 6.9's "resume previous session"/Sprint 6.8's project-inactivity check both need.
- `KnowledgeGraphStore.add_relationship(relationship: Relationship) -> None` — rejects (raises `TooManyRelationshipsError`, new, `knowledge/errors.py`) once an entity's own relationship count would exceed `max_relationships_per_entity`, the same defensive-bound-enforced-at-the-write-boundary discipline Sprint 6.2's `add_dependency()` established for cycles.
- `KnowledgeGraphStore.related_entities(entity_id: str, relationship_type: RelationshipType | None = None, depth: int = 1) -> list[Entity]` — direct relationships at `depth=1`; a bounded breadth-first traversal for `depth>1`, clamped to `knowledge_graph_config.max_traversal_depth` regardless of what a caller requests.

## Data Flow

```
Sprint 6.1: an accepted Goal  →  (caller, wired at 6.13) KnowledgeGraphStore.save_entity(
    Entity(entity_type=EntityType.GOAL, name=goal.statement, ...))
Sprint 6.9/existing device_control/workflow: a referenced project folder/file  →
    save_entity(Entity(entity_type=EntityType.PROJECT/FILE, ...))
      ↓
add_relationship(...) links them (e.g. GOAL --DEPENDS_ON--> PROJECT)
      ↓
KnowledgeGraphStore persists (SQLite, entities + relationships tables)
      ↓
find_entities() / related_entities()
      ↓
Sprint 6.3 (Context Engine — populates known_projects for real)
Sprint 6.8 (Proactive Assistant — project-inactivity via last_referenced_at)
Sprint 6.9 (Multi-Step Workflow Engine — "resume previous session" lookup)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml`/`config/loader.py` — `KnowledgeGraphConfig`.
2. `knowledge/errors.py` — `TooManyRelationshipsError`.
3. `knowledge/knowledge_model.py` — `EntityType`, `Entity`, `RelationshipType`, `Relationship`.
4. `knowledge/knowledge_graph_store.py` — two-table DDL, `save_entity()`/`get_entity()`/`find_entities()`/`add_relationship()`/`related_entities()` with bounded traversal.
5. Unit tests: entity upsert (update preserves `created_at`, refreshes mutable fields); relationship-count bound enforcement; `related_entities()` at depth 1, at a depth greater than 1 (real multi-hop traversal against a hand-built small graph), and depth clamped when a caller requests more than `max_traversal_depth`; persistence round trip surviving close/reopen.

## Architecture Notes

`last_referenced_at` is deliberately a plain, directly-settable field on `Entity` rather than something `KnowledgeGraphStore` infers automatically from query activity — a caller (e.g. Sprint 6.9, when a workflow step actually opens a project) is what decides a reference genuinely happened, since a mere `find_entities()` lookup (e.g. by Sprint 6.3's `ContextEngine` on every `build()` call) is not itself evidence of real user engagement with that entity. This avoids a subtle correctness trap: if reads counted as references, `ContextEngine` polling the graph would itself keep every entity looking perpetually "active," defeating Sprint 6.8's whole purpose for this field.

`related_entities()`'s traversal is breadth-first and cycle-safe (a `Relationship` graph is not guaranteed acyclic, unlike Sprint 6.2's `TaskGraph` — `PART_OF`/`RELATES_TO` relationships between real-world entities have no reason to stay a DAG) — visited-entity tracking prevents infinite revisits regardless of `depth`.

## Integration Considerations

- No live caller yet. Sprint 6.3's `ContextEngine` (already built, at 6.3) gains a real `knowledge_graph_store` constructor collaborator only once this sprint exists — a small, additive constructor-parameter change to `ContextEngine`, not a redesign (its `known_projects` field/optional-collaborator pattern was built at 6.3 specifically anticipating this). Sprint 6.13 (Integration) is where this connection is actually made and where `KnowledgeGraphStore` is registered as a real `ManagedModule` with `CoreManager`.
- Sprint 6.7 (Learning Engine v2), 6.8 (Proactive Assistant), and 6.9 (Multi-Step Workflow Engine) are this Sprint Book's own further real consumers.

## Potential Risks

- **No automatic entity extraction from conversation** — nothing in this sprint infers "the user mentioned a new project" from raw turn text and creates an `Entity` for it; every `save_entity()` call in this Book is explicit, caller-driven. Automatic extraction is real, additional LLM-reasoning work (Sprint 6.4's `ReasoningEngine`-adjacent territory), not built here without a textual basis naming it as this sprint's job.
- **`KnowledgeGraphStore`'s own SQLite calls have no Fail Gracefully hardening this sprint** — deliberate, matching every prior storage-first-sprint precedent (`CalendarStore`, `UsageStore`, `TaskGraphStore`); Sprint 6.14's job once real callers exist.
- **No conflict resolution for two entities that plausibly represent the same real-world thing** (e.g. "the JARMINEI project" saved twice with slightly different names) — `save_entity()`'s upsert is keyed by `entity_id`, which a caller must already know to reuse; no fuzzy-matching/deduplication is built. A real, disclosed gap, not solved speculatively.

## Acceptance Criteria

- `save_entity()` on a new `entity_id` inserts; on an existing `entity_id` updates `description`/`last_referenced_at` while preserving the original `created_at`.
- `add_relationship()` succeeds up to `max_relationships_per_entity` for a given entity and raises `TooManyRelationshipsError` beyond it, without partially applying the rejected relationship.
- `related_entities(depth=1)` returns exactly an entity's direct relationships; `related_entities(depth=N>1)` performs a real multi-hop traversal, never revisiting an entity twice even in a graph containing a cycle, and never traverses deeper than `max_traversal_depth` regardless of the requested `depth`.
- Entities and relationships survive a `KnowledgeGraphStore` close/reopen cycle against the same SQLite file.

## Testing Checklist

- [ ] Unit: `Entity`/`Relationship` construction and defaults.
- [ ] Unit: `save_entity()` insert-then-update, confirming `created_at` preservation.
- [ ] Unit: `add_relationship()` bound enforcement (accepted up to the limit, rejected beyond it).
- [ ] Unit: `related_entities()` — depth 1, multi-hop depth, cycle safety, depth clamping.
- [ ] Unit: `find_entities()` filtering by type and by name substring.
- [ ] Unit: persistence round trip against a real temp-file SQLite database.

## Documentation Checklist

- [ ] `knowledge/knowledge_model.py`/`knowledge_graph_store.py` docstrings: the explicit `MemoryStore`-vs-`KnowledgeGraphStore` boundary (per Engineering Rationale above), and the deliberate no-automatic-extraction scope.
- [ ] `docs/STATUS.md` — Level 6 Part A narrative extended.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium–High.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

6.7 — Learning Engine v2.

## Future Considerations

- Automatic entity/relationship extraction from conversation and memory — named above as a real, disclosed gap; natural territory for a future Reasoning-Engine-assisted sprint, not this one.
- Entity deduplication/merge tooling — no basis in this brief's own text; not built speculatively.
- Graph visualization (a literal rendered knowledge graph in the Presentation Layer) — no sprint in this Book names a UI surface for it; a plausible, real future direction, not decided here.

## Sprint Completion Report (2026-08-09)

Implemented as specified, authorized directly ("continue with sprint 6.6") in the same session as Sprints 6.4/6.5, right after 6.5 closed.

Delivered a new `knowledge/` package: `knowledge/knowledge_model.py` (`EntityType`, `Entity`, `RelationshipType`, `Relationship`), `knowledge/knowledge_graph_store.py` (`KnowledgeGraphStore`, a real `ManagedModule` with its own two-table DDL — `entities`, `relationships`), and `knowledge/errors.py` (`TooManyRelationshipsError`); plus `KnowledgeGraphConfig` (`config/schema.py`/`config/defaults.yaml`/`config/loader.py`), continuing this Book's own established declaration order (planning → context_engine → reasoning → decision_engine_v2 → knowledge_graph → runtime).

**A real, deliberate boundary honored exactly as this sprint's own Engineering Rationale describes**: `save_entity()`'s upsert reuses `learning/pattern_store.py`'s own `INSERT ... ON CONFLICT(entity_id) DO UPDATE SET ...` idiom (Sprint 5.21) — a genuinely new (to this sprint) `entity_id` inserts every column as-is; a conflicting `save_entity()` call refreshes only `description`/`last_referenced_at`, leaving `created_at` (per this sprint's own literal Acceptance Criteria text) AND `entity_type`/`name` (a disclosed extension of that same "only the fields explicitly named as mutable get refreshed" reading — no textual basis names either as updatable via this call) untouched. Verified via three dedicated tests: description/last_referenced_at refresh, created_at preservation, and entity_type/name preservation.

**Two real, disclosed design decisions this sprint file's own text left genuinely open (not textual errors like 6.1/6.3/6.5's own corrections, but real judgment calls with no single textually-forced answer), both resolved directly and documented in the store's own docstring rather than guessed silently**:

1. **`add_relationship()`'s own `max_relationships_per_entity` bound counts a relationship against BOTH endpoints' own total graph degree** (as either `from_entity_id` or `to_entity_id`), not outgoing edges only. This sprint's own Engineering Rationale cites Sprint 6.2's `add_dependency()` as the precedent shape, but that bound is deliberately directed and incoming-only (a `Task`'s own prerequisite count) — a general `Relationship` has no equivalent single privileged direction; even a directed type like `DEPENDS_ON` should count against both endpoints, since an entity accumulating many incoming edges is exactly as real a "too connected" signal as accumulating outgoing ones. Verified via a dedicated test confirming an entity hits its own limit purely from `to_entity_id`-side relationships.
2. **`related_entities()` treats the relationship graph as undirected for traversal** — an entity's neighbors are every entity connected via a relationship row in either direction. This sprint's own Architecture Notes already requires genuine cycle-safety ("a Relationship graph is not guaranteed acyclic... has no reason to stay a DAG"), which only matters for a traversal that actually walks the graph as a graph; no textual basis prefers an outgoing-only walk, and "what's related to X" reads most naturally as "what's connected to X" regardless of storage direction. Verified via a dedicated test: a relationship stored with the query entity as `to_entity_id` still surfaces it as related.

A third, smaller correction, the same shape as Sprint 6.1's Task/Goal: `Entity`'s field declaration order places every required field (`entity_id`, `entity_type`, `name`, `created_at`, `last_referenced_at`) before the one defaulted field (`description = ""`) — not this sprint file's own literal prose order, which is not valid as a dataclass declaration.

`related_entities()` is real breadth-first search with visited-set cycle safety (verified against a hand-built 3-entity cycle, confirming no infinite loop and no duplicate result) and clamps any requested `depth` to `knowledge_graph_config.max_traversal_depth` regardless of what a caller asks for (verified: a `depth=10` request against a `max_traversal_depth=1` config returns only depth-1 neighbors). `add_relationship()` never partially applies a rejected relationship — verified directly by confirming the graph's own state after a rejected call exactly matches its state before.

32 new tests: `tests/unit/knowledge/test_knowledge_model.py` (5 — `Entity`/`Relationship` construction and defaults, both enums' exact five-member sets), `tests/unit/knowledge/test_knowledge_graph_store.py` (24 — the full save/get/find/add_relationship/related_entities/persistence/health_check surface, including every scenario named above), plus 3 more `KnowledgeGraphConfig` validation tests in `test_schema.py` (default valid, each of the two fields' own non-positive rejection).

Full suite (unit + integration, opt-in real-model marker excluded): 2060 passing (2028 + 32 new), 1 skipped, zero failures, zero new flakiness. `ruff check .` clean repo-wide.

`docs/STATUS.md` (Level 6 Part A narrative extended, Part A header → "6/15 implemented," Context & Knowledge phase → "6.3 and 6.6 Complete"), `docs/sprint_book/INDEX.md` (6.6 row → `Complete`), and `docs/backlog/technical_debt.md` (new item 45, `knowledge/` top-level package addition, same treatment as items 2/40/42/43/44) all updated.

**No git commit made** — per this project's own "only commit when explicitly asked" rule; changes left in the working tree alongside Sprints 6.4/6.5's own still-uncommitted work, the user not yet asked whether to commit. **Sprint 6.7 (Learning Engine v2) is next.**
