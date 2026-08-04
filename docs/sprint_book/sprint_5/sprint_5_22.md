# Sprint 5.22 — Adaptive Wellness

## Sprint ID

5.22

## Sprint Name

Adaptive Wellness

## Purpose

Close the Wellness trio — per `02_System_Architecture.md`'s Wellness Engine section: "Adaptive Wellness Rule: Learn work patterns. Adjust reminders accordingly." Bridges Sprint 5.18/5.19's own time-and-escalation-driven Wellness Engine with Sprint 5.21's Pattern Recognition, without either engine gaining a direct dependency on the other's own internals.

## Engineering Rationale

Corresponds to the roadmap-granularity `Adaptive Wellness` entry (originally numbered `5.19`, Phase 5.2), renumbered to `5.22` per this Sprint Book's own real build order — its own roadmap-granularity `Depends On` column already named `5.18, 5.22` in the *original* numbering (Wellness Escalation, and Pattern Recognition), which is exactly the forward reference that forced this Sprint Book's own renumbering in the first place (see `docs/sprint_book/INDEX.md`'s "Level 5 Part B breakdown changes" note). Both real dependencies (now `5.19` and `5.21`) are satisfied at this sprint's own new position.

**A real, disclosed integration-seam decision, not a new dependency edge between Wellness and Learning's own core packages**: rather than having `wellness/wellness_tracker.py` import anything from `learning/`, this sprint adds one small, optional adapter — `AdaptiveWellnessAdjuster` — that reads `PatternStore` (5.21) and produces plain numeric interval overrides, which `WellnessTracker.evaluate_triggers()` (5.18) accepts through a new, additive, optional parameter. `wellness/` still imports nothing from `learning/` directly (the mechanical AST-based boundary test Sprint 5.18 already wrote is extended here to also allow `wellness/adaptive_wellness.py` specifically, the one deliberate, disclosed exception, the same "narrow, disclosed exception to an otherwise-enforced boundary" precedent `presentation/gesture_engine.py`'s own renderer-import boundary already established at Sprint 5.9). This keeps Sprint 5.18/5.19's own independence claims true in spirit — `WellnessTracker` itself still has no hard dependency on Pattern Recognition; only a caller who chooses to wire the adapter in gets adaptive behavior, and one who does not gets Sprint 5.18/5.19's original, already-tested static-threshold behavior unchanged.

**Bounded adjustment, never unbounded** — Part 2's own "Adjust reminders accordingly" is implemented as a config-capped multiplier on the *existing* static threshold, never a full override with no floor or ceiling: an aggressively-learned pattern can widen a break interval by at most a configured factor, and can never turn a reminder off entirely (that remains the Hard Limit Rule's own, separate mechanism from Sprint 5.19). This is the same "adaptive within a structural safety bound" discipline `presentation/gesture_engine.py`'s own rate-limiting and `wellness/escalation.py`'s own escalation cap already established for their own respective concerns.

## Objectives

- `AdaptiveWellnessAdjuster`: reads `LearnedPattern`s (5.21) and produces bounded per-trigger interval multipliers.
- `WellnessTracker.evaluate_triggers()` (5.18/5.19) gains a further additive parameter accepting these multipliers.

## Dependencies

5.19 (Wellness Escalation & Hard Limit — the `WellnessTracker`/`WellnessEscalationManager` pairing this sprint layers on top of, unmodified in its own core behavior), 5.21 (Pattern Recognition — `PatternStore`, `LearnedPattern`, `PatternType.WORK_HABIT`/`PREFERRED_TIME`, this sprint's own sole real input).

## Files to Create

- `wellness/adaptive_wellness.py` — `AdaptiveWellnessAdjuster`.
- `tests/unit/wellness/test_adaptive_wellness.py`

## Files to Modify

- `wellness/wellness_tracker.py` — `evaluate_triggers()` gains an `interval_overrides: dict[WellnessTriggerType, float] | None = None` parameter (a per-trigger multiplier applied to that trigger's own configured interval before the threshold check — e.g. `1.2` widens a break interval by 20%; absent or `None` behaves exactly as Sprints 5.18/5.19 already specified, a strictly additive, backward-compatible change).
- `config/schema.py` — `WellnessConfig` gains `adaptive_min_multiplier: float = 0.75` and `adaptive_max_multiplier: float = 1.5` (the structural bound named above — any multiplier `AdaptiveWellnessAdjuster` computes is clamped into this range before ever reaching `evaluate_triggers()`).
- `wellness/escalation.py` — untouched; recorded here explicitly (a deliberate non-change, the same "confirmed untouched, not silently assumed" discipline `sprint_4_12.md`'s own completion report already modeled for a different file) since a reader might otherwise expect "adaptive" to also mean "adaptive hard limits," which Part 2's own text does not support.

## Expected Classes

- `AdaptiveWellnessAdjuster` — constructor DI: `(pattern_store: PatternStore, wellness_config: WellnessConfig)`.

## Expected Interfaces

None new.

## Expected Functions

- `AdaptiveWellnessAdjuster.compute_overrides() -> dict[WellnessTriggerType, float]` — reads `pattern_store.list_by_type(PatternType.WORK_HABIT)`/`list_by_type(PatternType.PREFERRED_TIME)`; a trigger type with no relevant pattern evidence gets a multiplier of exactly `1.0` (inert — the honest "nothing learned yet" default), never a guess. The one real rule this sprint ships: a `WORK_HABIT` pattern whose `subject` maps (via `AnalyticsConfig.category_map`/`habit_category_names`, reused from Sprint 5.17/5.20 rather than a new, parallel config surface) to sustained, high-consistency activity widens `BREAK`/`EYE_PROTECTION`'s own interval multiplier proportionally to `LearnedPattern.confidence` (a more confident, well-established habit is trusted slightly more), clamped to `[adaptive_min_multiplier, adaptive_max_multiplier]`.
- `AdaptiveWellnessAdjuster.explain(trigger_type: WellnessTriggerType) -> str` — a one-sentence, human-readable justification for that trigger's own current multiplier (`"No pattern evidence yet — using the default interval."` or `"Widened by 18% based on a consistent afternoon work habit."`) — the Explainability Rule's own deliverable, mirroring `decision/authority.py`'s `DecisionTrace.reasoning_text` precedent, so a future settings UI or voice query ("why did you wait longer to remind me?") has a real, honest answer available rather than an opaque number.

## Data Flow

```
(future) periodic caller, or a direct pre-tick call (Sprint 5.24's job)
      ↓
AdaptiveWellnessAdjuster.compute_overrides()
      ↓
PatternStore.list_by_type(WORK_HABIT) / list_by_type(PREFERRED_TIME)
      ↓
dict[WellnessTriggerType, float]  (clamped)
      ↓
WellnessTracker.evaluate_triggers(interval_overrides=...)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `adaptive_min_multiplier`/`adaptive_max_multiplier`.
2. `wellness/adaptive_wellness.py` — `AdaptiveWellnessAdjuster`: `compute_overrides()`, `explain()`.
3. `wellness/wellness_tracker.py` — `evaluate_triggers()`'s new optional `interval_overrides` parameter.
4. Extend the Sprint 5.18 AST-based import-boundary test to allow `wellness/adaptive_wellness.py` (and only that file) to import from `learning/`.
5. Unit tests: no pattern evidence → multiplier `1.0` for every trigger; a high-confidence `WORK_HABIT` pattern → a widened, correctly-clamped multiplier; a multiplier that would exceed `adaptive_max_multiplier` before clamping is verified actually clamped, not silently allowed through; `explain()`'s two branches (no evidence vs. real evidence); `evaluate_triggers()` with `interval_overrides=None` matches Sprint 5.19's own existing test expectations exactly (no regression).

## Architecture Notes

`AdaptiveWellnessAdjuster` never talks to `WellnessEscalationManager` and never itself decides whether a trigger fires — it only ever widens or narrows the *interval* a trigger's own threshold check compares against, strictly upstream of Sprint 5.19's own hard-limit/escalation logic, which remains entirely unaware that adaptation exists. This one-directional composition (`AdaptiveWellnessAdjuster` → `WellnessTracker`, never the reverse, and never touching `WellnessEscalationManager` at all) is what keeps Part 2's own "Adjust reminders accordingly" claim honestly scoped to *when* a reminder fires, not *whether* the Hard Limit Rule still applies once it does.

## Integration Considerations

- Registered into `main.py`'s composition only insofar as `WellnessTracker`/`PatternStore` themselves are (Sprint 5.24) — `AdaptiveWellnessAdjuster` has no `ManagedModule` lifecycle of its own, the same non-`ManagedModule`-helper-class precedent `wellness/escalation.py`'s `WellnessEscalationManager` already established at Sprint 5.19.
- `compute_overrides()` has no real periodic caller yet within this Sprint Book — Sprint 5.24 decides whether it is recomputed once per `WellnessTracker` tick (simplest, but redundant work each tick since patterns rarely change that often) or once per `PatternRecognizer.run_detection_pass()` (more efficient, deferred to that sprint's own real wiring decision).

## Potential Risks

- **`adaptive_min_multiplier`/`adaptive_max_multiplier` are unvalidated guesses**, the same tuned-constant caveat every comparable bound in this codebase already carries — genuinely no basis beyond "not zero, not unbounded."
- **A `WORK_HABIT` pattern reflecting an unhealthy habit (e.g. consistently working very late) could, taken naively, widen the very reminders meant to counter it** — this sprint deliberately widens only `BREAK`/`EYE_PROTECTION` from a *consistency* signal, never from `LATE_NIGHT`/`OVERWORK`'s own triggers, and `LATE_NIGHT`/`OVERWORK` are excluded from `compute_overrides()`'s own real rule entirely in this sprint (always `1.0` for those two) — a real, deliberate, disclosed narrowing to avoid exactly this perverse-incentive failure mode, not an oversight.
- **This sprint's own real-world testability is limited to directly constructed `PatternStore` fixtures** — no live caller yet, the same honest scoping limitation every earlier component sprint in this Book has already named for itself.

## Acceptance Criteria

- No relevant pattern evidence produces a multiplier of exactly `1.0` for every trigger type.
- A high-confidence `WORK_HABIT` pattern produces a widened `BREAK`/`EYE_PROTECTION` multiplier, correctly clamped within the configured bounds.
- `LATE_NIGHT`/`OVERWORK` are never widened by `compute_overrides()` in this sprint, verified directly.
- `explain()` returns an honest, evidence-grounded sentence for both the no-evidence and real-evidence cases.
- `evaluate_triggers()` with no `interval_overrides` behaves identically to Sprint 5.19's own already-tested behavior (no regression).

## Testing Checklist

- [ ] Unit: `compute_overrides()` — no-evidence default, high-confidence widening, clamping at both bounds.
- [ ] Unit: `LATE_NIGHT`/`OVERWORK` exclusion from adaptive widening.
- [ ] Unit: `explain()` both branches.
- [ ] Regression: `evaluate_triggers()` with `interval_overrides=None` matches Sprint 5.19's own existing tests.
- [ ] Static/AST: import-boundary test updated, confirms only `adaptive_wellness.py` bridges `wellness/`→`learning/`.

## Documentation Checklist

- [ ] `wellness/adaptive_wellness.py` docstring: the deliberate `LATE_NIGHT`/`OVERWORK` exclusion (the perverse-incentive avoidance) and the one-directional composition, both stated explicitly (per Engineering Rationale/Potential Risks above).
- [ ] `docs/STATUS.md` — Phase 5.2 (Wellness Engine) narrative updated; row moves to `Complete`, closing all three Wellness component sprints (5.18, 5.19, 5.22).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium–High.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

5.23 — Preference Learning & Recommendations.

## Future Considerations

- Extending adaptive behavior to `HYDRATION` from a genuinely relevant pattern signal (today only `BREAK`/`EYE_PROTECTION` are widened, since Sprint 5.21's own `WORK_HABIT` detection has no natural hydration-specific analogue yet) — a real gap, not built speculatively without a concrete signal behind it.
- A settings-UI surface exposing `explain()`'s own reasoning directly to the user — no settings-UI sprint exists anywhere in this Sprint Book to host it.

## Sprint Completion Report (2026-08-04)

Implemented as specified, continuing directly from Sprint 5.21's own completion ("Sprint 5.22 (Adaptive Wellness) is next"), matching this project's established direct-continue precedent.

Delivered `wellness/adaptive_wellness.py` (`AdaptiveWellnessAdjuster` — `compute_overrides()`/`explain()`), a new optional `interval_overrides` parameter on `wellness/wellness_tracker.py`'s `WellnessTracker.evaluate_triggers()`/`_is_crossed()`, and two new `WellnessConfig` fields (`adaptive_min_multiplier`/`adaptive_max_multiplier`) in `config/schema.py`/`config/defaults.yaml`.

**The PREFERRED_TIME-fetched-but-not-consumed decision, disclosed directly in `compute_overrides()`'s own docstring**: Expected Functions names both `list_by_type(WORK_HABIT)` and `list_by_type(PREFERRED_TIME)` as reads `compute_overrides()` performs, but "the one real rule this sprint ships" (the sprint file's own phrasing) only ever derives a multiplier from `WORK_HABIT` evidence — `PREFERRED_TIME` is fetched (matching the literal Expected Functions text, and giving Sprint 5.24 or a future extension the plumbing already in place) but genuinely unused by this sprint's own single rule, an honest "field/call exists, no real consumer yet" gap matching this Sprint Book's own repeated precedent for exactly this shape of disclosed incompleteness (e.g. `WellnessPrompt.escalation_level` at Sprint 5.18, given real behavior only at Sprint 5.19).

**`interval_overrides` deliberately NOT added to `WellnessTracker`'s own constructor**, unlike `escalation_manager`/`emotional_state_manager` before it — the sprint's own Integration Considerations explicitly defers the real wiring cadence decision ("recomputed once per tick... or once per `run_detection_pass()`") to Sprint 5.24, so adding a constructor-level default here would have prematurely committed to a caching/refresh strategy nothing in this sprint's own scope decides. `evaluate_triggers()`'s own new parameter is call-time-only, and `_on_tick()` is entirely untouched by this sprint.

**`explain()`'s own message names the real driving pattern's `subject`** (e.g. `"Widened by 20% based on a consistent 'coding' work habit."`), not a generic canned string — a more honestly evidence-grounded justification than the sprint file's own illustrative example text ("a consistent afternoon work habit," which would have implied consuming `PREFERRED_TIME` data this sprint deliberately does not use) required literally; the percent figure is computed from the exact same `_multiplier_from_confidence()` call `compute_overrides()` itself uses, so the two can never silently disagree.

The Sprint 5.18 AST-based import-boundary test (`tests/unit/wellness/test_wellness_tracker.py`) was extended from a single-file check into a whole-`wellness/`-package scan, mechanically confirming `adaptive_wellness.py` is the only file under `wellness/` importing from `learning/` and that no file under `wellness/` imports from `voice/`/`ui/`/`device_control/` — the same "narrow, disclosed exception to an otherwise-enforced boundary" precedent `presentation/gesture_engine.py`'s own renderer-import boundary already established (Sprint 5.9).

34 new tests: 12 for `AdaptiveWellnessAdjuster` in isolation (no-evidence default, high-confidence widening, clamping at both the configured min and max, the strongest-of-several-patterns selection, the `LATE_NIGHT`/`OVERWORK`/`HYDRATION` exclusion, both `explain()` branches), plus new `interval_overrides` coverage in `test_wellness_tracker.py` (widening suppresses an otherwise-crossed trigger, an override only affects its own named trigger, `LATE_NIGHT` is unaffected since it has no numeric threshold, `OVERWORK` is affected since it does) and a dedicated regression test confirming `evaluate_triggers()` with no `interval_overrides` reproduces Sprint 5.19's exact original behavior. `AdaptiveWellnessAdjuster` is tested against a duck-typed fake `PatternStore` — `PatternStore`'s own persistence/upsert logic is already exhaustively tested at Sprint 5.21.

Deliberately left `wellness/escalation.py` completely untouched, per the sprint's own Files to Modify's explicit "confirmed untouched, not silently assumed" note — verified via `git diff` showing zero changes to that file.

**Full-suite verification**: the unit suite (1703 passing, 1 skipped) ran clean first. The complete combined suite (unit + integration + system, opt-in real-model tests excluded via marker) ran 1770 passing + 2 skipped + exactly one failure — the identical already-documented `test_context_analyzer_extracts_a_nonempty_topic_for_real_input` real-Ollama-output nondeterminism flake, in a file this sprint never touches. Runtime returned to the usual ~5.5 minutes, confirming Sprint 5.21's own ~16-minute run was a genuine transient host/Ollama-load anomaly, not a new baseline. A real, non-mocked load of `config/defaults.yaml` via `config.loader.load_config()` also confirmed the new `adaptive_min_multiplier`/`adaptive_max_multiplier` fields parse and validate cleanly end-to-end. `ruff check .` clean across the entire repository.

`docs/STATUS.md` (Phase 5.2 Wellness Engine row → `Complete`, closing all three of 5.18/5.19/5.22, narrative extended with this sprint's own paragraph) and `docs/sprint_book/INDEX.md` (5.22 row → `Complete`) both updated. **Sprint 5.23 (Preference Learning & Recommendations) is next.**
