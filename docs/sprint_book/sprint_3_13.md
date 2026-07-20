# Sprint 3.13 — Error Handling & Recovery Hardening

## Sprint ID

3.13

## Sprint Name

Error Handling & Recovery Hardening

## Purpose

Apply the Fail Gracefully Rule across every new failure surface Level 3 introduced, mirroring Sprint 2.13's role for Level 2: *"Failure of one subsystem must never terminate the entire application. Unavailable modules should report their status while allowing the remaining modules to continue functioning."*

## Engineering Rationale

Level 3 introduced two genuinely new categories of failure Level 1/2 never had to handle: an external always-on **AI runtime dependency** (Ollama — can be down, slow, or missing its model) and a **dual-backend persistence** layer (SQLite + ChromaDB, which can now disagree or partially fail). `sprint_book/INDEX.md`'s Level 2 breakdown note explained why Level 2 earned its own dedicated hardening sprint rather than folding resilience into the last component sprint: *"Level 2's real-time, hardware-and-ML-dependent integration surface is much larger than Level 1's."* Level 3's surface is comparably large, for the same underlying reason — real external dependencies with real, not merely theoretical, failure modes — so it earns the same treatment.

Each of the six scenarios below is a *specific* failure mode already named as a risk somewhere earlier in this Sprint Book, not a speculative worry invented here — this sprint's job is to turn each one into a real regression test with a real fix, exactly as Sprint 2.13 did for its own six scenarios.

## Objectives

Six specific hardening scenarios, each with a dedicated regression test:

**(a) Ollama unreachable / model not pulled.** `IntentDetector.detect()`/`ContextAnalyzer.analyze()` already degrade to safe defaults per their own sprints (3.7/3.8) — this sprint verifies that degradation holds under a *simulated real connection failure* (not just a fake client's canned error), and adds a startup-time `OllamaClient` readiness check that logs a clear, actionable warning (not a crash) if Ollama is unreachable when `main.py` starts.

**(b) ChromaDB unavailable or corrupted.** `MemoryStore` degrades to SQLite-only mode: `store()` still succeeds (structured data persists), `semantic_search()` catches the Chroma failure, logs it, and returns an empty list rather than raising — callers (`PersonaScopedMemory`, `EventMemory`, `MemoryRetrievalEngine`) must all tolerate an empty result from a degraded search as a normal "no relevant memory found" outcome, not a distinguishable error state (per Fail Gracefully, the caller shouldn't need to know *why* nothing came back).

**(c) Confidence scoring math edge cases.** `ConfidenceScorer.score()` is hardened against a record with `last_accessed_at` equal to `created_at` (zero elapsed time — must not divide by zero in the recency decay curve) and against `access_count == 0` (a freshly-created, never-yet-read record).

**(d) Memory Lifecycle cleanup partial failure.** Already specified as a per-record try/except in Sprint 3.6's own `run_cleanup_pass()` — this sprint adds the *regression test* proving one corrupted/unreadable record does not abort the rest of the pass, closing the loop Sprint 3.6 opened but didn't itself verify under a real induced failure.

**(e) Authority Evaluator must fail safe-down, never safe-up.** Any unhandled exception anywhere inside `AuthorityEvaluator.evaluate()`'s own body must result in `AuthorityLevel.INFORM` (the lowest, safest level) — never silently propagate an exception up into `CommunicationPipeline`, and never default to a *higher* authority level than the input would have produced cleanly. This is a direct, mechanical application of Human First + Reliability over Intelligence: a broken decision engine must become more cautious, not more permissive.

**(f) `CommunicationPipeline._run_decision_pipeline()` as a whole must not abort a turn.** If any single stage (Intent, Context, Memory Retrieval, Priority, Authority) raises an exception not already caught by its own sprint's fail-safe contract, the whole pipeline call is wrapped so `_handle_turn_complete()` still reaches `persona_manager.compose_reply_safely()` with `decision_trace=None` — the exact scenario `Persona.compose_reply()`'s `decision_trace: DecisionTrace | None` signature (Sprint 3.12) was designed to tolerate.

## Dependencies

3.12 (Decision Engine Integration)

## Files to Create

- `tests/integration/test_decision_engine_hardening.py` — one dedicated test per scenario (a)–(f), mirroring `sprint_2_13.md`'s test structure exactly.

## Files to Modify

- `decision/llm_client.py` — `OllamaClient` gains a `check_readiness() -> bool` cheap connectivity probe (used at `main.py` startup, not on every `generate()` call).
- `memory/memory_store.py` — `semantic_search()` wraps the Chroma call in a try/except, logs, returns `[]` on failure; `store()`'s existing Chroma-failure handling (Sprint 3.1) is reviewed and confirmed still correct under this sprint's real-failure simulation, not just the happy-path unit test it originally shipped with.
- `memory/confidence_scorer.py` — `score()`'s recency-decay computation guarded against zero-elapsed-time; `access_count == 0` confirmed to produce a valid (low, not `NaN`/error) frequency term.
- `memory/lifecycle_manager.py` — `run_cleanup_pass()`'s existing per-record try/except (Sprint 3.6) gains the regression test proving it.
- `decision/authority.py` — `AuthorityEvaluator.evaluate()` wrapped so any internal exception is caught, logged, and results in the safe-default `DecisionTrace(authority_level=INFORM, selected_engine=INFORM_ONLY, reasoning_text="Decision Engine encountered an internal error; defaulting to the safest response.", ...)`.
- `voice/pipeline.py` — `_run_decision_pipeline()` wrapped so any uncaught exception results in `decision_trace=None` reaching `_handle_turn_complete()`'s downstream call, exactly as Sprint 2.13 hardened `_handle_turn_complete()` itself with no exception handling at all before that sprint existed.
- `main.py` — startup sequence calls `OllamaClient.check_readiness()` and logs a clear warning (does not abort startup) if unreachable.

## Expected Classes

None new.

## Expected Interfaces

None new.

## Expected Functions

- `OllamaClient.check_readiness() -> bool` — a lightweight connectivity probe (e.g. a version/list-models call with a short timeout), distinct from `generate()`'s own per-call timeout handling.
- No other new public functions — this sprint modifies existing function *bodies* for resilience, per its own scope (hardening, not new capability).

## Data Flow

```
(happy path, Sprint 3.12, unchanged)

failure injected at any stage:
  Ollama connection refused          → IntentDetector/ContextAnalyzer → UNKNOWN/neutral default (3.7/3.8, verified under real-failure simulation)
  ChromaDB read/write failure        → MemoryStore.semantic_search() → [] (this sprint)
  malformed MemoryRecord timestamps  → ConfidenceScorer.score() → valid clamped score, no exception (this sprint)
  one corrupted record mid-pass      → MemoryLifecycleManager.run_cleanup_pass() → continues, logs to CleanupReport.errors (verified this sprint)
  any exception inside evaluate()    → AuthorityEvaluator → safe-default DecisionTrace(INFORM) (this sprint)
  any exception in the pipeline call → CommunicationPipeline._run_decision_pipeline() → decision_trace=None → compose_reply_safely() (this sprint)
```

## Implementation Tasks

1. `decision/llm_client.py` — `check_readiness()`; `main.py` startup integration.
2. `memory/memory_store.py` — `semantic_search()` failure handling; confirm `store()`'s existing handling under real failure injection.
3. `memory/confidence_scorer.py` — zero-elapsed-time and zero-access-count guards.
4. `decision/authority.py` — `evaluate()`'s outer exception guard, safe-default `DecisionTrace`.
5. `voice/pipeline.py` — `_run_decision_pipeline()`'s outer exception guard.
6. `tests/integration/test_decision_engine_hardening.py` — one test per scenario (a)–(f), each using a real induced failure (a broken fake connection, a corrupted record, a raising stub) rather than merely asserting the code path exists.

## Architecture Notes

Every fix in this sprint is a defensive addition around already-correct happy-path logic from Sprints 3.1–3.12 — no sprint's core algorithm changes, only its failure boundary. This mirrors Sprint 2.13's own framing exactly: hardening is discovered and fixed *after* real wiring exists, because some failure modes (like scenario (f)'s pipeline-level exception propagation) are only observable once the full chain is connected, not from any single component's own unit tests.

## Integration Considerations

- Scenario (a)'s startup readiness check is advisory only — `main.py` still starts even if Ollama is unreachable, consistent with Fail Gracefully ("unavailable modules should report their status while allowing the remaining modules to continue functioning"); a user can still have a Level-2-quality conversation (persona replies without decision-engine enrichment) with Ollama down.
- Scenario (e)/(f) together guarantee `compose_reply()` always receives *something* usable (`DecisionTrace | None`), closing the loop Sprint 3.12's signature change opened.
- No new failure scenario introduced by this sprint's own changes — every change here is strictly subtractive of risk, adding no new code paths beyond the guards themselves.

## Potential Risks

- **Real-failure simulation for Ollama/ChromaDB requires genuinely breaking a fake connection**, not just asserting against a pre-built exception — matching Sprint 2.13's own established technique (`_RaisingSqliteClient`-style local test doubles, per Sprint 2.7's precedent) rather than relying on the library's real error types, which this project doesn't want its tests coupled to.
- **Adversarial re-reading discipline**: Sprint 2.14's own precedent found real gaps (`QuietModeController`, `ConversationSessionStore.purge_older_than()`) only through a dedicated adversarial re-read *after* this kind of hardening sprint, not during it — this sprint covers the six *named* scenarios; a further adversarial pass is explicitly Sprint 3.14's job, not assumed already complete here.

## Acceptance Criteria

- All six scenarios (a)–(f) have a dedicated regression test using a real induced failure, and all pass.
- A real conversation turn completes successfully (with a degraded-but-present reply) when Ollama is entirely unreachable.
- A real conversation turn completes successfully when ChromaDB is entirely unreachable.
- No scenario in (a)–(f) can cause `AuthorityLevel` to resolve to anything higher than what clean inputs would have produced.
- Full existing test suite (Levels 1–3 to this point) still passes.

## Testing Checklist

- [ ] Integration: Ollama connection failure at `IntentDetector`/`ContextAnalyzer` (real-failure simulation).
- [ ] Integration: ChromaDB failure at `MemoryStore.semantic_search()`.
- [ ] Unit: `ConfidenceScorer.score()` zero-elapsed-time and zero-access-count guards.
- [ ] Integration: one corrupted record does not abort `run_cleanup_pass()`.
- [ ] Unit: `AuthorityEvaluator.evaluate()` internal exception → safe-default `DecisionTrace(INFORM)`.
- [ ] Integration: `_run_decision_pipeline()` exception → `decision_trace=None` reaches `compose_reply_safely()`, turn still completes.
- [ ] Integration: `main.py` starts successfully with Ollama unreachable (warning logged, not fatal).

## Documentation Checklist

- [ ] Each modified file's docstring updated with its specific failure-handling contract (matching the precision of Sprint 2.13's own documentation of its six scenarios).
- [ ] `docs/STATUS.md` — no phase status change (hardening, not new scope) but a note added mirroring Sprint 2.13's own changelog treatment.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days.

## Next Sprint

3.14 — Integration Testing & Level Freeze.

## Future Considerations

- A health-watchdog for a silently-dead `IntentDetector`/`ContextAnalyzer` connection during a long idle period (the Level 3 analogue of Sprint 2.13's own flagged wake-word-thread gap) — recommended as a Level 6 (6.2 Reliability) candidate, not built speculatively here, matching that exact precedent.

---

## Sprint Completion Report (2026-07-20)

### Summary

Applied the Fail Gracefully Rule across Level 3's six named failure scenarios, mirroring Sprint 2.13's role for Level 2. The real, surprising finding of this sprint: **four of the six scenarios (a, b, c, d) were already correctly handled by production code shipped in earlier sprints** (3.1, 3.5, 3.6, 3.7/3.8) — this sprint's job for those four was to add the real-induced-failure regression tests proving it, not to write new production code. Only two scenarios (e, f) needed an actual code change: `AuthorityEvaluator.evaluate()` gained an outer exception guard (scenario e), and `CommunicationPipeline._handle_turn_complete()`'s Decision Engine pipeline call gained its own narrower exception boundary, degrading to `decision_trace=None` instead of ending the session (scenario f). 608/608 tests passing (598 prior + 10 new: 3 `AuthorityEvaluator` tests, 1 `MemoryStore` test, 2 `ConfidenceScorer` tests, 4 integration tests in the new file, minus 0 removed — the one rewritten `test_pipeline.py` test is a 1-for-1 replacement, not a net addition), `ruff check .` clean.

### Files Modified

- `decision/authority.py` — `evaluate()`'s body wrapped in try/except; any internal exception resolves to `DecisionTrace(authority_level=INFORM, selected_engine=INFORM_ONLY, reasoning_text="Decision Engine encountered an internal error; defaulting to the safest response.")`, exactly as specced. Module docstring updated.
- `voice/pipeline.py` — `_handle_turn_complete()`'s call to `_run_decision_pipeline()` gained its own inner try/except, distinct from the pre-existing outer one; on failure, `decision_trace = None` and the turn continues (persona selection falls back to `select_from_context(None, transcript)`, `compose_reply_safely()` receives `decision_trace=None`) rather than ending the session. Method and module docstrings updated.
- `tests/unit/voice/test_pipeline.py` — `test_handle_turn_complete_contains_a_decision_pipeline_failure` (which its own docstring said was a Sprint-3.13-pending placeholder) rewritten as `test_decision_pipeline_failure_degrades_gracefully_without_ending_the_session`, asserting the new behavior instead of the old one.
- `tests/unit/decision/test_authority.py` — 3 new tests for scenario (e): safe-default on an internal exception, that every other `DecisionTrace` field still survives the degrade, and that a failure in the reasoning-text builder specifically (called last) still discards any already-computed authority/engine values.
- `tests/unit/memory/test_memory_store.py` — `_QueryFailingChromaClient` local double + `test_semantic_search_returns_empty_list_on_a_chroma_query_failure` (scenario b's read-path regression test; the write-path one, `test_store_swallows_and_logs_a_chroma_embedding_failure`, already existed from Sprint 3.1).
- `tests/unit/memory/test_confidence_scorer.py` — 2 new tests for scenario (c)'s two named edge cases, both confirming already-correct behavior (no code change).
- `tests/integration/conftest.py` — `FakeLanguageModelClient` gained a `should_raise` flag (mirroring `FakeSpeechToText`/`FakeTextToSpeech`'s own established convention) so integration tests can simulate Ollama being genuinely unreachable, not just return a canned response.
- `tests/integration/test_decision_engine_hardening.py` (new) — 4 tests: a full turn completing with Ollama entirely unreachable; a `CoreManager`-level startup check with Ollama unreachable; a full turn completing with ChromaDB entirely unreachable; a full turn completing when an unexpected bug in a Decision Engine stage (simulated via a raising `MemoryRetrievalEngine.retrieve()`) would otherwise have ended the session.
- `decision/llm_client.py`, `memory/memory_store.py`, `memory/confidence_scorer.py`, `memory/lifecycle_manager.py` — docstrings only, documenting why no production code change was needed for scenarios (a), (b)'s write path, (c), and (d) respectively (see Engineering Decisions below).
- `docs/STATUS.md` — a note appended to the Level 3 section (no phase status change, per this sprint's own Documentation Checklist).

### Tests Added

10 new, 1 rewritten. See Files Modified above for the per-file breakdown. Every new test uses a real induced failure (a local raising double, or a genuinely raising monkeypatched method) per this sprint's own Potential Risks guidance — none assert against a pre-built exception type from an external library.

### Acceptance Criteria Checklist

- ✔ All six scenarios (a)-(f) have a dedicated regression test using a real induced failure, and all pass — four (a, b, c, d) via unit tests proving already-correct behavior, two (e, f) via unit + integration tests proving the new guards.
- ✔ A real conversation turn completes successfully (with a degraded-but-present reply) when Ollama is entirely unreachable — `test_full_turn_completes_when_ollama_entirely_unreachable`.
- ✔ A real conversation turn completes successfully when ChromaDB is entirely unreachable — `test_full_turn_completes_when_chromadb_entirely_unreachable`.
- ✔ No scenario in (a)-(f) can cause `AuthorityLevel` to resolve to anything higher than what clean inputs would have produced — `AuthorityEvaluator.evaluate()`'s new guard only ever degrades toward `INFORM`, never away from it; confirmed by `test_internal_exception_in_reasoning_builder_also_degrades_safely` specifically (a partial success before the failure point does not leak a more permissive level).
- ✔ Full existing test suite (Levels 1-3 to this point) still passes — 608/608.

### Engineering Decisions

- **Four of the six scenarios needed no production code change.** This sprint's own Engineering Rationale predicted this was possible ("Every fix in this sprint is a defensive addition around already-correct happy-path logic"), but the extent was still worth calling out explicitly:
  - **(a) Ollama unreachable**: `IntentDetector.start()`/`ContextAnalyzer.start()` (Sprint 3.7/3.8) already call the injected client's optional `is_reachable()` capability defensively and never raise; `detect()`/`analyze()` already catch `LlmError` and degrade to `UNKNOWN`/neutral defaults. `CoreManager._start_module()` (Sprint 1.5) also independently catches any `start()` exception per-module regardless. The sprint's own named "Expected Function" `OllamaClient.check_readiness()` was found to already exist under the name `is_reachable()`, built ahead of schedule in Sprint 3.7 for this exact purpose — adding a second, identically-behaved method would be pure duplication, so it was not added. See `decision/llm_client.py`'s updated docstring.
  - **(b) ChromaDB unavailable**: `MemoryStore.store()`/`semantic_search()` (Sprint 3.1) already wrap their respective Chroma calls in try/except, logging and degrading (an empty list for search, a persisted-but-unsearchable record for store) rather than raising. Only a regression test for the previously-untested read path (`semantic_search()`) was added; the write path already had one.
  - **(c) Confidence scoring edge cases**: `ConfidenceScorer.score()`'s frequency term (`access_count / (access_count + 1)`) can never divide by zero for any non-negative `access_count`, including 0; the recency term's only zero-division risk is `recency_half_life_days` (a config value, already validated `> 0` at the config layer, Sprint 1.7's `AppConfig.validate()`), never a per-record timestamp. Both named edge cases were already safe.
  - **(d) Memory Lifecycle cleanup partial failure**: `MemoryLifecycleManager.run_cleanup_pass()`'s per-record try/except (Sprint 3.6) already had a dedicated regression test (`test_one_record_scoring_failure_does_not_abort_the_rest_of_the_pass`, using a real `_ScoreRaisingConfidenceScorer` local double) — added during Sprint 3.6's own implementation, ahead of this sprint's formal ask, rather than deferred as the spec anticipated.
- **`main.py` needed no change either**, for the same reason as (a) above — its startup sequence already tolerates Ollama being unreachable via the mechanisms described, with no direct `check_readiness()` call needed. Verified via a dedicated `CoreManager`-level integration test rather than the full 15-module graph, since building that graph would require faking the entire mic/wake/STT/TTS boundary just to reach two modules that don't need any of it.
- **Scenario (f)'s test needed a genuinely different failure injection point than (a) or (b)**: since Intent Detection, Context Analysis, and Memory Retrieval-via-Chroma-failure all already degrade internally without raising, none of them can actually exercise `_run_decision_pipeline()`'s new outer guard. `MemoryRetrievalEngine.retrieve()` itself has no internal try/except of its own (by design — it composes Sprint 3.1-3.6 wrappers that each already handle their own failures, so it never needed one), making a monkeypatched `retrieve()` that raises unconditionally the honest way to simulate "an unexpected bug in a stage nothing else already catches," per the scenario's own wording.
- **`AuthorityEvaluator.evaluate()`'s safe-default still returns the caller-supplied `intent`/`context_analysis`/`retrieved_memories`/`priority_level`** rather than replacing them with placeholders — only `authority_level`/`selected_engine`/`reasoning_text` (the three fields `_determine_authority()`/`_determine_engine()`/`_build_reasoning()` compute) are overridden. This keeps `DecisionTrace`'s contract intact for downstream callers (`CommunicationPipeline`, `Persona.compose_reply()`) even on the safe-default path.

### Remaining Risks

- This sprint's own Future Considerations item (a health-watchdog for a silently-dead `IntentDetector`/`ContextAnalyzer` connection during a long idle period) remains unbuilt, as explicitly recommended — a Level 6 (6.2 Reliability) candidate, not built speculatively here.
- Sprint 3.14's own job (an adversarial re-read of Level 3's source beyond these six named scenarios) has not been performed as part of this sprint, per this sprint's own Potential Risks note distinguishing the two.
- `backlog/technical_debt.md` items 11, 15, 16 (recurring lifecycle cadence, Scheduler-dependent purge, the `gemma3`/`llama3` model default mismatch) are unaffected by this sprint and remain open.

### Technical Debt

None new.

**Sprint 3.13 (Error Handling & Recovery Hardening) is complete.** **Sprint 3.14 (Integration Testing & Level Freeze) is next** — the formal Level 3 acceptance/freeze gate, mirroring Sprint 2.14's own pattern for Level 2.
