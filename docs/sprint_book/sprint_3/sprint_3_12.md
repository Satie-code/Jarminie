# Sprint 3.12 — Decision Engine Integration

## Sprint ID

3.12

## Sprint Name

Decision Engine Integration

## Purpose

Wire every module built across Sprints 3.1–3.11 (Memory Engine, Dynamic Memory, Decision Engine) into one real system, mirroring exactly what Sprint 2.12 (Communication Pipeline Integration) did for Level 2: `CommunicationPipeline` and `main.py` gain the real reasoning path this Level built, replacing Level 2's deliberate placeholders with real memory-and-decision-informed behavior.

## Engineering Rationale

Every sprint in this Sprint Book from 3.1 onward deliberately left `main.py`/`voice/pipeline.py` untouched — the same discipline Sprints 2.1–2.11 followed before Sprint 2.12 existed, for the same reason: wiring correctness deserves its own dedicated integration sprint rather than being folded piecemeal into whichever component sprint happens to finish last. `sprint_book/INDEX.md`'s Level 2 breakdown note recorded exactly why this pattern was adopted (*"Level 2's real-time, hardware-and-ML-dependent integration surface is much larger than Level 1's, so wiring... [is] given [its] own planned sprint rather than folded into the last component sprint"*) — Level 3's integration surface is at least as large (SQLite + ChromaDB + Ollama + a six-stage pipeline), so the same reasoning applies without needing re-justification.

Three specific, previously-flagged placeholders are retired by name in this sprint, each because the sprint that created it explicitly said so:

1. **`Persona.compose_reply()`'s signature grows a new parameter.** `personas/base.py`'s own docstring anticipated this exactly: *"this interface itself is not expected to change beyond the anticipated (not yet added) extra parameter flagged in [Sprint 2.9's Risks]."* This sprint adds it: `compose_reply(transcript: str, context: ConversationContext, decision_trace: DecisionTrace | None) -> str`. Both `JarvisPersona` and `MiniePersona` (2.9/2.10) are modified to use `decision_trace.retrieved_memories` and `decision_trace.reasoning_text` when composing a reply, replacing the templated acknowledgement with a genuinely informed one. `decision_trace` is typed `| None` deliberately — Sprint 3.13 hardens the case where the Decision Engine pipeline itself fails, and `compose_reply()` must still produce *something* reasonable with no trace at all (Fail Gracefully).
2. **`PersonaManager.detect_context_heuristic()`'s keyword lists are retired as the primary source.** Sprint 2.11's own Risks section named this sprint as the intended replacement. `PersonaManager.select()` is now driven by `ContextAnalysis.suggested_persona` (3.8) via `SwitchReason.CONTEXT_DETECTION`; the Level 2 heuristic is kept as a hardened fallback (Sprint 3.13), not deleted.
3. **`ShortTermMemory.promote_from_turn()` and `ConfidenceScorer.detect_override_phrase()` gain real callers** in the turn-processing path, alongside `MemoryLifecycleManager.run_cleanup_pass()`/`run_monthly_review()` gaining a real (if only startup-time) invocation, per Sprint 3.6's own deferred-caller note.

## Objectives

- `CommunicationPipeline._handle_turn_complete()` runs the full Decision Engine pipeline (Intent → Context → Memory Retrieval → Priority → Authority) between transcript-received and persona-reply-composed.
- `Persona.compose_reply()` receives a real `DecisionTrace` and uses it.
- `PersonaManager.select()` is driven by real `ContextAnalysis.suggested_persona`.
- Every Level 3 `ManagedModule` (Memory Store, Confidence Scorer/Lifecycle Manager, Intent Detector, Context Analyzer, Memory Retrieval Engine, Priority Queue Manager, Authority Evaluator) is constructed and registered in `main.py`'s composition root alongside Level 1/2's existing graph.
- `MemoryLifecycleManager`'s cleanup/review passes run once at startup (per Sprint 3.6's deferred-cadence note — no new scheduler is built here).

## Dependencies

3.1–3.11 (all of Level 3's individual-component sprints), 2.12 (Communication Pipeline Integration — the graph this sprint extends)

## Files to Create

- `tests/integration/test_decision_engine_integration.py`

## Files to Modify

- `voice/pipeline.py` — `CommunicationPipeline._handle_turn_complete()` gains the Decision Engine pipeline call sequence; constructor DI grows to accept the new Level 3 modules.
- `personas/base.py` — `Persona.compose_reply()` signature gains `decision_trace: DecisionTrace | None`.
- `personas/jarvis.py`, `personas/minie.py` — `compose_reply()` implementations updated to use `decision_trace` when present, falling back to something equivalent to the prior templated behavior when `None`.
- `personas/persona_manager.py` — `select()`'s context-detection call site now prefers `ContextAnalysis.suggested_persona`, falling back to `detect_context_heuristic()` only if no `ContextAnalysis` is available (Sprint 3.13 formalizes the failure-triggered fallback specifically; this sprint wires the happy-path preference).
- `main.py` — composition root constructs and registers every Level 3 module, in dependency order, following the exact same "this is the only file allowed to construct concrete subsystem instances" rule Sprint 1.5 established.
- `docs/STATUS.md` — Level 3 phase rows updated to reflect integration.

## Expected Classes

None new — this sprint wires existing classes together; see Files to Modify.

## Expected Interfaces

None new.

## Expected Functions

- `CommunicationPipeline._run_decision_pipeline(transcript: str, context: ConversationContext, session_id: str) -> DecisionTrace` — new private method: `intent_detector.detect()` → `context_analyzer.analyze()` → `memory_retrieval_engine.retrieve(context_analysis.primary_topic, active_persona_name, session_id)` → `priority_queue_manager.classify(intent)` → `authority_evaluator.evaluate(...)`. Returns the resulting `DecisionTrace`. Exception handling for this whole sequence is Sprint 3.13's job, not this sprint's — this sprint wires the happy path correctly first, matching the exact sequencing Sprint 2.12 (wiring) → Sprint 2.13 (hardening) already established.
- `CommunicationPipeline._handle_turn_complete()` (modified) — now calls `_run_decision_pipeline()`, then `short_term_memory.promote_from_turn()`, then passes the resulting trace into `persona_manager.compose_reply_safely(transcript, context, decision_trace)` (itself modified to accept and forward the new parameter).

## Data Flow

```
Transcript (VoiceSessionManager, 2.5) + ConversationContext (2.8)
      ↓
CommunicationPipeline._run_decision_pipeline(transcript, context, session_id)
      ↓
IntentDetector.detect()  →  ContextAnalyzer.analyze()  →  MemoryRetrievalEngine.retrieve()
      ↓                                                          ↓
PriorityQueueManager.classify()  ────────────────────→  AuthorityEvaluator.evaluate()
      ↓
DecisionTrace
      ↓                                    ↓
PersonaManager.select(                ShortTermMemory.promote_from_turn(turn)
  context_analysis.suggested_persona,
  SwitchReason.CONTEXT_DETECTION)
      ↓
PersonaManager.compose_reply_safely(transcript, context, decision_trace)
      ↓
Persona.compose_reply() — real, decision-informed reply
      ↓
ConversationSessionStore.record_turn()  (2.7, unchanged)  →  TextToSpeech (2.4, unchanged)
```

## Implementation Tasks

1. `personas/base.py` — extend `Persona.compose_reply()`'s signature; update the abstract method's docstring to remove the "deliberately minimal placeholder" framing now that it is no longer accurate.
2. `personas/jarvis.py`, `personas/minie.py` — real `decision_trace`-informed reply composition, `None`-safe.
3. `personas/persona_manager.py` — `select()` call-site preference for `ContextAnalysis.suggested_persona` over the Level 2 heuristic.
4. `voice/pipeline.py` — `_run_decision_pipeline()`, modified `_handle_turn_complete()`, constructor DI growth.
5. `main.py` — construct and register every Level 3 `ManagedModule`; invoke `MemoryLifecycleManager.run_cleanup_pass()`/`run_monthly_review()` once during startup, after all modules reach `RUNNING`.
6. `tests/integration/test_decision_engine_integration.py` — a full turn through the real pipeline (fakes at the Ollama/Chroma boundary, per the established convention) confirming the Decision Engine's output actually reaches and influences the composed reply.
7. Update every affected unit test suite (`personas/`, `voice/pipeline.py`) for the new signatures.

## Architecture Notes

This is the first sprint in this Sprint Book to modify Level 2 code — expected and previously flagged (Sprint 1.5's own Recommendations: *"expect `main.py` to be modified... that constraint was for **this** sprint, not a promise `main.py` is frozen going forward"*). No Level 1/2 module's own internal logic changes beyond the specific, named signature/call-site changes above — `MicrophoneManager`, `WakeWordDetector`, `WhisperSpeechToText`, `CoquiTextToSpeech`, `VoiceSessionManager`, `QuietModeController`, `ConversationSessionStore`, `ContextManager` are all untouched.

## Integration Considerations

- `MemoryLifecycleManager`'s startup-time-only invocation is a deliberate, documented limitation (Sprint 3.6's own deferred-cadence note) — not silently "fixed" here; a real periodic cadence remains tracked in `backlog/technical_debt.md`.
- This sprint does not yet harden any of the new failure surfaces it introduces (Ollama down, Chroma degraded, a Decision Engine stage raising) — that is Sprint 3.13's explicit, separate job, matching the Sprint 2.12 → 2.13 precedent exactly.
- `AuthorityEvaluator.explain()` remains uncalled by any live trigger after this sprint — still a Future Consideration, not required here.

## Potential Risks

- **The turn-processing critical path grows by five sequential calls** (Intent → Context → Memory Retrieval → Priority → Authority), each potentially involving a real Ollama round-trip (Intent, Context) — real-world latency impact is unknown until Sprint 3.14's real-model verification; if unacceptable, parallelizing Intent/Context (they don't strictly depend on each other's *output*, only both need `ConversationContext`) is a plausible future optimization, not built here (no premature optimization).
- **`compose_reply()`'s `decision_trace: DecisionTrace | None` parameter makes every existing call site a potential oversight point** — every one of `JarvisPersona`/`MiniePersona`'s existing unit tests must be reviewed, not just the new ones, to confirm none silently pass `None` where a real trace was expected. Explicitly flagged for code review (Development Guide Step 9).
- **This sprint's own scope temptation**: it would be easy to also fix newly-discovered gaps (e.g. a real periodic cleanup cadence) while "already in `main.py`" — resist, per Step 10's "suggest improvements only if they belong to future sprints; do not implement future sprint functionality" — record any such finding as a Recommendation instead.

## Acceptance Criteria

- A real conversation turn through `main.py`'s full graph produces a reply that measurably differs from the Level 2 templated placeholder for a fixture question with a matching stored memory (proving the wiring is real, not just present).
- `PersonaManager.select()` correctly switches persona based on `ContextAnalysis.suggested_persona` for a clearly-technical vs. clearly-casual scripted exchange.
- `MemoryLifecycleManager.run_cleanup_pass()`/`run_monthly_review()` are confirmed to execute once during a real `main.py` startup (log-verified).
- Every existing Level 1/2 test still passes unmodified in behavior (only signature/call-site updates, no logic regressions) — full suite green.

## Testing Checklist

- [ ] Integration: full turn through the real Decision Engine pipeline (fakes at Ollama/Chroma boundary) confirming `DecisionTrace` reaches `compose_reply()`.
- [ ] Integration: persona switching driven by `ContextAnalysis.suggested_persona`.
- [ ] Integration: `MemoryLifecycleManager` passes run once at startup.
- [ ] Unit: updated `JarvisPersona`/`MiniePersona`/`PersonaManager` tests for the new signature, including the `decision_trace=None` fallback path.
- [ ] Full existing suite (Level 1 + Level 2) still passes.

## Documentation Checklist

- [ ] `personas/base.py` docstring updated — no longer describes `compose_reply()` as a "deliberately minimal placeholder."
- [ ] `voice/pipeline.py` docstring — documents the new Decision Engine call sequence.
- [ ] `docs/STATUS.md` — Level 3 phase rows (3.1, 3.2, 3.3) marked reflecting full integration; Level 3 milestone table entry updated.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium-High.

## Estimated Development Time

2–2.5 days.

## Next Sprint

3.13 — Error Handling & Recovery Hardening.

## Future Considerations

- Parallelizing Intent Detection and Context Analysis's Ollama calls, if Sprint 3.14's real-model verification shows sequential latency is a genuine problem.
- A real periodic cadence for `MemoryLifecycleManager` — remains explicitly deferred, not this sprint's scope.

---

## Sprint Completion Report (2026-07-19)

### Summary

Wired every Level 3 module (Sprints 3.1–3.11) into the real turn-processing path, mirroring Sprint 2.12's own role for Level 2. `CommunicationPipeline` gained `_run_decision_pipeline()` and a rewritten `_handle_turn_complete()`; `Persona.compose_reply()` grew its long-anticipated `decision_trace` parameter; `PersonaManager` gained `select_from_context()`; `main.py` now constructs and registers all 15 Level 1+2+3 modules. 598/598 tests passing (571 prior + 27 new), `ruff check .` clean. This was the largest, riskiest sprint in the Sprint Book so far — real, non-mocked verification (no fakes at all: real Whisper/Coqui/openWakeWord/Ollama/Chroma) confirmed the full 15-module graph starts, runs, and correctly processes real conversation turns end to end.

### Files Created

- `tests/integration/test_decision_engine_integration.py` — 5 tests.

### Files Modified

- `personas/base.py` — `Persona.compose_reply()` gains `decision_trace: DecisionTrace | None` (required, not defaulted — every call site must consciously decide what trace applies); docstring rewritten, no longer describes the method as a "deliberately minimal placeholder."
- `personas/jarvis.py`, `personas/minie.py` — real `decision_trace`-informed reply composition: a top retrieved memory's content, plus an authority-level-appropriate prefix (`RECOMMEND`/`EMERGENCY_ASSIST`), layered onto the unchanged Level 2 base acknowledgement; falls back to that exact base when `decision_trace is None`.
- `personas/persona_manager.py` — `compose_reply_safely()` gains and forwards `decision_trace`; new `select_from_context(context_analysis, transcript)` method encapsulating the "prefer `ContextAnalysis.suggested_persona`, fall back to `detect_context_heuristic()` only if `context_analysis` is entirely `None`" policy.
- `memory/lifecycle_manager.py` — `start()` now runs `run_cleanup_pass()`/`run_monthly_review()` once and logs the results (see Engineering Decisions — this file wasn't in the sprint's own Files to Modify list, added out of necessity).
- `voice/pipeline.py` — `CommunicationPipeline` constructor grows eight new parameters (`intent_detector`, `context_analyzer`, `memory_retrieval_engine`, `priority_queue_manager`, `authority_evaluator`, `short_term_memory`, `confidence_scorer`, `memory_lifecycle_manager`); new `_run_decision_pipeline()`; `_handle_turn_complete()` rewritten to run the Decision Engine pipeline, drive persona selection from its `ContextAnalysis`, pass the resulting `DecisionTrace` into `compose_reply_safely()`, and promote/override short-term memory after persisting the turn.
- `main.py` — `_Level3Modules` dataclass; `_construct_level3_modules()` (construction only) and `_register_level3_modules()` (registration only, called separately — see Engineering Decisions for why); `_register_level2_modules()` now accepts and forwards the constructed Level 3 objects into `CommunicationPipeline`.
- `tests/unit/personas/conftest.py` — `context_analysis_factory`, `decision_trace_factory`.
- `tests/unit/personas/test_jarvis.py`, `test_minie.py`, `test_persona_manager.py` — all `compose_reply`/`compose_reply_safely` call sites updated for the new signature; new tests for decision-informed replies and `select_from_context()`.
- `tests/unit/voice/test_pipeline.py` — rewritten for the grown constructor and new call sequence.
- `tests/unit/memory/test_lifecycle_manager.py` — new test for `start()`'s two-pass invocation.
- `tests/integration/conftest.py`, `tests/system/conftest.py` — real Level 3 wiring added to `pipeline_harness`/`app_harness` (real `MemoryStore`/Chroma throughout, a new local `FakeLanguageModelClient` fake only at the Ollama boundary); registration-order and timing fixes (see Engineering Decisions).
- `tests/integration/test_voice_pipeline_integration.py`, `tests/system/test_level2_acceptance.py` — signature/assertion updates for the new `compose_reply` parameter and the six new registered module names.
- `docs/STATUS.md` — Level 3 phase rows updated to describe the integration; a new paragraph summarizing Sprint 3.12's own outcome.

### Tests Added

27 total. Persona-layer tests cover: `decision_trace=None` falling back to the exact prior Level 2 templated reply; a matching retrieved memory producing a measurably different reply; authority-level-specific prefixes (`RECOMMEND`/`EMERGENCY_ASSIST`); an empty transcript ignoring `decision_trace` entirely; `compose_reply_safely()` forwarding the trace; and `select_from_context()`'s three branches (prefers `suggested_persona`, no switch when present-but-`None`, falls back to the heuristic only when `context_analysis` itself is `None`) plus a priority-system regression check (`EXPLICIT_SELECTION` still beats a suggested persona). Pipeline-layer tests cover the full `_run_decision_pipeline()` call sequence and argument passing, the explicit-vs-`select_from_context()` branch, memory promotion/override across all four true/false combinations, and that a Decision Engine failure still degrades through the existing outer exception containment. The new integration file covers all three of this sprint's own Acceptance Criteria for real, against a real `MemoryStore`/Chroma and a fake-Ollama-only `LanguageModelClient`.

### Documentation Updated

This file (Sprint Completion Report). `personas/base.py`'s module docstring (no longer "deliberately minimal placeholder"). `voice/pipeline.py`'s module docstring (the new Decision Engine call sequence, plus the override-application and GIL-contention engineering decisions below). `memory/lifecycle_manager.py`'s docstring (why `start()` is the correct hook). `main.py`'s new function docstrings (why construction and registration are split, and why registration order changed). `docs/STATUS.md` as above.

### Acceptance Criteria Checklist

- ✔ A real conversation turn through `main.py`'s full graph produces a reply that measurably differs from the Level 2 placeholder for a fixture question with a matching stored memory — verified both in the new integration test and in a real, non-mocked smoke run (see Remaining Risks).
- ✔ `PersonaManager.select()` (via `select_from_context()`) correctly switches persona based on `ContextAnalysis.suggested_persona` for a clearly-technical vs. clearly-casual scripted exchange — verified in the new integration test, with a companion test proving `EXPLICIT_SELECTION` still overrides it.
- ✔ `MemoryLifecycleManager.run_cleanup_pass()`/`run_monthly_review()` confirmed to execute once during a real startup, log-verified — both in a dedicated integration test and observed directly in the real composition-root smoke run's own log output.
- ✔ Every existing Level 1/2 test still passes — full suite green (598/598), no logic regressions, only the anticipated signature/call-site updates.

### Engineering Decisions

- **`MemoryLifecycleManager.start()` itself runs both lifecycle passes**, even though `memory/lifecycle_manager.py` wasn't in this sprint's own Files to Modify list. The Objective ("cleanup/review passes run once at startup") requires this to happen after `MemoryStore.start()` but the only two files that could plausibly own "when" — `ui/app.py` (calls `core_manager.startup()`) and `core/manager.py` (drives the module-iteration loop) — were both outside this sprint's Files to Modify too, and changing either would ripple further than a Level 3 integration sprint should. Since `CoreManager.startup()` already calls every registered module's `start()` exactly once, in registration order, making the pass run from *inside* `start()` itself, with `memory_store` registered first, is the one hook available without touching either off-limits file. Documented thoroughly in the module's own docstring so this doesn't read as an accidental scope violation.
- **`main.py` splits Level 3 into `_construct_level3_modules()` (construction only) and `_register_level3_modules()` (registration only, called AFTER `_register_level2_modules()`)** — an early version registered Level 3 immediately, all in one function, before Level 2's `wake_word_detector`/`communication_pipeline` pair. That ordering is what the sprint's own Purpose text implies at first read ("construct and register every Level 3 module... alongside Level 1/2's existing graph"), but it's actually a real bug: `CoreManager.startup()` starts modules in registration order, and `wake_word_detector`'s background thread can begin firing (and, via a short-lived fake wake engine, complete an entire session cycle) the moment its own `start()` runs — if `communication_pipeline.start()` (which wires the `on_turn_complete`/`on_session_ended` relays) doesn't happen until after several slower Level 3 `start()` calls (`MemoryStore`'s Chroma embedding-model initialization chief among them), a session that begins and ends inside that widened gap routes through unwired relays and is silently dropped (logged: "CallbackRelay invoked before wiring was established"). Concretely reproduced in `tests/system`'s own harness before this fix. Registering Level 3 after `communication_pipeline` restores the tight Level-2-only gap between `wake_word_detector` and `communication_pipeline` that existed before this sprint.
- **`ConfidenceScorer.detect_override_phrase()`'s "real caller" is `MemoryLifecycleManager.apply_user_override()`, applied to whatever `ShortTermMemory.promote_from_turn()` promoted the same turn** — the sprint's own Objectives named the two detection/promotion methods needing real callers but didn't spell out this exact chain; without connecting detection to the persisted-override method, "gains a real caller" would mean nothing actually happens with the result. If the transcript contains an override phrase but nothing was promoted this turn (the two trigger-phrase lists —`short_term_salience_triggers` and `override_trigger_phrases` — are independent and can disagree, e.g. "remember this" isn't in the salience list by default), there is honestly nothing to override; not treated as a bug to fix by widening either list, which would be tuning/hardening work outside this sprint's scope.
- **`select_from_context()` does NOT fall back to the Level 2 heuristic when `context_analysis` is present but its `suggested_persona` is `None`** — only when `context_analysis` itself is entirely missing (the Decision Engine pipeline failed, Sprint 3.13's concern). Falling back on a present-but-unclear signal would treat Sprint 3.8's own "no clear signal" as equivalent to "unavailable," contradicting 3.8's own spec language that it is authoritative, not merely advisory.

### Remaining Risks

- **A real, reproducible test-infrastructure timing bug was found and fixed, not just this sprint's own production code.** Level 3's added registration-order startup latency (a real `MemoryStore`/Chroma initialization) exposed two pre-existing, previously-safe timing assumptions in `tests/system`/`tests/integration`'s own fixtures: (1) the registration-order bug above; (2) both fixtures' `voice_config.session_timeout_seconds`/`max_utterance_seconds` (0.8s/2.0s) had enough margin against a fast, Level-2-only startup to never matter, but not against Level 3's added latency — a session could begin (and its own inter-turn timeout clock start ticking) during fixture setup itself, before a test's own `wait_for_active_capture()` polling even begins, silently consuming timeout budget the test never observed. Fixed via a combination of increased margins (`session_timeout_seconds=3.0`, `max_utterance_seconds=10.0` in both fixtures) and, more robustly, resetting `FakeWakeWordEngine.calls = 0` at the start of each timing-sensitive test (the same technique `test_wake_word_thread_death_is_recoverable_via_restart` already established) so wake detection happens relative to a known baseline rather than whatever happened during setup. A third, subtler variant was found in the new integration test itself: a real, CPU/GIL-bound Chroma embedding call (`remember()`) sharing the GIL with `VoiceSessionManager._capture_one_utterance()`'s unthrottled busy-spin loop (fine against real hardware, which naturally rate-limits reads; not fine against the fake, instantly-returning audio backend) ran measurably slower in that context than in isolation — fixed by doing that real work before wake activation, not during an active session.
- **Confirmed via real, non-mocked verification beyond this sprint's own committed scope**: a real composition-root smoke run (all 15 modules, real Whisper/Coqui/openWakeWord/Ollama/Chroma) reached `RUNNING` with passing health checks for every module, and a real driven turn ("Help, there is a fire in the kitchen!") correctly produced `RECOMMEND`-not-`EMERGENCY_ASSIST` phrasing through the actual wired `CommunicationPipeline`, not just the isolated Decision Engine components Sprint 3.11 verified. One environment hiccup along the way (`text_to_speech` failing to start with "No espeak backend found") was the already-documented stale-shell-PATH issue from Sprint 2.12's own completion report, not a Sprint 3.12 regression — confirmed by adding the known-good install directory to the current shell's `PATH` directly.
- This sprint's own flagged risks stand as expected: no exception handling was added around the new Decision Engine pipeline call sequence itself (Sprint 3.13's explicit job); `AuthorityEvaluator.explain()` remains uncalled by any live trigger; `backlog/technical_debt.md` item 16 (the `gemma3`/`llama3` mismatch) applies to this sprint's own real verification too — used `llama3` explicitly.

### Technical Debt

None new. The registration-order and test-timing fixes are documented as Engineering Decisions/Remaining Risks above, not technical debt, since they are permanent, non-shortcut corrections.

### Recommendations

- **For Sprint 3.13 (Error Handling & Recovery Hardening)**: the Decision Engine pipeline call sequence inside `_handle_turn_complete()` currently has no scenario-specific handling of its own — a failure anywhere in it (Ollama down, Chroma degraded, an unexpected exception in any stage) falls through to this method's existing outer `except Exception` (ending the session with `SessionEndReason.ERROR`), which is correct but coarse. Sprint 3.13 should consider whether individual stages deserve the same graceful-degrade-without-ending-the-session treatment Sprint 2.13 gave Level 2's own failure scenarios.
- **For whoever eventually revisits `backlog/technical_debt.md` items 11/15/16**: this sprint's real verification reconfirms all three are still open and unchanged by this sprint's own work.
- **The GIL-contention finding** (a real, CPU-bound Python call sharing the GIL with an unthrottled fake-backed busy-spin loop running measurably slower than in isolation) is worth keeping in mind for any future test that does real, non-trivial Python work while a voice session is active in these same fixtures — doing such work before activation, not during it, sidesteps the issue entirely.

**Sprint 3.12 (Decision Engine Integration) is complete.** **Sprint 3.13 (Error Handling & Recovery Hardening) is next.**
