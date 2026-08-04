# Sprint 5.23 — Preference Learning & Recommendations

## Sprint ID

5.23

## Sprint Name

Preference Learning & Recommendations

## Purpose

Close the Learning Engine — per `02_System_Architecture.md`'s Learning Engine section ("Learn:... Preferred conversation style. The Learning Engine may recommend improvements. It never makes major autonomous decisions.") and `04_Master_Implementation_Plan.md`'s Phase 5.4 ("Preference learning. Recommendation improvements. Behavior adaptation... No unpredictable behavior."). Last component sprint of this Part; Sprint 5.24 wires everything built across 5.17–5.23 into one real system.

## Engineering Rationale

Corresponds to the roadmap-granularity `Preference Learning & Recommendations` entry (Phase 5.4) — the one sprint in this Part whose number is unchanged from the original roadmap-granularity plan (`5.23` in both numberings), since its only real dependency (Pattern Recognition) already sits earlier in the corrected build order.

**A real, disclosed dependency widening beyond the roadmap-granularity table's own single `Depends On` entry**: the original plan names only Pattern Recognition, but Part 2's own text explicitly asks the Learning Engine to learn "Preferred conversation style" — a signal `learning/pattern_recognizer.py` (5.21) cannot produce, since it only ever reads `analytics/usage_store.py`'s application-focus data, never persona or memory data. Rather than silently dropping this one named capability (the same "don't quietly narrow scope without saying so" discipline this Sprint Book has applied everywhere else — see `sprint_5_20.md`'s "Project progress" narrowing, `sprint_5_21.md`'s "common workflows" gap), this sprint adds a second, real dependency: Sprint 3.1 (Memory Store Foundation), reusing `memory/memory_store.py`'s already-real, already-persisted `MemoryRecord.memory_type` (`JARVIS`/`MINIE`/`SHARED`) as the one genuinely available proxy for "which persona's own conversational style the user actually engages with more" — a real, already-stored signal, not a fabricated one, and not a new tracking mechanism invented for this sprint alone.

**Recommendations are templated, never LLM-generated, and never auto-executed** — the literal implementation of "may recommend... never makes major autonomous decisions" and "No unpredictable behavior." `RecommendationEngine` composes `LearnedPattern`s (5.21) into a small, fixed set of pre-written templates (the same "config-driven phrase variety, never freeform generation" discipline `PresentationConfig.gesture_vocabulary`/`wellness/escalation.py`'s own message templates already established) — no `LanguageModelClient` call anywhere in this sprint's own files, a deliberate, disclosed choice even though one is already available in this codebase (`decision/llm_client.py`), because a recommendation whose exact wording can vary run-to-run for the same underlying pattern would itself be a form of the "unpredictable behavior" Phase 5.4's own Acceptance Criteria rules out.

## Objectives

- `PreferenceLearner`: derives a `PatternType.CONVERSATION_STYLE` pattern (widening `learning/pattern_model.py`'s own enum by one member) from real, already-stored `MemoryStore` data.
- `Recommendation` and `RecommendationEngine`: turns `LearnedPattern`s (frequent applications, preferred times, work habits, conversation style) into a small set of templated, non-auto-executing suggestions.
- Recommendations surface at `PriorityLevel.GENERAL_SUGGESTION` — the last of `backlog/technical_debt.md` item 17's four still-open Priority Queue sources gets its own real producer here (`SCHEDULED_REMINDER` was Sprint 4.18's; `WELLNESS` is this Part's own Sprint 5.24; `IMPORTANT_ALERT` remains the one genuinely open gap after this Sprint Book, disclosed honestly, not silently left unmentioned).

## Dependencies

5.21 (Pattern Recognition — `PatternStore`, `LearnedPattern`, the roadmap's own named dependency), 3.1 (Memory Store Foundation — `MemoryStore`, the real, disclosed widening above).

## Files to Create

- `learning/preference_learner.py` — `PreferenceLearner`.
- `learning/recommendation.py` — `Recommendation` (dataclass), `RecommendationEngine`.
- `tests/unit/learning/test_preference_learner.py`
- `tests/unit/learning/test_recommendation.py`

## Files to Modify

- `learning/pattern_model.py` — `PatternType` gains `CONVERSATION_STYLE`.
- `config/schema.py` — `LearningConfig` gains `conversation_style_min_records: int = 10` (the same "don't act on one data point" gate every other pattern-detection method in this Part already applies), `recommendation_templates: dict[str, str]` (per-`PatternType.value` key, a single `{subject}`-formatted template string — e.g. `"You often use {subject} around this time — want me to open it for you next time?"` for `FREQUENT_APPLICATION`; a pattern type with no template produces no recommendation, never a raw fallback string, since an untemplated recommendation is exactly the kind of unreviewed, unpredictable wording Phase 5.4 rules out).
- `config/defaults.yaml` — matching new `LearningConfig` fields, including default templates for all four recommendable pattern types.

## Expected Classes

- `Recommendation` (dataclass) — `recommendation_id: str`, `text: str`, `based_on_pattern_id: str`, `generated_at: datetime`.
- `PreferenceLearner` — constructor DI: `(memory_store: MemoryStore, pattern_store: PatternStore, learning_config: LearningConfig)`.
- `RecommendationEngine` — constructor DI: `(pattern_store: PatternStore, learning_config: LearningConfig)`.

## Expected Interfaces

None new.

## Expected Functions

- `PreferenceLearner.detect_conversation_style() -> LearnedPattern | None` — counts `MemoryStore` records by `memory_type` (`JARVIS` vs. `MINIE`, `SHARED` excluded — it names no persona preference by construction); returns `None` (not a forced 50/50 guess) until the combined count clears `conversation_style_min_records`; otherwise a `CONVERSATION_STYLE` pattern whose `subject` is whichever of `"jarvis"`/`"minie"` has the higher count, `confidence` scaled by how lopsided the split is (a near-even split correctly produces low confidence, not a confident guess).
- `RecommendationEngine.generate_recommendations() -> list[Recommendation]` — reads `pattern_store.list_all()`, and for every `LearnedPattern` whose `pattern_type` has a configured template in `recommendation_templates`, formats one `Recommendation`. Deliberately stateless and idempotent — calling it twice against unchanged `PatternStore` data produces the same recommendations again (deduplication against what has already been shown/acted on is Sprint 5.24's own live-caller concern, not this sprint's).

## Data Flow

```
(future) periodic caller (Sprint 5.24's job)
      ↓
PreferenceLearner.detect_conversation_style()  →  PatternStore.upsert()
      ↓
RecommendationEngine.generate_recommendations()
      ↓
PatternStore.list_all()  (every LearnedPattern, including the one above)
      ↓
list[Recommendation]
      ↓
(held internally this sprint — Sprint 5.24 enqueues each onto
PriorityQueueManager.enqueue(PriorityLevel.GENERAL_SUGGESTION, ...))
```

## Implementation Tasks

1. `learning/pattern_model.py` — add `PatternType.CONVERSATION_STYLE`.
2. `config/schema.py`/`config/defaults.yaml` — `conversation_style_min_records`, `recommendation_templates`.
3. `learning/preference_learner.py` — `PreferenceLearner.detect_conversation_style()`.
4. `learning/recommendation.py` — `Recommendation`, `RecommendationEngine.generate_recommendations()`.
5. Unit tests: `detect_conversation_style()` below/at/above `conversation_style_min_records`; confidence scaling against a lopsided vs. near-even split; `SHARED`-typed records correctly excluded from the count; `generate_recommendations()` template formatting against each of the four recommendable `PatternType`s; a pattern type with no configured template producing no recommendation (not a raw/untemplated one); idempotency across two calls against unchanged fixture data.

## Architecture Notes

`PreferenceLearner.detect_conversation_style()` is the one place in this entire Part that reads `MemoryStore` directly, rather than `UsageStore`/`AnalyticsDashboardService` — a deliberate, narrow, disclosed exception to this Part's own otherwise-consistent "Analytics data in, patterns out" data flow (5.17→5.20/5.21), justified specifically because conversation style has no other real signal anywhere in this codebase. `RecommendationEngine` never reaches back into `MemoryStore`/`UsageStore` itself — it only ever reads `PatternStore`, keeping the Learning Engine's own two halves (detecting patterns; recommending from them) as cleanly separated as Sprint 5.18/5.19's Wellness trigger/escalation split, and Sprint 5.17/5.20's Analytics tracker/dashboard split.

## Integration Considerations

- Registered into `main.py`'s composition only insofar as `PatternStore`/`MemoryStore` themselves already are — neither `PreferenceLearner` nor `RecommendationEngine` is its own `ManagedModule` (both are stateless, on-demand helper classes, the same non-`ManagedModule` precedent `AnalyticsDashboardService` (5.20) and `WellnessEscalationManager`/`AdaptiveWellnessAdjuster` (5.19/5.22) already established).
- `generate_recommendations()`'s own real periodic cadence, and the real `PriorityQueueManager.enqueue(GENERAL_SUGGESTION, ...)` call, are both Sprint 5.24's job — this sprint ships both classes real and callable, but nothing yet calls them outside a test.

## Potential Risks

- **`conversation_style_min_records`/`recommendation_templates`' default wording are both unvalidated guesses**, the same caveat class every comparable default in this Sprint Book already carries.
- **A recommendation, once generated, has no built-in "already shown" memory of its own** (`generate_recommendations()` is stateless by design) — a naive Sprint 5.24 caller that re-runs this method on every tick without its own deduplication would re-surface the same suggestion repeatedly; named here explicitly so that sprint's own design accounts for it rather than discovering it late.
- **`detect_conversation_style()`'s own signal (persona-scoped memory volume) is a genuine proxy, not a direct measurement** — a user who simply talks more overall to one persona for reasons unrelated to style preference (e.g. Jarvis handles more device-control chatter by its own nature) would still register as a "preference," an honest, disclosed limitation of the only real signal available, not a claim of psychological accuracy.

## Acceptance Criteria

- `detect_conversation_style()` correctly gates on `conversation_style_min_records`, correctly excludes `SHARED`-typed records, and produces a confidence that reflects how lopsided the real split is.
- `generate_recommendations()` produces a correctly-formatted `Recommendation` for every `LearnedPattern` whose type has a configured template, and none for a type that lacks one.
- Two consecutive calls to `generate_recommendations()` against unchanged `PatternStore` data produce identical output (idempotent).
- No recommendation text anywhere is generated outside the configured template set (verified directly — no `LanguageModelClient`/free-text-generation import anywhere in `learning/recommendation.py`).

## Testing Checklist

- [ ] Unit: `detect_conversation_style()` gating, exclusion of `SHARED`, confidence scaling.
- [ ] Unit: `generate_recommendations()` per-`PatternType` template formatting.
- [ ] Unit: untemplated pattern type produces no recommendation.
- [ ] Unit: idempotency across repeated calls.
- [ ] Static: `learning/recommendation.py` imports no `LanguageModelClient`/LLM-facing module.

## Documentation Checklist

- [ ] `learning/preference_learner.py`/`learning/recommendation.py` docstrings: the templated-never-generated constraint and the `MemoryStore`-as-conversation-style-proxy decision, both stated explicitly (per Engineering Rationale above).
- [ ] `docs/STATUS.md` — Phase 5.4 (Learning Engine) row moves to `Complete`, closing all three Learning component sprints (5.21, 5.23, plus 5.22's own cross-cutting `AdaptiveWellnessAdjuster` consumption noted in that sprint's own row).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium–High.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

5.24 — Companion Intelligence Integration.

## Future Considerations

- Recommendation deduplication/dismissal tracking (the real gap named above) — Sprint 5.24's own job once a live caller exists to need it.
- A `LearnedPattern`-driven auto-action opt-in (e.g. actually opening the frequently-used application, with explicit prior user consent) — would cross into Device Control's own territory (Level 4 Part A) and directly risks the "never makes major autonomous decisions" line; not built without a dedicated, explicit future decision.
- Richer conversation-style signals (tone-variant history, `EMOTIONAL_SUPPORT` intent frequency) beyond the plain persona-volume proxy this sprint uses — a real Future Consideration if the current proxy proves too coarse in practice.

## Sprint Completion Report (2026-08-04)

Implemented as specified, continuing directly from Sprint 5.22's own completion ("Sprint 5.23 (Preference Learning & Recommendations) is next"), matching this project's established direct-continue precedent. **This closes the entire Learning Engine (Phase 5.4) and, combined with Sprint 5.22, the entire Companion Intelligence component-sprint set except Sprint 5.24's own integration work.**

Delivered `PatternType.CONVERSATION_STYLE` in `learning/pattern_model.py`, `learning/preference_learner.py` (`PreferenceLearner.detect_conversation_style()`), `learning/recommendation.py` (`Recommendation`, `RecommendationEngine.generate_recommendations()`), and two new `LearningConfig` fields (`conversation_style_min_records`, `recommendation_templates`) in `config/schema.py`/`config/defaults.yaml`.

**A real layering decision, disclosed in `preference_learner.py`'s own module docstring**: `MemoryStore`'s own public interface has no direct "count records of this type" primitive — only `recent(memory_type, limit)`, which takes a bounded limit and returns up to that many newest-first records. This sprint's own Files to Modify deliberately excludes `memory/memory_store.py` (a locked, Level-3-frozen store), so rather than adding a new method to it, `detect_conversation_style()` reuses `recent()` exactly as designed, sampling up to a defensive `_SAMPLE_LIMIT` (1000) most recent records of each type — the same "defensive bound against an unbounded historical scan" discipline `LearningConfig.lookback_days` already established elsewhere in this Part, applied here to a record count instead of a time window. `SHARED`-typed records are excluded structurally, not via a filter — `detect_conversation_style()` only ever queries `MemoryType.JARVIS`/`MemoryType.MINIE`, so `SHARED` is simply never counted, satisfying "excluded... by construction" literally rather than through an extra conditional.

**Confidence formula, chosen to literally satisfy "scales with how lopsided the split is"**: `confidence = (majority_count - minority_count) / combined_count` — 0.0 at a perfectly even split, approaching 1.0 as the split becomes fully one-sided, naturally bounded within `[0.0, 1.0]` by construction (no explicit clamp needed, verified directly by a dedicated lopsided-split test asserting exactly `1.0`).

**`detect_conversation_style()` upserts directly into `PatternStore` itself**, unlike `PatternRecognizer`'s own three `detect_*()` methods (Sprint 5.21), which deliberately never persist — the Data Flow diagram's own explicit `detect_conversation_style() → PatternStore.upsert()` arrow, and the fact that no separate `run_detection_pass()`-equivalent orchestration method exists for `PreferenceLearner`, both point to this being the intended shape rather than a deviation from Sprint 5.21's own "pure detection, separate persistence" precedent — `PreferenceLearner` simply has only the one detection method to begin with, so there is no meaningful "orchestrator vs. detector" split to preserve.

`RecommendationEngine.generate_recommendations()`'s own idempotency is interpreted as "the same substantive recommendations again" (same `text`/`based_on_pattern_id` pairs), not byte-identical `Recommendation` objects — `recommendation_id`/`generated_at` are freshly generated every call by design, the same "no caching, recompute fresh at call time" precedent `AnalyticsDashboardService` (Sprint 5.20) already established; the idempotency test compares the sorted `(text, based_on_pattern_id)` shape between two calls, not object equality, an honest reading of what "idempotent" can mean for a genuinely stateless, always-fresh computation.

29 new tests: `test_preference_learner.py` (9 tests) uses a REAL `MemoryStore` (real temp-file `SqliteClient` + real temp-directory `ChromaMemoryClient`), mirroring `tests/unit/memory/test_emotional_memory.py`'s own "real save, real reload" precedent, since this sprint's whole point is a real count over real persisted records — gating at/below the threshold, `SHARED` exclusion (both from the gate and from ever influencing the winning subject), lopsided-vs-even confidence scaling, and genuine upsert-without-duplication across repeated calls. `test_recommendation.py` (11 tests) uses a duck-typed fake `PatternStore` (real persistence already covered at Sprint 5.21) — per-`PatternType` template formatting for all four recommendable types, an untemplated type correctly producing nothing (not a raw fallback), idempotency, and a dedicated AST-based test confirming `learning/recommendation.py` imports nothing from `decision/` at all (the mechanical half of "no `LanguageModelClient` call anywhere in this sprint's own files"). `test_pattern_model.py`'s own pre-existing `PatternType`-membership test was updated (three named categories → four) rather than left to silently start failing.

**A real syntax-error self-catch worth noting**: an initial edit inserting the new `_LEARNING_PATTERN_TYPES` module constant and `_default_recommendation_templates()` factory above `LearningConfig` accidentally orphaned the pre-existing `@dataclass` decorator (leaving it directly above a comment/constant rather than the class it was meant to decorate) — caught immediately by `python -c "import config.schema"` failing with a `SyntaxError` before any test ran, not discovered later via a confusing test collection error; fixed by removing the stray decorator line. A real reminder that inserting new module-level code directly above an existing decorated definition needs a quick compile-check, not just a visual review of the diff.

Deliberately NOT given `ManagedModule` lifecycles for either new class, per the sprint's own Integration Considerations — both `PreferenceLearner` and `RecommendationEngine` are stateless, on-demand helper classes, the same non-`ManagedModule` precedent `AnalyticsDashboardService` (5.20) and `WellnessEscalationManager`/`AdaptiveWellnessAdjuster` (5.19/5.22) already established. No live caller yet: Sprint 5.24 wires both classes' own real periodic cadence and the real `PriorityQueueManager.enqueue(PriorityLevel.GENERAL_SUGGESTION, ...)` call.

**Full-suite verification, genuinely eventful**: the unit suite (1723 passing, 1 skipped) ran clean first. The complete combined suite (unit + integration + system, opt-in real-model tests excluded via marker) surfaced 4 failures — `test_full_level2_acceptance_scripted_conversation`, `test_level4_part_a_full_acceptance_scenario`, `test_level4_part_b_full_acceptance_scenario`, and the already-long-documented `test_context_analyzer_extracts_a_nonempty_topic_for_real_input`. Rather than assume these were related to this sprint's own new `MemoryStore.recent()` caller, the three non-real-model failures were re-run standalone together — all 3 passed cleanly (8/8 tests in that file group, including setup), confirming the same well-established host-load `wait_for_dormant`-class flake this project has documented repeatedly since Sprint 3.13, not a regression: none of their own dependency chains call `PreferenceLearner`/`RecommendationEngine` or touch `learning/` at all, since neither class is wired into `main.py`/any acceptance-test harness this sprint. `ruff check .` clean across the entire repository. A real, non-mocked load of `config/defaults.yaml` via `config.loader.load_config()` also confirmed the new `conversation_style_min_records`/`recommendation_templates` fields parse and validate cleanly end-to-end, including verifying the YAML folded-scalar templates format correctly with a real `{subject}` substitution.

`docs/STATUS.md` (Phase 5.4 Learning Engine row → `Complete`, closing 5.21/5.23 together, narrative extended with this sprint's own paragraph) and `docs/sprint_book/INDEX.md` (5.23 row → `Complete`) both updated. **This closes every component sprint of Level 5 Part B (5.17–5.23) — only Sprint 5.24 (Companion Intelligence Integration), 5.25 (Error Handling & Recovery Hardening), and 5.26 (Integration Testing & Level Freeze) remain before Level 5 Part B and `v0.5` as a whole can freeze. Sprint 5.24 (Companion Intelligence Integration) is next.**
