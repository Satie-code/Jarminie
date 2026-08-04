# Sprint 5.21 — Pattern Recognition

## Sprint ID

5.21

## Sprint Name

Pattern Recognition

## Purpose

Give the Learning Engine its detection half — per `02_System_Architecture.md`'s Learning Engine section ("Learn: Preferred study times. Frequently used applications. Common workflows. Work habits... The Learning Engine may recommend improvements. It never makes major autonomous decisions.") and `04_Master_Implementation_Plan.md`'s Phase 5.4 ("Pattern recognition... Acceptance Criteria: User patterns learned gradually. No unpredictable behavior."). Detection only — recommending anything from a detected pattern is Sprint 5.23's own job, and adjusting Wellness behavior from one is Sprint 5.22's.

## Engineering Rationale

Corresponds to the roadmap-granularity `Pattern Recognition` entry (originally numbered `5.22`, Phase 5.4), renumbered to `5.21` per this Sprint Book's own real build order — moved ahead of Sprint 5.22 (Adaptive Wellness, originally `5.19`) specifically because that sprint's own roadmap-granularity `Depends On` column already named it (`5.18, 5.22` in the original numbering) — a real forward dependency that could not survive the "every sprint depends only on earlier-numbered sprints" discipline `docs/sprint_book/INDEX.md`'s Level 3/Level 4 breakdown notes already established. See that file's own "Level 5 Part B breakdown changes" note for the full renumbering table.

**"Gradually" and "no unpredictable behavior" (Phase 5.4's own Acceptance Criteria) are taken as real, binding design constraints, not just phrasing**: every detection method in this sprint is a small, explainable, arithmetic threshold-and-frequency computation over already-real stored data (`analytics/usage_store.py`'s `UsageStore`, Sprint 5.17) — never a trained model, embedding-similarity search, or LLM call. This mirrors `memory/confidence_scorer.py`'s own "explainable arithmetic over real signals, not machine learning" precedent exactly (Sprint 3.5), and directly satisfies the Development Guide's own "Reliability over intelligence" Mandatory Rule and the Learning Engine's own "never makes major autonomous decisions" line — there is no decision here at all, only observation. A pattern only becomes `LearnedPattern`-worthy once it has been observed `learning_config.pattern_min_occurrences` times across at least `learning_config.pattern_min_days` distinct days (both config-driven, defaulting to conservative-not-hasty values) — the literal mechanism behind "gradually."

**A real modeling decision made explicitly here**: `LearnedPattern`s are stored in a new, dedicated `PatternStore` (own SQLite table via `SqliteClient`, the same "caller owns its own DDL" precedent every prior storage class has established) rather than as a sixth `MemoryType`. `memory/models.py`'s `MemoryType` enum (`SHARED`/`JARVIS`/`MINIE`/`EVENT`/`SHORT_TERM`) has been a locked, small set since Sprint 3.1, and `memory/confidence_scorer.py`'s/`memory/persona_scoped_memory.py`'s own scoring/scoping rules are written specifically around those five — widening it for a conceptually different kind of record (a learned statistical fact, not a conversational memory) would be a cross-cutting change to Level 3's own frozen architecture with no real benefit, when a small, independent store (the same shape `analytics/usage_store.py` and `scheduler/calendar_store.py` already use) serves this sprint's own real need cleanly.

## Objectives

- `PatternType` (`PREFERRED_TIME`, `FREQUENT_APPLICATION`, `WORK_HABIT`) and `LearnedPattern`.
- `PatternStore`: persistent (SQLite) storage for `LearnedPattern`s, including upsert-by-identity (a re-detected pattern strengthens its own existing record rather than duplicating it).
- `PatternRecognizer`: a `ManagedModule` composing `UsageStore` (5.17) and `AnalyticsDashboardService` (5.20) into the three named detection methods.
- `LearningConfig` (new `config/schema.py` section).

## Dependencies

3.2 (Shared Memory & Persona Memory — `memory/persona_scoped_memory.py`'s established "query real stored history, never speculate" precedent this sprint's own detection methods follow, and the sibling `SqliteClient`-via-DI storage pattern), 5.17 (Usage & Habit Tracking — `UsageStore`, this sprint's own sole real data source), 5.20 (Analytics Dashboard Data — `AnalyticsDashboardService.habit_consistency()`, reused rather than reimplemented per Engineering Rationale below).

## Files to Create

- `learning/pattern_model.py` — `PatternType` (Enum), `LearnedPattern` (dataclass).
- `learning/pattern_store.py` — `PatternStore`.
- `learning/pattern_recognizer.py` — `PatternRecognizer`.
- `tests/unit/learning/test_pattern_model.py`
- `tests/unit/learning/test_pattern_store.py`
- `tests/unit/learning/test_pattern_recognizer.py`

## Files to Modify

- `config/schema.py` — new `LearningConfig` dataclass: `pattern_min_occurrences: int = 5` (the same category of "don't act on one data point" guard `emotion/detection_engine.py`'s own confidence-bonus-only-on-agreement discipline already established), `pattern_min_days: int = 3` (spread across distinct days — one very active single day should not alone read as a "habit"), `preferred_time_bucket_hours: int = 2` (groups usage into 2-hour buckets — e.g. 14:00–16:00 — rather than exact-hour buckets, which Part 2's own "Preferred study times" language does not demand with finer precision than this), `lookback_days: int = 30` (how far back into `UsageStore` each detection method looks — a defensive bound against an unbounded historical scan, the same category of guard `SchedulerConfig.max_lookahead_days` already established).
- `config/defaults.yaml` — matching `learning:` section.

## Expected Classes

- `PatternType` (Enum) — `PREFERRED_TIME`, `FREQUENT_APPLICATION`, `WORK_HABIT`.
- `LearnedPattern` (dataclass) — `pattern_id: str`, `pattern_type: PatternType`, `description: str` (a plain, human-readable sentence — e.g. `"Frequently active between 14:00 and 16:00"` — the Explainability Rule's own deliverable applied here, matching `decision/authority.py`'s `DecisionTrace.reasoning_text` precedent), `subject: str` (the pattern's own key — an hour-bucket label, a process name, or a habit category, depending on `pattern_type`), `confidence: float` (0.0–1.0, `evidence_count` scaled against `pattern_min_occurrences` — the same "confidence as an honest scalar, never a false certainty" discipline `EmotionEstimate.confidence`/`ConfidenceScorer`'s own scores already established), `evidence_count: int`, `first_observed_at: datetime`, `last_updated_at: datetime`.
- `PatternStore(ManagedModule)` — constructor DI: `(sqlite_client: SqliteClient)`. Owns its own table DDL (`learned_patterns`).
- `PatternRecognizer(ManagedModule)` — constructor DI: `(usage_store: UsageStore, dashboard_service: AnalyticsDashboardService, pattern_store: PatternStore, learning_config: LearningConfig)`.

## Expected Interfaces

None new.

## Expected Functions

- `PatternStore.upsert(pattern: LearnedPattern) -> None` — identity is `(pattern_type, subject)`; an existing record's `evidence_count`/`confidence`/`last_updated_at` are overwritten with the freshly computed values (the caller, `PatternRecognizer`, always recomputes the full picture from `UsageStore` rather than incrementally patching, keeping this store a pure cache of the *latest* computed state, never a append-only log).
- `PatternStore.list_by_type(pattern_type: PatternType) -> list[LearnedPattern]`
- `PatternStore.list_all() -> list[LearnedPattern]`
- `PatternRecognizer.detect_preferred_times() -> list[LearnedPattern]` — buckets `UsageStore.list_sessions_since(now - lookback_days)` by `preferred_time_bucket_hours`-wide hour-of-day windows; a bucket clearing both `pattern_min_occurrences` (session count) and `pattern_min_days` (distinct calendar days) becomes a `PREFERRED_TIME` pattern.
- `PatternRecognizer.detect_frequent_applications() -> list[LearnedPattern]` — the same two-gate discipline, grouped by `process_name` instead of time bucket.
- `PatternRecognizer.detect_work_habits() -> list[LearnedPattern]` — calls `dashboard_service.all_habit_consistency()` (5.20) rather than re-querying `UsageStore` directly, per the Dev Guide's own "extend or improve existing functionality instead of recreating it" Step 1 rule; a category whose `HabitConsistency.consistency_ratio` clears `learning_config.pattern_min_occurrences / pattern_min_days`'s own equivalent ratio becomes a `WORK_HABIT` pattern.
- `PatternRecognizer.run_detection_pass() -> list[LearnedPattern]` — calls all three `detect_*()` methods and `pattern_store.upsert()`s every result; returns what was upserted. The one method a future periodic caller (Sprint 5.24) needs.

## Data Flow

```
(future) TaskScheduler daily job  -- OR --  a direct test/manual call
      ↓
PatternRecognizer.run_detection_pass()
      ↓
detect_preferred_times() / detect_frequent_applications() / detect_work_habits()
      ↓
UsageStore.list_sessions_since()  /  AnalyticsDashboardService.all_habit_consistency()
      ↓
LearnedPattern(s)
      ↓
PatternStore.upsert()  →  persisted (SQLite, learned_patterns table)
      ↓
Sprint 5.22 (Adaptive Wellness), Sprint 5.23 (Preference Learning & Recommendations)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `LearningConfig`.
2. `learning/pattern_model.py` — `PatternType`, `LearnedPattern`.
3. `learning/pattern_store.py` — `PatternStore`, own DDL, `upsert()`/`list_by_type()`/`list_all()`.
4. `learning/pattern_recognizer.py` — `PatternRecognizer`: three `detect_*()` methods, `run_detection_pass()`.
5. Unit tests: each `detect_*()` method against fixture `UsageStore` data crossing/not-crossing both gates (occurrence count and distinct-day count independently — a fixture with enough occurrences on too few days must not produce a pattern, and vice versa); `confidence` scaling; `upsert()`'s identity-based overwrite (re-running `run_detection_pass()` against unchanged fixture data does not duplicate rows, only refreshes `last_updated_at`); `detect_work_habits()` genuinely calls `AnalyticsDashboardService` rather than `UsageStore` directly (a collaboration test, not just an output test).

## Architecture Notes

`PatternRecognizer` never writes to `PatternStore` from inside a `detect_*()` method — only `run_detection_pass()` persists, keeping the three detection methods pure, individually testable functions over their own inputs (the same "decision separated from its own side effect" discipline `wellness/wellness_tracker.py`'s `evaluate_triggers()` (5.18) already established for a different subsystem). `LearnedPattern.confidence` is capped at `1.0` regardless of how far evidence exceeds the minimum — more data past the threshold should read as "still confident," never as a runaway, unbounded score.

## Integration Considerations

- Registered as a `ManagedModule` with `CoreManager` by Sprint 5.24; `run_detection_pass()`'s own real periodic cadence (a daily `TaskScheduler` job, the same "closing the recurring-cadence gap for real" precedent `backlog/technical_debt.md` items 11/15/17 already established) is that sprint's own job too — this sprint ships `run_detection_pass()` real and callable, but nothing yet calls it outside a test.
- Sprint 5.22 (Adaptive Wellness) and Sprint 5.23 (Preference Learning & Recommendations) are this sprint's own real, immediate consumers within this Sprint Book.

## Potential Risks

- **`preferred_time_bucket_hours`/`pattern_min_occurrences`/`pattern_min_days`/`lookback_days` are all unvalidated guesses**, the same tuned-constant caveat every comparable default in this codebase already carries.
- **A genuinely irregular schedule (real, but never falling into the same bucket twice) will correctly never produce a `PREFERRED_TIME` pattern** — an honest, intended consequence of the "gradually, not from one data point" design, not a bug, but worth naming so a future reader does not read a sparse `PatternStore` as a detection failure.
- **`detect_work_habits()`'s own quality is entirely inherited from Sprint 5.20's own "Project progress"-class limitation** — if `AnalyticsConfig.habit_category_names` is left empty (the honest default), `detect_work_habits()` has nothing to detect and correctly returns an empty list, not an error.
- **No Fail Gracefully hardening for `PatternStore`'s own SQLite calls this sprint** — deliberate, matching `CalendarStore`'s/`UsageStore`'s identical precedent; Sprint 5.25's job once a real periodic caller exists.

## Acceptance Criteria

- Each `detect_*()` method correctly requires both `pattern_min_occurrences` AND `pattern_min_days` before producing a pattern, verified against fixtures that satisfy only one gate.
- `confidence` scales with evidence and is capped at `1.0`.
- `run_detection_pass()` upserts without duplicating on repeated runs against unchanged data.
- `detect_work_habits()` is verified (via a collaboration/mock assertion) to call `AnalyticsDashboardService`, not to reimplement its aggregation.
- Every `LearnedPattern.description` is a genuinely human-readable sentence, not a raw data dump.

## Testing Checklist

- [ ] Unit: `LearnedPattern`/`PatternType` construction and defaults.
- [ ] Unit: `PatternStore.upsert()` identity-based overwrite, `list_by_type()`/`list_all()`.
- [ ] Unit: `detect_preferred_times()` — both-gates-required, bucket boundaries.
- [ ] Unit: `detect_frequent_applications()` — both-gates-required.
- [ ] Unit: `detect_work_habits()` — collaboration with `AnalyticsDashboardService`, empty-config degrade.
- [ ] Unit: `run_detection_pass()` idempotency against unchanged fixture data.
- [ ] Unit: persistence survives close/reopen against a real (temp-file) SQLite database.

## Documentation Checklist

- [ ] `learning/pattern_recognizer.py` docstring: the "explainable arithmetic, never ML" constraint and the dedicated-`PatternStore`-not-a-sixth-`MemoryType` decision, both stated explicitly (per Engineering Rationale above).
- [ ] `docs/STATUS.md` — Phase 5.4 (Learning Engine) row moves to `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

High.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

5.22 — Adaptive Wellness.

## Future Considerations

- A true "common workflows" detection (Part 2 names this explicitly; this sprint's own `WORK_HABIT`/`FREQUENT_APPLICATION` patterns are a real but partial proxy — genuine sequence/workflow-mining over usage sessions is a materially larger, unbuilt capability) — flagged honestly, not attempted here.
- Decaying old evidence (today `run_detection_pass()` always recomputes from the full `lookback_days` window, so a pattern that stops being true eventually stops being re-upserted, but a stale `LearnedPattern` from before a behavior change lingers until the next pass) — acceptable at this sprint's own scope.
- "Preferred conversation style" (Part 2's own sixth named thing to learn) — deliberately not built here; Sprint 5.23's own job, using a different real data source (see that sprint's own Engineering Rationale).
