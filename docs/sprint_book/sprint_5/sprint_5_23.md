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
