# Sprint 3.5 — Confidence Scoring Engine

## Sprint ID

3.5

## Sprint Name

Confidence Scoring Engine

## Purpose

Begin Phase 3.2 (Dynamic Memory) by implementing the Dynamic Memory Formula in full, per [02_System_Architecture.md](../02_System_Architecture.md): *"Every memory receives a confidence score. Factors: Frequency, Recency, Importance, Category, Emotional significance."* Score bands: 0–29 Temporary, 30–49 Short-term, 50–69 Monthly review, 70–89 Long-term, 90–100 Permanent. Also implements the User Override Rule: *"When the user explicitly states 'Remember this' / 'Never forget this' / 'This is important', the memory immediately receives maximum confidence. Automatic deletion is disabled."*

## Engineering Rationale

Two of the formula's five factors are already fully backed by real data from Sprints 3.1–3.4: **Frequency** (`MemoryRecord.access_count`, incremented by every `MemoryStore.get_by_id()` call) and **Recency** (`last_accessed_at`). **Category** is backed by the existing free-text `category` field, scored via a small configurable weight table rather than hardcoded logic (Configuration Management rule — "no hardcoded... thresholds"). The remaining two factors have no real signal source yet at this point in the roadmap:

- **Importance** has one legitimate, already-available signal: the User Override Rule itself (an explicit user statement is the strongest possible importance signal there is) — handled as a formula short-circuit, not a weighted input, exactly as Part 2 specifies ("immediately receives maximum confidence," not "receives a boosted score").
- **Emotional significance** has no real source until Level 5's Emotion Engine (Phase 5.1) exists. Rather than fabricate an emotional signal from crude keyword-spotting (which this project's established culture explicitly avoids — see `Persona.compose_reply()`'s docstring: "never a fabricated 'smart' response that could be mistaken for real reasoning"), this sprint applies a fixed **neutral default weight** for this factor and documents it plainly as a placeholder input, not a real emotional assessment. This is recorded here as a genuine, load-bearing engineering decision rather than a silent assumption, and is the first concrete integration point for Sprint 5.2 (Emotion Inference) once that Level exists.

`ConfidenceScorer` is a pure, stateless-per-call class — the same design choice as `ContextManager` (2.8) and `PersonaScopedMemory` (3.2) — because scoring is a deterministic function of a record's fields plus configuration, with no state of its own to manage.

## Objectives

- A `ConfidenceScorer.score(record) -> float` implementing the five-factor Dynamic Memory Formula, fully config-driven (no magic numbers).
- A `ConfidenceScorer.band(score) -> ConfidenceBand` mapping a score to Part 2's five named bands exactly.
- User Override detection and application: an explicit trigger phrase forces `confidence_score = 100.0`, `user_override = True`, and `score()` becomes a no-op (short-circuits) for any record with `user_override = True` thereafter.

## Dependencies

3.2 (Shared Memory & Persona Memory), 3.3 (Event Memory), 3.4 (Short-Term Memory)

## Files to Create

- `memory/confidence_scorer.py` — `ConfidenceBand` (Enum), `ConfidenceScorer`.
- `tests/unit/memory/test_confidence_scorer.py`

## Files to Modify

- `config/schema.py` — extend `MemoryConfig`: `frequency_weight: float = 0.25`, `recency_weight: float = 0.25`, `recency_half_life_days: float = 14.0`, `importance_weight: float = 0.2`, `category_weight: float = 0.15`, `category_importance: dict[str, float] = {"project": 0.9, "goal": 0.9, "routine": 0.6, "preference": 0.7}` (default weights per known category examples from Part 2's Shared Memory list; unrecognized categories fall back to a configurable `category_default_weight: float = 0.5`), `emotional_weight: float = 0.15` (applied against a fixed neutral placeholder value until Sprint 5.2 exists), `override_trigger_phrases: list[str] = ["remember this", "never forget this", "this is important"]`. Add validation in `AppConfig._validate_paths()` (or a new `_validate_memory()`, following the existing per-section validator pattern) confirming the five weights sum to `1.0` within a small tolerance.
- `config/defaults.yaml` — updated to match.

## Expected Classes

- `ConfidenceBand` (Enum) — `TEMPORARY`, `SHORT_TERM`, `MONTHLY_REVIEW`, `LONG_TERM`, `PERMANENT`, in ascending score order, matching Part 2's five bands exactly.
- `ConfidenceScorer` — constructor DI: `(memory_config: MemoryConfig)`.

## Expected Interfaces

None new — a plain class, no `ManagedModule` (same reasoning as `ContextManager`, `ConfidenceScorer` owns no resource of its own).

## Expected Functions

- `ConfidenceScorer.score(record: MemoryRecord) -> float` — returns `100.0` immediately, unchanged, if `record.user_override` is `True` (short-circuit, per the User Override Rule's "automatic deletion is disabled" implying the score itself must not silently drift back down either). Otherwise computes the weighted sum of frequency (diminishing-returns curve over `access_count`), recency (exponential decay over `last_accessed_at` using `recency_half_life_days`), category (`category_importance` lookup, falling back to `category_default_weight`), and the fixed emotional-significance placeholder — clamped to `[0.0, 100.0]`.
- `ConfidenceScorer.band(score: float) -> ConfidenceBand` — pure range lookup against Part 2's five bands.
- `ConfidenceScorer.detect_override_phrase(transcript: str) -> bool` — case-insensitive substring match against `override_trigger_phrases`, identical technique to `PersonaManager.detect_explicit_selection()` (Sprint 2.11).
- `ConfidenceScorer.apply_user_override(record: MemoryRecord) -> MemoryRecord` — returns a new record (dataclasses are otherwise treated as read-mostly in this codebase's convention) with `confidence_score=100.0`, `user_override=True`; the caller (Sprint 3.6, or Sprint 3.12's later integration) is responsible for persisting it via `MemoryStore.update_confidence()`.

## Data Flow

```
MemoryRecord (from 3.1–3.4)
      ↓
ConfidenceScorer.score(record)
      ↓ (user_override already True?)  → 100.0, unchanged
      ↓ (else) weighted formula over access_count, last_accessed_at, category, emotional placeholder
      ↓
float score → ConfidenceScorer.band(score) → ConfidenceBand
      ↓
MemoryStore.update_confidence(record.id, score)   (3.1)
      ↓
MemoryLifecycleManager.run_cleanup_pass() / run_monthly_review()   (3.6, consumes band)

transcript
      ↓
ConfidenceScorer.detect_override_phrase(transcript) → bool
      ↓ (True)
ConfidenceScorer.apply_user_override(record) → MemoryRecord(confidence_score=100.0, user_override=True)
```

## Implementation Tasks

1. `config/schema.py` — `MemoryConfig` weight/threshold fields, `override_trigger_phrases`; weight-sum validation; `config/defaults.yaml` updated.
2. `memory/confidence_scorer.py` — `ConfidenceBand`, `ConfidenceScorer`, all four functions above.
3. Unit tests for each formula factor in isolation (holding the others constant), the override short-circuit, and band boundaries.

## Architecture Notes

`ConfidenceScorer` depends only on `MemoryRecord`'s fields and `MemoryConfig` — it has no dependency on `MemoryStore` itself (it scores a record it's handed, it does not fetch one), keeping it trivially unit-testable without any database or Chroma fixture at all, unlike every other Sprint 3.1–3.4 test so far. This is a deliberate design choice: the *pure function* stays pure; persistence is the caller's job.

## Integration Considerations

- No live caller persists scores yet — Sprint 3.6's `MemoryLifecycleManager` is the first real caller of `score()`/`band()`/`apply_user_override()` at scale; Sprint 3.12 wires `detect_override_phrase()` into the live turn-processing path.
- Sprint 3.9's Memory Retrieval Engine reads `confidence_score` (already persisted by whatever last called `update_confidence()`) to weight ranking — it does not call `ConfidenceScorer` itself, avoiding a runtime rescoring cost on every retrieval.
- Event Memory (3.3) records are never passed through `score()` in practice (`is_permanent=True` records are excluded upstream, by Sprint 3.6's own filtering) — `score()` itself has no special-case for `is_permanent`, since that guarantee belongs entirely to Sprint 3.6's caller-side filtering, not this pure function (Single Responsibility: permanence is a lifecycle concern, not a scoring concern).

## Potential Risks

- **The emotional-significance placeholder is a fixed neutral value, not a real signal** — explicitly documented in both code and this file so nobody mistakes current scores as emotionally informed before Sprint 5.2 exists. Flagged as the clearest single integration point for that future sprint.
- **Weight tuning is a guess** (0.25/0.25/0.2/0.15/0.15) with no real usage data — config-driven specifically so it's trivially adjustable without a code change once Sprint 3.14's real-world verification or later usage reveals better values.
- **`category_importance` is a static dict**, not learned — acceptable for Level 3; Level 5's Learning Engine (Phase 5.4) is the natural future home for adapting these weights from observed behavior, not this sprint.

## Acceptance Criteria

- Higher `access_count`, all else equal, produces a higher score (frequency factor verified in isolation).
- More recent `last_accessed_at`, all else equal, produces a higher score (recency factor verified in isolation).
- A record with `user_override=True` always scores exactly `100.0`, regardless of its other fields.
- `detect_override_phrase()` matches all three configured default phrases case-insensitively and does not match unrelated text.
- `band()` correctly maps scores at each of the five bands' boundaries (0, 29/30, 49/50, 69/70, 89/90, 100).
- The five configured weights sum to `1.0`; `AppConfig` loading rejects a configuration where they don't.

## Testing Checklist

- [ ] Unit: frequency factor in isolation.
- [ ] Unit: recency factor in isolation (including the half-life decay curve at a few known points).
- [ ] Unit: category factor (known category, unknown category fallback).
- [ ] Unit: `user_override=True` short-circuit.
- [ ] Unit: `detect_override_phrase()` match/no-match, case-insensitivity.
- [ ] Unit: `apply_user_override()` returns the correct new record without mutating the input in place.
- [ ] Unit: `band()` boundary values.
- [ ] Unit: `AppConfig` weight-sum validation (accepts 1.0, rejects e.g. 0.9 or 1.1).

## Documentation Checklist

- [ ] `memory/confidence_scorer.py` docstring: full formula explanation, explicit "emotional significance is a placeholder until Sprint 5.2" statement, and the User Override short-circuit's exact behavior.
- [ ] `docs/STATUS.md` — Phase 3.2 (Dynamic Memory) row updated to `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium-High — the formula itself is straightforward arithmetic, but getting the recency decay curve, category fallback, and override short-circuit each independently correct and independently tested is real surface area.

## Estimated Development Time

1.5–2 days.

## Next Sprint

3.6 — Memory Lifecycle Manager.

## Future Considerations

- Sprint 5.2 (Emotion Inference & Contextual Adaptation) should replace the fixed emotional-significance placeholder with a real signal — the exact function signature (`score(record)`) should not need to change, only what feeds the emotional term internally, if this sprint's separation is respected.
- Sprint 5.4 (Pattern Recognition / Preference Learning) is a plausible future home for learned, per-user category weights instead of the static default table — not built now.
