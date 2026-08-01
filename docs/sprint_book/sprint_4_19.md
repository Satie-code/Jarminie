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

## Sprint Completion Report (2026-08-01)

Implemented as specified, authorized directly ("continue with the sprint 4.19"). All six scenarios investigated against the REAL, fully-wired Sprint 4.18 graph before any code was written, per this sprint's own Implementation Task 1 — matching Sprint 3.13's own precedent, three needed real production changes and three were already correctly handled.

**Scenario (e), the one explicitly expected to need real hardening, did**: `scheduler/calendar_store.py`'s `list_due_within()` now degrades to `[]` on a SQLite failure — its only real read-path caller, `ReminderEngine._poll_due_items()`, already treats "nothing due" as normal, and a transient failure simply means that one poll cycle finds nothing (the item is still persisted, picked up on the next successful poll). `get()`/`list_all()`/`mark_completed()`/`delete()` stay deliberately unhardened, matching `WorkflowStore`'s own precedent — none has a real production caller yet. `save()` itself is deliberately left unwrapped by `CalendarStore` — its one real caller, `voice/pipeline.py`'s `_handle_scheduler_turn()`, gained its own narrow try/except instead, degrading to an honest "I'm sorry, I couldn't save that reminder right now" reply. This was a genuine design decision, not a mechanical copy of the read-method pattern: `_handle_scheduler_turn()`'s own reply text makes an explicit success claim ("Done — I'll remind you...") immediately after the save — silently swallowing the failure inside `CalendarStore.save()` itself would have produced a **false** "Done" the user never actually got, worse than the pre-hardening behavior (falling through to `_handle_turn_complete()`'s outer catch, which speaks no reply and ends the session — safe, but coarser than necessary). The narrow catch at the call site is what makes the degrade both honest and non-disruptive at once, the same "a narrower catch beats the coarse outer one once a failure mode is specific enough to degrade instead of aborting" reasoning `_run_decision_pipeline()`'s own Sprint 3.13 hardening already established. See `sprint_4_14.md`'s own Post-Sprint Fix for the full write-up (per this sprint's own Documentation Checklist, scenario (e) is documented there, the file that owns `CalendarStore`).

**Scenarios (c), (d), and (f) — all concerning Sprint 4.18's own code — needed zero new production changes**, confirmed by reading the actual current implementation before assuming otherwise, not by inspection alone:

- **(c)**: re-verified Sprint 4.15's own two-synthetic-job isolation guarantee against the REAL, fully-wired five-job graph. `ActionAuditLog.purge_older_than()` made to fail on every call after its own real startup call (letting `ActionAuditLog.start()` — which itself calls `purge_older_than()` once, unguarded — complete normally; an earlier draft that failed unconditionally crashed test fixture setup before the test body ever ran, a real, useful finding about `start()`'s own unrelated lack of defense, not itself in scope here) confirms it keeps being invoked on schedule while the other four real jobs keep ticking normally.
- **(d)**: reading `voice/quiet_mode.py`/`voice/session_manager.py` directly found `QuietModeController.current_mode()`/`deactivate()` are each a single plain attribute read/write — genuinely atomic at the Python bytecode level, with no possible "torn" intermediate state for `_check_and_announce_due_reminder()` to observe. Proven under real, sustained concurrent pressure (a due reminder sitting in the queue through an entire session's own real timeout transition, `health_check()` sampled continuously throughout) rather than assumed safe from the code-level reasoning alone.
- **(f)**: `QuietModeController.activate()` already wraps `begin_session()` in a broad try/except (built at Sprint 2.14, explicitly re-documented at Sprint 4.18 as covering the `announce_first` path too) that rolls `_mode` back to `DORMANT` on any failure. Confirmed for real with an induced `TextToSpeechError` during the announcement itself, through the actual proactive job. One real, honest, deliberately out-of-scope limitation named, not fixed: the due reminder is already popped off `PriorityQueueManager` before the failed announcement attempt, so it isn't retried — this scenario's own job is state consistency, not reminder redelivery.

**Scenarios (a)/(b) (Internet Agent) needed no production changes either** — `ResearchEngine.research()`/`Summarizer.summarize()`'s existing never-raises degrades (Sprints 4.16/4.17) already covered both; (a) already had a real regression test from Sprint 4.18 itself (`test_live_turn_search_provider_failure_degrades_to_the_same_honest_reply`), (b) gained a new one (`test_live_turn_summarization_llm_failure_degrades_to_an_honest_reply`) proving a search-succeeds-but-summarization-fails path specifically, via a new `should_raise_for_summary` flag on the shared `FakeLanguageModelClient` (distinct from `should_raise`, which would fail the turn's own earlier Intent/Context stages before routing ever reached `INTERNET_AGENT`).

**The adversarial sweep (Implementation Task 3) is split into two, not one shared parametrize**, reflecting a real, deliberate distinction investigation found rather than forcing an artificial common shape: `_handle_scheduler_turn()`/`_handle_internet_agent_turn()` both run inside `_handle_turn_complete()`'s own try/except (Sprint 2.13) and must never propagate — 4 parametrized cases confirm this (`calendar_store.save`, `research_engine.research`, `source_validator.validate`, `summarizer.summarize`), with `calendar_store.save`'s own narrower guard verified separately from the other three's fall-through to the outer catch. `_check_and_announce_due_reminder()` has no try/except of its own, by design — its collaborators are all in-memory, already-hardened objects with no real external I/O, so a fault there is a genuine bug, not an anticipatable environmental failure, and the CORRECT expected behavior is that it raises, safely absorbed by the same `TaskScheduler`/`APScheduler` job-isolation guarantee scenario (c) re-verifies — 5 parametrized cases confirm it raises rather than silently swallowing (`quiet_mode_controller.current_mode`, `priority_queue_manager.peek_next`/`pop_next`, `persona_manager.active_persona`, `quiet_mode_controller.activate`).

13 new unit tests (`tests/unit/scheduler/test_calendar_store.py` +2, `tests/unit/scheduler/test_reminder_engine.py` +1, `tests/unit/voice/test_pipeline.py` +10 including both sweeps) and 4 new integration tests (`tests/integration/test_internet_agent_integration.py` +1, `tests/integration/test_scheduler_integration.py` +3). Full-suite run: 1054 total, 1038 passing, 1 skipped, 15 failed — exactly the already-tracked `backlog/technical_debt.md` item 29 `test_text_to_speech.py` failures, nothing more; zero additional flaky failures this run. `ruff check .` clean. `docs/STATUS.md`'s Phase 4.3/4.4 rows correctly left unchanged (`Complete`, set by Sprint 4.18) — a new narrative paragraph documents this sprint's own honest real-code-vs-regression-test-only split instead. `docs/sprint_book/INDEX.md` (4.19 row → `Complete`) updated. **This closes Sprint 4.19. Sprint 4.20 (Integration Testing & Level Freeze, Part B) is next — the final sprint before Level 4 Part B, and `v0.4` as a whole, formally freezes.**
