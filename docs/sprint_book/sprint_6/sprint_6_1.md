# Sprint 6.1 — Planning Engine

## Sprint ID

6.1

## Sprint Name

Planning Engine

## Purpose

Open Level 6 Part A (Autonomous Intelligence & Cognitive Architecture) with the layer everything else in this Part ultimately serves: turning a user-stated Goal into a structured, reviewable breakdown — `Goal → Milestones → Tasks → Actions` — without ever executing anything itself. This is the first sprint of an entirely new cognitive layer sitting above the existing Decision Engine (`decision/`), not a replacement for it: Intent Detection/Context Analysis/Engine Selection (Level 3) still decide *what kind of turn this is*; the Planning Engine is what JARMINEI reaches for once a turn's answer is "the user wants to accomplish something larger than one action."

## Engineering Rationale

Commissioned as new scope, substantially different from the locked `04_Master_Implementation_Plan.md`'s own "LEVEL 6 — Stabilization" (Phases 6.1–6.5: Performance, Reliability, Security, Documentation, Final Testing). Per `docs/sprint_book/INDEX.md`'s "Level 6 breakdown changes" note, the user chose (via `AskUserQuestion`, mirroring the Level 4/Level 5 precedent exactly) to split Level 6 into two Sprint Books: **Part A — Autonomous Intelligence & Cognitive Architecture** (this Sprint Book, 6.1–6.15) and **Part B — Stabilization** (the original roadmap content, renumbered 6.16–6.23, kept at roadmap granularity until it becomes current). `v1.0` is gated on both parts, identical to `v0.4`'s and `v0.5`'s own two-part gating.

**A new top-level `planning/` package is introduced** — no existing top-level directory in `03_Engineering_Standards.md`'s Repository Structure list is a plausible home for goal decomposition, and `01_Project_Vision.md`/`02_System_Architecture.md` name no such subsystem at all (this whole Part is new scope). Same treatment as `emotion/` (Sprint 1.1) and `presentation/` (Level 5 Part A): disclosed here as the point of decision, with the corresponding `backlog/technical_debt.md` entry deferred to whichever sprint first creates the folder for real (this one), per this project's own established practice.

**Reused, not reinvented**: goal decomposition is LLM-driven and reuses `decision/llm_client.py`'s existing `LanguageModelClient`/`OllamaClient` Protocol — the same "one LLM integration, many callers" precedent `internet/summarizer.py` (Sprint 4.17), `internet/research_engine.py`, and `decision/response_generator.py` (0.4.2) already established. No second model integration is introduced.

**A deliberate scope boundary, stated explicitly because it shapes every sprint after this one**: the Planning Engine produces a *proposed* decomposition only. It never persists it (Sprint 6.2's job), never schedules or dispatches a single Action (Sprint 6.9/6.13's job), and never runs without the decomposition being reviewable by the user first — this is Level 6's own "Plan Before Executing" design principle applied to the very first sprint that could plausibly violate it.

## Objectives

- `Goal`, `Milestone`, `Task` data models — a strict three-level decomposition, matching the brief's own literal shape (`Goal ↓ Milestones ↓ Tasks ↓ Actions`, where "Actions" are Sprint 6.9's existing `device_control.ActionRequest`/`WorkflowStep` shapes, not a fourth new model).
- `PlanningEngine`: given a natural-language goal statement, produces a proposed `Goal` (with nested `Milestone`s and `Task`s) via one LLM call, structured-output parsed (the same regex/JSON-parse discipline `decision/intent_detector.py`/`decision/context_analyzer.py` already established).
- `PlanningConfig` (new `config/schema.py` section, this Sprint Book's first — will grow across 6.2/6.10).

## Dependencies

3.1–3.6 (Memory Engine — a proposed `Goal` is stored as a `MemoryRecord` for continuity across sessions, `MemoryType.SHARED` since a goal is not persona-scoped), Ollama runtime (`decision/llm_client.py`, Sprint 3.7's own integration). No dependency on Task Graph (6.2) — this sprint proposes structure, 6.2 is what makes that structure durable and queryable.

## Files to Create

- `planning/planning_model.py` — `Goal`, `Milestone`, `Task`, `PlanningStatus` (enum).
- `planning/planning_engine.py` — `PlanningEngine`.
- `tests/unit/planning/test_planning_model.py`
- `tests/unit/planning/test_planning_engine.py`

## Files to Modify

- `config/schema.py` — new `PlanningConfig` dataclass: `max_milestones_per_goal: int = 5`, `max_tasks_per_milestone: int = 8` (both defensive upper bounds on LLM output, not product requirements — a decomposition that returns more is truncated with a logged warning, never silently accepted), `decomposition_timeout_seconds: float = 45.0` (goal decomposition is a larger, more open-ended generation than Intent Detection/Context Analysis's short structured answers, so a longer per-call timeout than `ModelConfig`'s own defaults is warranted — mirrors `internet/summarizer.py`'s identical reasoning for its own longer generation).
- `config/defaults.yaml` — matching `planning:` section.
- `config/loader.py` — `_SECTION_SCHEMAS` entry for `PlanningConfig`, matching every prior new-config-section precedent (`AnalyticsConfig` at 5.17, `EmotionConfig` at 5.1, etc.).

## Expected Classes

- `PlanningStatus` (Enum) — `PROPOSED`, `ACCEPTED`, `IN_PROGRESS`, `COMPLETED`, `ABANDONED`. Applies uniformly to `Goal`/`Milestone`/`Task` (all three share the same lifecycle vocabulary — Sprint 6.2's `TaskGraph` is what actually transitions a `Task` through it; this sprint only ever produces `PROPOSED`).
- `Task` (dataclass) — `task_id: str`, `title: str`, `description: str`, `status: PlanningStatus = PlanningStatus.PROPOSED`, `estimated_effort: str | None` (a short human phrase, e.g. "15 minutes" — deliberately not a typed duration; the LLM's own effort estimate is a rough hint, not a scheduling commitment).
- `Milestone` (dataclass) — `milestone_id: str`, `title: str`, `tasks: list[Task]`, `status: PlanningStatus = PlanningStatus.PROPOSED`.
- `Goal` (dataclass) — `goal_id: str`, `statement: str` (the user's own original phrasing, preserved verbatim — Human First Rule applied to planning: JARMINEI's own decomposition never overwrites what the user actually asked for), `milestones: list[Milestone]`, `status: PlanningStatus = PlanningStatus.PROPOSED`, `created_at: datetime`.
- `PlanningEngine` — constructor DI: `(llm_client: LanguageModelClient, model_config: ModelConfig, planning_config: PlanningConfig)`. Not a `ManagedModule` — no lifecycle of its own, matching `internet/summarizer.py`'s/`decision/response_generator.py`'s identical "wraps an LLM call, nothing to start/stop" precedent.

## Expected Interfaces

None new — `PlanningEngine` is a plain class, not a Protocol; it consumes the existing `LanguageModelClient` Protocol (`decision/llm_client.py`) exactly as every other LLM-calling class in this codebase already does.

## Expected Functions

- `PlanningEngine.decompose_goal(statement: str) -> Goal` — builds a structured prompt (instructing the model to return milestones and tasks in a strictly delimited, parseable format, the same discipline `decision/intent_detector.py`'s own prompt already established), calls `llm_client.generate(..., stop=[...])`, parses the response into a `Goal` tree. Truncates to `planning_config.max_milestones_per_goal`/`max_tasks_per_milestone` if the model over-produces, logging a warning rather than raising. Raises `LlmError` (re-exported from `decision/llm_client.py`, not a new exception type) on an unreachable model or a response that fails to parse into at least one milestone — the caller (Sprint 6.13) decides the user-facing fallback, matching `ResponseGenerator`'s own established call-site-owns-the-fallback precedent.
- `PlanningEngine._parse_decomposition(raw_text: str) -> list[Milestone]` — the regex/section-split parser, isolated for direct unit testing against a fixed corpus of realistic (and deliberately malformed) model outputs, the same "parser tested independently of a live model" discipline `decision/context_analyzer.py`'s own `_parse_response()` already established.

## Data Flow

```
User goal statement (from a live turn, wired at Sprint 6.13)
      ↓
PlanningEngine.decompose_goal(statement)
      ↓
prompt built from statement + planning_config bounds
      ↓
LanguageModelClient.generate(..., stop=["\n\n"])   → real Ollama call
      ↓
_parse_decomposition(raw_text)  →  list[Milestone(list[Task])]
      ↓
Goal (status=PROPOSED)
      ↓
(returned to caller — not persisted by this sprint)
      ↓
Sprint 6.2 (Task Graph) — persistence, dependency edges, execution-readiness
Sprint 6.13 (Integration) — the live turn that calls this and shows the user the proposal before anything is accepted
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml`/`config/loader.py` — `PlanningConfig`.
2. `planning/planning_model.py` — `PlanningStatus`, `Task`, `Milestone`, `Goal`.
3. `planning/planning_engine.py` — `PlanningEngine.decompose_goal()`/`_parse_decomposition()`.
4. Unit tests: model construction/defaults; parser against well-formed output, over-long output (truncation + warning), and malformed/unparseable output (raises, doesn't fabricate a fake `Goal`); `decompose_goal()` against a fake `LanguageModelClient` covering a normal case, an `LlmError`-raising case, and a stop-sequence-respecting case (mirrors `decision/intent_detector.py`'s own established fake-client test shape).

## Architecture Notes

The Planning Engine deliberately does **not** call any other Level 6 Part A component yet — no Context Engine (6.3), no Knowledge Graph (6.6), no Reasoning Engine (6.4). It takes a plain string and returns a plain tree. This is a conscious "thinnest possible first sprint" choice: every later sprint in this Part composes with `Goal`/`Milestone`/`Task` as a stable foundation, the same role `memory/models.py`'s `MemoryRecord` played for the whole of Level 3, or `device_control/action_engine.py`'s `ActionRequest`/`ActionResult` played for all of Level 4 Part A.

`Task` is deliberately **not** typed against `device_control/action_engine.py`'s `ActionType` — a proposed Task from a fresh LLM decomposition is a human-readable intention ("Pull the latest changes from the repository"), not yet a dispatchable `ActionRequest`. The translation from `Task` to a concrete `ActionRequest`/`WorkflowStep` is Sprint 6.9's own job, exactly mirroring how `workflow/workflow_model.py`'s own docstring already describes translating a `WorkflowStep` into an `ActionRequest` as "a one-line operation," not a first-class model concern.

## Integration Considerations

- No live caller exists yet. `PlanningEngine` is fully implemented and unit-tested in isolation — Sprint 6.13 (Autonomous Intelligence Integration) gives it its first real turn-triggered caller via a new `EngineSelection.PLANNING` route, the same "component sprint ships untethered, the Level's own Integration sprint wires it" precedent every prior Level in this project has already used (e.g. Sprint 5.23's `PreferenceLearner.detect_conversation_style()` had no live caller until 5.24).
- Sprint 6.2 (Task Graph) is this sprint's own real, in-Sprint-Book consumer: it takes a `Goal` returned by `decompose_goal()` and makes it durable/executable.

## Potential Risks

- **LLM decomposition quality is inherently variable** — a vague goal statement ("get organized") may produce a shallow or generically-worded plan. No sprint in this Book adds goal-statement validation/clarification-questioning (that is Sprint 6.4's Reasoning Engine "What if?"/clarification territory, deliberately deferred, not built speculatively here).
- **`_parse_decomposition()` is a regex/section parser against free-form LLM text**, the same class of fragility `decision/context_analyzer.py`'s own parser already carries — a sufficiently unusual model output could fail to parse into any milestone at all; handled by raising rather than fabricating a plausible-looking but wrong `Goal` (Human First Rule: never invent structure the model didn't actually produce).
- **No de-duplication against an already-existing `Goal`** — asking JARMINEI to plan the same thing twice produces two independent `Goal` trees. Left to Sprint 6.6 (Knowledge Graph)/6.13 (Integration) to decide whether and how to surface "this looks like an existing goal" — no basis to guess a resolution here.

## Acceptance Criteria

- `decompose_goal()` returns a `Goal` whose `statement` exactly matches the input, with at least one `Milestone` containing at least one `Task`, for a well-formed model response.
- A model response producing more than `max_milestones_per_goal`/`max_tasks_per_milestone` is truncated to those bounds, with a logged warning — never silently exceeded, never raised as an error.
- An unparseable or empty model response raises rather than returning a fabricated `Goal`.
- `decompose_goal()` propagates `LlmError` when `llm_client.generate()` raises it — no swallowing, no fallback within this class (call-site's job).
- Zero changes to any existing `decision/`, `memory/`, or `voice/` file — this sprint is additive only.

## Testing Checklist

- [ ] Unit: `Task`/`Milestone`/`Goal` construction and default `PlanningStatus`.
- [ ] Unit: `_parse_decomposition()` against a well-formed multi-milestone/multi-task response, a single-milestone response, an over-long response (truncation), and a malformed/empty response (raises).
- [ ] Unit: `decompose_goal()` against a fake `LanguageModelClient` — normal case, `LlmError` propagation, `stop=` sequence passed through.
- [ ] Unit: `PlanningConfig` validation (`_validate_planning()` in `config/loader.py`, matching every prior section's own validation-function precedent).

## Documentation Checklist

- [ ] `planning/planning_model.py`/`planning_engine.py` docstrings: the "proposal only, no persistence/execution" scope boundary, stated explicitly.
- [ ] `docs/STATUS.md` — new Level 6 section added, Part A row → `Designing`.
- [ ] `docs/backlog/technical_debt.md` — new entry recording the `planning/` top-level package addition (same treatment as `emotion/`/`presentation/`), to be added once this sprint is actually implemented.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

6.2 — Task Graph.

## Future Considerations

- Goal-statement clarification (asking the user a narrowing question before decomposing a vague goal) — natural territory for Sprint 6.4's Reasoning Engine, not built here.
- Multi-turn, incremental goal refinement (the user amending a proposed `Goal` in conversation rather than restating it from scratch) — no basis in this sprint's own scope; a Future Consideration for whichever sprint first gives Planning a live conversational surface (6.13).
- Goal templates/reuse for recurring goal shapes — no basis named anywhere in this brief; not built speculatively.

## Sprint Completion Report (2026-08-06)

Implemented as specified, authorized directly ("continue with the sprint 6.1") right after this Sprint Book's own Pass-1 planning session closed in the same conversation — the spec was already complete and unmodified, so implementation proceeded without a separate stop-and-ask round trip, matching this project's established precedent for a direct "proceed" instruction against an already-complete sprint file (`sprint_4_14.md`'s/`sprint_5_17.md`'s own identical precedent).

Delivered `planning/planning_model.py` (`PlanningStatus`, `Task`, `Milestone`, `Goal` — field declaration order rearranged from the sprint file's own prose listing so every required field precedes any defaulted one, a plain Python dataclass necessity, not a content change), `planning/planning_engine.py` (`PlanningEngine.decompose_goal()`/`_parse_decomposition()`/`_parse_task_line()`), and `config/schema.py`'s `PlanningConfig` (wired through `config/loader.py`'s `_SECTION_SCHEMAS` and `config/defaults.yaml`, with `_validate_planning()` added to `AppConfig.validate()` — the sprint file's own Files to Modify said this validation function lives in `config/loader.py`; the real, established codebase pattern is `AppConfig._validate_X()` methods in `config/schema.py` itself, `config/loader.py`'s `_SECTION_SCHEMAS` being only the YAML-section-to-dataclass registry — implemented against the real pattern, not the sprint file's own imprecise wording).

**Two deliberate, disclosed corrections from this sprint file's own text, both found by checking real, established codebase precedent before implementing rather than following the sprint file literally:**

1. **No `stop=` sequence is passed to `generate()`**, despite the sprint file's own Data Flow diagram showing `stop=["\n\n"]`. `IntentDetector`/`ContextAnalyzer`'s own `"\n\n"` stop sequence (0.4.3) exists specifically because their prompts request a short, fixed number of lines with no legitimate blank line inside a correct answer. A goal decomposition is the opposite shape — a variable-length, potentially many-line structured block (several milestones, each with several tasks) a real model is likely to visually separate with blank lines for readability, which a blank-line stop sequence would silently truncate after the first milestone, breaking multi-milestone decomposition without ever raising an error. This generation is structurally closer to `ResponseGenerator`'s/`Summarizer`'s own free-form, longer output — both of which 0.4.3 already established deliberately pass no stop sequence at all ("a blank-line stop would risk real truncation") — so `decompose_goal()` follows that precedent instead. Verified directly against both real source files before deciding, not assumed.
2. **`_parse_decomposition()`/`_parse_task_line()` are tested only through the public `decompose_goal()` contract**, not imported and called directly, despite this sprint file's own Testing Checklist describing the parser as "isolated for direct unit testing." Checked `test_context_analyzer.py`/`test_intent_detector.py` first — neither imports `_parse_response()`/`_build_prompt()` by name; both test parsing behavior exclusively through the public `analyze()`/`detect()` methods against a fake `LanguageModelClient` returning specific raw text. Followed that real, established convention instead of the sprint file's own general phrasing, which described the intent (parser correctness independently verifiable) but not this codebase's own actual mechanism for achieving it.

**A third, smaller disclosed decision**: `model_config: ModelConfig` is accepted by `PlanningEngine.__init__()` exactly as specified but is not used to derive the call timeout (`planning_config.decomposition_timeout_seconds` is, per this sprint's own explicit config design) — kept for constructor-shape consistency with every other `LanguageModelClient` caller in this codebase, documented as such in the class's own docstring rather than silently dropped or silently used for something it wasn't specified for.

31 new tests: 18 in `tests/unit/planning/` (`test_planning_model.py`, `test_planning_engine.py` — covering multi-milestone/multi-task parsing, milestone/task truncation with logged warnings, an unparseable/empty-response `LlmError`, a task line arriving before any milestone line, `LlmError` propagation from `generate()` itself, the dedicated-timeout-not-`ModelConfig` proof, and the no-stop-sequence proof) plus 4 new `PlanningConfig` validation tests appended to `tests/unit/config/test_schema.py` (matching that file's own established `AppConfig(section=...).validate()` pattern). **A real, disclosed, out-of-scope observation made while adding the config validation tests**: `AnalyticsConfig`/`WellnessConfig`/`LearningConfig` (Sprints 5.17–5.23) have zero validation test coverage anywhere in this suite — confirmed via a repo-wide grep for `ConfigError` and for each config class name in `tests/unit/config/` — a real, pre-existing gap, not introduced by this sprint and not backfilled here (out of Sprint 6.1's own scope; noted in `test_schema.py` itself as a comment for whichever future sprint or hardening pass picks it up).

Full suite verification: `tests/unit/planning/` (18/18) and the widened `tests/unit/config/test_schema.py` (all passing) run individually first; then the complete `tests/unit` + `tests/integration` suite (opt-in real-model marker excluded, `tests/unit/voice/test_text_to_speech.py` deselected per its own already-documented, unrelated environment-specific failures — `backlog/technical_debt.md` item 29) — 1829 passing, zero failures, zero new flakiness. A spot-check system test (`tests/system/test_level5_part_b_acceptance.py`, 4/4 passing) confirmed the real, complete Level 1–5 `CoreManager` graph still constructs, starts, and shuts down cleanly with the new `PlanningConfig` section added — `main.py` needed no change (a new, all-defaulted config section is additive by construction), consistent with this sprint's own Files to Modify never naming `main.py`. `ruff check .` clean repository-wide.

`docs/STATUS.md` (new Level 6 Part A narrative paragraph added, Part A header moved to "1/15 implemented," Planning & Reasoning phase row → `Developing`), `docs/sprint_book/INDEX.md` (6.1 row → `Complete`), and `docs/backlog/technical_debt.md` (new item 42, recording the `planning/` top-level package addition — same treatment as items 2/`emotion/` and 40/`presentation/`, logged at this sprint's own implementation time rather than deferred to a later freeze sprint) all updated.

**No git commit made** — per this project's own "only commit when explicitly asked" rule; changes left in the working tree, the user not yet asked whether to commit. **Sprint 6.2 (Task Graph) is next.**
