# Sprint 6.15 — Integration Testing & Level Freeze (Part A)

## Sprint ID

6.15

## Sprint Name

Integration Testing & Level Freeze (Level 6 Part A)

## Purpose

Formally close Level 6 Part A — Autonomous Intelligence & Cognitive Architecture — with a full system-level acceptance pass through the real, complete Level 1–6 Part A `CoreManager` graph, matching the identical closing ritual every prior Level/Part has used (2.14, 3.14, 4.13/4.20, 5.16/5.26). This sprint does **not** tag `v1.0` — per the Part A/Part B split this Book's own "Level 6 breakdown changes" note establishes, `v1.0` is gated on both Part A (this sprint) and Part B (Stabilization, sprints 6.16–6.23, not yet expanded to full detail).

## Engineering Rationale

Six-part closing structure, matching every prior freeze sprint's own established shape: (1) one continuous scripted system-acceptance scenario exercising Level 6 Part A's own core promise end-to-end; (2) re-confirmation of Sprint 6.14's six hardening scenarios at the system level (not full re-investigation — a lighter touch for scenarios already hardened and regression-tested, matching Sprint 5.26's own explicit precedent for when a re-confirmation can reason "component-level or naturally re-exercised" rather than needing a dedicated repeat); (3) an adversarial re-read of every Level 6 Part A file; (4) full-suite verification; (5) documentation closure; (6) an explicit, honest statement of what remains manual-only or otherwise outstanding, matching Sprint 2.14's own precedent for naming a real, unautomatable gap rather than glossing over it.

## Objectives

- `tests/system/test_level6_part_a_acceptance.py` — one continuous scripted scenario: state a multi-step goal → review the proposed decomposition → accept it → run the derived workflow (including a step gated by the empty-by-default `approved_commands` allowlist, confirming it is honestly blocked, not silently skipped) → ask "why did you suggest that?" and receive a real, sourced `Explanation` → confirm a `ProactiveAssistant`-sourced item is announced only while `DORMANT` and only per `AdaptivePrioritizer`'s own judgment → confirm the completed workflow's outcome reaches `SelfEvaluator` and is retrievable via `TaskGraphStore.list_evaluations_for_goal()`.
- Re-confirm Sprint 6.14's six scenarios at the system level.
- Adversarial re-read of `planning/`, `context/`, `reasoning/`, `decision/decision_engine_v2.py`, `decision/adaptive_prioritizer.py`, `knowledge/`, `learning/`'s four new detectors, `proactive/`, `workflow/task_graph_adapter.py`, `workflow/session_resumption.py`, `device_control/application_manager.py`'s `open_url()`, and every `voice/pipeline.py`/`decision/authority.py` change from Sprint 6.13.
- Full-suite verification (unit + integration + system, opt-in real-model marker excluded); `ruff check .` clean.
- `docs/STATUS.md`, `docs/sprint_book/INDEX.md`, `docs/sprint_book/README.md` updated to reflect Level 6 Part A fully `Complete`.

## Dependencies

6.14 (hardening must precede freeze, matching every prior Level's own ordering).

## Files to Create

- `tests/system/test_level6_part_a_acceptance.py`

## Files to Modify

Determined by the adversarial re-read (Objective 3 above) — any genuine gap found gets a Post-Sprint Fix on its owning sprint's own file, matching this project's established convention, or a new `backlog/technical_debt.md` entry if sized beyond a freeze sprint's own "verify and harden what exists" scope (per the size-based judgment call `sprint_5_26.md`'s own Sprint Completion Report established as precedent).

## Expected Classes

None new.

## Expected Functions

None new — this sprint is verification, not implementation.

## Data Flow

The full Level 1–6 Part A pipeline, exercised end-to-end through the real `CoreManager` graph — no new data flow, confirmation of every flow already documented across sprints 6.1–6.14.

## Implementation Tasks

1. `tests/system/test_level6_part_a_acceptance.py` — the full scripted scenario described in Objectives.
2. System-level re-confirmation of Sprint 6.14's six scenarios.
3. Adversarial re-read of every Level 6 Part A file, per the file list in Objectives.
4. Full-suite run(s), investigating any failure per this project's own established discipline (standalone re-run to distinguish a real regression from the already-documented host-load/real-model-nondeterminism flake classes).
5. `docs/STATUS.md` — Level 6 Part A section rewritten to `Complete`; a new Level 6 Part B section restructured from roadmap-granularity "Planned" (already the case since this Book's own creation) into the same shape Level 4/5's own Part B sections used before their own later expansion.
6. `docs/sprint_book/INDEX.md` — 6.1–6.15 rows → `Complete`; Milestones table gains a `6.15 → Level 6 Part A complete... not a semver tag` row, matching `5.16`'s/`4.13`'s own identical precedent.
7. `docs/sprint_book/README.md` — Detail Status note updated.
8. Sprint Completion Report appended to this file once implemented, per every prior freeze sprint's own precedent.

## Architecture Notes

This sprint changes no production behavior by design — a freeze sprint verifies and, where a genuine gap is found, hardens; it does not add capability. Any capability-shaped finding during the adversarial re-read is logged, not implemented, per this project's own "freeze sprint finds at least one, discloses rather than scope-creeps" established pattern.

## Integration Considerations

- Level 6 Part B (Stabilization, sprints 6.16–6.23) remains at roadmap granularity until it becomes current, per this Book's own "Level 6 breakdown changes" note — this sprint does not expand it.
- `v1.0` is explicitly not tagged by this sprint, matching `v0.4`'s/`v0.5`'s own two-part gating precedent exactly.

## Potential Risks

- **The propose→accept two-turn planning flow (Sprint 6.13's own most delicate new conversational logic) is the piece most likely to surface a genuine system-level gap** neither its own component sprint nor the integration sprint's own narrower tests caught — worth the acceptance scenario's own explicit attention, matching this project's now-established pattern of freeze sprints finding at least one real, previously-latent gap.
- **A `Task`-Graph-derived workflow's own inert `SYSTEM_COMMAND` step (empty `approved_commands`) could be mistaken for a test failure** if the acceptance scenario doesn't explicitly assert the honest-denial behavior rather than a successful run — named explicitly in Objectives to guard against exactly this.

## Acceptance Criteria

- The full scripted scenario (Objectives, item 1) passes against the real, complete Level 1–6 Part A `CoreManager` graph.
- Every one of Sprint 6.14's six scenarios is re-confirmed at the system level.
- The adversarial re-read either finds no new gap, or any gap found is disclosed and either fixed (if sized within a freeze sprint's own scope) or logged to `backlog/technical_debt.md` (if not).
- Full test suite passes with zero unexplained failures (every failure individually traced to an already-documented flake class or fixed).
- `ruff check .` clean repository-wide.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md`/`docs/sprint_book/README.md` all accurately reflect Level 6 Part A's own real, complete state.

## Testing Checklist

- [ ] System: full scripted plan → accept → run → explain → proactive-announce → evaluate scenario.
- [ ] System: Sprint 6.14's six hardening scenarios, re-confirmed.
- [ ] Full unit + integration + system suite, opt-in real-model marker excluded.
- [ ] `ruff check .`.

## Documentation Checklist

- [ ] `docs/STATUS.md` — Level 6 Part A → `Complete`.
- [ ] `docs/sprint_book/INDEX.md` — 6.1–6.15 rows → `Complete`; Milestones table updated.
- [ ] `docs/sprint_book/README.md` — Detail Status note updated.
- [ ] `docs/backlog/technical_debt.md` — any new finding from the adversarial re-read logged.
- [ ] Sprint Completion Report appended to this file.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium–High.

## Estimated Development Time

2–3 days.

## Risks

See Potential Risks above.

## Next Sprint

6.16 — Startup & Caching Optimization (Level 6 Part B — Stabilization; roadmap-granularity only until expanded to full detail, per this Book's own "Level 6 breakdown changes" note).

## Future Considerations

- Level 6 Part B's own expansion to full sprint-file detail — the natural next step once Part A is frozen and the user requests it, mirroring every prior Part A→Part B transition in this project's history.
- A supervised, human-observed real-machine verification pass for Level 6 Part A's own conversational surfaces (planning, explanation, proactive announcements) — named here explicitly as the same category of outstanding manual criterion every prior Level's own freeze sprint has disclosed (starting with Sprint 2.14's wake-word round trip), not performed by this sprint itself.

## Sprint Completion Report (2026-08-12)

Implemented as specified, authorized directly ("continue with sprint 6.15") right after Sprint 6.14 closed — the final sprint of Level 6 Part A.

**Delivered `tests/system/test_level6_part_a_acceptance.py`** (3 tests): one continuous scripted scenario (`test_level6_part_a_full_acceptance_scenario`) through the real, complete Level 1–6 Part A `CoreManager` graph — propose a goal → human-reviewed accept (the Human-First gate, only the `Goal`'s own status bumps, each `Task` stays `PROPOSED`) → run it → a real "why did you suggest that?" follow-up → a real `ProactiveAssistant`-sourced announcement, `DORMANT`-gated — plus two dedicated system-level re-confirmations of Sprint 6.14's own hardening scenarios (c) and (f), the two genuinely composition-dependent ones (matching Sprint 5.26's own precedent for when a hardening scenario needs a system-level repeat versus when component-level coverage already suffices).

**A real, deliberate departure from Sprint 6.13's own integration test, exercising exactly what this sprint's Objectives ask for and that test explicitly avoided**: the default fake planning task ("Do the first concrete thing") classifies as an unapproved `SYSTEM_COMMAND` (`HIGH` risk) — `WorkflowExecutor`'s own real, unmodified whole-workflow confirmation gate fires, and since a live-voice-triggered confirmation reply can never actually be answered (`backlog/technical_debt.md` item 26's own disclosed, unfixed single-thread reentrancy limitation), it honestly times out after 2.0s and denies the step — precisely the "empty-by-default `approved_commands` allowlist... honestly blocked, not silently skipped" behavior this sprint's own Objectives names. Handled the identical confirmation-prompt-vs-final-reply race Sprint 6.13's own test docstring already named, by polling for the final reply's own content (`wait_until(..."wasn't confirmed"...)`) rather than a single `spoken_event.wait()`.

**A real, disclosed correction to this sprint's own Objectives text, the same "a sprint's own scenario list can itself go stale" pattern first named at Sprint 6.14's own scenario (e)**: "the completed workflow's outcome... is retrievable via `TaskGraphStore.list_evaluations_for_goal()`" repeats the exact already-disclosed Sprint 6.10 premise error (that method joins on `tasks.task_id`, but `evaluate_workflow_run()` always keys `subject_id` on the run's own `run_id`) already found and worked around at Sprint 6.13/6.14 — verified here identically, via the raw `evaluation_records` table.

**A real, previously-unnoticed bug in the test's own design, found and fixed while writing this sprint's own scenario, then found to ALSO affect a pre-existing test**: `ProactiveAssistant`'s `MISSED_MEAL` trigger is wall-clock-hour-dependent (fires whenever "now" falls inside the default noon-to-2pm window with no qualifying break in `recent_applications`) — a real, environment-dependent flake. Fixed in this sprint's own new test by hard-limiting `missed_meal_window_start_hour`/`_end_hour` to an impossible window (the direct-call, synchronous-tick shape used there makes a config poke reliable). Investigating the full-suite run then surfaced the SAME root cause already latent in Sprint 6.13's own `tests/integration/test_autonomous_intelligence_integration.py::test_real_upcoming_deadline_is_detected_and_announced_when_idle` — but there, `ProactiveAssistant` ticks continuously and independently from fixture-setup time onward (real `TaskScheduler` recurrence, the test's own whole point), so a config poke inside the test body cannot reliably win the race against a tick that already fired during fixture setup itself, before the test body's first statement runs. Fixed instead by making the assertion robust to an extra, unrelated announcement — polling for the specific expected reply content rather than assuming `speak_calls[0]` — a real, disclosed test-only bug, not a production regression.

**The mandated adversarial re-read (Objective 3) found and fixed one real gap**: `device_control/application_manager.py`'s `ApplicationManager.execute()` dispatched `ActionType.OPEN_URL` (Sprint 6.9) *outside* the `try/except (OSError, psutil.Error, pywintypes.error)` block wrapping every other operation — the identical shape of gap `backlog/technical_debt.md` item 28 already fixed once in this exact method (for `pywintypes.error` specifically). Not a live safety gap either way (`ActionRegistry.dispatch()`'s own outer `except Exception` already covers it, per item 28's own established reasoning) but a real, disclosed structural inconsistency — fixed by moving the `OPEN_URL` dispatch inside the same `try` block, with 1 new regression test (`test_execute_open_url_degrades_honestly_when_open_browser_raises`).

**Two further real, disclosed findings from the same re-read, logged rather than fixed** — genuinely new cross-file wiring, not narrow same-file hardening, per this sprint's own "verify and harden what exists, don't add capability" Architecture Notes:
- **`backlog/technical_debt.md` item 48**: `context/context_model.py`'s `WorkingContext.known_projects` has never been populated by `ContextEngine.build()` — `ContextEngine.__init__()` has no `knowledge_graph_store` parameter at all. This was explicitly anticipated at Sprint 6.3 ("stays an untyped placeholder... until Sprint 6.6 gives it a real Entity type and a real producer") and repeatedly re-named as "the next sprint's job" through 6.6/6.7/6.8/6.9/6.13's own STATUS.md narratives — none of them actually did it. A real, four-sprint-deferred gap that survived all the way to Level 6 Part A's own freeze. The one real consumer that needed project data (`ProactiveAssistant`'s `PROJECT_INACTIVITY` trigger) quietly routed around the gap by reading `KnowledgeGraphStore` directly rather than through `WorkingContext`, which is why nothing ever surfaced this as a hard failure.
- **`backlog/technical_debt.md` item 49**: `ReasoningEngine.what_if()`/`alternatives()` (6.4) and `DecisionEngineV2.requires_confirmation()`/`suggest_alternatives()` (6.5) all have zero callers in production code (confirmed via repo-wide grep, each appears only in its own unit test) — no live conversational surface anywhere asks "what if I did X instead," "what are my other options," or "does this specific action need my confirmation," even though `rank_actions()` (their real, live-wired sibling) has worked since Sprint 6.13.

**Sprint 6.14 hardening re-confirmation (Objective 2)**: (a)/(b) are purely component-level, already exhaustively covered by Sprint 6.14's own dedicated unit tests against real (if narrowly faked) SQLite/LLM failures; (d) is a pure data-structure property proven by a real 8-thread stress test with no dependency on the real graph's own composition; (e) was proven via a real, repo-wide AST scan, a static analysis whose proof holds regardless of which harness runs it — none of these four warranted a system-level repeat, documented rather than re-implemented, the same judgment call Sprint 5.26 already established for its own (a)/(b)/(c). (c) is naturally re-exercised by this sprint's own dedicated `test_proactive_assistant_genuinely_recurs_at_system_level` (a real, recurring `TaskScheduler` job — a raising tick killing it would show up as a failed second announcement). (f) is genuinely composition-dependent and got its own dedicated `test_self_evaluator_failure_never_blocks_or_reverses_task_bookkeeping`, driving `_finalize_workflow_run()` directly against a real, persisted `Goal`/`Task` and a real SQLite write, with `SelfEvaluator.evaluate_workflow_run()` monkeypatched to raise.

Full suite (unit + integration + system): 2336 passing + 5 skipped across repeated full runs, with only the two already-long-documented pre-existing flake classes ever appearing — the host-load `wait_for_dormant`-class flake (this run's own captured log showed a genuine `core.resource_monitor` CPU CRITICAL breach at the exact failure moment, direct confirmation of the root cause already named since Sprint 3.13) and the real-Ollama-output-nondeterminism class (`decision/context_analyzer.py`, untouched by this or any Level 6 sprint, first logged at Sprint 5.2) — each individually re-confirmed via standalone re-run. An intermediate full run also showed the pre-existing `test_real_upcoming_deadline_is_detected_and_announced_when_idle` flake described above, before its own fix; a subsequent clean full run confirmed it resolved. `ruff check .` clean repo-wide.

`docs/STATUS.md` (Level 6 Part A header → "✔ Complete (2026-08-12, Sprint 6.15)", full Sprint 6.15 narrative appended, Integration phase row → `Complete`), `docs/sprint_book/INDEX.md` (6.15 row → `Complete`; the Milestones table's own "6.15 → Level 6 Part A complete" row was already present, added predictively when the Sprint Book was first written), `docs/sprint_book/README.md` (Detail Status note — Level 6 Part A now explicitly named formally frozen) all updated. `docs/backlog/technical_debt.md` items 48/49 added.

**Level 6 Part A (sprints 6.1–6.15) is now formally frozen.** `v1.0` remains gated on Level 6 Part B (Stabilization, sprints 6.16–6.23, still roadmap-granularity only) plus a supervised real-machine verification pass plus explicit user authorization — matching every prior two-part Level's own identical gating discipline. The outstanding manual verification (a planning proposal's own spoken wording actually sounding natural, a real "why did you suggest that?" follow-up actually answering what a real user meant, a real proactive announcement actually landing at a sensible moment) is explicitly disclosed as not performed by this automated suite, per every prior Level-freeze sprint's own precedent since Sprint 2.14.

**No git commit made** — per this project's own "only commit when explicitly asked" rule; changes left in the working tree alongside Sprints 6.1–6.14's own still-uncommitted work, the user not yet asked whether to commit. **Level 6 Part B (Stabilization, sprints 6.16–6.23) remains at roadmap granularity only — expand to full sprint-file detail when the user says it's next.**
