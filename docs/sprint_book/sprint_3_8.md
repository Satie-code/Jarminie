# Sprint 3.8 — Context Analysis

## Sprint ID

3.8

## Sprint Name

Context Analysis

## Purpose

Implement the Decision Engine pipeline's second stage, per [02_System_Architecture.md](../02_System_Architecture.md): *"Intent Detection → Context Analysis → Memory Retrieval → ..."* Deepens Sprint 3.7's classification into a structured understanding of the conversation — topic, entities, and which persona the request is actually suited to — using `ConversationContext` (2.8) and the same `LanguageModelClient` (3.7).

## Engineering Rationale

This is the sprint `PersonaManager.detect_context_heuristic()` (Sprint 2.11) named as its own intended replacement: *"a known-crude placeholder... explicitly scheduled for replacement by Sprint 3.8's real Context Analysis."* That heuristic's keyword lists (`_MINIE_HEURISTIC_KEYWORDS`/`_JARVIS_HEURISTIC_KEYWORDS`) stay in the codebase as a Fail Gracefully fallback (Sprint 3.13 hardens exactly this: if Context Analysis is unavailable, fall back to the Level 2 heuristic rather than guessing), but this sprint's `ContextAnalyzer.suggested_persona` becomes the real, primary source once wired in Sprint 3.12.

`Context Manager` (2.8) was deliberately built as "a pure aggregator, not a reasoning engine" specifically so this sprint could exist without the two ever competing — 2.8's own Engineering Rationale named this exact sprint as the reason the boundary had to be kept sharp: *"Keeping this distinction sharp now avoids Context Manager quietly growing into a second, competing Context Analysis implementation that Sprint 3.8 would then have to reconcile with or replace."* This sprint is that reconciliation arriving on schedule, with no competing implementation to untangle.

`sentiment_hint` is deliberately coarse (a small fixed vocabulary, not a numeric or clinical scale) — the project's Level 5 Emotion Engine explicitly must "never perform medical diagnosis" (Part 4, Phase 5.1), and nothing in Level 3 should produce output that could later be mistaken for a diagnostic signal. This sprint's sentiment output is a conversational-tone hint only, consumed by Sprint 3.5's confidence-scoring emotional-significance placeholder in a *future* sprint at most, never framed as an assessment of the user's wellbeing.

## Objectives

- A `ContextAnalyzer` producing a `ContextAnalysis`: primary topic, mentioned entities, whether the request references a past memory, a suggested persona, and a coarse sentiment hint.
- `suggested_persona` becomes the real replacement for `PersonaManager.detect_context_heuristic()`, wired in Sprint 3.12.
- No diagnostic or clinical framing anywhere in this sprint's output.

## Dependencies

3.7 (Intent Detection — shares `LanguageModelClient`), 2.8 (Context Manager)

## Files to Create

- `decision/context_analyzer.py` — `ContextAnalysis` (dataclass), `SentimentHint` (Enum), `ContextAnalyzer(ManagedModule)`.
- `tests/unit/decision/test_context_analyzer.py`

## Files to Modify

None — reuses `decision/llm_client.py`'s `LanguageModelClient`/`OllamaClient` from Sprint 3.7 unchanged.

## Expected Classes

- `SentimentHint` (Enum) — `NEUTRAL`, `POSITIVE`, `STRESSED`, `FRUSTRATED`, `TIRED`. Deliberately coarse and conversational, not clinical (see Engineering Rationale).
- `ContextAnalysis` (dataclass) — `primary_topic: str`, `mentioned_entities: list[str]`, `references_past_memory: bool`, `suggested_persona: str | None` (`"jarvis"` / `"minie"` / `None` if no clear signal), `sentiment_hint: SentimentHint`, `analyzed_at: datetime`.
- `ContextAnalyzer(ManagedModule)` — constructor DI: `(llm_client: LanguageModelClient, model_config: ModelConfig)`.

## Expected Interfaces

- `ManagedModule` (reused) — same shape as `IntentDetector` (3.7): `start()` readiness check, `stop()` no-op, `health_check()` cheap cached-state report.

## Expected Functions

- `ContextAnalyzer.analyze(intent: Intent, context: ConversationContext) -> ContextAnalysis` — builds a prompt from `intent.category`, `context.recent_turns`, and `context.active_persona_name`; calls `llm_client.generate()`; parses the response. Any failure (`LlmError`, timeout, unparseable response) degrades to `ContextAnalysis(primary_topic="", mentioned_entities=[], references_past_memory=False, suggested_persona=None, sentiment_hint=NEUTRAL, analyzed_at=now())` — logged, never raised, identical fail-safe contract to `IntentDetector.detect()`.

## Data Flow

```
Intent (3.7) + ConversationContext (2.8)
      ↓
ContextAnalyzer.analyze(intent, context)
      ↓
prompt construction (intent.category + recent_turns + active_persona_name)
      ↓
LanguageModelClient.generate(prompt, timeout_seconds)   (shared with 3.7)
      ↓ (success)                                  ↓ (failure)
response parsed into ContextAnalysis          ContextAnalysis(neutral defaults)
      ↓
Sprint 3.9's Memory Retrieval Engine (query text = primary_topic)
Sprint 3.12's PersonaManager.select(suggested_persona, CONTEXT_DETECTION)
```

## Implementation Tasks

1. `decision/context_analyzer.py` — `SentimentHint`, `ContextAnalysis`, `ContextAnalyzer(ManagedModule)`.
2. Unit tests against a fake `LanguageModelClient`, covering topic/entity extraction, `suggested_persona` correctness against clearly-technical vs. clearly-casual fixtures, and the fail-safe degrade path.

## Architecture Notes

`ContextAnalyzer` depends on `Intent` (3.7's output) as an input, making the pipeline ordering explicit in code, not just in this Sprint Book — `analyze()`'s signature literally cannot be called before `detect()` has produced something. It has no dependency on `MemoryStore` or any Sprint 3.1–3.6 module — memory-informed context is Sprint 3.9's job, kept as the next distinct pipeline stage rather than folded in here (this is precisely the boundary this Sprint Book's rationale draws from Part 2's own diagram — see `sprint_book/INDEX.md`'s Level 3 breakdown note for the full reasoning).

## Integration Considerations

- No live caller exists yet — wired into the real turn-processing path by Sprint 3.12, immediately after `IntentDetector.detect()`.
- Sprint 3.13 hardens the specific fallback: if `ContextAnalyzer` is unavailable or fails, `PersonaManager` falls back to Sprint 2.11's `detect_context_heuristic()` rather than defaulting `suggested_persona` to `None` and losing context-based switching entirely.
- `primary_topic` becomes Sprint 3.9's `MemoryRetrievalEngine.retrieve()` query text — the two sprints share this one string as their integration point, nothing more.

## Potential Risks

- **Entity extraction accuracy depends entirely on prompt quality and the underlying model**, same class of risk as Sprint 3.7 — mitigated the same way (fail-safe default, downstream tolerance of empty/neutral output).
- **`suggested_persona` disagreeing with the Level 2 heuristic** on the same input is an expected, not exceptional, outcome during the transition — Sprint 3.12 makes this sprint authoritative, not merely advisory, per its own Objectives; any real-world mismatches surfaced during Sprint 3.14's verification should be treated as prompt-tuning feedback, not a sign either implementation is "wrong."
- **`sentiment_hint` scope creep toward the Emotion Engine (Level 5)** is an explicit, named risk — this field must stay a conversational-tone hint only; any temptation to make it richer or more clinically-framed belongs to Phase 5.1, not here.

## Acceptance Criteria

- `analyze()` correctly extracts `primary_topic`/`mentioned_entities` for a fixed labeled test set (fake client).
- `suggested_persona` matches the expected persona for clearly-technical vs. clearly-casual fixture transcripts.
- A simulated `LlmError`/timeout/unparseable response degrades to the documented neutral-default `ContextAnalysis`, logged, never raised.
- No value in `SentimentHint` or any field name in `ContextAnalysis` uses clinical/diagnostic language.

## Testing Checklist

- [ ] Unit: topic/entity extraction against a fixed labeled fixture set.
- [ ] Unit: `suggested_persona` correctness (technical vs. casual fixtures).
- [ ] Unit: `references_past_memory` detection against fixtures that do/don't reference prior conversation.
- [ ] Unit: `LlmError`/timeout/malformed-response degrade path.
- [ ] Unit: an empty transcript/context does not raise.

## Documentation Checklist

- [ ] `decision/context_analyzer.py` docstring: explicit statement that `suggested_persona` is the real replacement for Sprint 2.11's heuristic, and that `sentiment_hint` is deliberately non-clinical.
- [ ] `docs/STATUS.md` — Phase 3.3 (Decision Engine) row remains `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium-High.

## Estimated Development Time

1.5–2 days.

## Next Sprint

3.9 — Memory Retrieval Engine.

## Future Considerations

- Sprint 5.2 (Emotion Inference) is the natural future consumer of a richer emotional signal — `sentiment_hint` should stay coarse until that Level exists, not be expanded speculatively now.
- If `suggested_persona` and the Level 2 heuristic disagree often in real use (Sprint 3.14+), that is prompt-tuning feedback, not a signal to keep the heuristic as a permanent second opinion.
