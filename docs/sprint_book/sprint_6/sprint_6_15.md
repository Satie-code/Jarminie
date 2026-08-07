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
