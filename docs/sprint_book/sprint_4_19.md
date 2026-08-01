# Sprint 4.19 — Error Handling & Recovery Hardening (Part B)

## Sprint ID

4.19

## Sprint Name

Error Handling & Recovery Hardening (Part B)

## Purpose

Apply the Fail Gracefully Rule across Level 4 Part B's own named failure scenarios, mirroring the exact role Sprint 2.13/3.13/4.12 played for Levels 2, 3, and Part A respectively — the last hardening pass before Sprint 4.20 formally freezes Level 4 Part B (and, with it, all of `v0.4`).

## Engineering Rationale

**New sprint**, following the identical precedent every prior Level has already established for itself: a dedicated hardening sprint, separate from both the component sprints that build the capability and the integration sprint that wires it live, since real-induced-failure testing against the *fully wired* graph is a different, later-arriving concern than either. `sprint_4_12.md`'s own Engineering Rationale is the most directly analogous precedent — Level 4 Part B's own risk surface (two brand-new external dependencies, `APScheduler` and a real network-facing `SearchClient`, plus the first genuinely proactive/non-turn-triggered behavior in this project) is different in *kind* from Part A's real-machine-action risk, not smaller, and earns the same dedicated treatment.

Six scenarios, matching the established "name them explicitly, investigate current code before writing anything, only fix what's genuinely broken" discipline every prior hardening sprint has followed (Sprint 3.13's own notable finding: four of its six scenarios were already correctly handled by earlier sprints' own quality bar, and this sprint's own scenarios should be investigated with the same expectation, not assumed broken by default):

**(a) `SearchClient`/network failure during a live turn.** Sprint 4.16's own `ResearchEngine.research()` already degrades to `[]` on failure per its own Acceptance Criteria — this scenario's job is a real, induced-failure regression test proving that holds end-to-end through `CommunicationPipeline._handle_internet_agent_turn()` (Sprint 4.18), and that the resulting spoken reply is an honest "I couldn't search right now," never silence or a crash.

**(b) `LanguageModelClient`/Ollama failure during summarization.** Sprint 4.17's own `Summarizer.summarize()` already degrades to an honest "couldn't summarize" `ResearchSummary` per its own Acceptance Criteria — same treatment as (a): a real regression test through the fully wired path, not new production code, unless investigation finds a real gap.

**(c) A `TaskScheduler` job's own exception must not stop any other registered job.** Sprint 4.15's own Testing Checklist already named this in isolation (two jobs, one failing); this scenario re-verifies it against the REAL, fully-wired Sprint 4.18 graph — five real jobs registered at once (`ReminderEngine`'s poll, the proactive-announcement check, and the three purge/review passes) — since a real multi-job scheduler under real composition is a different, more adversarial condition than two synthetic jobs in isolation.

**(d) The reminder-announcement/session-transition race**, named explicitly as a real, accepted-but-untested edge case in `sprint_4_18.md`'s own Potential Risks: a reminder becoming due in the narrow window between `VoiceSessionManager`'s watchdog deciding to end a session and the session actually ending. This scenario needs a real, deliberately-timed regression test proving the system degrades to "the reminder waits for the next poll cycle," never a crash or a corrupted `QuietModeController` state (stuck `ACTIVE` with no real session, the same failure shape Sprint 2.14's own adversarial re-read already found and fixed once for `QuietModeController.activate()`'s ordinary wake-word path).

**(e) `CalendarStore`'s own SQLite calls have no Fail Gracefully wrapping yet.** Unlike `WorkflowStore` (which `backlog/technical_debt.md` item 27 deliberately left unhardened at Sprint 4.9 pending "a second real caller," only resolved once Sprint 4.13 found one), `CalendarStore` already has two real callers by the time this sprint runs — `ReminderEngine`'s own poll (4.15) and `CommunicationPipeline._handle_scheduler_turn()` (4.18) — so hardening it now is justified by this project's own established "don't harden speculatively ahead of a real caller" rule, not a violation of it.

**(f) `VoiceSessionManager` failure mid-proactive-announcement.** The speak-first-then-listen sequence Sprint 4.18 built (`activate(SCHEDULED_ALERT)` → `begin_session()` → immediate `speak_reply()`) is a genuinely new call shape with a real, previously-unexercised failure window: what happens if `begin_session()` succeeds but `speak_reply()` itself fails (a Coqui TTS failure, the same class Sprint 2.13's own scenario (c) already hardened for the ordinary turn-reply path, but never exercised for this specific speak-first ordering)? Must degrade to a clean `end_session()`/`QuietModeController.deactivate()`, never a stuck `ACTIVE` state with no way back to listening for the next real wake word.

## Objectives

- Six real-induced-failure regression tests (or, where investigation finds an existing gap, real production fixes plus tests), one per scenario (a)–(f) above.
- An explicit adversarial sweep confirming every internal call site in `CommunicationPipeline._handle_scheduler_turn()`/`_handle_internet_agent_turn()`/`_check_and_announce_due_reminder()` degrades gracefully, the same parametrized-sweep discipline Sprint 4.12's own Implementation Task 2/Acceptance Criteria already established for `ActionRegistry.dispatch()`/`WorkflowExecutor.run()`.

## Dependencies

4.18 (Scheduler & Internet Agent Integration) — this sprint hardens the fully-wired graph, not any component in isolation.

## Files to Create

- New regression test files/additions under `tests/unit/scheduler/`, `tests/unit/internet/`, `tests/integration/test_scheduler_integration.py`, `tests/integration/test_internet_agent_integration.py` (extending, not replacing, Sprint 4.18's own files) — exact file/test names depend on what investigation finds, matching every prior hardening sprint's own "named scenarios first, files second" discipline.

## Files to Modify

- `scheduler/calendar_store.py` — Fail Gracefully wrapping for scenario (e), if investigation confirms it's genuinely missing (expected, per Engineering Rationale — `CalendarStore` was never in Sprint 4.14's own Files to Modify for hardening, that was always deferred here, unlike `WorkflowStore`'s more ambiguous history).
- `voice/pipeline.py` — scenario (d)/(f) fixes, if investigation finds a real gap beyond what Sprint 4.18 already built defensively.
- `scheduler/task_scheduler.py` — scenario (c), only if the real, fully-wired multi-job test surfaces something Sprint 4.15's own isolated two-job test didn't.
- Exact file list finalized after investigation, per every prior hardening sprint's own established practice of not assuming which files need real changes before checking.

## Expected Classes

None new — this sprint hardens existing classes, it does not add new ones, matching Sprint 2.13/3.13/4.12's own identical shape.

## Expected Interfaces

None new.

## Expected Functions

None new at the public API level — internal exception-handling changes only, the same "this sprint changes robustness, not shape" discipline every prior hardening sprint has followed.

## Data Flow

Not applicable — this sprint modifies failure-path behavior within already-specified data flows (see `sprint_4_18.md`'s own Data Flow diagrams), it does not introduce new ones.

## Implementation Tasks

1. Investigate each of scenarios (a)–(f) against the REAL, Sprint-4.18-wired codebase before writing anything — per every prior hardening sprint's own precedent, some may already be correctly handled by existing quality bar (Sprint 4.16/4.17's own degrade-on-failure design) and need only a regression test, not new code.
2. Fix whatever scenarios investigation finds genuinely unhandled — narrow, targeted guards, never one blanket catch that could mask an unrelated bug (the same discipline Sprint 4.12's own scenario (d) explicitly followed for `WorkflowExecutor.run()`).
3. A dedicated adversarial sweep test parametrized across every internal call site in the three new `CommunicationPipeline` methods (4.18), matching Sprint 4.12's own precedent for `ActionRegistry.dispatch()`/`WorkflowExecutor.run()`.
4. Full regression run confirming no prior Level 1–4 behavior changed.

## Architecture Notes

Scenario (d) and (f) both concern the same new proactive-announcement call sequence Sprint 4.18 introduced — worth investigating together (a shared test fixture simulating the announcement path under two different induced-failure conditions) rather than as fully independent scenarios, the same "related scenarios investigated together" efficiency Sprint 3.13 already applied to its own six.

`TaskScheduler`'s own job-isolation guarantee (scenario c) is fundamentally an APScheduler behavior this project depends on but has never directly, adversarially verified against the real, fully-composed job set — this sprint is the first to do so with all five real jobs present simultaneously, not just two synthetic ones.

## Integration Considerations

- This sprint changes only internal robustness — no new live callers, no new capability. `docs/STATUS.md`'s Phase 4.3/4.4 rows stay `Complete` (set by Sprint 4.18), unchanged by this sprint, the same "hardening an already-complete phase doesn't change its status" precedent Sprint 2.13 already established.
- Any real, unexpected finding from this sprint's own investigation (a scenario found broken, not just unverified) gets fixed here directly and documented as this sprint's own work — not deferred to Sprint 4.20, matching every prior hardening sprint's own "fix real bugs now, don't defer to the freeze sprint" precedent.

## Potential Risks

- **Scenario (d)/(f)'s timing-sensitive regression tests risk flakiness** — the same category of risk this project has repeatedly accepted and documented elsewhere (`test_full_level2/3_acceptance_scripted_conversation`'s own known "passes standalone, occasionally times out under full-suite load" flake class) rather than chased to zero; a real, deliberate, small-config-value + explicit-synchronization approach (matching `VoiceSessionManager`'s own timing-test precedent from Sprint 2.5, "small config values + `threading.Event` synchronization, not sleep-and-hope") should be used here too, not blind `time.sleep()` calls.
- **Scenario (c)'s real multi-job test could itself be a source of test-suite flakiness** if `poll_interval_seconds`-shaped intervals aren't tuned short enough for fast test execution while still being long enough to avoid a race against test setup — the same tuning judgment call every prior real-`BackgroundScheduler`/real-timer test in this codebase has had to make.
- **Investigation may find zero of the six scenarios need real production code changes** (an honest, plausible outcome, matching Sprint 3.13's own "four of six already handled" finding) — this sprint's own value would then be entirely in the regression-test coverage it adds, not new robustness; a legitimate, not-a-failure outcome, worth stating up front so it isn't read as under-scoping if it happens.

## Acceptance Criteria

- Each of scenarios (a)–(f) has a real, induced-failure regression test proving graceful degradation through the fully-wired Sprint 4.18 graph.
- No scenario's failure ever leaves `QuietModeController`/`VoiceSessionManager` in an inconsistent state (`ACTIVE` with no real session, or vice versa) — verified directly via `health_check()`, not assumed.
- No scenario's failure stops any other, unrelated `TaskScheduler` job from continuing to run on schedule.
- Every internal call site in `_handle_scheduler_turn()`/`_handle_internet_agent_turn()`/`_check_and_announce_due_reminder()` is covered by the adversarial sweep test.
- Full existing Level 1–4 Part A + Part B test suite passes with zero regressions.

## Testing Checklist

- [ ] Scenario (a): induced `SearchClient` failure through a live turn — honest spoken degrade, no crash.
- [ ] Scenario (b): induced `LanguageModelClient` failure during summarization through a live turn — honest spoken degrade, no crash.
- [ ] Scenario (c): a real, fully-composed five-job `TaskScheduler` — one job's induced exception doesn't stop the other four.
- [ ] Scenario (d): a reminder becoming due during the session-end transition window — degrades to "waits for next poll," no corrupted state.
- [ ] Scenario (e): induced `CalendarStore` SQLite failure — degrades gracefully at both real call sites (`ReminderEngine`'s poll, `CommunicationPipeline._handle_scheduler_turn()`).
- [ ] Scenario (f): induced `VoiceSessionManager`/TTS failure mid-proactive-announcement — clean `end_session()`/`deactivate()`, no stuck `ACTIVE` state.
- [ ] Adversarial sweep: every internal call site in the three new `CommunicationPipeline` methods, parametrized.
- [ ] Full regression: entire existing suite passes unchanged.

## Documentation Checklist

- [ ] Each fixed scenario documented as a Post-Sprint Fix on its owning sprint file (`sprint_4_14.md` for scenario (e), `sprint_4_18.md` for (c)/(d)/(f), `sprint_4_16.md`/`sprint_4_17.md` for (a)/(b) if any real code changes prove necessary there) — matching this project's own established "fix lands here, documentation lands on the owning sprint's own file" convention.
- [ ] `docs/STATUS.md` — new Sprint 4.19 paragraph, mirroring Sprint 2.13/3.13/4.12's own style, including an honest statement of which scenarios needed real code vs. only regression tests.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

4.20 — Integration Testing & Level Freeze (Part B).

## Future Considerations

None beyond what's already named above — this sprint's own scope is deliberately bounded to the six named scenarios, matching every prior hardening sprint's own anti-scope-creep discipline.
