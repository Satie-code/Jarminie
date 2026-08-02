# Sprint 5.3 — Emotional Memory

## Sprint ID

5.3

## Sprint Name

Emotional Memory

## Purpose

Give JARMINEI real, persisted emotional context — the brief's own "Remember: previous stress, celebrations, important moments, long-term emotional context" — and, in doing so, **resolve a real, long-standing, explicitly-named placeholder**: `memory/confidence_scorer.py`'s `_NEUTRAL_EMOTIONAL_SIGNIFICANCE` constant has stood since Sprint 3.5 with a comment reading *"The single integration point for Sprint 5.2 (Emotion Inference) to replace with a real signal"*, and `config/schema.py`'s `MemoryConfig.emotional_weight` docstring says the same thing. This sprint is that integration point — Level 5 Part A's own numbering (5.1 Emotion Detection, 5.2 Emotional State) happens to land in the exact position that comment anticipated.

## Engineering Rationale

**New sprint.** Two design choices made explicitly:

1. **Extend `MemoryRecord`, don't add a sixth `MemoryType`.** Part 2's Memory Architecture names exactly five layers (Shared, Jarvis, Minie, Event, Short-Term); "emotionally significant" is an orthogonal property a record in *any* of those five layers can have (a Shared-memory project milestone can be emotionally significant; so can a Minie-memory conversation), not a sixth storage location. `MemoryRecord` (`memory/models.py`) gains one new field, `emotional_significance: float = 0.0` (0.0–1.0), the same "add one field, don't add a new type" precedent Sprint 3.1's own Post-Sprint Fix already set for `occurred_at`/`band_entered_at`. `ConfidenceScorer.score()`'s `emotional_factor` now reads `record.emotional_significance` directly instead of the fixed `_NEUTRAL_EMOTIONAL_SIGNIFICANCE` placeholder — a one-line, surgical change exactly where the standing comment said it would happen.
2. **A thin `EmotionalMemory` wrapper, mirroring `EventMemory`'s own established shape exactly** (constructor DI over `MemoryStore`, not a `ManagedModule` — owns no resource of its own, same reasoning `PersonaScopedMemory`/`EventMemory`/`ShortTermMemory` already share): `record_significant_moment()` computes `emotional_significance` from a supplied `EmotionalState` snapshot (Sprint 5.2) at write time — a real, derived number, not a caller-supplied guess — then persists through the existing `MemoryStore.store()` (Sprint 3.1), untouched.

## Objectives

- `memory/models.py`: `MemoryRecord` gains `emotional_significance: float = 0.0`.
- `memory/confidence_scorer.py`: `ConfidenceScorer.score()`'s emotional factor now reads `record.emotional_significance`; `_NEUTRAL_EMOTIONAL_SIGNIFICANCE` remains as the fallback for pre-existing records written before this sprint (a record whose `emotional_significance` was never set defaults to `0.0`, not the old neutral `0.5` — see Architecture Notes for why this is a deliberate, disclosed behavior change, not an oversight).
- `memory/emotional_memory.py`: `EmotionalMemory` — `record_significant_moment()`, `recall_recent_moments()`.
- A significance-scoring function translating an `EmotionalState` snapshot (Sprint 5.2) into a single 0.0–1.0 `emotional_significance` value.

## Dependencies

5.2 (Emotional State Manager), 3.1–3.6 (Memory Engine — `MemoryStore`, `ConfidenceScorer`, the five existing memory-type wrappers).

## Files to Create

- `memory/emotional_memory.py`
- `tests/unit/memory/test_emotional_memory.py`

## Files to Modify

- `memory/models.py` — `MemoryRecord.emotional_significance: float = 0.0`.
- `memory/confidence_scorer.py` — `score()`'s emotional factor reads `record.emotional_significance`; `_NEUTRAL_EMOTIONAL_SIGNIFICANCE` docstring updated to explain its new, narrower "legacy-record fallback only" role rather than removed outright (removing it would silently change behavior for every record written before this sprint with no documented reasoning).
- `tests/unit/memory/test_confidence_scorer.py` — new cases: a record with a real `emotional_significance` value scores accordingly; a legacy record (`emotional_significance` left at its `0.0` default, indistinguishable from "genuinely computed as zero" — see Potential Risks) still scores without error.

## Expected Classes

- **`EmotionalMemory`**: constructor DI receives `MemoryStore` (existing) only — no direct `EmotionalStateManager` dependency; callers pass an already-read `EmotionalState` snapshot, keeping this class as thin and single-purpose as `EventMemory`.

## Expected Interfaces

None new.

## Expected Functions

- `EmotionalMemory.record_significant_moment(content: str, memory_type: MemoryType, category: str, state: EmotionalState, occurred_at: datetime | None = None) -> str` — computes `emotional_significance` via `_score_significance(state)` (module-private), constructs a `MemoryRecord` with that value set, `memory_type` restricted to `SHARED`/`JARVIS`/`MINIE` (a `ValueError` for `EVENT`/`SHORT_TERM` — those two layers already have their own dedicated, narrower wrapper classes with their own invariants; this method must not become a second, competing way to write into them), persists via `MemoryStore.store()`, returns the new record's id.
- `EmotionalMemory.recall_recent_moments(memory_type: MemoryType, limit: int = 5) -> list[MemoryRecord]` — thin passthrough to `MemoryStore`'s existing query capability, filtered to records with `emotional_significance` above `MemoryConfig.emotional_moment_recall_threshold` (new field, this sprint), most-significant-first. The real, intended consumer is Sprint 5.13 (Companion Experience)'s relationship-continuity callbacks — not called from anywhere in this sprint itself.
- `_score_significance(state: EmotionalState) -> float` (module-private) — a deliberately simple, explainable formula: the maximum absolute deviation of `stress`, `mood`, and `comfort` from their own neutral midpoints, normalized to 0.0–1.0 (a state sitting exactly at neutral scores `0.0`; a state at any dimension's extreme scores `1.0`). Chosen because "significant" moments are, definitionally, ones where the state is far from baseline — a stress spike and a joy spike are both significant, an ordinary neutral exchange is not.

## Data Flow

```
Sprint 5.2's EmotionalState (a snapshot, passed in by the caller)
        |
        v
EmotionalMemory.record_significant_moment()
        |
        +--> _score_significance(state) -> emotional_significance: float
        |
        v
MemoryRecord(..., emotional_significance=...)
        |
        v
MemoryStore.store()  (existing, Sprint 3.1, unchanged)


Separately, on every ConfidenceScorer.score() call (existing call sites, unchanged):
        |
        v
record.emotional_significance  -->  emotional_factor  -->  weighted sum (unchanged formula shape)
```

## Implementation Tasks

1. `memory/models.py` — add `emotional_significance` field.
2. `memory/confidence_scorer.py` — wire the real field in; update the module docstring's own "Sprint 5.2" forward-reference to instead point at this sprint (5.3), the sprint that actually delivers it, and note the naming gap honestly (see Architecture Notes).
3. `config/schema.py`/`config/defaults.yaml` — `MemoryConfig.emotional_moment_recall_threshold: float = 0.6`; `_validate_memory()` extended with a bounds check.
4. `memory/emotional_memory.py` — `EmotionalMemory` per Expected Functions.
5. `tests/unit/memory/test_emotional_memory.py`, extended `tests/unit/memory/test_confidence_scorer.py`.

## Architecture Notes

**Naming note, disclosed rather than silently left confusing**: `_NEUTRAL_EMOTIONAL_SIGNIFICANCE`'s own comment names "Sprint 5.2 (Emotion Inference)" as the sprint that would resolve it — written before this Sprint Book's own final numbering existed. This expansion's actual Sprint 5.2 is "Emotional State Manager," and the real resolution lands in Sprint 5.3 (this sprint) instead, since a real `emotional_significance` value needs a *state* to derive from (5.2's own deliverable), not just a per-turn estimate (5.1's). This sprint's own implementation should update that comment to reference `sprint_5_2.md`/`sprint_5_3.md` correctly rather than leave a stale forward-reference — the same "keep cross-sprint references accurate, don't let them silently drift" discipline `docs/sprint_book/INDEX.md` itself already applies throughout.

**Behavior-change disclosure**: before this sprint, every record's emotional factor was the fixed `0.5` neutral placeholder; after this sprint, a record written by ordinary `MemoryStore.store()` calls that never set `emotional_significance` (i.e. every record NOT written through `EmotionalMemory.record_significant_moment()`) now defaults to `0.0`, not `0.5` — a real, mechanical behavior change to every pre-existing memory record's own confidence score (very slightly lower, since `emotional_weight` is only `0.15` of the total formula). This is judged the more honest default: `0.5` claimed false certainty ("moderate emotional significance") for content nobody ever actually assessed; `0.0` correctly states "not assessed as emotionally significant" for the overwhelming majority of ordinary records (a routine fact, a project note), while genuinely significant moments now score meaningfully higher than before, not just uniformly higher. Documented explicitly here and in the Documentation Checklist rather than left as a silent scoring drift — the same "a real, disclosed behavior change, not hidden" discipline this project applied to, e.g., Sprint 3.14's `ollama_model` default change.

## Integration Considerations

- **No live caller until Sprint 5.14** — `record_significant_moment()` needs a real trigger (a detected stress spike, a celebration) to call it from a live turn; that wiring is explicitly Sprint 5.14's job, not this sprint's, matching every prior memory-layer sprint's own "component before integration" precedent (`EventMemory` itself shipped the same way at Sprint 3.3, only wired at 3.12).
- Sprint 5.13 (Companion Experience) is `recall_recent_moments()`'s real intended consumer.

## Potential Risks

- **A `0.0`-valued `emotional_significance` is ambiguous** between "genuinely assessed as not significant" and "never assessed at all" — an acceptable ambiguity for this sprint (both cases correctly contribute nothing extra to the formula), but worth naming for whoever later builds analytics over this field (Part B's own Analytics Engine, a real future consumer) rather than assumed obviously fine.
- **`_score_significance()`'s formula is a first-pass, unvalidated heuristic**, the same honestly-acknowledged category as every other tuned constant in this codebase.
- **Restricting `record_significant_moment()` to `SHARED`/`JARVIS`/`MINIE` is a real, deliberate constraint** that could be wrong if a genuine "this deserves to be a permanent Event Memory milestone AND is emotionally significant" case arises — not solved here; `EventMemory.record_milestone()` remains the sole writer for `EVENT`-type records, and a future sprint could add its own `emotional_significance` parameter to that method specifically if a real need appears (not built speculatively now).

## Acceptance Criteria

- `ConfidenceScorer.score()` genuinely reflects `record.emotional_significance` when set, verified against a real computed score, not just "doesn't crash."
- `EmotionalMemory.record_significant_moment()` rejects `EVENT`/`SHORT_TERM` `memory_type` with a clear `ValueError`, never silently miswriting into either layer's own invariants.
- `recall_recent_moments()` correctly filters and orders by significance.
- `ruff check .` clean; full existing suite (including every pre-existing `ConfidenceScorer` test) still passes with the new default in place.

## Testing Checklist

- [ ] Unit: `_score_significance()` across a range of `EmotionalState` fixtures (neutral, one dimension at an extreme, multiple dimensions displaced).
- [ ] Unit: `record_significant_moment()` persists a real record with the computed significance set; rejects `EVENT`/`SHORT_TERM`.
- [ ] Unit: `recall_recent_moments()` filtering/ordering.
- [ ] Unit (regression): `ConfidenceScorer.score()` with `emotional_significance` set vs. left at its `0.0` default, both producing correct, different scores.
- [ ] Full regression: existing suite passes with the new default value in place (a pre-existing test asserting an exact score value from the old `0.5` placeholder would need updating — confirm none silently mask a real regression here).

## Documentation Checklist

- [ ] `memory/confidence_scorer.py`'s `_NEUTRAL_EMOTIONAL_SIGNIFICANCE` comment updated to state its new, narrower role and point at the correct resolving sprint (this one).
- [ ] `config/schema.py`'s `MemoryConfig` docstring's own "applied against a fixed neutral placeholder value until Sprint 5.2" language corrected to name Sprint 5.3.
- [ ] The `0.5 -> 0.0` default behavior change documented plainly (Architecture Notes above) in this file and cross-referenced from `backlog/technical_debt.md` if any downstream sprint's tests need updating because of it.
- [ ] `docs/STATUS.md` — Level 5 Part A row updated.

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

Medium–High.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

5.4 — Persona Behavioral Adaptation.

## Future Considerations

- A periodic, Part-B-shaped "surface Emotional Memory highlights" review (mirroring `MemoryLifecycleManager.run_monthly_review()`'s own shape) is plausible future work, not built here — this sprint is write/recall only, no lifecycle/decay logic of its own (Emotional Memory records still go through the ordinary `MemoryLifecycleManager` cleanup/review passes unchanged, via their own `confidence_score`, same as every other record).
- If `EventMemory.record_milestone()` ever needs an `emotional_significance` parameter of its own, add it there directly rather than routing Event-type writes through `EmotionalMemory` (Potential Risks above).

## Sprint Completion Report (2026-08-02)

Implemented as specified, authorized directly ("continue with sprint 5.3") right after Sprint 5.2 closed in the same session.

### Summary

`memory/models.py`'s `MemoryRecord` gained `emotional_significance: float = 0.0`; `memory/confidence_scorer.py`'s `score()` now reads it directly. `memory/emotional_memory.py`'s `EmotionalMemory` delivers `record_significant_moment()` (rejecting `EVENT`/`SHORT_TERM` with a clear `ValueError`) and `recall_recent_moments()` (threshold-filtered, most-significant-first, via `MemoryConfig.emotional_moment_recall_threshold`). `_score_significance()` implements the spec's own formula exactly: the maximum absolute deviation of `stress`/`mood`/`comfort` from their neutral midpoints, normalized to 0.0–1.0.

**A real, necessary gap beyond the sprint's own stated Files to Modify was found and fixed**: `memory/memory_store.py`'s SQLite schema (`_CREATE_TABLE_SQL`, `_SELECT_COLUMNS`, `store()`'s INSERT, `_row_to_record()`) had no `emotional_significance` column at all — without adding it, the new `MemoryRecord` field would exist only in Python and never actually persist, defeating this sprint's whole purpose. Beyond the schema addition itself, a real migration concern was investigated and confirmed, not assumed away: this repository's own standing `database/jarminie.db` already has a real, on-disk `memory_records` table (confirmed directly via `PRAGMA table_info`), and `CREATE TABLE IF NOT EXISTS` is a no-op against an already-existing table — so a pre-existing database would never gain the new column, and every subsequent `store()` call would fail with "table memory_records has no column named emotional_significance." `MemoryStore.start()` now runs an idempotent `ALTER TABLE ... ADD COLUMN` migration, swallowing only the specific "duplicate column" failure that means it already ran; verified with a dedicated test that builds a real pre-5.3-shaped table, inserts a real pre-existing row, then confirms `start()` migrates it cleanly with no data loss and the row correctly reads back `emotional_significance=0.0`.

Two spec ambiguities were resolved explicitly, not guessed silently:

1. **The "legacy-record fallback" framing for `_NEUTRAL_EMOTIONAL_SIGNIFICANCE`** (Files to Modify: "remains as the fallback for pre-existing records") doesn't hold once `MemoryRecord.emotional_significance` is a required field with a real default (0.0) matching the SQL column's own `DEFAULT 0.0` — every record, old or new, always carries a real value, so there is no missing-value case left to fall back for. Resolved in favor of the simpler, more honest design: the constant is kept (not deleted, per the spec's own instruction) but its docstring is corrected to state plainly that it is retired and no longer read by any code, rather than describing a fallback role that doesn't actually exist in this implementation.
2. **`EmotionalMemory`'s own constructor signature** — Expected Classes says "receives `MemoryStore` (existing) only," but `recall_recent_moments()` needs `MemoryConfig.emotional_moment_recall_threshold` (itself a new field this same sprint's own Implementation Tasks adds) from somewhere. Resolved as `__init__(self, memory_store: MemoryStore, memory_config: MemoryConfig)` — reading the spec's "only" as emphasizing "not `EmotionalStateManager`" (explicitly ruled out elsewhere in Expected Classes) rather than literally excluding a config dependency the method can't function without.

`recall_recent_moments()` was implemented via `MemoryStore.recent()` plus client-side filter/sort (never a new `MemoryStore` query method) — the identical technique `EventMemory.list_milestones()` already established for its own category filter, keeping `MemoryStore`'s own public API surface untouched.

### Files Created

- `memory/emotional_memory.py`
- `tests/unit/memory/test_emotional_memory.py`

### Files Modified

- `memory/models.py` — `MemoryRecord.emotional_significance` field + docstring.
- `memory/confidence_scorer.py` — `score()` reads the real field; module docstring and `_NEUTRAL_EMOTIONAL_SIGNIFICANCE`'s own comment corrected (see Summary above).
- `memory/memory_store.py` — schema/INSERT/`_row_to_record()` updated for the new column; `start()` gained the idempotent migration step. **Not named in the sprint file's own Files to Modify** — a real, necessary addition (Summary above).
- `config/schema.py` — `MemoryConfig.emotional_moment_recall_threshold` field + validation; `MemoryConfig`'s own docstring and the stale "Sprint 5.2" forward-reference corrected.
- `config/defaults.yaml` — matching `emotional_moment_recall_threshold` addition; stale comment near `emotional_weight` corrected.
- `tests/unit/memory/test_memory_store.py` — new `emotional_significance` round-trip/default tests, and the pre-existing-table migration test.
- `tests/unit/memory/test_confidence_scorer.py` — new emotional-significance-driven scoring tests, `emotional_moment_recall_threshold` validation test, **and a fix to one real pre-existing test** (`test_unknown_category_falls_back_to_default_weight`) that hardcoded the old `0.5` placeholder's exact contribution — exactly the regression the spec's own Testing Checklist warned to check for, found by actually running the suite rather than assumed clean.
- `tests/unit/memory/test_lifecycle_manager.py` — a stale docstring (not a test assertion — the test itself only checks the confidence *band*, which still holds) correcting a now-inaccurate exact-score claim in `make_temporary_scoring_record()`'s own comment, found via a repo-wide search for other `0.5`-placeholder assumptions beyond the one file the spec named.

### Tests Added

- `tests/unit/memory/test_emotional_memory.py` — 16 tests: `_score_significance()` (neutral scores zero; each of the three dimensions' own extreme scores ~1.0; multiple displaced dimensions use the maximum; bounds always respected); `record_significant_moment()` (persists with correct computed significance, `occurred_at` honored, rejects `EVENT`/`SHORT_TERM` for both values, accepts all three allowed types); `recall_recent_moments()` (filters below threshold, surfaces at/above it, orders most-significant-first, respects `limit`, scoped to the requested `memory_type` only, empty store returns empty list).
- `tests/unit/memory/test_memory_store.py` — 3 new tests: `emotional_significance` round-trips when set, defaults to `0.0`, and the pre-existing-table migration test.
- `tests/unit/memory/test_confidence_scorer.py` — 4 new tests: higher significance produces a higher score, the contribution exactly matches the configured weight, a default (never-set) record scores cleanly, `emotional_moment_recall_threshold` validation.

### Documentation Updated

- `memory/emotional_memory.py`'s module/class docstrings.
- `memory/confidence_scorer.py`'s module docstring and `_NEUTRAL_EMOTIONAL_SIGNIFICANCE`'s own comment (per Summary above).
- `memory/models.py`'s `MemoryRecord` docstring.
- `config/schema.py`'s `MemoryConfig` docstring.
- This Sprint Completion Report.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` updated (see below).

### Acceptance Criteria Checklist

- ✔ `ConfidenceScorer.score()` genuinely reflects `record.emotional_significance` when set — verified against a real computed score matching the configured weight exactly, not just "doesn't crash."
- ✔ `EmotionalMemory.record_significant_moment()` rejects `EVENT`/`SHORT_TERM` `memory_type` with a clear `ValueError`.
- ✔ `recall_recent_moments()` correctly filters and orders by significance.
- ✔ `ruff check .` clean; full existing suite passes with the new default in place — including the one pre-existing test that needed updating, found and fixed, not silently left broken or masked.

### Risks

- `_score_significance()`'s formula and `emotional_moment_recall_threshold`'s default are real, disclosed, unvalidated first-pass choices (Potential Risks, unchanged from the spec).
- The `0.0`-ambiguity Potential Risk (genuinely-assessed-as-zero vs. never-assessed) is unchanged from the spec — flagged for Part B's future Analytics Engine, not resolved here.
- No live caller yet — `record_significant_moment()`'s real trigger (a detected stress spike, a celebration) is Sprint 5.14's job.

### Technical Debt

None introduced. The `memory_store.py` schema/migration gap was found and fixed within this sprint, not deferred.

### Recommendations

- Same as Sprints 5.1/5.2: once Sprint 5.14 wires a live caller, capture real `EmotionalMemory` writes from actual conversation sessions and sanity-check `_score_significance()`'s output feels right before tuning further.
- Worth a brief, separate conversation about whether this project wants a real, general schema-migration mechanism (versioned migrations, not a one-off `ALTER TABLE` per new column) now that a second real column addition (after `occurred_at`/`band_entered_at`) has needed this same ad hoc treatment — not built here, named as a real, recurring pattern worth a deliberate decision.

### Verification

Full suite: 1202 passing + 2 correctly-skipped opt-in markers + 1 failure (`test_context_analyzer_extracts_a_nonempty_topic_for_real_input`), the same already-established real-Ollama-output nondeterminism this session confirmed at Sprint 5.2 (unrelated to `memory/`/`config/` — `decision/context_analyzer.py` is untouched by this sprint). `ruff check .` clean across the whole repository. A real, non-mocked config-load smoke test confirmed `ConfigLoader().load()` genuinely picks up the new `emotional_moment_recall_threshold` field end-to-end.

**No git commit made** — per this project's own "only commit when explicitly asked" rule, changes left in the working tree; the user has not yet been asked whether to commit.

**Sprint 5.4 (Persona Behavioral Adaptation) is next.**
