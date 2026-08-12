# Sprint 6.11 — Explainability Layer

## Sprint ID

6.11

## Sprint Name

Explainability Layer

## Purpose

Make good on the brief's own literal requirement — "Every decision should be explainable. User can ask: 'Why did you recommend this?' JARMINEI should answer." — by widening, not replacing, the Explainability mechanism this codebase has carried since Level 3. `02_System_Architecture.md`'s own "Explainability Rule" section already states this exact requirement in general terms; `decision/authority.py`'s `DecisionTrace`/`AuthorityEvaluator.explain()` (Sprint 3.11) already deliver it for ordinary turns. This sprint extends that same guarantee to cover everything Level 6 Part A has added: a Planning Engine decomposition, a Reasoning Engine conclusion, a Decision Engine v2 ranking, a Proactive Assistant prompt, and a Self Evaluation outcome.

## Engineering Rationale

Extends `reasoning/` (does not introduce a new top-level package) — explaining *is* a reasoning act, and `ReasoningEngine.explain_why()` (Sprint 6.4) is already this Book's own general-purpose "why" primitive; `ExplainabilityLayer` is the aggregator that knows *which* trace object to hand it, not a competing reasoning mechanism.

**A real, deliberate design call, made explicit because it is the crux of the whole sprint**: `ExplainabilityLayer` never *replaces* `DecisionTrace.reasoning_text` (Level 3's own existing, human-readable justification) — it *composes* it with whatever additional trace objects Level 6 Part A produced for the same turn or item (a `ReasoningTrace` from Sprint 6.4, a `RankedAction` from Sprint 6.5, a `Goal`/`Task` from Sprint 6.1/6.2, an `EvaluationRecord` from Sprint 6.10), when any of those exist, and falls back to `DecisionTrace.reasoning_text` alone when none do. A plain Level-3-only turn (no planning, no ranking involved) is still fully explainable exactly as it always has been — this sprint adds coverage, it never narrows or changes existing behavior.

**Reused, not reinvented**: no new persistence. `ExplainabilityLayer` reads `DecisionTrace`s, `ReasoningTrace`s, and `EvaluationRecord`s from wherever they already live (or, for `DecisionTrace`, from the caller directly — Level 3 does not currently persist every `DecisionTrace`, confirmed against the real `voice/pipeline.py` implementation at implementation time before assuming otherwise); it does not add a new store of its own.

## Objectives

- `ExplanationRequest`/`Explanation` — the unified query/answer shape for "why did you do/recommend/decide X?"
- `ExplainabilityLayer`: resolves a user's "why?" question against whatever trace objects are available for the subject being asked about, composing them into one coherent, honest answer.
- `ReasoningConfig` gains the field this sprint needs.

## Dependencies

3.11 (`DecisionTrace`, `AuthorityEvaluator.explain()`), 6.4 (`ReasoningEngine`, `ReasoningTrace`), 6.1/6.2 (`Goal`/`Task`), 6.5 (`RankedAction`), 6.10 (`EvaluationRecord`).

## Files to Create

- `reasoning/explainability.py` — `ExplanationRequest`, `Explanation`, `ExplainabilityLayer`.
- `tests/unit/reasoning/test_explainability.py`

## Files to Modify

- `config/schema.py` — `ReasoningConfig` gains `max_explanation_sentences: int = 4` (a defensive bound on how long a composed explanation is allowed to run — an explanation stitched from several trace objects could otherwise grow unboundedly verbose; mirrors `ReasoningConfig.max_alternatives`'s own established bounding shape).
- `config/defaults.yaml` — matching addition to the `reasoning:` section.
- `decision/authority.py` — docstring correction only (no behavior change): `EngineSelection`'s own comment ("Every engine Part 2's full architecture names") is amended to note that Level 6 Part A adds engines beyond Part 2's original architecture — the inaccuracy Sprint 6.5 already flagged as needing correction, actually fixed here since this is the sprint that most directly depends on that enum's own honesty about its own scope.

## Expected Classes

- `ExplanationRequest` (dataclass) — `subject_id: str` (a `Task.task_id`, `Goal.goal_id`, `RankedAction`'s own `action_request`-derived identifier, or a `DecisionTrace`'s own turn identifier — whatever the user is asking "why?" about), `subject_kind: Literal["task", "goal", "ranked_action", "decision_trace", "evaluation"]`.
- `Explanation` (dataclass) — `subject_id: str`, `narrative: str` (the composed, human-readable answer — bounded by `max_explanation_sentences`), `sources: list[str]` (a short label per trace object actually used, e.g. `["DecisionTrace", "ReasoningTrace"]` — so the answer's own provenance is itself inspectable, not a black box), `confidence: float | None` (carried through from a `ReasoningTrace.confidence` when one contributed, `None` when the explanation is built purely from a `DecisionTrace`, which carries no numeric confidence of its own).
- `ExplainabilityLayer` — constructor DI: `(reasoning_engine: ReasoningEngine, task_graph_store: TaskGraphStore | None, decision_trace_lookup: Callable[[str], DecisionTrace | None] | None)`. `decision_trace_lookup` is a plain callable, not a store class — Level 3 does not persist `DecisionTrace`s in a queryable store of its own (confirmed against `voice/pipeline.py` before assuming so), so the live caller (Sprint 6.13) supplies whatever short-lived, in-memory lookup it already has (e.g. "the most recent turn's own trace"), the same "plain callable fixed at construction time" DI shape `WakeWordDetector.on_detected` already established at Sprint 2.2.

## Expected Interfaces

None new.

## Expected Functions

- `ExplainabilityLayer.explain(request: ExplanationRequest, working_context: WorkingContext | None = None) -> Explanation` — gathers whatever trace objects are actually available for `request.subject_id` given `request.subject_kind` (a `Task`/`Goal` via `task_graph_store.get_goal()`, a `DecisionTrace` via `decision_trace_lookup()`), then either (a) if at least one trace object was found, composes a narrative directly from their own existing text fields (`DecisionTrace.reasoning_text`, an `EvaluationRecord.summary`, etc.) without a fresh LLM call when that alone is sufficient, or (b) calls `reasoning_engine.explain_why()` for a subject with no existing trace text at all (e.g. a raw `Task.title` with no `ReasoningTrace` ever produced for it), so "why?" always gets a real answer, never a bare "no information available." Truncates the final `narrative` to `reasoning_config.max_explanation_sentences`.
- `ExplainabilityLayer._compose(sources: list[tuple[str, str]]) -> str` — the shared text-stitching helper (label, text) → one coherent paragraph, isolated for direct testing independent of any live trace lookup.

## Data Flow

```
User: "Why did you recommend this?" / "Why did that fail?"  (a live turn, wired at 6.13)
      ↓
ExplanationRequest(subject_id, subject_kind)   — resolved from conversation context (which
subject the user means), Sprint 6.13's own job, not this sprint's
      ↓
ExplainabilityLayer.explain(request, working_context)
      ↓
   gather available trace objects for subject_id:
   ┌──────────────────┬──────────────────┬───────────────────┬──────────────────┐
   ↓                  ↓                  ↓                   ↓                  ↓
DecisionTrace     Goal/Task          RankedAction        EvaluationRecord   (none found)
(decision_trace_  (task_graph_store)  (caller-supplied,   (task_graph_store)      ↓
 lookup)                              if this turn                          ReasoningEngine
                                       involved one)                        .explain_why()
   └──────────────────┴──────────────────┴───────────────────┴──────────────────┘
      ↓
_compose(sources)  →  Explanation (narrative, sources, confidence)
      ↓
returned to caller — spoken/displayed by whatever persona is active, same as any other reply
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `ReasoningConfig.max_explanation_sentences`.
2. `decision/authority.py` — `EngineSelection` docstring correction.
3. `reasoning/explainability.py` — `ExplanationRequest`, `Explanation`, `ExplainabilityLayer._compose()`, `explain()`.
4. Unit tests: `explain()` with only a `DecisionTrace` available (no fresh LLM call — verified via a call-count assertion against the fake `ReasoningEngine`, not just output inspection, mirroring Sprint 5.21's own established collaboration-test discipline); `explain()` with a `Goal`/`Task` and an `EvaluationRecord` both available (composed together); `explain()` with nothing available (falls through to `reasoning_engine.explain_why()`); `narrative` truncation at `max_explanation_sentences`; `_compose()` in isolation against a fixed set of `(label, text)` inputs.

## Architecture Notes

`ExplainabilityLayer` deliberately prefers **not** calling the LLM when existing trace text already answers the question — `DecisionTrace.reasoning_text` was already generated once, cheaply, as part of the original decision; re-explaining it via a fresh `ReasoningEngine` call would be redundant latency and a second, unnecessary chance for the model to say something inconsistent with what actually happened. This mirrors `internet/summarizer.py`'s own "don't call the model twice for one answer" discipline, applied here to explanation-composition instead of summarization.

`sources` existing as a first-class field on `Explanation` is itself an application of the Explainability Rule to the Explainability Layer's own output — a user (or a future debugging session) can always tell whether an answer was assembled from real, already-recorded decisions or freshly reasoned from scratch, never left to guess.

## Integration Considerations

- No live caller yet. Sprint 6.13 (Integration) is where a genuine "why?" follow-up question gets routed here for the first time, via the new `EngineSelection.EXPLANATION` member that sprint introduces — resolving *which* prior subject the user means ("that," "your last suggestion") is Sprint 6.13's own conversational-context job, using `voice/context_manager.py`'s existing recent-turn window, not something this sprint's own `ExplanationRequest` construction handles.
- `decision_trace_lookup`'s real implementation (however `CommunicationPipeline` tracks "the most recent turn's own `DecisionTrace`") is Sprint 6.13's own decision — this sprint only defines the callable's shape.

## Potential Risks

- **`decision_trace_lookup` returning `None` for a subject the user clearly remembers JARMINEI having just decided** is a real, if narrow, gap if Sprint 6.13's own lookup implementation has a short memory window — disclosed here as a dependency this sprint cannot itself guarantee, since the lookup's real backing store is out of this sprint's own scope.
- **`max_explanation_sentences=4` is an unvalidated guess**, matching every comparable default in this codebase.
- **A composed explanation drawing from multiple trace objects could, in principle, stitch together text that reads as more confident/coherent than any single source actually was** — mitigated by `sources` always being present so provenance stays inspectable, but not eliminated; disclosed rather than solved with a more elaborate confidence-reconciliation scheme this brief gives no basis for.

## Acceptance Criteria

- `explain()` given only a `DecisionTrace` produces a real `Explanation` without calling `reasoning_engine.explain_why()` — verified via a zero-call assertion on the fake.
- `explain()` given multiple available trace objects composes all of them into `sources` and a single coherent `narrative`.
- `explain()` given no available trace objects for the subject falls through to `reasoning_engine.explain_why()` and still produces a real, non-empty `Explanation`.
- `narrative` never exceeds `reasoning_config.max_explanation_sentences`.
- `EngineSelection`'s own docstring no longer claims completeness against "Part 2's full architecture" without qualification.

## Testing Checklist

- [ ] Unit: `ExplanationRequest`/`Explanation` construction.
- [ ] Unit: `explain()` — `DecisionTrace`-only (zero-LLM-call proof), multi-source composition, nothing-available fallback.
- [ ] Unit: `narrative` truncation.
- [ ] Unit: `_compose()` in isolation.
- [ ] Unit: `ReasoningConfig` validation for the new field.

## Documentation Checklist

- [ ] `reasoning/explainability.py` docstring: the "compose existing trace text before calling the LLM again" discipline, and the explicit relationship to `DecisionTrace`/`AuthorityEvaluator.explain()` (Sprint 3.11), both stated per Engineering Rationale above.
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

6.12 — Adaptive Prioritization.

## Future Considerations

- Persisting every `DecisionTrace` (not just the most recent, in-memory one) so `decision_trace_lookup` can answer "why?" about an arbitrarily old turn — a real, disclosed limitation of this sprint's own scope; would be a Level-3-touching change outside this Book's own Files to Modify unless a future sprint explicitly re-opens that boundary.
- A structured (not just narrative-text) explanation format for a future Presentation Layer surface — no basis named in this brief; not built speculatively.

## Sprint Completion Report (2026-08-09)

Implemented as specified, authorized directly ("continue with 6.11") in the same session as Sprints 6.1–6.10, right after 6.10 closed.

Delivered `reasoning/explainability.py` (`ExplanationRequest`, `Explanation`, `ExplainabilityLayer`), extending `reasoning/` (not a new top-level package) — the sixth sprint in a row to extend an existing package rather than fork one. New `ReasoningConfig.max_explanation_sentences`. `decision/authority.py`'s `EngineSelection` docstring corrected per this sprint's own Files to Modify (no behavior change).

**Three real, disclosed gaps, all found by checking what this sprint's own dependencies actually expose before implementing, matching this whole Sprint Book's own now fully-established discipline**:

1. **This sprint file's own literal constructor signature has nowhere to read `max_explanation_sentences` from.** Expected Classes lists `ExplainabilityLayer`'s constructor as `(reasoning_engine, task_graph_store, decision_trace_lookup)` — no `reasoning_config`. `ReasoningEngine` exposes no public accessor for its own private `_reasoning_config`, so nothing in that literal signature could ever read the bound this sprint's own Acceptance Criteria requires `explain()` to enforce. Resolved by adding a fourth, disclosed parameter, `reasoning_config: ReasoningConfig | None = None` (defaulting to `ReasoningConfig()`), the identical necessary-addition-beyond-the-literal-signature shape `planning/task_graph.py`'s own `TaskGraph.__init__()` already established for `planning_config` at Sprint 6.2.
2. **`TaskGraphStore` has no "get one Task by task_id" method**, and this sprint's own Files to Modify does not list `task_graph_store.py` — no new store method was authorized. A `subject_kind="task"` request is resolved by scanning every `Goal` returned by the already-existing `list_goals()` for a matching `task_id` (`ExplainabilityLayer._find_task()`), an O(goals × tasks) scan using only pre-existing public methods.
3. **`subject_kind="ranked_action"` is a real `Literal` member this sprint's own Expected Classes names, but nothing in this codebase can ever resolve one.** `DecisionEngineV2.rank_actions()` (6.5) never persists a `RankedAction` — there is no store, and this sprint's own constructor defines no `ranked_action_lookup` callable the way it does `decision_trace_lookup` for `DecisionTrace`. Every `"ranked_action"` request gathers zero sources and falls through to the LLM fallback — the fourth instance of this Book's own "accepted but not yet consumable" pattern (6.5's `authority_evaluator`, 6.8's `decision_engine_v2`/`pattern_recognizer`, 6.10's `evaluation_timeout_seconds`), disclosed rather than silently invented. A related, smaller inherited limitation flows from the same root cause: `TaskGraphStore.list_evaluations_for_goal()` (6.10) can never return a `WorkflowRunResult` evaluation (that sprint's own disclosed scope limit) — a `subject_kind="evaluation"` request for one falls through the identical way, confirmed via `_gather_evaluation()`'s own cross-goal scan finding nothing for a subject_id that was never a `Task.task_id`.

The "compose before calling the LLM again" discipline was verified directly, not just asserted: `test_explain_with_only_decision_trace_makes_no_llm_call` and every other found-a-source test asserts `fake_client.calls == []`, confirming zero `ReasoningEngine.explain_why()` calls occur whenever existing trace text already answers the question — mirroring Sprint 5.21's own established collaboration-test discipline (a call-count assertion against a fake, not just output inspection) per this sprint's own explicit Implementation Tasks item. `_compose()` is tested directly in isolation (stitching, blank-source skipping, truncation) per this sprint's own explicit Testing Checklist item — the one deliberate exception to this codebase's usual "never test an underscore-prefixed helper directly" convention, since this sprint's own text names it by name for direct coverage the same way Sprint 6.10 named `SelfEvaluator._summarize()`.

18 new tests: 17 in `tests/unit/reasoning/test_explainability.py` (zero-LLM-call proof for `DecisionTrace`-only; `Task`+`EvaluationRecord` and `Goal`+`EvaluationRecord` multi-source composition, including a goal with no evaluations composing alone; an evaluation-kind cross-goal scan; every degrade-to-fallback path — missing lookup, `None`-returning lookup, no store, unknown task id, `ranked_action`; `narrative` truncation via both the LLM path and the composed path; `_compose()` in isolation), plus 1 more `ReasoningConfig` validation test in `test_schema.py`.

Full suite (unit + integration + system, opt-in real-model marker excluded): 2202 passing + 5 skipped + exactly 1 failure, confirmed a pre-existing non-regression by standalone re-run — `test_context_analyzer_extracts_a_nonempty_topic_for_real_input` failed once standalone, then passed on an immediate second standalone run with zero code changes in between, the textbook signature of genuine real-Ollama-output nondeterminism rather than a deterministic bug. This is the identical already-long-documented flake class first logged at Sprint 5.2, in `decision/context_analyzer.py` — a file this sprint never touches. `ruff check .` clean repo-wide.

`docs/STATUS.md` (Level 6 Part A narrative extended, Part A header → "11/15 implemented"), `docs/sprint_book/INDEX.md` (6.11 row → `Complete`) both updated. No new `backlog/technical_debt.md` entry — this sprint extends `reasoning/`, no new top-level package, mirroring 6.2's/6.5's/6.7's/6.9's/6.10's own identical precedent.

**No git commit made** — per this project's own "only commit when explicitly asked" rule; changes left in the working tree alongside Sprints 6.1–6.10's own still-uncommitted work, the user not yet asked whether to commit. **Sprint 6.12 (Adaptive Prioritization) is next.**
