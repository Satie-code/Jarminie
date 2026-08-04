# Sprint 5.25 — Error Handling & Recovery Hardening, Part B (Companion Intelligence)

## Sprint ID

5.25

## Sprint Name

Error Handling & Recovery Hardening, Part B (Companion Intelligence)

## Purpose

Apply the Fail Gracefully Rule across six named failure scenarios spanning Sprints 5.17–5.24 — the same discipline every prior hardening sprint (`sprint_2_13.md`, `sprint_3_13.md`, `sprint_4_12.md`, `sprint_4_19.md`, `sprint_5_15.md`) has already applied to its own Level/Part. An honest split, matching those sprints' own established pattern: some scenarios need real production changes, others are confirmed-already-correct via a new regression test proving it.

## Engineering Rationale

New sprint, not present in the original roadmap-granularity plan, added for the identical reason `sprint_5_24.md`/`sprint_5_26.md` were both added — see that file's own Engineering Rationale and `docs/sprint_book/INDEX.md`'s "Level 5 Part B breakdown changes" note. Named "Part B (Companion Intelligence)" rather than plainly, mirroring `sprint_4_19.md`'s own "Part B" suffix precedent (the first hardening sprint of a Level/Part pair goes unsuffixed — `sprint_4_12.md`, `sprint_5_15.md` — only the second gets the explicit disambiguating suffix).

The six scenarios below are chosen the same way every prior hardening sprint chose its own six: real, concrete failure points this Part's own new external-facing surfaces introduce (`win32gui`/`win32process`/`psutil` calls against real, mutable OS state in `UsageTracker`/`WellnessTracker`; three new SQLite-backed stores; a widened proactive-announcement dispatcher; two new periodic `TaskScheduler` jobs) — not a generic, unfocused sweep.

## Dependencies

5.24 (Companion Intelligence Integration — every real caller this sprint's own scenarios need to exist first).

## Scenarios

**(a) `UsageTracker._sample_foreground_window()`'s own `psutil` race (Sprint 5.17's own named risk, now with a real caller via Sprint 5.24's `TaskScheduler` job).** Confirm `psutil.NoSuchProcess`/`psutil.AccessDenied` (a process exiting, or a protected process, between the `hwnd` read and the `psutil.Process()` lookup) both degrade to "no sample recorded this tick," never a raised exception reaching `TaskScheduler`'s own job wrapper. Real production change only if Sprint 5.17's own implementation did not already catch both exception types identically (a genuine possibility flagged in that sprint's own Potential Risks as "if only one is handled").

**(b) `UsageStore`/`PatternStore` SQLite failures.** `UsageStore.list_samples_since()`/`list_sessions_since()` and `PatternStore.list_by_type()`/`list_all()` degrade to `[]` on a real SQLite failure, matching `MemoryStore`/`CalendarStore`'s already-established convention (`CalendarStore.list_due_within()`'s own Sprint 4.19 precedent is the direct template). `record_sample()`/`upsert()` (the write paths) are deliberately left unwrapped at this layer, the same "the caller needs to compose an honest degraded response, wrapping here would risk a false success" reasoning `sprint_4_19.md` already applied to `CalendarStore.save()`.

**(c) `WellnessTracker._sample_idle_seconds()`'s own `win32api` failure.** A real `win32api.GetLastInputInfo()`/`GetTickCount()` failure (a genuine, if rare, Win32 API failure mode) must not crash the `TaskScheduler` job — degrades to treating the tick as "not significantly inactive" (the conservative choice: better to under-reset than to spuriously reset a user's genuine continuous-activity counters on a transient API hiccup), logged once per failure streak and reset on recovery, the same "logged once, not per-tick" discipline `sprint_5_15.md`'s scenario (c) already established for `HolographicSphereWidget`/`SegmentedRingWidget`'s own `_on_tick()`.

**(d) One job's exception never stops another's (confirmed already correct, no new production code).** A real, fully-wired six-job `TaskScheduler` graph (`UsageTracker`, `WellnessTracker`, `PatternRecognizer`, `RecommendationEngine`, plus the two pre-existing Part A/4.18 jobs) confirms one job's repeated exception never stops the other five — the same confirmation `sprint_4_19.md`'s own scenario (c) already ran for a five-job graph, extended here to six; `TaskScheduler`'s own per-job isolation (Sprint 4.15) needs no change.

**(e) `_check_and_announce_priority_item()`'s widened three-source dispatch (Sprint 5.24) degrades per-source, never cross-contaminating.** A real, induced failure inside the `WELLNESS` branch (e.g. `persona_manager.select()` itself failing mid-force-switch) must not corrupt `PriorityQueueManager`'s own queue state or leave `PersonaManager` stuck on Minie — a narrow try/except around the force-switch/announce/resume sequence specifically guarantees `resume_previous()` is still called (or the failure is absorbed before ever switching, if `select()` itself is what failed) via a `try`/`finally`, mirroring `presentation/lip_sync.py`'s own Sprint 5.11 "one mechanism, one `try`/`finally`, guaranteeing the cleanup call regardless of how the body failed" precedent. A `GENERAL_SUGGESTION`/`SCHEDULED_REMINDER` announcement failing must not affect a `WELLNESS` item still queued behind it, or vice versa.

**(f) `_handle_wellness_turn()`/`RecommendationEngine.generate_recommendations()` against missing or corrupted `PatternStore`/`UsageStore` data.** Both already degrade honestly per their own sprint's design (5.20's/5.21's/5.23's own "empty input → valid, zeroed/empty output, never raise" acceptance criteria) — this scenario is a regression confirmation through the real, live-wired Sprint 5.24 call sites specifically (a live turn; a real `TaskScheduler`-driven recommendation pass), not a new code path, the same "confirmed already correct through the real object graph" treatment `sprint_4_19.md`'s scenarios (a)/(b) already received.

## Files to Modify

- `analytics/usage_tracker.py` — scenario (a), if not already fully handled.
- `analytics/usage_store.py`, `learning/pattern_store.py` — scenario (b).
- `wellness/wellness_tracker.py` — scenario (c).
- `voice/pipeline.py` — scenario (e), the `_check_and_announce_priority_item()` `try`/`finally` around the `WELLNESS` branch's force-switch/announce/resume sequence.
- `tests/integration/test_companion_intelligence_resilience.py` (new) — scenarios (a)–(f), mirroring `tests/integration/test_presentation_layer_resilience.py`'s own Sprint 5.15 shape.

## Implementation Tasks

1. Read every file touched by Sprints 5.17–5.24 fresh (not from memory of writing them) — the same adversarial-re-read discipline every prior hardening/freeze sprint in this project has applied, since real gaps have been found this way in nearly every one of them (`sprint_2_14.md`, `sprint_3_14.md`, `sprint_4_13.md`, `sprint_5_16.md`'s own precedent, all cited elsewhere in this Sprint Book).
2. Implement scenarios (a), (b), (c), (e) where a real gap is confirmed; write regression tests proving (d), (f) are already correct.
3. Full-suite run; update `backlog/technical_debt.md` with any further real, disclosed findings the adversarial re-read surfaces (not silently fixed without a trace, matching every prior hardening sprint's own documentation discipline).

## Architecture Notes

Scenario (e)'s own `try`/`finally` is this sprint's single largest real risk, precisely because it is the first place in this codebase where a proactive announcement can itself force a persona switch — every prior proactive announcement (`SCHEDULED_ALERT` since Sprint 4.18) never touched `PersonaManager` at all, so there was no equivalent failure mode to have hardened yet. This scenario is the direct, disclosed consequence of Sprint 5.24's own new choreography, not a pre-existing gap this sprint merely rediscovers.

## Potential Risks

- Exactly the kind of risk this sprint exists to close — see Scenarios above for the concrete list. No further speculative risk is introduced by this sprint's own work, which touches no new capability, only the reliability of capability Sprints 5.17–5.24 already built.

## Acceptance Criteria

- Each of the six scenarios is demonstrated via a real, adversarially-induced failure (a monkeypatched OS call, a monkeypatched SQLite failure, a monkeypatched `PersonaManager.select()`), not merely asserted by code inspection.
- No scenario's fix masks or silently swallows a genuine bug elsewhere — every guard is as narrow as the scenario it addresses, the same "never one blanket catch" discipline `sprint_4_12.md`'s scenario (d) already established.
- `resume_previous()` is confirmed called (or the switch confirmed never attempted) in every induced-failure variant of scenario (e).

## Testing Checklist

- [ ] Integration: scenario (a) — `psutil` race, both exception types.
- [ ] Integration: scenario (b) — `UsageStore`/`PatternStore` read-path SQLite failure degrade.
- [ ] Integration: scenario (c) — `win32api` idle-check failure degrade, logged-once-per-streak.
- [ ] Integration: scenario (d) — six-job `TaskScheduler` isolation, extended fixture.
- [ ] Integration: scenario (e) — induced `PersonaManager.select()` failure during a `WELLNESS` announcement, `resume_previous()`/queue-state invariants confirmed; cross-source non-contamination confirmed.
- [ ] Integration: scenario (f) — live-turn and real-`TaskScheduler`-driven regression confirmation.

## Documentation Checklist

- [ ] Each modified file's own docstring updated with its new hardening behavior, per this project's own established per-scenario documentation convention.
- [ ] `backlog/technical_debt.md` updated with any further real, disclosed findings.
- [ ] `docs/STATUS.md` — Level 5 Part B hardening narrative added.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days.

## Risks

See Scenarios/Potential Risks above.

## Next Sprint

5.26 — Integration Testing & Level Freeze (Part B).

## Future Considerations

None beyond what is already named across Sprints 5.17–5.24's own Future Considerations sections — this sprint hardens existing scope, it does not add new capability.
