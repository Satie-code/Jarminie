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
