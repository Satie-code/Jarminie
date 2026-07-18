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
