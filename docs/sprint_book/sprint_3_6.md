# Sprint 3.6 — Memory Lifecycle Manager

## Sprint ID

3.6

## Sprint Name

Memory Lifecycle Manager

## Purpose

Complete Phase 3.2 (Dynamic Memory) by turning Sprint 3.5's confidence bands into real lifecycle behavior, per [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md)'s Phase 3.2 tasks: *"Confidence Score [3.5]. User Override [3.5 + this sprint's enforcement]. Automatic cleanup. Monthly review."* Closes Phase 3.2's acceptance criteria: *"Scores update correctly. Memory lifecycle functions."*

## Engineering Rationale

Part 2's five confidence bands imply three distinct lifecycle treatments, not one: **0–29 (Temporary)** records past a grace period are deleted; **30–89 (Short-term through Long-term)** records are simply rescored on each pass and left alone; **50–69 (Monthly review)** is explicitly a *human check-in* band, not an automatic action — the name itself says "review," not "delete" or "promote." This sprint therefore builds two genuinely different operations, `run_cleanup_pass()` (automatic, band-driven deletion) and `run_monthly_review()` (surfacing a report for a human, no automatic mutation), rather than one combined "maintenance" method — a direct application of Single Responsibility to two operations that must never be allowed to silently merge (an automatic cleanup pass accidentally deleting Monthly-review-band memories would violate the User Override Rule's spirit even for records that were never explicitly overridden).

Both operations **must** structurally exclude `is_permanent=True` (Event Memory, Sprint 3.3) and `user_override=True` (Sprint 3.5) records — not as a filter condition that could be forgotten in a future edit, but as a guard checked first, before any record is even considered a cleanup candidate, with a dedicated defensive test proving no code path can reach a deletion call for either flag.

This sprint also resolves — honestly, not by inventing a scheduler — a real tension `docs/backlog/technical_debt.md` item 11 already surfaced for `ConversationSessionStore.purge_older_than()`: [03_Engineering_Standards.md](../03_Engineering_Standards.md)'s Technology Stack lists APScheduler's responsibilities as including "periodic maintenance," but APScheduler itself doesn't arrive until Level 4 (Phase 4.3, Sprint 4.8+). Following the same "Core owns *how*, a future timer owns *when*" pattern established since `CoreManager.check_resources()` (Sprint 1.5), this sprint builds `run_cleanup_pass()`/`run_monthly_review()` as directly callable methods with no periodic trigger of their own — invoked once at startup (via Sprint 3.12's integration) and otherwise manually callable, with a real recurring cadence deferred to Sprint 4.9 (Reminder Engine) or wherever APScheduler is first wired in, exactly like `purge_older_than()`'s own still-open item.

## Objectives

- `run_cleanup_pass()` — rescoring + deletion of records that fall in the Temporary band past a grace period, excluding permanent/override records unconditionally.
- `run_monthly_review()` — a read-only report of Monthly-review-band records, for human confirmation, with no automatic mutation.
- `apply_user_override(record_id)` — the real, persisted counterpart to Sprint 3.5's pure `apply_user_override()`, wired to `MemoryStore.update_confidence()`.

## Dependencies

3.5 (Confidence Scoring Engine)

## Files to Create

- `memory/lifecycle_manager.py` — `MemoryLifecycleManager(ManagedModule)`, `CleanupReport` (dataclass), `ReviewReport` (dataclass).
- `tests/unit/memory/test_lifecycle_manager.py`

## Files to Modify

- `config/schema.py` — extend `MemoryConfig`: `cleanup_grace_period_days: int = 7` (a Temporary-band record must be both scored Temporary *and* untouched for this many days before it's a deletion candidate — protects a genuinely new record from being deleted before it's had any chance to be reinforced), `monthly_review_min_band_days: int = 30` (a record must have sat in the Monthly-review band this long before appearing in a review report, avoiding a report flooded with records that only just crossed the threshold).

## Expected Classes

- `CleanupReport` (dataclass) — `records_rescored: int`, `records_deleted: int`, `deleted_record_ids: list[str]`, `errors: list[str]` (per-record failures collected, not raised — see Architecture Notes).
- `ReviewReport` (dataclass) — `records: list[MemoryRecord]`, `generated_at: datetime`.
- `MemoryLifecycleManager(ManagedModule)` — constructor DI: `(memory_store: MemoryStore, confidence_scorer: ConfidenceScorer, memory_config: MemoryConfig)`.

## Expected Interfaces

- `ManagedModule` (reused) — `start()` logs readiness (owns no external resource of its own beyond its injected dependencies, which are already started by the time `MemoryLifecycleManager` is registered — ordering enforced by `CoreManager`'s registration sequence, Sprint 1.5); `stop()` is a no-op beyond logging; `health_check()` confirms `memory_store.health_check()` still passes (delegated, not duplicated).

## Expected Functions

- `MemoryLifecycleManager.run_cleanup_pass() -> CleanupReport` — for every non-permanent, non-override record: rescore via `confidence_scorer.score()`, persist via `memory_store.update_confidence()`; if the resulting band is `TEMPORARY` **and** the record is older than `cleanup_grace_period_days`, delete it via `memory_store.delete()`. A single record's failure (e.g. a corrupt row) is caught, logged, and appended to `CleanupReport.errors` — the pass continues over the remaining records rather than aborting (Fail Gracefully applied at the per-record level, not just the per-call level).
- `MemoryLifecycleManager.run_monthly_review() -> ReviewReport` — a pure read query for records currently in the `MONTHLY_REVIEW` band that have been in that band for at least `monthly_review_min_band_days`; performs no writes at all.
- `MemoryLifecycleManager.apply_user_override(record_id: str) -> bool` — fetches the record, applies `confidence_scorer.apply_user_override()`, persists via `memory_store.update_confidence(record_id, 100.0, user_override=True)`; returns `False` (logged) if the record doesn't exist rather than raising.

## Data Flow

```
MemoryStore.recent(memory_type, ...) for each non-permanent MemoryType   (3.1)
      ↓
[record for record if not record.is_permanent and not record.user_override]
      ↓
ConfidenceScorer.score(record)   (3.5)
      ↓
MemoryStore.update_confidence(record.id, new_score)   (3.1)
      ↓ (band == TEMPORARY and age > grace period)
MemoryStore.delete(record.id)   (3.1)
      ↓
CleanupReport(records_rescored, records_deleted, deleted_record_ids, errors)

transcript
      ↓
ConfidenceScorer.detect_override_phrase(transcript)   (3.5, called by 3.12's later integration)
      ↓ (True)
MemoryLifecycleManager.apply_user_override(record_id)
```

## Implementation Tasks

1. `config/schema.py` — `MemoryConfig` additions; `config/defaults.yaml` updated.
2. `memory/lifecycle_manager.py` — `CleanupReport`, `ReviewReport`, `MemoryLifecycleManager(ManagedModule)`.
3. Unit tests, including the defensive is_permanent/user_override exclusion test and the per-record error-isolation test.

## Architecture Notes

This sprint closes **Phase 3.2 (Dynamic Memory)**. Combined with Sprint 3.5, the full Dynamic Memory Formula is now real: scores compute correctly (3.5) and drive real lifecycle outcomes (3.6) — satisfying Phase 3.2's "Scores update correctly. Memory lifecycle functions." in full.

Per-record error isolation in `run_cleanup_pass()` mirrors `CoreManager.restart_module()`'s established pattern (Sprint 1.5): one failure must not abort work on everything else. `run_monthly_review()`'s complete absence of any write path is itself a Human First Rule application — "monthly review" band memories exist in a state where the system has decided it isn't confident enough to act unilaterally, so it doesn't.

## Integration Considerations

- **No periodic caller exists yet** (see Engineering Rationale) — `run_cleanup_pass()`/`run_monthly_review()` are invoked once at Sprint 3.12's integration-time startup sequence and are otherwise manually callable; a real recurring cadence is explicitly deferred, tracked the same way as `backlog/technical_debt.md` item 11.
- `run_monthly_review()`'s `ReviewReport` has no UI surface in this Level — Level 3's goal list does not include new UI work, and none of Level 1's UI sprints (Status Panel, Settings Window, Debug Console) anticipated a memory-review surface. Exposing it is flagged as a Future Consideration, not built here.
- Sprint 3.12 wires `apply_user_override()` to the real turn-processing path, triggered by `ConfidenceScorer.detect_override_phrase()` matching a live transcript.

## Potential Risks

- **No live caller for the periodic cadence** — same class of gap as `backlog/technical_debt.md` item 11; recorded explicitly here rather than silently assumed solved, so it is tracked identically once this sprint ships.
- **`cleanup_grace_period_days` interacting with `recency_half_life_days`** (Sprint 3.5) could, for badly-tuned config values, delete a record before it's had a realistic chance to be reinforced by repeat access — mitigated by keeping both values config-driven and independently tunable, not by hardcoding a "safe" relationship between them now with no real usage data to justify one.
- **`run_monthly_review()` producing no action at all could mean review reports are silently generated and never seen** until a UI surface exists — explicitly flagged rather than treated as solved.

## Acceptance Criteria

- `run_cleanup_pass()` never deletes or rescoring-mutates a record with `is_permanent=True` or `user_override=True`, verified defensively (a record deliberately constructed with both flags set to `False`-defeating values cannot reach the deletion branch).
- A Temporary-band record younger than `cleanup_grace_period_days` survives a cleanup pass; the same record, once older, is deleted on the next pass.
- `run_monthly_review()` performs zero writes (verified via a store/mock call-count assertion) and returns only records that are both Monthly-review-band and old enough in that band.
- `apply_user_override()` persists `confidence_score=100.0`, `user_override=True`, verified by a subsequent `MemoryStore.get_by_id()` read.
- A single record's scoring failure during `run_cleanup_pass()` is caught, logged, and recorded in `CleanupReport.errors` without aborting the rest of the pass.

## Testing Checklist

- [ ] Unit: `is_permanent=True` records are never touched by `run_cleanup_pass()` (defensive).
- [ ] Unit: `user_override=True` records are never touched by `run_cleanup_pass()` (defensive).
- [ ] Unit: grace-period boundary (just-under, just-over) for Temporary-band deletion.
- [ ] Unit: `run_monthly_review()` performs no writes; boundary correctness for `monthly_review_min_band_days`.
- [ ] Unit: `apply_user_override()` persists correctly; returns `False` for an unknown `record_id`.
- [ ] Unit: a single record's scoring exception during `run_cleanup_pass()` is isolated (rest of the pass completes, error recorded).

## Documentation Checklist

- [ ] `memory/lifecycle_manager.py` docstring: full lifecycle-band-to-action mapping table, explicit "no periodic caller yet" statement cross-referencing `backlog/technical_debt.md`.
- [ ] `docs/STATUS.md` — Phase 3.2 (Dynamic Memory) marked **Complete**.
- [ ] `docs/backlog/technical_debt.md` — new item recording the deferred periodic-cadence caller for `run_cleanup_pass()`/`run_monthly_review()`, alongside the existing item 11 for `purge_older_than()` (both belong to the same future Scheduler-wiring resolution).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md). This sprint also closes Phase 3.2 (Dynamic Memory).

## Estimated Complexity

Medium.

## Estimated Development Time

1–1.5 days.

## Next Sprint

3.7 — Intent Detection.

## Future Considerations

- A UI surface for `run_monthly_review()`'s reports (Status Panel or a new Settings tab) — no Level 3 UI sprint exists for this; revisit once a concrete need or user request arrives.
- A real periodic caller once Sprint 4.9 (Reminder Engine) or APScheduler more broadly exists — do not build a timer mechanism speculatively before then, consistent with `backlog/technical_debt.md` item 11's own resolution guidance.

---

## Sprint Completion Report (2026-07-18)

### Summary

Implemented `memory/lifecycle_manager.py`'s `CleanupReport`/`ReviewReport`/`MemoryLifecycleManager` and the `MemoryConfig` additions this sprint's spec named. This sprint closes **Phase 3.2 (Dynamic Memory)** and, with it, all of Level 3's individual "Memory Engine"/"Dynamic Memory" component sprints (3.1–3.6). One real gap against Sprint 3.1's shipped `MemoryRecord` was found and fixed at the root before implementing — see `sprint_3_1.md`'s Post-Sprint Fix (`band_entered_at`).

### Files Created

- `memory/lifecycle_manager.py` — `CleanupReport`, `ReviewReport`, `MemoryLifecycleManager` (`run_cleanup_pass`, `run_monthly_review`, `apply_user_override`, plus the `ManagedModule` trio).
- `tests/unit/memory/test_lifecycle_manager.py` — 16 tests.

### Files Modified

- `config/schema.py` — `MemoryConfig.cleanup_grace_period_days: int = 7`, `monthly_review_min_band_days: int = 30`; validation added to `_validate_memory()` (both positive).
- `config/defaults.yaml` — `memory:` section extended to match.
- `memory/models.py`, `memory/memory_store.py`, `tests/unit/memory/test_memory_store.py` — the `band_entered_at` addition, a prerequisite discovered while implementing this sprint (counted in Sprint 3.1's Post-Sprint Fix, not duplicated here).
- `docs/STATUS.md` — Phase 3.2 (Dynamic Memory) marked **Complete**.
- `docs/backlog/technical_debt.md` — new item recording the deferred periodic-cadence caller, alongside item 11.

### Tests Added

16 tests in `test_lifecycle_manager.py`, all against a real `MemoryStore` + real `ConfidenceScorer`: the defensive `is_permanent`/`user_override` exclusion tests for both `run_cleanup_pass()` and `run_monthly_review()`; rescoring count reporting; the grace-period boundary (just-under survives, just-over is deleted); `band_entered_at` advancing only on a genuine band transition and staying put otherwise; per-record error isolation via a small `_ScoreRaisingConfidenceScorer` double (one record fails, the rest of the pass still completes and the failure is recorded); `run_monthly_review()`'s zero-write contract and its own band/age boundary correctness; `apply_user_override()`'s persistence and unknown-id handling; and `health_check()` delegation. 405/405 tests passing project-wide, `ruff check .` clean.

### Documentation Updated

This file (Sprint Completion Report). `memory/lifecycle_manager.py`'s module docstring (full band-to-action table). `docs/STATUS.md` — Phase 3.2 marked Complete. `docs/backlog/technical_debt.md` — new item 15.

### Acceptance Criteria Checklist

- ✔ `run_cleanup_pass()` never deletes or rescoring-mutates a record with `is_permanent=True` or `user_override=True`, verified defensively with records deliberately constructed to score in the Temporary band (`test_run_cleanup_pass_never_touches_is_permanent_records`, `test_run_cleanup_pass_never_touches_user_override_records`).
- ✔ A Temporary-band record younger than `cleanup_grace_period_days` survives a cleanup pass; the same record, once older, is deleted on the next pass (`test_temporary_record_younger_than_grace_period_survives`, `test_temporary_record_older_than_grace_period_is_deleted`).
- ✔ `run_monthly_review()` performs zero writes and returns only records that are both Monthly-review-band and old enough in that band (`test_run_monthly_review_performs_no_writes` and the three boundary/scope tests around it).
- ✔ `apply_user_override()` persists `confidence_score=100.0`, `user_override=True`, verified by a subsequent `get_by_id()` read.
- ✔ A single record's scoring failure during `run_cleanup_pass()` is caught, logged, and recorded in `CleanupReport.errors` without aborting the rest of the pass.

### Engineering Decisions

- **`band_entered_at` addition** — see `sprint_3_1.md`'s own Post-Sprint Fix for the full reasoning; this sprint is where the gap was found.
- **Both `run_cleanup_pass()` and `run_monthly_review()` iterate all five `MemoryType`s**, not a hardcoded "non-Event" subset — the spec's own Data Flow says "for each non-permanent MemoryType," but permanence is a per-*record* flag (`is_permanent`), not a per-*type* guarantee enforceable at the `MemoryType` level itself. Iterating every type and relying on the `is_permanent`/`user_override` guard to skip Event Memory records (which always carry `is_permanent=True`, per `EventMemory.record_milestone()`) is more defensive than assuming EVENT is special-cased by type — it doesn't hardcode an assumption about which types happen to be permanent today.
- **`update_confidence()`'s two-branch `if/else` generalized into a dynamic `SET`-clause builder** — adding `band_entered_at` as a third independently-optional field would have meant a third `if/elif` branch (four total combinations); the generalized version scales to any future optional field without further branching.

### Remaining Risks

All three risks named in this sprint's own Potential Risks remain open, unchanged by implementation: no periodic caller for either method (tracked below); `cleanup_grace_period_days`/`recency_half_life_days` interaction is untuned; `run_monthly_review()` reports have no UI surface yet.

### Technical Debt

- **New item 15** in `docs/backlog/technical_debt.md`: `run_cleanup_pass()`/`run_monthly_review()` have no periodic caller, mirroring item 11's still-open gap for `ConversationSessionStore.purge_older_than()` — both deferred to the same future Scheduler resolution (Sprint 4.9+), per this sprint's own Documentation Checklist instruction to record it alongside item 11 rather than as an isolated new gap.

### Recommendations

- **For Sprint 3.7 (Intent Detection)**: this is the first Decision Engine sprint and the first to touch Ollama — no memory-layer dependency, but worth a deliberate check (per the pattern established across 3.1–3.6) of whether its own spec's assumptions about `ConversationContext`/`Intent` match what Sprint 2.8 actually shipped, before implementing.
- **For whoever resolves `backlog/technical_debt.md` item 15/11 together (Sprint 4.9+)**: both `MemoryLifecycleManager`'s passes and `ConversationSessionStore.purge_older_than()` are simple, parameterless, idempotent methods — a single generic periodic-task registration mechanism could plausibly serve all of them, rather than three ad hoc timers. Worth deciding at that point, not now.

**Phase 3.2 (Dynamic Memory) is now `Complete`** — both sprints (3.5, 3.6) done; the full Dynamic Memory Formula computes real scores and drives real lifecycle outcomes. **This also closes all of Level 3's Memory Engine/Dynamic Memory component sprints (3.1–3.6).** **Sprint 3.7 (Intent Detection) is next**, beginning Phase 3.3 (Decision Engine).
