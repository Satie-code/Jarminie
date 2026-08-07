# Sprint 6.7 — Learning Engine v2

## Sprint ID

6.7

## Sprint Name

Learning Engine v2

## Purpose

Widen the existing Learning Engine (`learning/`, Sprint 5.21/5.23) to learn the four additional signal types this brief names — preferred workflows, preferred tools, daily routine, coding/study habits — while explicitly preserving the one constraint `02_System_Architecture.md`'s own Learning Engine section already states: *"The Learning Engine may recommend improvements. It never makes major autonomous decisions."* Level 6 Part A does not relax that rule; it gives the existing advisory-only Learning Engine more to be advisory about.

## Engineering Rationale

**Extends `learning/`, does not fork it.** `PatternType` (Sprint 5.21) already has four members (`PREFERRED_TIME`, `FREQUENT_APPLICATION`, `WORK_HABIT`, `CONVERSATION_STYLE`); this sprint widens it to eight, adding `PREFERRED_WORKFLOW`, `PREFERRED_TOOL`, `DAILY_ROUTINE`, `STUDY_SCHEDULE` — the same "widen a fixed enum, add corresponding detector methods" precedent Sprint 5.23 already used when it added `CONVERSATION_STYLE` as the enum's own fourth member. `PatternRecognizer`/`PatternStore`/`RecommendationEngine` (all three already existing classes) gain new detector methods and templates; no new top-level package, no new store.

**A real, deliberate constraint stated explicitly because this sprint is the one most likely to accidentally violate it**: every new detector method in this sprint returns a `LearnedPattern` (already-established shape: subject, confidence, evidence) or feeds `RecommendationEngine`'s existing templated (never LLM-generated) recommendation surface — exactly as `docs/sprint_book/INDEX.md`'s own Level 5 Part B breakdown note already required ("recommendations are templated-only, never LLM-generated, per Phase 5.4's own literal 'No unpredictable behavior' criterion"). Nothing in this sprint calls any executor, modifies any config, or changes JARMINEI's own behavior directly — every output is read by a downstream caller (Sprint 6.8's Proactive Assistant, Sprint 6.9's Multi-Step Workflow Engine) that decides, with the user, what if anything to do about it.

**"Preferred workflows" reuses the existing `workflow/workflow_store.py`'s `WorkflowStore`** (Sprint 4.9) as its evidence source — a pattern over which saved `WorkflowDefinition`s get run most often — rather than inventing a second workflow-usage log.

## Objectives

- `PatternType` widened by four members: `PREFERRED_WORKFLOW`, `PREFERRED_TOOL`, `DAILY_ROUTINE`, `STUDY_SCHEDULE`.
- `PatternRecognizer` gains `detect_preferred_workflows()`, `detect_preferred_tools()`, `detect_daily_routine()`, `detect_study_schedule()`.
- `RecommendationEngine` gains matching templates for the four new pattern types.
- `LearningConfig` gains the thresholds the four new detectors need.

## Dependencies

5.17/5.20 (`UsageStore`/`AnalyticsDashboardService`), 5.21 (`PatternRecognizer`/`PatternStore`, the class and store this sprint extends), 5.23 (`RecommendationEngine`), 4.9 (`WorkflowStore`), 6.6 (`KnowledgeGraphStore`, optional — grounds a detected pattern's "project" reference in a real `Entity` when one exists, degrades to an ungrounded pattern when it doesn't).

## Files to Create

- `tests/unit/learning/test_pattern_recognizer_v2.py` (new file for the four new detectors, keeping `test_pattern_recognizer.py`'s own existing five-detector suite untouched, matching Sprint 5.22's own established "extend the test file that matches the new scope, don't force everything into one" judgment).

## Files to Modify

- `learning/pattern_model.py` — `PatternType` widened to eight members.
- `learning/pattern_recognizer.py` — four new detector methods; `run_detection_pass()` widened to call all nine detectors (five existing + four new).
- `learning/recommendation.py` — `RecommendationEngine` gains four new templates, one per new `PatternType`.
- `config/schema.py` — `LearningConfig` gains `preferred_workflow_min_runs: int = 3` (a saved workflow run at least this many times is a "preferred" one), `preferred_tool_min_sessions: int = 5` (mirrors `PatternRecognizer.detect_frequent_applications()`'s own existing evidence-count shape, applied to a `category_map`-classified "tool" rather than a raw process name), `daily_routine_min_days: int = 5`, `study_schedule_min_sessions: int = 4` (a `UsageSession` whose `category` maps to a study/coding-adjacent label, per `AnalyticsConfig.category_map` — reused, not a new classification surface).
- `config/defaults.yaml` — matching additions to the `learning:` section.

## Expected Classes

No new classes — `PatternType`'s four new members are the only new data-model surface; every class involved (`LearnedPattern`, `PatternRecognizer`, `RecommendationEngine`, `Recommendation`) already exists.

## Expected Interfaces

None new.

## Expected Functions

- `PatternRecognizer.detect_preferred_workflows() -> list[LearnedPattern]` — reads `WorkflowStore.list_run_history()` (existing method, confirmed against the real signature at implementation time) grouped by `workflow_id`, surfaces any workflow run at least `preferred_workflow_min_runs` times.
- `PatternRecognizer.detect_preferred_tools() -> list[LearnedPattern]` — the same shape as the existing `detect_frequent_applications()` but scoped to `UsageSession`s whose `category` (via `AnalyticsConfig.category_map`) is non-`None`, distinguishing "a tool the user has deliberately categorized" from "any frequently-focused window," a real and useful distinction `detect_frequent_applications()` itself does not make.
- `PatternRecognizer.detect_daily_routine() -> list[LearnedPattern]` — composes `detect_preferred_times()`'s own existing time-bucket logic with day-of-week regularity, surfacing a pattern only when both the time-of-day *and* the day-count gate (`daily_routine_min_days`) clear — the same "two dimensionally-sound gates, not one impossible ratio" discipline `detect_work_habits()` already established at Sprint 5.21.
- `PatternRecognizer.detect_study_schedule() -> list[LearnedPattern]` — `UsageSession`s categorized as study/coding-adjacent (via `category_map`), gated by `study_schedule_min_sessions`; deliberately reuses the exact same `category_map`-driven classification surface `detect_preferred_tools()` uses above, rather than inventing a second one — a category like `"coding"` can legitimately support both a "preferred tool" pattern (the IDE itself) and a "study schedule" pattern (when it typically happens) without contradiction.
- `RecommendationEngine`'s internal template dispatch (existing, widened) gains four new entries keyed by the new `PatternType` members.

## Data Flow

```
UsageStore.list_sessions_since() / WorkflowStore.list_run_history()  (existing data, unchanged)
      ↓
PatternRecognizer.run_detection_pass()  →  now calls all nine detectors
      ↓
detect_preferred_workflows() / detect_preferred_tools() / detect_daily_routine() / detect_study_schedule()
      ↓
LearnedPattern (existing shape)  →  PatternStore.upsert()  (existing, unchanged)
      ↓
RecommendationEngine.generate_recommendations()  →  templated Recommendation (never LLM-generated)
      ↓
Sprint 6.8 (Proactive Assistant) — habit-based proactive triggers
Sprint 6.9 (Multi-Step Workflow Engine) — "you usually run this workflow around now" suggestions
```

## Implementation Tasks

1. `learning/pattern_model.py` — widen `PatternType`.
2. `config/schema.py`/`config/defaults.yaml` — the four new `LearningConfig` fields.
3. `learning/pattern_recognizer.py` — four new detectors, `run_detection_pass()` widened.
4. `learning/recommendation.py` — four new templates.
5. Unit tests (`test_pattern_recognizer_v2.py`): each new detector against a duck-typed fake `UsageStore`/`WorkflowStore` (matching Sprint 5.20's own "don't re-test an already-tested lower layer" discipline), including a below-threshold case (no pattern surfaced) and an at-threshold case (pattern surfaced) for each; `RecommendationEngine` template dispatch for all four new `PatternType`s.

## Architecture Notes

Every new detector is read-only against already-existing stores — none of the four writes anywhere except through `PatternStore.upsert()`, the exact same single write-path every existing detector already uses. This sprint adds zero new autonomous-action capability; it only adds more things `PatternRecognizer` notices and `RecommendationEngine` can phrase as a suggestion, directly preserving the Learning Engine's own "never makes major autonomous decisions" rule stated in `02_System_Architecture.md`. Any sprint that later wants Learning-derived output to actually *change* JARMINEI's own live behavior (e.g. auto-adjusting a config default) would need an explicit, separate design decision — nothing in this Book grants that implicitly.

## Integration Considerations

- `PatternRecognizer`/`RecommendationEngine` are already registered `ManagedModule`s (or already-wired plain classes) as of Sprint 5.24 — this sprint's new detector methods are picked up automatically by the existing `run_detection_pass()`/`generate_recommendations()` call sites in `voice/pipeline.py`'s `CommunicationPipeline`, with **no `main.py`/`CommunicationPipeline` change required**, unlike almost every other sprint in this Book. This is a deliberate, disclosed exception to the usual "wired at the Level's own Integration sprint" pattern, made possible specifically because this sprint extends an already-fully-wired Level 5 Part B subsystem rather than introducing a new one.
- Sprint 6.6 (Knowledge Graph) is an optional collaborator for grounding — if unavailable, the four new detectors still function, just without an `Entity` reference attached to a detected pattern's own subject.

## Potential Risks

- **`category_map`-driven detectors (`detect_preferred_tools()`, `detect_study_schedule()`) both inherit `AnalyticsConfig.category_map`'s own existing limitation**: it defaults to empty, so both detectors produce nothing on a fresh install until the user (or a future sprint) populates real categories — an honest, already-documented gap (`sprint_5_17.md`'s own Potential Risks), not new to this sprint.
- **`preferred_workflow_min_runs`/`daily_routine_min_days`/`study_schedule_min_sessions` are unvalidated guesses**, the same tuned-constant caveat every comparable threshold in this codebase carries.
- **No de-duplication between `detect_daily_routine()` and the existing `detect_preferred_times()`** — a user with one strong daily habit could produce two related-but-distinct `LearnedPattern`s. Disclosed rather than silently merged; `RecommendationEngine`'s own existing recommendation-generation already tolerates multiple related patterns without contradiction (confirmed against its real Sprint 5.23 implementation at implementation time, not assumed).

## Acceptance Criteria

- Each of the four new detectors surfaces a `LearnedPattern` only once its own configured threshold is cleared, and surfaces none below it.
- `run_detection_pass()` returns patterns from all nine detectors (five existing + four new) in one call, exactly as it already aggregates the existing five.
- `RecommendationEngine.generate_recommendations()` produces a real, non-empty, templated (never LLM-generated) `Recommendation` for at least one pattern of each of the four new types, verified by a dedicated AST-based test proving zero `decision/` imports anywhere in `learning/recommendation.py` — the same zero-LLM-import proof Sprint 5.23 already established.
- Zero changes to `voice/pipeline.py`, `main.py`, or any other integration point — this sprint is additive-only within `learning/` plus config.

## Testing Checklist

- [ ] Unit: `PatternType` widened correctly (eight members, existing four unchanged).
- [ ] Unit: `detect_preferred_workflows()` — below/at-threshold cases against a fake `WorkflowStore`.
- [ ] Unit: `detect_preferred_tools()` — below/at-threshold, category-map-driven filtering confirmed.
- [ ] Unit: `detect_daily_routine()` — both gates (time-of-day, day-count) required independently.
- [ ] Unit: `detect_study_schedule()` — below/at-threshold, shared `category_map` reuse with `detect_preferred_tools()` confirmed non-contradictory.
- [ ] Unit: `RecommendationEngine` template dispatch for all four new `PatternType`s.
- [ ] Unit: AST-based zero-`decision/`-import proof, extended to cover this sprint's own new template code.
- [ ] Unit: `LearningConfig` validation for the four new fields.

## Documentation Checklist

- [ ] `learning/pattern_recognizer.py` docstring: the four new detectors and their reused `category_map` dependency, stated explicitly.
- [ ] `docs/STATUS.md` — Level 6 Part A narrative extended; Phase note that this sprint requires zero `main.py` change, unlike its siblings.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

6.8 — Proactive Assistant.

## Future Considerations

- Learning-derived config auto-tuning (explicitly not built here, per Architecture Notes' own stated boundary) — a real future direction requiring its own deliberate design decision, not implied by this sprint.
- Cross-user/aggregate learning — no basis anywhere in this project's own single-user framing (`01_Project_Vision.md`); not applicable.
