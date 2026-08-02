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

## Sprint Completion Report (2026-08-02)

Implemented as specified, authorized directly ("Continue with the Sprint 5.1") right after the Level 5 Part A Sprint Book was written this same session — no separate Pass-1 round trip needed since the spec was already complete/unmodified, the same direct-proceed precedent Sprint 4.14's own Completion Report established.

**Note found during implementation, not caused by this sprint**: between this Sprint Book being written and this sprint's own implementation, the repository's `docs/sprint_book/` directory was reorganized into per-level subdirectories (this file now lives at `docs/sprint_book/sprint_5/sprint_5_1.md`, not the flat `docs/sprint_book/sprint_5_1.md` path this Sprint Book was originally written against) and several previously-uncommitted pieces of this session's own work (0.4.2, 0.4.3, the internet provider-fallback refactor) were committed directly to `main` by the repository's git author (`newbie-cmyk`), outside this conversation. Confirmed via `git show <commit> --stat` that this file's own content was carried over unchanged (a straight add, not a rewrite) — no content was lost or altered. Flagged to the user rather than silently worked around.

### Summary

`emotion/models.py`/`emotion/detection_engine.py` deliver exactly the spec's own Expected Classes/Functions: `EmotionLabel` (nine named states + `UNKNOWN`), `EmotionSignals`, `EmotionEstimate`, and `EmotionDetectionEngine` (`collect_signals()`/`estimate()`, never raising for any input). `EmotionConfig` was added to `config/schema.py` with a full `_validate_emotion()` pass, wired into `AppConfig`.

One real gap found and closed beyond the sprint file's own literal Files to Modify list: `config/loader.py`'s `_SECTION_SCHEMAS` dict is that file's own documented "single source of truth for every AppConfig section... adding a future section here is now the only place needed for both load paths to pick it up" (a comment written specifically because Sprint 1.7 once shipped a new config section that silently failed to load from YAML/env for exactly this reason). `EmotionConfig` was added there too — without it, `emotion:` in `config/defaults.yaml` would have been silently ignored at load time despite validating correctly against the dataclass default. Verified for real, not assumed: loaded the actual `config/defaults.yaml` through `ConfigLoader().load()` and confirmed `config.emotion.lexical_markers` reflects the real YAML content, not just the dataclass default.

`estimate()`'s exact scoring algorithm (how `SentimentHint`, lexical markers, and the two numeric signals combine into a label/confidence pair) was underspecified at the "described behavior, not exact formula" level the sprint file itself operates at — implemented as: `SentimentHint` (STRESSED/FRUSTRATED/TIRED/POSITIVE→HAPPY) as the primary signal when non-NEUTRAL, with lexical-marker agreement as a confidence bonus; when `SentimentHint` is NEUTRAL, matched lexical markers alone select a label (most-frequent match wins; a tie is broken by numeric-signal-supported arousal — fast speech toward STRESSED/FRUSTRATED/EXCITED/CURIOUS, a long pause toward TIRED/CALM/CONFUSED — then, deterministically, by `EmotionLabel` declaration order); a final `min_estimate_confidence` floor discounts any still-low-confidence result to `UNKNOWN`/`0.0`. Five new `EmotionConfig` weight fields (`sentiment_hint_base_confidence`, `lexical_marker_agreement_bonus`, `lexical_only_base_confidence`, `numeric_tie_break_bonus`, plus the spec's own `min_estimate_confidence`) were added beyond the sprint file's own literally-named four fields to make this concrete and config-tunable rather than hardcoded — a within-scope quality addition per this project's own autonomy guardrails ("free to exceed spec on quality within a sprint's own scope").

### Files Created

- `emotion/models.py`
- `emotion/detection_engine.py`
- `tests/unit/emotion/test_detection_engine.py`

Not created: `tests/unit/emotion/__init__.py`, named in the sprint file's own Files to Create — checked first and found no `tests/unit/<subsystem>/` directory anywhere in this codebase actually has an `__init__.py` (pytest doesn't require one for test discovery); the sprint file's own assumption was wrong, corrected here rather than silently followed.

### Files Modified

- `config/schema.py` — new `EmotionConfig` dataclass (`_default_lexical_markers()` factory, nine fields per Engineering Rationale above), `AppConfig.emotion` field, `_validate_emotion()` called from `AppConfig.validate()`.
- `config/defaults.yaml` — new `emotion:` section, field names matching `EmotionConfig` exactly.
- `config/loader.py` — `EmotionConfig` import, `_SECTION_SCHEMAS["emotion"]` entry (see Summary above — a real, necessary addition beyond the sprint file's own stated Files to Modify).
- `tests/unit/config/test_schema.py` — `EmotionConfig` import, four new validation tests, following this file's own existing per-config-section test grouping.

`ui/settings_window.py` was checked and confirmed to need no change: `SettingsWindow.to_config()` builds its candidate via `dataclasses.replace(self._original_config, ...)`, so a whole new, un-widgeted `AppConfig` section (like `emotion`) passes through unchanged automatically — the exact fix `backlog/technical_debt.md` item 14 already put in place for this class of gap.

### Tests Added

- `tests/unit/emotion/test_detection_engine.py` — 25 tests: lifecycle (`start()`/`stop()`/`health_check()`); `collect_signals()` (speaking-rate computation and its two None-producing edge cases, pause computation including the no-prior-turn case, `SentimentHint` passthrough and its `None`-context default, lexical-marker matching, `no_speech_probability` passthrough, never-raises on fully-empty input); `estimate()` (all four `SentimentHint`-mapped labels, sentiment+lexical agreement raising confidence, all five lexical-only-reachable labels, the `UNKNOWN` no-signal fallback, the `min_estimate_confidence` floor forcing `UNKNOWN`, both numeric tie-break directions, never-raises on degenerate input, the estimate always carrying its own signals).
- `tests/unit/config/test_schema.py` — 4 new tests: blank lexical-marker keyword, non-positive `speaking_rate_baseline_wpm`, non-positive `long_pause_threshold_seconds`, an out-of-range confidence field.

### Documentation Updated

- `emotion/models.py`/`emotion/detection_engine.py` module and class docstrings state the "behavioral estimate, never diagnosis" framing explicitly, per this sprint's own Documentation Checklist.
- `config/schema.py`'s `EmotionConfig` docstring documents every field's meaning/default and cross-references `emotion/detection_engine.py`'s own algorithm.
- This Sprint Completion Report.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` updated (see below).

### Acceptance Criteria Checklist

- ✔ `EmotionDetectionEngine.estimate()` never raises for any input, including empty/malformed transcripts and a `None` `ContextAnalysis` — verified directly (`test_never_raises_on_empty_everything`, `test_never_raises_for_degenerate_signals`).
- ✔ All nine named `EmotionLabel` values plus `UNKNOWN` are reachable via realistic fixture inputs in the test suite.
- ✔ No code path in this sprint produces or logs anything resembling a clinical/diagnostic label.
- ✔ `ruff check .` clean (whole repo, not just this sprint's own files); full existing suite still passes.

### Risks

- The scoring algorithm's exact weights (Summary above) are real, disclosed, unvalidated defaults — the same category as every other tuned constant in this codebase; correctable via config without a code change.
- No live caller exists yet (Integration Considerations, by design) — this sprint's own correctness is verified in isolation only; real behavior against live `TranscriptionResult`/`ContextAnalysis` data from an actual conversation is Sprint 5.14's job.

### Technical Debt

None introduced. The `config/loader.py` gap (Summary above) was found and fixed within this sprint, not deferred.

### Recommendations

- When Sprint 5.14 (Presentation Layer Integration) wires a live caller, capture a few real `EmotionEstimate` outputs from actual conversation turns and sanity-check the label distribution feels reasonable before tuning `EmotionConfig`'s weights further — the same "verify against real data before trusting a first-pass default" discipline this project has applied to every other tuned constant once real usage became possible.
- The mismatch between this repository's recent commit messages and their actual diffs (Note above) is worth a direct conversation with whoever is committing this work — a commit log that says more was built than actually was is a real, if non-code, accuracy problem for this project's own established "explainability/honest documentation" discipline.

### Verification

Full suite: 1 pre-existing, confirmed-standalone-passing flake (`test_due_reminder_is_deferred_while_a_session_is_active`, `tests/integration/test_scheduler_integration.py` — the same well-established "passes standalone, times out only under full-suite host-resource load" flake class this project has documented repeatedly; unrelated to this sprint's own `config/`/`emotion/` changes, confirmed by re-running that file standalone: 7/7 passing) + 1151 passing + 2 correctly-skipped opt-in markers = 1154 total. `ruff check .` clean across the whole repository. A real, non-mocked config-load smoke test confirmed `ConfigLoader().load()` genuinely picks up the new `emotion:` YAML section end-to-end, not just the dataclass default.

**No git commit made** — per this project's own "only commit when explicitly asked" rule, changes left in the working tree; the user has not yet been asked whether to commit.

**Sprint 5.2 (Emotional State Manager) is next.**
