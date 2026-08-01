# Sprint 4.18 — Scheduler & Internet Agent Integration

## Sprint ID

4.18

## Sprint Name

Scheduler & Internet Agent Integration

## Purpose

Wire every component built in Sprints 4.14–4.17 into one real system inside `main.py`, and give the Decision Engine's `EngineSelection.SCHEDULER`/`EngineSelection.INTERNET_AGENT` (reserved since Sprint 3.11) their first real handlers — the exact role Sprint 4.11 played for `DEVICE_CONTROL`/`WORKFLOW`, applied here to Level 4 Part B. This sprint also finally closes the queue-consumer gap Sprint 4.15 deliberately left open, and gives `backlog/technical_debt.md` items 11/15's recurring-cadence half a real caller for the first time.

## Engineering Rationale

**New sprint**, following the exact precedent `docs/sprint_book/INDEX.md`'s own Level 2/3/Part A breakdown-changes notes already established: a dedicated integration sprint for wiring, distinct from the component sprints that build the pieces being wired. `sprint_4_11.md`'s own Engineering Rationale named `_determine_engine()`'s additive-branch pattern as "the one that future work is expected to follow, not a one-off" specifically for `SCHEDULER`/`INTERNET_AGENT` — this sprint is that future work.

Three genuinely distinct wiring jobs converge in this one sprint, each already named as deferred by its own owning sprint, restated here so nothing is rediscovered:

1. **Decision Engine routing** (`sprint_4_16.md`/`sprint_4_17.md`'s own gap) — a live conversation turn asking JARMINEI to research something, or check/set a reminder, needs to actually reach `ResearchEngine`/`Summarizer` or `ReminderEngine`, the same `_determine_engine()` extension shape Sprint 4.11 already built for `DEVICE_CONTROL`/`WORKFLOW`.
2. **The reminder queue-consumer** (`sprint_4_15.md`'s own named gap) — popping a `SCHEDULED_REMINDER` `PriorityItem` off `PriorityQueueManager` when the system is idle, and actually announcing it via `QuietModeController.activate(ActivationReason.SCHEDULED_ALERT)` + `VoiceSessionManager.speak_reply()`. Unlike `DEVICE_CONTROL`/`WORKFLOW` (both triggered *by* a live turn), this is JARMINEI-initiated — the first genuinely proactive, non-turn-triggered behavior in this entire project. Every prior sprint's own conversation flow starts with the user speaking; this is the first path that starts with JARMINEI speaking first.
3. **The shared periodic-task registrations** (`sprint_4_15.md`'s own named gap, tracing back to `backlog/technical_debt.md` items 11/15) — `TaskScheduler.add_job()` calls for `MemoryLifecycleManager.run_cleanup_pass()`/`run_monthly_review()`, `ConversationSessionStore.purge_older_than()`, and `ActionAuditLog.purge_older_than()`, replacing their existing one-time-at-startup calls (still made inside each module's own `start()`, unchanged) with genuine recurring cadences for the first time in this project's history.

**Job 2 (proactive announcement) is this sprint's own largest, most novel piece of real engineering, named explicitly rather than treated as "just another handler branch.**" It requires `QuietModeController`'s already-reserved `ActivationReason.SCHEDULED_ALERT` (declared since Sprint 2.6, never used by any real caller until now) and a genuinely new interaction with `VoiceSessionManager`: `activate()` calls `begin_session()`, which starts *listening* — for a proactive reminder, the correct order is *speak first, then listen*, the reverse of every existing turn (wake word → listen → reply). `VoiceSessionManager.speak_reply()` (2.9+) already requires an active session to exist before it can be called, so the real sequence this sprint must build is: `activate(SCHEDULED_ALERT)` → session begins → immediately `speak_reply(reminder_text, ...)` (interrupting the just-started listen state to speak first) → session returns to listening for a possible response ("got it," "remind me in 10 minutes"). This exact ordering is a genuinely new call pattern no existing test or prior sprint has exercised — flagged here as a real design/verification risk, not assumed to fall out of existing pieces for free.

**Proactive announcement must also respect the case where the system is NOT idle** — Part 2's own Priority Queue language for Scheduled Reminders is explicit: *"Queued."* If `QuietModeController.current_mode()` is already `ACTIVE` (a live conversation in progress) when a reminder becomes due, this sprint's own consumer must NOT interrupt it — the item stays in `PriorityQueueManager` until the next idle-check finds the system dormant. This is exactly the priority-and-interruption policy `PriorityQueueManager`'s own docstring already anticipated ("classify() can only TENTATIVELY flag... Sprint 3.11 is what actually confirms... whether... JARMINEI is authorized to act on it") applied to a new, non-emergency case: a Priority 3 item waits, it does not preempt.

## Objectives

- `main.py` constructs every Level 4 Part B subsystem via DI (`TaskScheduler`, `CalendarStore`, `ReminderEngine`, `SearchClient`/`ResearchEngine`, `SourceValidator`, `Summarizer`) and registers each real `ManagedModule` with `CoreManager`.
- `decision/authority.py`'s `_determine_engine()` gains two more additive branches: a `MEMORY_RECALL`-or-`ACTION_REQUEST` intent naming a schedule-shaped target (a date/time/reminder keyword) routes to `EngineSelection.SCHEDULER`; an `INFORMATIONAL` intent whose `ContextAnalysis` indicates the user wants current/external information (not answerable from memory alone) routes to `EngineSelection.INTERNET_AGENT`.
- `voice/pipeline.py`'s `CommunicationPipeline` gains `_handle_scheduler_turn()` (create/postpone/acknowledge a `ScheduledItem` based on the transcript, report the result) and `_handle_internet_agent_turn()` (runs `ResearchEngine.research()` → `SourceValidator.validate()` → `Summarizer.summarize()`, speaks the summary with its citations).
- A new proactive-announcement mechanism (see Engineering Rationale, Job 2) — a periodic idle-check (itself a `TaskScheduler` job) that pops `PriorityQueueManager` when `QuietModeController.current_mode()` is `DORMANT` and, if a `SCHEDULED_REMINDER` item is waiting, activates and speaks it.
- `TaskScheduler.add_job()` registrations for `MemoryLifecycleManager`/`ConversationSessionStore`/`ActionAuditLog`'s three purge/review passes, on real, config-driven recurring intervals — closing `backlog/technical_debt.md` items 11/15's recurring-cadence half.
- A real, end-to-end smoke run: a live conversation turn ("what's the latest on X") produces a real, cited summary; a scheduled reminder set for the near future is proactively announced when the system is idle.

## Dependencies

4.14, 4.15, 4.16, 4.17 (every Level 4 Part B component sprint), 4.11 (Workflow & Device Control Integration, for the established `_determine_engine()`/`CommunicationPipeline` extension pattern this sprint follows), 2.12, 3.12.

## Files to Create

- `tests/integration/test_scheduler_integration.py` — real (non-mocked) `TaskScheduler`/`CalendarStore`/`ReminderEngine`/`PriorityQueueManager` wired together, including the proactive-announcement path.
- `tests/integration/test_internet_agent_integration.py` — real `ResearchEngine`/`Summarizer` wired into a live turn (network calls faked at the `SearchClient`/`LanguageModelClient` boundary, matching every prior integration test's own "fake only at the true hardware/external-service boundary" precedent).

## Files to Modify

- `main.py` — construct and register `TaskScheduler`, `CalendarStore`, `ReminderEngine`, `SearchClient`, `ResearchEngine`, `SourceValidator`, `Summarizer`; register the three periodic-maintenance jobs and the proactive-announcement job on `TaskScheduler`.
- `decision/authority.py` — `_determine_engine()` additive extension for `SCHEDULER`/`INTERNET_AGENT` routing; module docstring updated to remove "reserved: Level 4" language for these two values.
- `voice/pipeline.py` — `CommunicationPipeline` gains `_handle_scheduler_turn()`/`_handle_internet_agent_turn()`, plus whatever new collaborator references (`reminder_engine`, `research_engine`, `summarizer`) those need; the proactive-announcement mechanism (a new small method, e.g. `_check_and_announce_due_reminder()`, registered as a `TaskScheduler` job from `main.py` or `CommunicationPipeline.start()` — an implementation-time decision, not fully specified here, matching Sprint 4.11's own precedent of leaving a real tie-break/wiring detail to be decided and documented during implementation).

## Expected Classes

No new classes — this sprint composes Sprints 4.14–4.17's existing classes; `CommunicationPipeline` and `AuthorityEvaluator` are modified, not replaced, the same shape Sprint 4.11 already established for itself.

## Expected Interfaces

None new.

## Expected Functions

- `AuthorityEvaluator._determine_engine(intent, context_analysis) -> EngineSelection` — additive extension for `SCHEDULER`/`INTERNET_AGENT`, the exact tie-break rule (how a schedule-shaped request is distinguished from an internet-research-shaped one, both potentially sharing `IntentCategory.INFORMATIONAL`/`ACTION_REQUEST`) is this sprint's own implementation decision, not specified in advance — matching Sprint 4.11's own precedent for its DEVICE_CONTROL-vs-WORKFLOW tie-break.
- `CommunicationPipeline._handle_scheduler_turn(trace: DecisionTrace) -> None`
- `CommunicationPipeline._handle_internet_agent_turn(trace: DecisionTrace) -> None`
- `CommunicationPipeline._check_and_announce_due_reminder() -> None` (or equivalent name) — the proactive-announcement job body: peeks/pops `PriorityQueueManager` only when `quiet_mode_controller.current_mode() is OperatingMode.DORMANT`; if a `SCHEDULED_REMINDER` item is present, calls `quiet_mode_controller.activate(ActivationReason.SCHEDULED_ALERT)` then `session_manager.speak_reply(...)` with the reminder's own text.

## Data Flow

```
"What's the latest news on the JARMINEI project?" (live conversation turn)
      ↓
IntentDetector → ContextAnalyzer → AuthorityEvaluator._determine_engine()
      ↓
EngineSelection.INTERNET_AGENT
      ↓
CommunicationPipeline._handle_internet_agent_turn(trace)
      ↓
ResearchEngine.research(query) → SourceValidator.validate() → Summarizer.summarize()
      ↓
ResearchSummary(summary_text, citations) → spoken reply, citations included

---

(background, TaskScheduler job) CommunicationPipeline._check_and_announce_due_reminder()
      ↓
QuietModeController.current_mode() == DORMANT?
      ↓ yes
PriorityQueueManager.pop_next() → PriorityItem(payload=ScheduledItem, priority=SCHEDULED_REMINDER)
      ↓
QuietModeController.activate(SCHEDULED_ALERT) → VoiceSessionManager.begin_session()
      ↓
VoiceSessionManager.speak_reply(item.title, persona.voice_id)
      ↓
(session continues listening for "got it" / "remind me in 10 minutes")
```

## Implementation Tasks

1. `main.py` — construct and register the full Level 4 Part B object graph, following the existing `_construct_level3_modules()`/`_construct_level4_modules()` two-phase (construction, then registration) pattern.
2. `decision/authority.py` — `_determine_engine()` extension, docstring update.
3. `voice/pipeline.py` — `_handle_scheduler_turn()`, `_handle_internet_agent_turn()`, `_check_and_announce_due_reminder()`.
4. `TaskScheduler` job registrations for the three purge/review passes (items 11/15) and the proactive-announcement check.
5. Integration tests, plus a real, non-mocked smoke run (mirroring Sprint 4.11's own precedent) covering both a real research query and a real proactive reminder announcement.

## Architecture Notes

This sprint's `_determine_engine()` extension follows Sprint 4.11's own explicitly-named discipline: resolve a concrete, nameable target or fall back to the existing conversational path, never attempt general-purpose natural-language command parsing. A vague research query with no resolvable topic, or a reminder request with no resolvable time, both fall back to `CONVERSATIONAL_RESPONSE` with an honest capability-gap explanation, the same `_build_reasoning()` pattern Sprint 4.11 already established.

The proactive-announcement job is the one genuinely new architectural shape in this sprint — every prior `TaskScheduler`-registered job (the three purge/review passes) is a plain, side-effect-only maintenance call with no interaction with `voice/`'s live conversation state at all; this one is the first periodic job that reaches into `QuietModeController`/`VoiceSessionManager`. It must be written defensively against the same class of race Sprint 2.12 already found once (the wake-word thread competing with an active session for the same microphone) — a reminder becoming due at the exact moment a real wake-word-triggered session is beginning needs a clean, tested ordering (checking `current_mode()` immediately before `activate()`, inside whatever locking/synchronization `QuietModeController` already provides, not assumed race-free by inspection alone).

## Integration Considerations

- This sprint is the first live caller for `TaskScheduler`, `CalendarStore`, `ReminderEngine`, `ResearchEngine`, `SourceValidator`, `Summarizer` — every "no live caller yet" note in Sprints 4.14–4.17's own Integration Considerations sections is resolved here, the same discipline Sprint 4.11 already applied to Sprints 4.1–4.10's own equivalent gaps.
- `backlog/technical_debt.md` items 11 and 15 are fully resolved by this sprint (not just partially, as they've been since Sprint 3.12/the 2026-07-28 Technical Debt Resolution pass) — both should be updated to reflect a real recurring cadence now exists, not merely a one-time-at-startup call.
- `backlog/technical_debt.md` item 17 (`PriorityQueueManager`'s consumer side) gets its first real resolution for the `SCHEDULED_REMINDER` source specifically — `IMPORTANT_ALERT`/`WELLNESS`/`GENERAL_SUGGESTION` sources remain unwired, since nothing in this Sprint Book produces them; the item's own text should be updated to reflect exactly this partial scope, not overstated as fully resolved.
- Level 5's Emotion/Wellness Engines, when they arrive, are expected to reuse this exact same proactive-announcement mechanism (enqueue at their own `PriorityLevel`, let the existing idle-check consumer pop and announce) rather than building a second, parallel announcement path — named here as the precedent future levels should follow, the same "this sprint's own pattern is the one future work follows" framing Sprint 4.11 used for `_determine_engine()`'s own extension shape.

## Potential Risks

- **The proactive-announcement mechanism is a genuinely new interaction shape with real concurrency risk** — see Architecture Notes above. This sprint's own testing must exercise it directly (a real due reminder firing while the system is genuinely idle, and a second test proving it correctly waits when a session is genuinely active), not just assume `QuietModeController`'s existing state machine generalizes safely to a new caller.
- **A reminder announcement mid-session-timeout-window is a real edge case**: if a reminder becomes due in the few seconds between `VoiceSessionManager`'s own watchdog deciding to end a session and the session actually ending, the idle-check could see a stale `ACTIVE` reading. Acceptable to let the reminder simply wait for the next poll cycle (per `poll_interval_seconds`/this sprint's own idle-check interval) rather than building special-cased handling for a narrow timing window — named explicitly so it isn't rediscovered as a "bug" later.
- **This is the second Sprint Book integration surface making real, uncontrolled network calls** (the first being Sprint 4.16's own `SearchClient`) — this sprint's own integration tests must fake the network boundary, matching every prior integration test's own "fake only at the true external boundary" precedent; a real, opt-in network-touching test belongs in Sprint 4.20, not here.
- **`_determine_engine()`'s SCHEDULER-vs-INTERNET_AGENT-vs-existing-engines tie-break is a real, non-trivial classification problem** ("remind me to look up X" plausibly touches both) — this sprint's own implementation decision, not specified in advance, the same category of latitude Sprint 4.11's own Potential Risks already named for its own tie-break rule.

## Acceptance Criteria

- A live conversation turn asking for current/external information is correctly routed through `EngineSelection.INTERNET_AGENT` and produces a real, cited spoken summary.
- A live conversation turn creating a reminder is correctly routed through `EngineSelection.SCHEDULER`, persisted via `CalendarStore`, and picked up by `ReminderEngine`'s existing poll.
- A due reminder is proactively announced (via `QuietModeController.activate(SCHEDULED_ALERT)` + a real spoken message) when the system is idle, and correctly NOT announced (stays queued) while a session is active.
- `MemoryLifecycleManager.run_cleanup_pass()`/`run_monthly_review()`, `ConversationSessionStore.purge_older_than()`, and `ActionAuditLog.purge_older_than()` are each genuinely called on a real recurring cadence, verified directly (not just "registered"), closing `backlog/technical_debt.md` items 11/15.
- Every Level 1–4 Part A acceptance criterion continues to pass with no regression.
- `main.py` still starts and stops cleanly with the full Level 1–4 (Part A + Part B) module set registered, and every new module appears in the Status Panel via `module_states()` with zero `ui/status_panel.py` changes.

## Testing Checklist

- [ ] Integration: live-turn-to-real-research-summary round trip (`tests/integration/test_internet_agent_integration.py`), network faked at the `SearchClient`/`LanguageModelClient` boundary.
- [ ] Integration: live-turn-to-scheduled-reminder round trip (`tests/integration/test_scheduler_integration.py`).
- [ ] Integration: a due reminder is announced when idle, and correctly deferred when a session is active — both cases, directly tested, not inferred.
- [ ] Integration: the three periodic-maintenance jobs (`MemoryLifecycleManager`, `ConversationSessionStore`, `ActionAuditLog`) genuinely fire more than once across a real, short-interval test run — proving recurrence, not just a single registration call.
- [ ] Regression: full existing Level 1–4 Part A test suite passes unchanged.
- [ ] Manual/real, in a disposable scratch environment: a live spoken research request produces a real, sensible cited answer, and a real near-future reminder is genuinely spoken aloud when due — the same category of manual verification every prior integration sprint (2.12/3.12/4.11) has required and clearly separated from automated coverage.

## Documentation Checklist

- [ ] `decision/authority.py` docstring: `SCHEDULER`/`INTERNET_AGENT` reservation language removed, replaced with the real routing logic description.
- [ ] `voice/pipeline.py` docstring: the two new turn-handling branches and the proactive-announcement mechanism, in the same wiring-diagram style Sprint 4.11's own docstring update used.
- [ ] `backlog/technical_debt.md` — items 11, 15 marked fully resolved; item 17 updated to reflect the `SCHEDULED_REMINDER` source's real resolution while other sources remain open.
- [ ] `docs/STATUS.md` — Phase 4.3/4.4 rows confirmed `Complete`, integration-verified note added, matching Sprint 4.11's own precedent.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

High — the largest composition surface in Level 4 Part B, and the first sprint in this entire project building genuinely proactive (not turn-triggered) behavior.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

4.19 — Error Handling & Recovery Hardening (Part B).

## Future Considerations

- Extending `_determine_engine()` for `WELLNESS`/`EMOTION_SUPPORT` — explicitly Level 5's own future sprint, following this sprint's own additive-branch pattern.
- Reusing the proactive-announcement mechanism for Level 5's Wellness reminders — named above as the expected precedent, not built here.
- Richer schedule-vs-research disambiguation in `_determine_engine()` — a real future refinement, not built speculatively beyond this sprint's own reasonable tie-break.

## Sprint Completion Report (2026-08-01)

Implemented as specified, following directly from the 2026-08-01 provider-agnostic Internet refactor. `main.py` gained `_construct_level4_part_b_modules()`/`_register_level4_part_b_early()`, constructing and registering `TaskScheduler`/`CalendarStore`/`ReminderEngine`/`ResearchEngine`/`SourceValidator`/`Summarizer` — `task_scheduler`/`calendar_store` are registered *before* Level 2, since `CommunicationPipeline.start()` calls `task_scheduler.add_job()` directly and requires `TaskScheduler.start()` to have already run. `decision/authority.py`'s `_determine_engine()` gained the SCHEDULER/INTERNET_AGENT additive branches (`_is_schedulable_reminder_request()` requires both a scheduler keyword and a resolvable relative-time hint; `_wants_current_information()` checks for a "search for"/"latest"/"current"-shaped keyword), 7 new tests. `voice/pipeline.py` gained `_handle_scheduler_turn()`, `_handle_internet_agent_turn()`, and `_check_and_announce_due_reminder()` (this project's first genuinely proactive, JARMINEI-initiated behavior), plus 8 new constructor collaborators and 5 new `TaskScheduler` job registrations in `start()`/`stop()`. `VoiceSessionManager.begin_session()`/`QuietModeController.activate()` both gained an `announce_first` parameter for the "speak first, then listen" ordering a proactive announcement needs, the reverse of every prior wake→listen→reply turn shape.

**Two real, previously-latent concurrency bugs were found and fixed during this sprint's own testing — both pre-dated Sprint 4.18, only exposed because it's the first sprint to give several jobs genuine, independent recurring callers on the same shared resources:**

1. **`TaskScheduler.add_job()` fired a job's first execution almost immediately on registration**, not after waiting one full interval — APScheduler's `IntervalTrigger` defaults its own `start_date` to "now," so a first fire time computed from that is also "now." Undiagnosed, this meant every real app startup fired a burst of all five `CommunicationPipeline`-registered jobs (including four maintenance passes meant to run hourly) within about a second of `CoreManager.startup()` completing. Found via a genuinely reproducible `tests/system/test_level4_part_a_acceptance.py` timing failure (confirmed reproducible in isolation, not just under full-suite load, ruling out host-contention noise before concluding it was a real bug) — traced to this exact APScheduler default via a small throwaway probe script, not guessed. Fixed by explicitly setting `next_run_time = now + interval_seconds` in `add_job()`. Regression test: `test_add_job_does_not_run_the_callable_immediately`.
2. **`database/sqlite_client.py`'s `SqliteClient` had no synchronization around its one `sqlite3.Connection`** — `check_same_thread=False` only disables Python's own same-thread safety check; it does not make a single `Connection` object safe for genuinely concurrent multi-threaded use, a documented Python `sqlite3` module pitfall. Every prior caller in this project used one `SqliteClient` from a single thread at a time, so this was latent until this sprint gave `MemoryLifecycleManager.run_cleanup_pass()`/`run_monthly_review()` (both sharing `MemoryStore`'s one connection) their first real, independently-ticking `TaskScheduler` jobs, which can now run concurrently on different `APScheduler` thread-pool workers. Confirmed as a genuine, reproducible defect — not theoretical — via a standalone script hammering `execute()`/`query()` from several real threads concurrently, which reliably produced corrupted `sqlite3.InterfaceError("bad parameter or other API misuse")`/`DatabaseError("another row available")` results. Fixed with a `threading.Lock` guarding every connection-touching method (`connect()`/`execute()`/`query()`/`close()`). Regression test: `test_concurrent_execute_and_query_from_multiple_threads_never_corrupts`, using the identical multi-thread-hammer shape that first reproduced the bug.

Fixing bug (2) had a real second-order effect worth naming: SQLite access across the several 0.15s-interval background jobs now genuinely serializes instead of racing, so under sustained load some jobs' own next tick could arrive before their still-serializing predecessor finished (APScheduler's default `max_instances=1` then skips that tick — harmless, but it intermittently ate into a test's own bounded-wait margin). `tests/integration/conftest.py`'s `fast_scheduler_harness` fixture was tuned to a calmer 0.3s interval in response, and `test_scheduler_integration.py`'s own wait timeouts widened to 10s — both purely test-ergonomics changes; correctness never depended on speed.

`tests/integration/conftest.py` was refactored to extract `_pipeline_harness_impl()` (the shared object-graph builder) out of the `pipeline_harness` fixture, so a second fixture, `fast_scheduler_harness`, could reuse the identical graph with a short-interval `SchedulerConfig` for the two new dedicated test files this sprint's own spec required — `pipeline_harness` itself is unchanged (still `SchedulerConfig()`'s realistic 30s/3600s defaults, so none of Part B's background jobs ever fire during any other integration test in this project). Teardown ordering was also hardened: `task_scheduler.stop()` now runs immediately after `pipeline.stop()`, followed by a new `_wait_for_no_scheduler_worker_threads()` poll (bounded, best-effort) before any store's own `SqliteClient` connection closes — closing, not just narrowing, the exact close-vs-in-flight-job race a naive short-interval harness would otherwise reintroduce.

`tests/integration/test_scheduler_integration.py` (4 tests) covers: a live SCHEDULER-routed turn persisting a real `ScheduledItem` via `CalendarStore` (asserted against a tolerance window, not the reply's own exact "at HH:MM" string, to avoid a spurious minute-boundary failure); a due reminder proactively announced when idle (also stands in for "picked up by ReminderEngine's own poll," since that's the only path a due item can reach the announcement at all); a due reminder correctly deferred while a session is ACTIVE and then announced once it goes DORMANT; and all four periodic-maintenance jobs genuinely firing more than once via real `TaskScheduler` recurrence (proven by class-level monkeypatched counting wrappers around the real methods, applied before `CommunicationPipeline.start()` captures them as bound methods). One test needed a second real-race fix during development: `FakeWakeWordEngine`'s background thread can satisfy its `match_on_call` before the test body's very first line runs (the same race `pipeline_harness`'s own `voice_config` docstring already names), so pushing `match_on_call` out of reach *after* the fact was too late — the fix is `wait_for_dormant()` first, letting any such accidental session settle on its own real silence timeout, before neutralizing further matches.

`tests/integration/test_internet_agent_integration.py` (3 tests) covers: a live INTERNET_AGENT-routed turn producing a real cited summary (3 queued `SearchResult`s, 2 sharing enough real significant terms to genuinely corroborate through `SourceValidator`'s own term-overlap logic and 1 unrelated staying uncorroborated — proving the reply's citation count is computed, not hardcoded); a genuinely empty result set producing the honest "couldn't find anything" reply without ever reaching `Summarizer`; and a simulated `SearchProvider` failure degrading identically, through `ResearchEngine`'s own existing never-raises contract.

Full-suite run: 1037 total, 1021 passing, 1 skipped, 15 failed — exactly the already-tracked `backlog/technical_debt.md` item 29 `test_text_to_speech.py` failures (unrelated pre-existing environment issue), nothing more. One additional transient failure (`test_full_level3_acceptance_scripted_conversation`, with an explicit `resource_monitor: CRITICAL threshold(s) breached: cpu` warning in its own captured log) was observed on one `tests/system` run and confirmed non-reproducible standalone immediately after — the same already-established host-load flake class this project has repeatedly confirmed for this exact test, not a regression. `ruff check .` clean.

`backlog/technical_debt.md` items 11 and 15 marked fully resolved (the recurring-cadence half both were still tracking); item 17 updated to reflect the `SCHEDULED_REMINDER` consumer's real resolution while `IMPORTANT_ALERT`/`WELLNESS`/`GENERAL_SUGGESTION` sources remain unwired (nothing in this Sprint Book produces them). `docs/STATUS.md` (Phase 4.3/4.4 both → `Complete`) and `docs/sprint_book/INDEX.md` (4.18 row → `Complete`) updated. **This closes Level 4 Part B's Scheduler and Internet Agent phases, and all of Level 4's own live-turn wiring.** **Sprint 4.19 (Error Handling & Recovery Hardening, Part B) is next.**
