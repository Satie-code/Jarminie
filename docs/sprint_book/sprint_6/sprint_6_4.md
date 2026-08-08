# Sprint 6.4 — Reasoning Engine

## Sprint ID

6.4

## Sprint Name

Reasoning Engine

## Purpose

Give JARMINEI a dedicated place to reason *about* a plan, a decision, or a situation — not just classify it (Level 3's job) or decompose it (Sprint 6.1's job). Per the brief's own list: Why?, What if?, Alternative solutions, Trade-offs, Confidence estimation. This is the sprint that produces the raw reasoning material Sprint 6.5 (Decision Engine v2) ranks/gates and Sprint 6.11 (Explainability Layer) surfaces to the user on request.

## Engineering Rationale

A new top-level `reasoning/` package, for the same one-engine-one-folder reason `planning/` (6.1) and `context/` (6.3) were introduced — recorded here, `backlog/technical_debt.md` entry deferred to implementation.

**Reused, not reinvented**: `ReasoningEngine` is the fourth caller of `decision/llm_client.py`'s `LanguageModelClient` (after `IntentDetector`, `ContextAnalyzer`, `ResponseGenerator`/`Summarizer`) — no second model integration.

**A real, deliberate scope boundary against Sprint 6.1's `PlanningEngine`**: goal *decomposition* (turning a statement into milestones/tasks) stays in `planning/`; *reasoning about* an already-decomposed plan, an already-made decision, or a hypothetical ("what if I skip this task?") is this sprint's job. The two are sequential, composable LLM-backed capabilities, not overlapping ones — `ReasoningEngine` takes a `Goal`/`Task`/decision as **input**, `PlanningEngine` produces a `Goal` as **output**.

**Confidence estimation reuses the existing five-factor vocabulary this codebase already established**, rather than inventing a new scoring scheme: `memory/confidence_scorer.py`'s `ConfidenceScorer` (Sprint 3.5) already produces a 0–100 confidence band for memory records; `learning/pattern_recognizer.py`'s own `_confidence()` (Sprint 5.21) already produces an evidence-count-based confidence float for detected patterns. `ReasoningEngine.estimate_confidence()` is a **third**, LLM-elicited confidence source (the model's own stated certainty about a reasoning conclusion) — explicitly named as a different kind of confidence than either existing one (model self-assessment vs. derived-from-data), not a fourth attempt to unify all three into one number. Sprint 6.5 is where a caller that needs to combine more than one of these signals would do so.

## Objectives

- `ReasoningTrace` — the structured output of any reasoning call (question, conclusion, supporting factors, confidence, alternatives considered).
- `ReasoningEngine`: `explain_why(subject, context)`, `what_if(scenario, context)`, `alternatives(subject, context)`, `estimate_confidence(subject, context)` — four focused methods rather than one generic "reason about X" call, matching the brief's own four named reasoning shapes.
- `ReasoningConfig` (new `config/schema.py` section — will grow again at Sprint 6.11).

## Dependencies

6.1/6.2 (reasons about `Goal`/`Task` objects), 6.3 (`WorkingContext` grounds every reasoning call in real current state, not just the bare subject text), Ollama runtime (`decision/llm_client.py`).

## Files to Create

- `reasoning/reasoning_model.py` — `ReasoningTrace`, `Alternative` (dataclass: `description: str`, `estimated_trade_off: str`).
- `reasoning/reasoning_engine.py` — `ReasoningEngine`.
- `tests/unit/reasoning/test_reasoning_model.py`
- `tests/unit/reasoning/test_reasoning_engine.py`

## Files to Modify

- `config/schema.py` — new `ReasoningConfig` dataclass: `max_alternatives: int = 3` (defensive upper bound, matching `PlanningConfig`'s own bounding-not-requiring shape), `reasoning_timeout_seconds: float = 30.0`.
- `config/defaults.yaml` — matching `reasoning:` section.
- `config/loader.py` — `_SECTION_SCHEMAS` entry.

## Expected Classes

- `Alternative` (dataclass) — `description: str`, `estimated_trade_off: str` (a short human phrase, e.g. "Faster, but skips validation" — deliberately not a structured multi-field trade-off model; no basis in the brief's own text for anything richer).
- `ReasoningTrace` (dataclass) — `subject: str` (what was reasoned about — a `Goal.statement`, a `Task.title`, a free-form decision description), `question_type: Literal["why", "what_if", "alternatives", "confidence"]`, `conclusion: str`, `confidence: float` (0.0–1.0, the model's own self-reported certainty — distinct from `ConfidenceScorer`'s 0–100 band, deliberately a different scale so the two are never confusable in code), `alternatives: list[Alternative]` (empty except for `alternatives()` calls), `reasoned_at: datetime`.
- `ReasoningEngine` — constructor DI: `(llm_client: LanguageModelClient, model_config: ModelConfig, reasoning_config: ReasoningConfig)`. Not a `ManagedModule`, matching `PlanningEngine`'s identical shape.

## Expected Interfaces

None new.

## Expected Functions

- `ReasoningEngine.explain_why(subject: str, working_context: WorkingContext | None = None) -> ReasoningTrace` — "Why does/should X happen" — the general-purpose reasoning call; `working_context` is optional (a `ReasoningEngine` call with no context still produces a real, if less-grounded, answer rather than refusing).
- `ReasoningEngine.what_if(scenario: str, working_context: WorkingContext | None = None) -> ReasoningTrace` — a hypothetical ("what happens if I skip this task / miss this deadline / do X instead of Y").
- `ReasoningEngine.alternatives(subject: str, working_context: WorkingContext | None = None) -> ReasoningTrace` — populates `ReasoningTrace.alternatives`, bounded by `reasoning_config.max_alternatives`.
- `ReasoningEngine.estimate_confidence(subject: str, working_context: WorkingContext | None = None) -> ReasoningTrace` — asks the model to state its own confidence in a conclusion about `subject`, parsed into the `0.0`–`1.0` field; a response the parser cannot extract a numeric confidence from defaults to `0.5` (an honest "uncertain," never fabricated false precision) with a logged warning, rather than raising — confidence estimation is explicitly advisory input to Sprint 6.5, not a hard gate, so a degraded-but-present answer is more useful here than a raised exception would be.
- `ReasoningEngine._build_prompt(question_type, subject, working_context) -> str` — one shared prompt-builder, parameterized per question type, isolated for direct testing (mirrors `decision/response_generator.py`'s own established shared-prompt-builder shape).

## Data Flow

```
Caller (Decision Engine v2 6.5, Proactive Assistant 6.8, Explainability Layer 6.11 — wired at 6.13)
      ↓
ReasoningEngine.explain_why() / what_if() / alternatives() / estimate_confidence()
      ↓
_build_prompt(question_type, subject, working_context)
      ↓
LanguageModelClient.generate(..., stop=[...])   → real Ollama call
      ↓
response parsed into ReasoningTrace
      ↓
returned to caller — not persisted by this sprint (Sprint 6.11 is what makes a
ReasoningTrace durable/queryable as part of a unified explanation)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml`/`config/loader.py` — `ReasoningConfig`.
2. `reasoning/reasoning_model.py` — `Alternative`, `ReasoningTrace`.
3. `reasoning/reasoning_engine.py` — `_build_prompt()`, all four public methods, the confidence parser with its `0.5` default-on-failure.
4. Unit tests: each of the four methods against a fake `LanguageModelClient`; `alternatives()` truncation at `max_alternatives`; `estimate_confidence()`'s parser against a well-formed numeric response, a non-numeric response (defaults to 0.5, logs), and an out-of-range response (clamped to `[0.0, 1.0]`).

## Architecture Notes

Every `ReasoningEngine` method is a pure input→output call — no state, no memory of prior reasoning calls within the class itself (a caller wanting continuity, e.g. "explain why, then let me ask a follow-up," re-supplies context each time via `working_context`/`subject`). This mirrors `internet/summarizer.py`'s/`decision/response_generator.py`'s own stateless-per-call shape exactly; keeping four focused methods (rather than one method with a `mode` parameter) matches the brief's own explicit enumeration of four distinct reasoning shapes and keeps each one's own prompt independently tunable.

`confidence` on `ReasoningTrace` is scaled `0.0`–`1.0` specifically to be visually and programmatically distinct from `ConfidenceScorer`'s `0`–`100` — a deliberate anti-confusion choice, not an oversight; any future code combining the two must convert explicitly, never compare them directly.

## Integration Considerations

- No live caller yet. Sprint 6.5 (Decision Engine v2) and Sprint 6.11 (Explainability Layer) are this Sprint Book's own real consumers; Sprint 6.13 (Integration) is where a user's own live "why?"/"what if?" question gets routed here for the first time.
- `working_context` is a soft dependency — every method accepts `None`, so this sprint has no hard ordering requirement against Sprint 6.3 being wired into a live turn yet, only against the `ContextEngine`/`WorkingContext` *types* existing (which they do, as of 6.3).

## Potential Risks

- **LLM-elicited confidence is not a calibrated probability** — a model stating "I am 90% confident" carries no guarantee of matching real-world accuracy 90% of the time. Documented here as a known, disclosed limitation (matching `internet/summarizer.py`'s own identical disclosed grounding-limitation precedent at Sprint 4.17) rather than presented to the user as a rigorous statistic; Sprint 6.5/6.11 must treat it as one advisory signal among several, never the sole basis for an autonomous decision.
- **`what_if()`/`alternatives()` on a sensitive or destructive hypothetical could produce a plausible-sounding but factually wrong answer** — the same hallucination-risk class every LLM-backed feature in this codebase already carries; no new mitigation beyond the existing "never silently execute anything reasoning-derived" boundary (nothing in this sprint calls any executor).
- **`reasoning_timeout_seconds=30.0` is an unvalidated guess**, the same tuned-constant caveat every comparable default in this codebase carries.

## Acceptance Criteria

- Each of the four public methods returns a `ReasoningTrace` with `question_type` correctly set and a non-empty `conclusion` for a well-formed model response.
- `alternatives()` never returns more than `reasoning_config.max_alternatives` entries.
- `estimate_confidence()` never returns a `confidence` outside `[0.0, 1.0]`, and defaults to `0.5` (logged) rather than raising when the model's response contains no parseable number.
- All four methods propagate `LlmError` when `llm_client.generate()` raises it.
- Calling any method with `working_context=None` succeeds and produces a real (if less-grounded) `ReasoningTrace`, never a raised exception for that reason alone.

## Testing Checklist

- [ ] Unit: `ReasoningTrace`/`Alternative` construction and defaults.
- [ ] Unit: `explain_why()`/`what_if()`/`alternatives()`/`estimate_confidence()` against a fake `LanguageModelClient`, each with and without `working_context`.
- [ ] Unit: `alternatives()` truncation at the configured bound.
- [ ] Unit: `estimate_confidence()` parser — numeric in range, numeric out of range (clamped), non-numeric (defaults to 0.5, warning logged).
- [ ] Unit: `LlmError` propagation from all four methods.
- [ ] Unit: `ReasoningConfig` validation.

## Documentation Checklist

- [ ] `reasoning/reasoning_engine.py` docstring: the two different confidence scales (`0.0`–`1.0` here vs. `ConfidenceScorer`'s `0`–`100`), stated explicitly per Engineering Rationale above.
- [ ] `docs/STATUS.md` — Level 6 Part A narrative extended.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

2 days.

## Risks

See Potential Risks above.

## Next Sprint

6.5 — Decision Engine v2.

## Future Considerations

- Calibrating LLM-elicited confidence against real outcome data (Sprint 6.10's Self Evaluation records) — a genuinely interesting future direction named nowhere in this brief; not built speculatively.
- Multi-turn reasoning threads (a running "why" conversation rather than independent stateless calls) — deferred, matching this sprint's own stateless-by-design boundary.

## Sprint Completion Report (2026-08-09)

Implemented as specified, authorized directly ("continue with the sprint 6.4") in a new session; found the working tree clean and Sprints 6.1–6.3 already committed (contrary to a stale memory note claiming they were still uncommitted — confirmed via `git log`/`git status` before proceeding, not assumed from memory, per this project's own "trust current repo state over memory" rule).

Delivered `reasoning/reasoning_model.py` (`Alternative`, `ReasoningTrace`) and `reasoning/reasoning_engine.py` (`ReasoningEngine.explain_why()`/`what_if()`/`alternatives()`/`estimate_confidence()`, each backed by one shared, parameterized `_build_prompt()`) — a new `reasoning/` package — and `ReasoningConfig` (`config/schema.py`/`config/defaults.yaml`/`config/loader.py`), mirroring `PlanningConfig`/`ContextEngineConfig`'s own established wiring exactly (field, `AppConfig` slot, `_validate_reasoning()`, `_SECTION_SCHEMAS` entry, `defaults.yaml` section, in the same 6.1→6.3 declaration order).

**One real, disclosed design decision this sprint file's own text left open, resolved directly rather than guessed silently**: `ReasoningTrace.confidence` is specified as a non-optional `float`, but only `estimate_confidence()` actually elicits a real value from the model — the sprint's own four-focused-methods design means `explain_why()`/`what_if()`/`alternatives()` never ask the model to self-assess at all. Widening the field to `float | None` would have rippled an optionality check into every future caller (Sprint 6.5/6.11) for a distinction the field's own 0.0–1.0 scale can express honestly on its own; instead, those three methods set it to a fixed, disclosed `1.0` placeholder (documented directly on the `ReasoningTrace` dataclass and at the one call site that sets it), never a fabricated self-assessment the model was never asked for.

**Parsing, mirroring `planning/planning_engine.py`'s own established shape**: `_extract_conclusion()` prefers a labeled `CONCLUSION:` line but falls back to the whole stripped response when the model doesn't follow the requested format exactly — never an empty conclusion for a genuinely non-empty response. `_parse_alternatives()` truncates to `reasoning_config.max_alternatives` with a single logged warning (not per discarded item), the identical discipline `_parse_decomposition()` already established. `_parse_confidence()` extracts the `CONFIDENCE:` line's own number, clamps out-of-range values into `[0.0, 1.0]` (never rejects them), and defaults to `0.5` with a logged warning when no numeric `CONFIDENCE:` line parses at all — exactly this sprint's own Acceptance Criteria, verified by dedicated tests for in-range, out-of-range (both directions), and unparseable responses.

All four public methods let `LlmError` propagate unmodified from `llm_client.generate()` — verified via a parametrized test calling all four against a failing fake client — and all four accept `working_context: WorkingContext | None = None`, verified to succeed (never raise) with `None` as well as with a populated `WorkingContext`, the latter confirming the optional context actually reaches the prompt (a "Current context:" summary block, built from plain `len()` counts over `WorkingContext`'s own collection fields — no fabricated detail beyond what the snapshot actually contains).

28 new tests: `tests/unit/reasoning/test_reasoning_model.py` (4 — `Alternative` construction, `ReasoningTrace` defaults/verbatim-subject/alternatives-carrying), `tests/unit/reasoning/test_reasoning_engine.py` (20 — each of the four methods with and without `working_context`, `alternatives()` truncation plus its logged warning, `estimate_confidence()`'s parser across in-range/out-of-range/unparseable responses, `LlmError` propagation from all four methods via one parametrized test, the dedicated-timeout-not-model-config check), plus 4 more `ReasoningConfig` validation tests appended to `tests/unit/config/test_schema.py`.

Full suite (unit + integration, opt-in real-model marker excluded): 2012 passing (1984 + 28 new), 1 skipped, zero failures, zero new flakiness. `ruff check .` clean repo-wide (two line-length violations and one unused import caught and fixed before this count).

`docs/STATUS.md` (Level 6 Part A narrative extended, Part A header → "4/15 implemented," Planning & Reasoning phase notes → "6.1–6.2 and 6.4 Complete"), `docs/sprint_book/INDEX.md` (6.4 row → `Complete`), and `docs/backlog/technical_debt.md` (new item 44, `reasoning/` top-level package addition, same treatment as items 2/40/42/43) all updated.

**No git commit made** — per this project's own "only commit when explicitly asked" rule; changes left in the working tree, the user not yet asked whether to commit. **Sprint 6.5 (Decision Engine v2) is next.**
