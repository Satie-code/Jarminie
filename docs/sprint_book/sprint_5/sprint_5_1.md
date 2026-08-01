# Sprint 5.1 — Emotion Detection Engine

## Sprint ID

5.1

## Sprint Name

Emotion Detection Engine

## Purpose

Give JARMINEI its first real behavioral-signal read on the user — the foundation Part 4's Phase 5.1 ("Stress detection. Fatigue detection. Frustration detection... Behavior adapts appropriately. Never performs medical diagnosis.") names, and the first sprint of Level 5 Part A (Emotional Intelligence & Presentation Layer). Produces, per real conversation turn, a **behavioral estimate** — never a diagnosis — of which of nine named states (Happy, Calm, Stressed, Tired, Excited, Frustrated, Confused, Curious, Focused) best fits the user's current tone, built entirely from signals this codebase already collects for other reasons (Whisper's own timing data, Sprint 3.8's `SentimentHint`, conversation cadence) plus one small new lexical layer. This sprint produces the estimate only — it does not yet decide what to do with it; that is Sprint 5.2's (Emotional State Manager) job.

## Engineering Rationale

**New sprint, first of Level 5 Part A.** Two real design choices made explicitly, not assumed:

1. **Rule-based, not a second LLM call.** `decision/context_analyzer.py`'s `ContextAnalyzer` already produces a `SentimentHint` (`NEUTRAL`/`POSITIVE`/`STRESSED`/`FRUSTRATED`/`TIRED`) via a real Ollama call — that file's own docstring explicitly reserves richer emotional framing for "Phase 5.1," i.e. this sprint. Rather than add a second, competing LLM classification pass (cost, latency — see `backlog/technical_debt.md`'s own 0.4.3 latency-fix precedent — and a second place emotional framing could drift out of sync with the first), this sprint's `EmotionDetectionEngine` treats `SentimentHint` as one input signal among several and combines them with a small, explainable, config-driven rule set. This keeps every emotion label traceable to a concrete signal (the Explainability Rule), which a second opaque LLM call would not improve on for a five-signal decision this simple.
2. **Two-stage split preserved, but collapsed to one sprint.** The original Level 5 roadmap (before this expansion) planned "5.1 Emotion Signal Collection" and "5.2 Emotion Inference & Contextual Adaptation" as separate sprints, mirroring Sprint 3.7/3.8's Intent Detection/Context Analysis split. Here the two stages are kept as separate internal responsibilities (`collect_signals()` vs `estimate()` — see Expected Functions) but shipped as one sprint/one module, because — unlike Intent, which is consumed independently by Context Analysis, Memory Retrieval, *and* Priority Queue — raw `EmotionSignals` has exactly one real consumer (the estimation step within this same class) as of Level 5 Part A. Splitting them into two sprints would add sprint-boundary overhead with no real decoupling benefit; if a second, independent consumer of raw signals ever emerges, they can be split then, the same "don't decouple speculatively" discipline this project applies elsewhere (e.g. `ContextManager`'s own Sprint 2.8 docstring warning against pre-emptively duplicating Level 3's later responsibilities).

**Never a diagnosis, structurally, not just by convention**: `EmotionLabel`/`EmotionEstimate` (Expected Classes) carry no field resembling a clinical severity score, and this sprint's own docstrings and Documentation Checklist require every consumer-facing description to use "behavioral estimate," never "diagnosis," "condition," or "disorder" — matching the Authority System's own "structurally unreachable, not merely undocumented" discipline (`decision/authority.py`'s `approved_emergency_procedures`).

## Objectives

- `emotion/models.py`: `EmotionLabel` enum (nine named states + `UNKNOWN`, the safe-failure default, mirroring `IntentCategory.UNKNOWN`'s own precedent), `EmotionSignals` and `EmotionEstimate` dataclasses.
- `emotion/detection_engine.py`: `EmotionDetectionEngine` (a `ManagedModule`) — `collect_signals()` assembles `EmotionSignals` from a `TranscriptionResult` (Sprint 2.3), a `ContextAnalysis | None` (Sprint 3.8), and a `ConversationContext` (Sprint 2.8); `estimate()` turns `EmotionSignals` into an `EmotionEstimate` via an explainable, weighted rule set.
- `config/schema.py`: new `EmotionConfig` dataclass (lexical marker lists, signal weights, minimum-confidence floor) plus `AppConfig.emotion`/`_validate_emotion()`, following every prior subsystem's identical config pattern.
- Never raises for any input, including a transcript with no words, a `None` `ContextAnalysis` (Decision Engine pipeline failure), or an empty conversation history — degrades to `EmotionLabel.UNKNOWN` at `confidence=0.0`, the same fail-safe contract `IntentDetector.detect()`/`ContextAnalyzer.analyze()` already established.

## Dependencies

2.3 (Speech-to-Text — `TranscriptionResult.duration_ms`/`average_confidence`), 2.8 (Context Manager — `ConversationContext.recent_turns`/timestamps), 3.8 (Context Analysis — `SentimentHint`, reused not duplicated).

## Files to Create

- `emotion/models.py`
- `emotion/detection_engine.py`
- `tests/unit/emotion/test_detection_engine.py`
- `tests/unit/emotion/__init__.py` (matches every other `tests/unit/<subsystem>/` package)

## Files to Modify

- `config/schema.py` — new `EmotionConfig` dataclass, `AppConfig.emotion` field, `_validate_emotion()` called from `AppConfig.validate()`.
- `config/defaults.yaml` — new `emotion:` section with the same field names.

## Expected Classes

- **`EmotionLabel`** (`emotion/models.py`, `Enum`): `HAPPY`, `CALM`, `STRESSED`, `TIRED`, `EXCITED`, `FRUSTRATED`, `CONFUSED`, `CURIOUS`, `FOCUSED`, `UNKNOWN`. Docstring states explicitly: "a behavioral estimate derived from voice/text signals, never a medical or psychological diagnosis."
- **`EmotionSignals`** (dataclass): `speaking_rate_wpm: float | None` (words ÷ (`duration_ms`/60000); `None` when `duration_ms` is zero/unavailable — never a divide-by-zero guess), `pause_before_turn_seconds: float` (gap since the previous turn's `last_activity_at`, from `ConversationContext`), `sentiment_hint: SentimentHint` (passthrough from `ContextAnalysis`, or `SentimentHint.NEUTRAL` when unavailable), `matched_lexical_markers: list[EmotionLabel]` (see below), `no_speech_probability: float` (passthrough from `TranscriptionResult`, a data-quality signal — a high value means the other signals here are less trustworthy, not that the user is emotionally flat), `collected_at: datetime`.
- **`EmotionEstimate`** (dataclass): `label: EmotionLabel`, `confidence: float` (0.0–1.0, this engine's own self-reported certainty — unrelated to Level 3's Dynamic Memory confidence score, the identical distinction `Intent.confidence`'s own docstring already draws), `signals: EmotionSignals` (the estimate always carries its own evidence — Explainability Rule), `estimated_at: datetime`.
- **`EmotionDetectionEngine`** (`ManagedModule`): constructor DI receives only `EmotionConfig` (no LLM client — see Engineering Rationale).

## Expected Interfaces

None new — `EmotionDetectionEngine` implements the existing `ManagedModule` Protocol (`core/module_registry.py`), the same contract every prior engine (`IntentDetector`, `ContextAnalyzer`, `MemoryStore`, ...) already implements. No abstract base is introduced for emotion detection itself: unlike `SpeechToText`/`SearchProvider`, there is exactly one real implementation planned and no near-term second one, so an interface here would be speculative (this project's own established "don't add an interface without two real implementations coming" discipline — contrast with Sprint 5.8's `AvatarRenderer`, which genuinely needs one).

## Expected Functions

- `EmotionDetectionEngine.start() -> None` / `.stop() -> None` / `.health_check() -> bool` — this engine holds no external resource (no model load, no network, no file handle), so `health_check()` always returns `True` once started, the same trivially-healthy shape `ContextManager`/`PersonaManager` already have for stateless-dependency modules.
- `EmotionDetectionEngine.collect_signals(transcription: TranscriptionResult, context_analysis: ContextAnalysis | None, context: ConversationContext) -> EmotionSignals` — pure, deterministic, never raises (a malformed/empty `transcription.text` yields `speaking_rate_wpm=None` and an empty `matched_lexical_markers`, not an exception).
- `EmotionDetectionEngine.estimate(signals: EmotionSignals) -> EmotionEstimate` — never raises. Combines `sentiment_hint` (primary signal, config-weighted highest by default — it is already LLM-derived and contextual, the richest single input available) with `matched_lexical_markers` (a secondary confirming/overriding signal) and the two numeric signals (`speaking_rate_wpm` vs `EmotionConfig.speaking_rate_baseline_wpm`, `pause_before_turn_seconds` vs a configured threshold) as tie-breakers only when `sentiment_hint` is `NEUTRAL` and at least one lexical marker fired. Falls back to `EmotionLabel.UNKNOWN`/`confidence=0.0` whenever no signal points anywhere specific — an honest "no read" is always preferred over a forced guess, matching `ContextAnalyzer`'s own "a lack of signal is not itself grounds to guess" precedent.
- `_match_lexical_markers(text: str, config: EmotionConfig) -> list[EmotionLabel]` (module-private) — case-insensitive substring matching against `EmotionConfig.lexical_markers` (a `dict[str, list[str]]` keyed by `EmotionLabel.value`), the identical technique `PersonaManager.detect_context_heuristic()`/`MemoryConfig.short_term_salience_triggers` already use — no NLU, deliberately crude and named as such.

## Data Flow

```
CommunicationPipeline._handle_turn_complete()  (existing, Sprint 2.12/3.12)
        |
        v
TranscriptionResult (2.3)  +  ContextAnalysis | None (3.8)  +  ConversationContext (2.8)
        |
        v
EmotionDetectionEngine.collect_signals() -> EmotionSignals
        |
        v
EmotionDetectionEngine.estimate() -> EmotionEstimate
        |
        v
   (consumed by Sprint 5.2's EmotionalStateManager.apply_estimate() — not this sprint's job)
```

This sprint does not itself call `EmotionalStateManager` (Sprint 5.2 doesn't exist yet within this sprint's own scope) and does not modify `voice/pipeline.py` — `EmotionDetectionEngine` is built, constructed, and unit-tested standalone this sprint, exactly the same "component before integration" discipline every prior Level's first component sprint used (e.g. Sprint 3.7 Intent Detection shipped with zero live caller until Sprint 3.12).

## Implementation Tasks

1. `emotion/models.py` — `EmotionLabel`, `EmotionSignals`, `EmotionEstimate`.
2. `config/schema.py`/`config/defaults.yaml` — `EmotionConfig` (`lexical_markers: dict[str, list[str]]` with a small, real default set per label; `speaking_rate_baseline_wpm: float = 150.0`; `long_pause_threshold_seconds: float = 4.0`; `min_estimate_confidence: float = 0.35`); `_validate_emotion()`.
3. `emotion/detection_engine.py` — `EmotionDetectionEngine` per Expected Functions above.
4. `tests/unit/emotion/test_detection_engine.py` — signal collection from real `TranscriptionResult`/`ContextAnalysis`/`ConversationContext` fixtures; estimation across all nine labels plus the `UNKNOWN` fallback; explicit test that a `None` `ContextAnalysis` degrades cleanly (Decision Engine pipeline failure path, matching `ContextAnalyzer`'s own precedent).

## Architecture Notes

`EmotionDetectionEngine` is a **pure aggregator-plus-rule-evaluator**, not a reasoning engine of its own — the same distinction `ContextManager`'s docstring draws for itself. It must never grow a second, competing LLM integration; if a future sprint finds the rule set genuinely insufficient, the correct fix is deepening `ContextAnalyzer`'s own `SENTIMENT:` prompt output (Sprint 3.8's file), not adding a parallel classifier here.

`emotion/` already exists as an empty top-level package (`emotion/__init__.py`, added at Sprint 1.1 per `backlog/technical_debt.md` item 2, "for consistency with every other engine's one-module-one-folder pattern") — this sprint is its first real content, not a new folder.

## Integration Considerations

- **No live caller until Sprint 5.14** (Presentation Layer Integration) — `voice/pipeline.py` is not touched this sprint, the identical "implemented and tested in isolation, no live caller yet" shape every Level's first component sprint has (Sprint 3.7, Sprint 4.1, Sprint 4.14 all shipped this way) — not a gap, a deliberate sequencing choice named here rather than silently left implicit.
- Sprint 5.2 (Emotional State Manager) is the real, intended consumer of `EmotionEstimate` — this sprint must not itself maintain any state across turns (no "last three estimates" buffer here); that continuity belongs entirely to 5.2.
- Sprint 5.4 (Persona Behavioral Adaptation) and Sprint 5.5 (Presentation State Engine) both read the *state* (5.2's output), never this sprint's per-turn `EmotionEstimate` directly — keeps a single, well-defined seam between "one turn's read" and "the user's ongoing emotional state."

## Potential Risks

- **Lexical markers are a crude, English-only, culturally-narrow heuristic** — the same honestly-acknowledged limitation `PersonaManager.detect_context_heuristic()`/`MemoryConfig.short_term_salience_triggers` already carry. Documented as a known limitation, not silently presented as more capable than it is.
- **`speaking_rate_wpm` is unreliable for very short utterances** (a two-word reply has no meaningful "rate") — mitigated by `min_estimate_confidence` discounting low-evidence estimates rather than a hard word-count cutoff, since a hard cutoff would just move the same edge case elsewhere.
- **Risk of the estimate being mistaken for a diagnosis by a future sprint or a future engineer** — mitigated structurally (no severity/clinical field exists to misuse) and procedurally (Documentation Checklist requires "behavioral estimate" language everywhere this class is described).

## Acceptance Criteria

- `EmotionDetectionEngine.estimate()` never raises for any input, including empty/malformed transcripts and a `None` `ContextAnalysis`.
- All nine named `EmotionLabel` values plus `UNKNOWN` are reachable via realistic fixture inputs in the test suite.
- No code path in this sprint produces or logs anything resembling a clinical/diagnostic label.
- `ruff check .` clean; full existing suite still passes (this sprint adds files, modifies only `config/`).

## Testing Checklist

- [ ] Unit: `collect_signals()` against real `TranscriptionResult`/`ContextAnalysis`/`ConversationContext` fixtures, including edge cases (zero-duration transcription, empty recent-turns history, `context_analysis=None`).
- [ ] Unit: `estimate()` reaches each of the nine labels plus `UNKNOWN` under a constructed fixture; confidence honestly reflects signal strength (a lexical-marker-only match scores lower than a `SentimentHint` + lexical-marker agreement).
- [ ] Unit: `EmotionConfig` validation (empty lexical marker lists per label rejected; `min_estimate_confidence` bounds checked).
- [ ] Full regression: existing suite unaffected.

## Documentation Checklist

- [ ] `emotion/models.py`/`emotion/detection_engine.py` module docstrings state the "behavioral estimate, never diagnosis" framing explicitly, matching Part 4's own Phase 5.1 acceptance criterion.
- [ ] `config/schema.py`'s `EmotionConfig` docstring explains each field's default and where it came from (mirrors every other Config dataclass's documentation depth).
- [ ] `docs/STATUS.md` — Level 5 Part A row added, `5.1 Emotion Detection Engine` marked in progress once implementation starts (not this sprint file's own job to mark `Complete` — that happens at actual implementation time).

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

Medium.

## Estimated Development Time

1–1.5 days.

## Risks

See Potential Risks above.

## Next Sprint

5.2 — Emotional State Manager.

## Future Considerations

- If a genuinely independent second consumer of raw `EmotionSignals` emerges later, split `collect_signals()`/`estimate()` into two sprints/modules then — not built speculatively now (Engineering Rationale).
- A future richer signal (e.g. real prosody/pitch analysis from the raw audio buffer, not just Whisper's derived timing) is plausible but out of this sprint's scope — `VoiceSessionManager`/`WhisperSpeechToText` would both need new capability first; named here as a pointer, not built.
