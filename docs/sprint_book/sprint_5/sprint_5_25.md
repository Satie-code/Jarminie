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

## Sprint Completion Report (2026-08-05)

Implemented directly ("continue with the implementation of sprint 5.25"), same session continuing from Sprint 5.24's own uncommitted work (confirmed via `git status`/`git diff --stat` — the 5.24 diff matched its own completion report before building on top of it, per this project's established "verify uncommitted state before continuing" discipline).

**Three scenarios needed real production changes; three were confirmed already correct via new regression tests, the same honest split every prior hardening sprint has used.**

**(a) `UsageTracker._sample_foreground_window()`'s own `psutil.NoSuchProcess`/`AccessDenied` race — confirmed already fully handled, no production change.** Sprint 5.17's own implementation already caught both exception types identically (the "if only one is handled" risk this sprint file itself flagged as a real possibility did not materialize). `tests/integration/conftest.py`'s `_pipeline_harness_impl()` gained a new optional `analytics_config` parameter (mirroring `wellness_config`/`learning_config`'s own existing shape) and `fast_level5_part_b_harness` was widened to pass a fast `AnalyticsConfig(sample_interval_seconds=0.3)` — a strictly additive extension, safe for every existing Sprint 5.24 caller of that fixture — so this sprint's own three new integration tests could call the real, registered `_on_tick()` directly and confirm no sample is recorded (for either exception type) without raising, and that the very next successful tick records normally.

**(b) `UsageStore.list_samples_since()`/`PatternStore.list_by_type()`/`list_all()` now degrade to `[]` on a real SQLite failure.** Matches `CalendarStore.list_due_within()`'s own Sprint 4.19 precedent exactly (`try`/`except Exception`, `logger.exception(...)`, return `[]`). `list_sessions_since()` inherits the degrade automatically since it derives entirely from `list_samples_since()`'s own result — no separate wrapping needed. Write paths (`record_sample()`/`upsert()`) deliberately left unwrapped, the same "wrapping the write path risks a false success the caller never actually got" reasoning `CalendarStore.save()` already established — disclosed in both module docstrings, which previously said "Sprint 5.25's job," now updated to describe the real hardening in place.

**(c) `WellnessTracker._sample_idle_seconds()`'s own `win32api.GetLastInputInfo()`/`GetTickCount()` failure now degrades to 0.0** ("not significantly inactive" — the conservative choice named in this sprint's own Scenarios text), via a new `_win32_failure_active` instance flag: logged once (`logger.exception`) on the first failure of a streak, silent on repeats, and logged once more (`logger.info`) on recovery. `pywintypes.error` specifically, not a bare `Exception` — matching `device_control/application_manager.py`'s/`window_manager.py`'s own established win32-failure convention (`docs/CODING_STANDARDS.md`'s "catch only what you can meaningfully handle" rule), a real, deliberate choice over the broader `except Exception` used for scenario (b)'s SQLite failures, since `Exception` there is genuinely the right (and only practical) granularity for an arbitrary third-party SQLite driver failure, while `pywintypes.error` is the real, specific, already-precedented type for a Win32 API call failing.

**(d) One job's exception never stops another's — confirmed already correct, no production change.** `TaskScheduler`'s own Sprint 4.15 per-job isolation (APScheduler's `max_instances=1` per job, each job's own exception caught, logged, and retried on its own next tick, independent of every other registered job) needed nothing new. Re-verified against a real six-job graph — `UsageTracker`, `WellnessTracker`, `PatternRecognizer`, `RecommendationEngine`, plus two pre-existing jobs (`ReminderEngine._poll_due_items`, `CommunicationPipeline._check_and_announce_priority_item`, both originally Sprint 4.18, the latter widened at 5.24) — extending `test_scheduler_integration.py`'s own Sprint 4.19 five-job `one_job_failing_call_counts` fixture technique (class-level counting-wrapper monkeypatches) into a new, self-contained `six_job_failing_call_counts` fixture scoped to this file alone, with `UsageTracker._on_tick` failing on every call (unlike `ActionAuditLog.purge_older_than`'s own Sprint 4.19 "let the first call through" precedent — `UsageTracker.start()` never calls `_on_tick()` synchronously during its own startup, so there is no real first call that must succeed here).

**(e) `_announce_wellness()`'s force-switch/announce/resume sequence — this sprint's own single largest real risk, per its own Architecture Notes.** Wrapped `select()`/`active_persona()`/`activate()` in one `try`/`except`/`finally` (`switched` initialized `False` before the block, set only if `select()` itself returns), mirroring `presentation/lip_sync.py`'s own Sprint 5.11 "one mechanism, one `try`/`finally`, guaranteeing the cleanup call regardless of how the body failed" precedent exactly. `resume_previous()` runs in the `finally` block only when `switched` is `True` — a real induced failure anywhere in the sequence (a mocked `PersonaManager.select()` raising, or a mocked `QuietModeController.activate()` raising after a genuine switch already applied) is logged (`logger.exception`) and absorbed rather than propagating, and `PersonaManager` is never left stuck on Minie. The dedup-set discard and escalation-manager `register_prompt_shown()` calls were deliberately left OUTSIDE the try/except/finally, unconditionally executed exactly as before this sprint — the spec's own text scopes the guard to "the force-switch/announce/resume sequence" specifically, not this method's full body, and widening it further wasn't needed to satisfy any named Acceptance Criterion.

**A real, concretely reproduced test-design race found and fixed while writing this exact scenario's own tests — not a production bug, disclosed here because it's a genuinely generalizable lesson.** The first draft of these tests called `h.pipeline._check_and_announce_priority_item()` directly, immediately followed by an assertion — but `fast_scheduler_harness`'s own real, already-running background `TaskScheduler` job (0.3s poll interval, registered by `CommunicationPipeline.start()` itself) was *also* ticking concurrently. APScheduler's own `max_instances=1` only prevents that SCHEDULED job from overlapping *itself*; it has no knowledge of an out-of-band direct call racing it from a test's own thread. Two consecutive full runs of the file reproduced two *different* failures this way — first `test_announce_step_raising_after_a_real_switch_still_resumes_the_previous_persona` landing on `'minie'` instead of `'jarvis'`, then (after removing the direct calls in favor of `wait_until`) the SAME test plus `test_a_wellness_announcement_failure_does_not_contaminate_a_later_reminder` failing identically — because `pop_next()` empties the queue *before* the handler (which performs the real switch) even starts running, so a predicate checking only `peek_next() is None` can observe the real, narrow transient window between the switch applying and `resume_previous()` completing in the `finally` block. Fixed by (1) relying solely on the real background job (never also calling the dispatcher directly) and (2) widening every affected `wait_until` predicate to check the FINAL settled state (`peek_next() is None AND active_persona().name == "jarvis"`), not queue-emptiness alone. Generalizable pattern for this codebase: a fixture with a fast-ticking real background `TaskScheduler` job and an out-of-band direct call to that same job's own bound method are not safe to combine in one test — pick one caller, not both; and when polling toward a multi-step state transition, the wait predicate must check the transition's own true end state, not an intermediate side effect that happens to occur first.

**(f) `_handle_wellness_turn()`/`RecommendationEngine.generate_recommendations()` against a broken `PatternStore`/`UsageStore` — confirmed already correct through scenario (b)'s own new hardening, no separate production change.** Both already read exclusively through the now-hardened store methods (`AnalyticsDashboardService.daily_summary()` → `list_samples_since()`; `generate_recommendations()` → `list_all()`), so a genuine SQLite failure degrades identically to the empty-data case both already handled honestly since their own owning sprints (5.20/5.23). Re-verified through the real live-turn/`TaskScheduler` call sites specifically — a live wellness turn against a broken `UsageStore` (not just an empty one), and a real `TaskScheduler`-driven recommendation pass against a broken `PatternStore`, confirming the job keeps ticking and never enqueues a fabricated `GENERAL_SUGGESTION`.

**Testing.** 14 new integration tests (`tests/integration/test_companion_intelligence_resilience.py`), mirroring `test_presentation_layer_resilience.py`'s own Sprint 5.15 file shape and section-per-scenario organization. `tests/integration/conftest.py` changed (the additive `analytics_config` parameter/`fast_level5_part_b_harness` widening described under scenario (a) above) — every pre-existing caller of that fixture re-verified unaffected by running `test_companion_intelligence_integration.py`/`test_scheduler_integration.py` alongside the full `wellness`/`analytics`/`learning`/`voice.pipeline` unit suites (246 tests, all passing) before the full-suite run below.

Each modified production file's own module/method docstring updated in place with its new hardening behavior (`usage_store.py`, `pattern_store.py`, `wellness_tracker.py`'s module docstring and `_sample_idle_seconds()`, `voice/pipeline.py`'s `_announce_wellness()`), per this sprint's own Documentation Checklist. No new `backlog/technical_debt.md` finding surfaced during the Implementation Task 1 adversarial re-read of every Sprint 5.17–5.24 file this sprint's own Scenarios touch — the six scenarios named in this sprint's own Sprint Book proved to be the complete, accurate list; nothing further disclosed.

Full suite (unit + integration + system, opt-in real-model tests excluded via marker): 1843 passing + 5 skipped + exactly 1 pre-existing failure (the identical already-long-documented `test_context_analyzer_extracts_a_nonempty_topic_for_real_input` real-Ollama-output-nondeterminism flake first logged at Sprint 5.2, in a file this sprint never touches — recognized as the same known class on sight, consistent with every prior sprint since). `ruff check .` clean across the whole repository.

`docs/STATUS.md` (Level 5 Part B hardening narrative added, continuing the Sprint 5.24 paragraph) and `docs/sprint_book/INDEX.md` (5.25 row → `Complete`) both updated. `backlog/technical_debt.md` unchanged — no new disclosed finding this sprint (see above).

**This closes Level 5 Part B's own hardening pass. Sprint 5.26 (Integration Testing & Level Freeze, Part B) is next — the final sprint of Level 5 Part B, and of Level 5 as a whole once Part A's own freeze (Sprint 5.16) is joined by it.**
