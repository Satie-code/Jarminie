# Sprint 5.26 — Integration Testing & Level Freeze (Part B)

## Sprint ID

5.26

## Sprint Name

Integration Testing & Level Freeze (Part B)

## Purpose

Formally close Level 5 Part B — Companion Intelligence, and with it all of Level 5 (Companion) and the `v0.5` milestone's own gating condition — mirroring `sprint_2_14.md`/`sprint_3_14.md`/`sprint_4_13.md`/`sprint_4_20.md`/`sprint_5_16.md`'s own identical closing role for every prior Level/Part.

## Engineering Rationale

New sprint, not present in the original roadmap-granularity plan — see `sprint_5_24.md`'s Engineering Rationale and `docs/sprint_book/INDEX.md`'s "Level 5 Part B breakdown changes" note for why this Sprint Book adds this sprint, 5.24, and 5.25 beyond the original seven-sprint roadmap-granularity table. Named with the parenthetical "(Part B)" suffix, matching `sprint_4_13.md`'s "(Part A)"/`sprint_4_20.md`'s "(Part B)"/`sprint_5_16.md`'s "(Part A)" precedent — freeze sprints always carry the disambiguating suffix, unlike hardening sprints (see `sprint_5_25.md`'s own Engineering Rationale for that distinction).

## Dependencies

5.25 (Error Handling & Recovery Hardening, Part B).

## Objectives

- A new `tests/system/test_level5_part_b_acceptance.py` driving one continuous scripted scenario through the real, complete Level 1–5 (Part A + Part B) `CoreManager` graph.
- Re-confirmation of Sprint 5.25's own six hardening scenarios at the system level, with the same reasoned "only what a system-level repeat would actually add confidence to" judgment `sprint_3_14.md`/`sprint_4_13.md`/`sprint_4_20.md`/`sprint_5_16.md` have each already applied to their own six.
- An adversarial re-read of every `analytics/`, `wellness/`, and `learning/` source file.
- Formal closure of `backlog/technical_debt.md` item 17's `WELLNESS`/`GENERAL_SUGGESTION` halves (already updated at Sprint 5.24; reconfirmed here as still accurate).
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` updated: Level 5 Part B marked Complete; the Milestones table's own `v0.5` row reconfirmed as gated on both Part A (5.16) and this sprint.

## Scripted Acceptance Scenario

Mirroring `test_level5_part_a_acceptance.py`'s/`test_level4_part_b_acceptance.py`'s own established shape (an `app_harness` fixture, real `CoreManager.startup()`/registration/`shutdown()` ordering, no hand-assembled graph):

1. A sequence of simulated `AppFocusSample`s (fixture-injected, not a real multi-hour wait) produces a real, non-empty `AnalyticsDashboardService.daily_summary()`.
2. A directly-advanced `WellnessTracker` state (the same `_due_item()`-style "persist the end state directly rather than waiting a real interval" technique `test_level4_part_b_acceptance.py` already established for `ReminderEngine`, and `test_level5_part_a_acceptance.py` for `CompanionExperienceEngine`'s greeting) crosses the `BREAK` threshold, producing a real, spoken announcement through Minie's own voice — with whichever persona was active immediately before (a real, live-switched Jarvis session) correctly restored immediately after, confirmed by a direct `PersonaManager.active_persona()` check pre- and post-announcement.
3. Three simulated postponements against that same `BREAK` trigger correctly engage the Hard Limit — a fourth simulated crossing produces no further prompt, verified directly.
4. A `PatternRecognizer.run_detection_pass()` over fixture `UsageStore` data crossing both gates (`pattern_min_occurrences`, `pattern_min_days`) produces a real, persisted `LearnedPattern`; `RecommendationEngine.generate_recommendations()` over that same `PatternStore` state produces a real, templated `Recommendation`, correctly surfaced at `PriorityLevel.GENERAL_SUGGESTION` and announced without any persona switch.
5. A real live turn ("How am I doing today?") is routed to `EngineSelection.WELLNESS` and answered honestly from the same real, fixture-seeded state steps 1–2 produced.
6. A direct confirmation that `UsageTracker`'s, `WellnessTracker`'s, `PatternRecognizer`'s, and `RecommendationEngine`'s own `TaskScheduler` jobs each genuinely fire more than once, using the same `fast_scheduler_app_harness`-style fixture `test_level4_part_b_acceptance.py` already established.

## Hardening Re-confirmation

Sprint 5.25's six scenarios, following the same "only where a system-level repeat adds real confidence" reasoning every prior freeze sprint has applied to its own hardening sprint's six: (a)/(b)/(c) are purely component-level, already exhaustively covered by Sprint 5.25's own dedicated integration tests against real (if narrowly faked) OS/SQLite failures — a full-system repeat would add ceremony, not confidence. (d) is naturally re-exercised by this scenario's own step 6 (six real jobs, one continuous run) rather than needing a separate dedicated repeat. (e)/(f) are genuinely composition-dependent on the real, full graph and are re-confirmed as dedicated functions within the new acceptance test file, the same treatment `sprint_5_16.md` gave its own scenarios (b)/(e).

## Adversarial Re-Read

Every file under `analytics/`, `wellness/`, `learning/`, plus every file Sprint 5.24 modified (`voice/pipeline.py`, `decision/authority.py`, `personas/persona_manager.py`, `main.py`), re-read fresh against this Sprint Book's own stated intent for each — the same discipline that has found at least one real, previously-latent gap in nearly every prior freeze sprint (`sprint_3_14.md`'s `MemoryStore` SQLite gap, `sprint_4_13.md`'s `WorkflowStore` gap, `sprint_4_20.md`'s `BraveSearchProvider` parsing gap, `sprint_5_16.md`'s `QtTransitionOverlay`/`PresentationHostWidget` gaps). Any real finding is fixed and disclosed as a Post-Sprint Fix on the sprint file that owns the affected code, per this project's own established convention — not assumed absent in advance of actually doing the re-read.

## Acceptance Criteria

- Phase 5.2 ("Wellness Engine" — Master Plan: "Gentle reminders. Correct postponement. Adaptive behavior.") is checked directly: a real gentle (level-1) prompt, a real postponement sequence reaching the Hard Limit, and a real Adaptive Wellness multiplier all demonstrated together in one scripted run.
- Phase 5.3 ("Analytics" — "Reliable analytics. Meaningful insights.") is checked directly: a real `DailySummary` computed from real (fixture) samples, with every field verified against the known fixture, not merely "did not raise."
- Phase 5.4 ("Learning Engine" — "User patterns learned gradually. No unpredictable behavior.") is checked directly: the both-gates-required detection discipline re-confirmed through the real graph, and a real recommendation's own text verified to come only from the configured template set (no free-generation import reachable from the live path).
- Every one of Sprint 5.25's six hardening scenarios is accounted for, per the Hardening Re-confirmation section above.
- The full combined suite (unit + integration + system) passes in one process, matching every prior freeze sprint's own verification standard; `ruff check .` clean.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` both updated to reflect Level 5 Part B — and therefore all of Level 5 — as Complete.

## Testing Checklist

- [ ] System: the full six-step scripted scenario above, through a real `CoreManager` graph.
- [ ] System: Sprint 5.25 scenario (e)/(f) re-confirmed at the system level.
- [ ] System: `fast_scheduler_app_harness`-style confirmation of all four new recurring jobs.
- [ ] Full combined suite (unit + integration + system) run in one process.
- [ ] `ruff check .` clean.

## Documentation Checklist

- [ ] `docs/STATUS.md` — Level 5 Part B section completed, mirroring Part A's own narrative depth; Phases 5.2/5.3/5.4 rows all `Complete`; Level 5 heading itself reflects both parts Complete.
- [ ] `docs/sprint_book/INDEX.md` — Part B's own roadmap table rows all marked `Complete`; Level 5 breakdown note updated to record this closure date.
- [ ] `docs/sprint_book/README.md` — Detail Status note updated (already due for a correction predating this sprint — see that file's own stale "Levels 5-6 exist at roadmap/index granularity" line, corrected as part of this Sprint Book's own opening work, not deferred to this sprint).
- [ ] `backlog/technical_debt.md` item 17 — final state reconfirmed (`WELLNESS`/`GENERAL_SUGGESTION` resolved; `SCHEDULED_REMINDER` already resolved at Sprint 4.18; `IMPORTANT_ALERT` explicitly still open).
- [ ] `docs/changelog/` — a new entry once this sprint's own real, human-observed verification (see below) and explicit user authorization make a `v0.5` tag appropriate; not written prematurely by this sprint alone.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium–High.

## Estimated Development Time

2–2.5 days.

## Risks

- The same class of "one criterion no automated test can satisfy" risk every prior freeze sprint has named: a supervised, real-machine, human-observed pass (a real wellness prompt genuinely heard and correctly handed to Minie's own voice and back; real application-usage data genuinely reflecting what the machine actually ran; a real recommendation genuinely making sense to the person hearing it) remains outstanding until a person actually performs it — named explicitly as outstanding by this sprint, not assumed done, matching Sprint 2.14/3.12/4.11/4.20/5.16's own identical precedent.

## Next Sprint

None within this Sprint Book — Level 5 Part B, and with it all of Level 5 (Companion), closes here. `v0.5` ("Complete personal AI companion") is gated on this sprint AND Sprint 5.16 (Part A, already Complete) AND the outstanding manual verification named above AND explicit user authorization — the same two-part-plus-manual-plus-authorization gating discipline `v0.2.0`/`v0.3.0`/`v0.4.0` have each already established; no semver tag is created by this sprint alone. Level 6 (Stabilization, target `v1.0`) is next at roadmap granularity only, expanded to full detail once it becomes current, per this project's own "expand when current" practice.

## Future Considerations

None beyond what Sprints 5.17–5.25 have already each named in their own Future Considerations sections.
