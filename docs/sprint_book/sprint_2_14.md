# Sprint 2.14 — Integration Testing & Level Freeze

## Sprint ID

2.14

## Sprint Name

Integration Testing & Level Freeze

## Purpose

Formally close Level 2 — Communication and prepare Release v0.2, per [04_Master_Implementation_Plan.md](../04_Master_Implementation_Plan.md): *"Release Version 0.2 — Voice interaction operational."* Confirms every Phase 2.1/2.2/2.3 acceptance criterion holds simultaneously, with zero regression against Level 1, using the existing (currently empty) `tests/integration/` and `tests/system/` directories for the first time.

## Engineering Rationale

Level 1 closed with an Acceptance Pass appended to its last sprint's file after the fact ([sprint_1_9.md](sprint_1_9.md)) because Level 1's integration surface was small enough that one desktop-shell sprint could reasonably absorb it. Level 2's integration surface — real audio hardware, three ML models, multiple background threads, a persona-switching state machine, and a persisted conversation log — is large enough to warrant its own planned sprint rather than being folded into Sprint 2.13's hardening work or assumed complete once 2.12 runs once. This sprint is where that assumption gets tested formally, matching this task's own suggested "Integration Testing & Level Freeze" sprint, and reusing the exact discipline established in Level 1's Post-Release Review: full regression, adversarial re-read, and a documented sign-off — done here as planned closure rather than a retroactive add-on.

## Objectives

- Populate `tests/integration/` and `tests/system/` with real Level 2 coverage (previously empty placeholders since Sprint 1.1's bootstrap).
- Run and document the full Level 2 Acceptance Pass against every Phase 2.1/2.2/2.3 criterion from the Master Implementation Plan, in combination.
- Confirm zero regression in the full Level 1 suite.
- Tag and document Release v0.2.

## Dependencies

2.13 (Error Handling & Recovery Hardening)

## Files to Create

- `tests/integration/test_voice_pipeline_integration.py` — expands on Sprint 2.12's integration test with the failure scenarios hardened in 2.13 (each of scenarios a–f gets an integration-level, not just unit-level, confirmation).
- `tests/system/test_level2_acceptance.py` — a full-application system test: real `main.py` composition, a scripted multi-turn conversation (via fixture audio) exercising wake → listen → transcribe → persona reply → speak → persona switch → timeout → Quiet Mode, asserting the whole Phase 2.1–2.3 acceptance list at once.
- `docs/changelog/0.2.0.md` — release summary, following the exact structure of [changelog/0.1.0.md](../changelog/0.1.0.md).

## Files to Modify

- `docs/STATUS.md` — Level 2 marked **✔ RELEASED**, matching Level 1's existing dashboard convention.
- `docs/sprint_book/INDEX.md` — Level 2 table rows marked **Complete** once each sprint is actually implemented (a per-sprint update as implementation proceeds, not a single batch edit at the end — matches how Level 1's INDEX rows were updated incrementally, sprint by sprint).

## Expected Classes

None — this sprint is testing and documentation, not new production code, consistent with Level 1's own Acceptance Pass containing no new classes either.

## Expected Interfaces

None.

## Expected Functions

None new in production code. Test functions per the Files to Create list above, following existing test-naming conventions (e.g. `test_<scenario>_<expected_outcome>`, matching Sprint 1.9's Post-Release Review regression test names).

## Data Flow

Not a new pipeline — this sprint exercises the full Data Flow already established across Sprints 2.1–2.13 end-to-end, adding assertions rather than new behavior:

```
tests/system/test_level2_acceptance.py
      ↓ drives
main.py → run_app() → CoreManager.startup() (full Level 1 + Level 2 module graph)
      ↓
scripted fixture-audio conversation through CommunicationPipeline (2.12)
      ↓
assertions against every Phase 2.1/2.2/2.3 acceptance criterion, together
```

## Acceptance Criteria

- Every criterion from Phase 2.1 ("Wake phrase activates JARMINEI. Speech recognition functions. Voice responses function."), Phase 2.2 ("Natural conversations maintained during session."), and Phase 2.3 ("Correct persona selected. Correct voice selected. No simultaneous personas.") is verified together in one system test run.
- The complete Level 1 test suite (95 tests as of `v0.1.0`) plus all Level 2 unit/integration tests pass together with zero regressions.
- `docs/changelog/0.2.0.md` accurately summarizes what shipped, mirroring `0.1.0.md`'s structure (including a Post-Release Review section if this sprint's own adversarial pass finds anything, per the Level 1 precedent).
- Real-hardware manual verification (the wake-word-to-spoken-reply round trip flagged as manual-only since Sprint 2.1) is performed at least once on the actual target laptop before tagging the release — this is the one criterion that cannot be satisfied by any automated test in this Sprint Book.

## Testing Checklist

- [ ] System: full scripted multi-turn conversation exercising every Phase 2.1–2.3 criterion together.
- [ ] Integration: each of Sprint 2.13's six hardened failure scenarios confirmed at the integration level, not just unit level.
- [ ] Regression: full combined Level 1 + Level 2 suite green.
- [ ] Manual: one real-hardware end-to-end conversation on the target laptop, notes recorded in the changelog.
- [ ] Adversarial re-read: apply the same "read every source file against its originating sprint's spec, look specifically for unhandled-exception paths and untested documented risks" discipline used in Level 1's Post-Release Review ([sprint_1_9.md](sprint_1_9.md)) across all of `voice/` and `personas/`.

## Documentation Checklist

- [ ] `docs/changelog/0.2.0.md` created.
- [ ] `docs/STATUS.md` — Level 2 marked ✔ RELEASED.
- [ ] `docs/sprint_book/INDEX.md` — Level 2 rows marked Complete (as each sprint actually completes, per Files to Modify above).
- [ ] Every Level 2 sprint file (2.1–2.13) has its Sprint Completion Report appended by the time this sprint runs — this sprint's Acceptance Pass depends on all of them being genuinely done, the same dependency check the Sprint Workflow rule requires before starting any sprint.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md). This sprint closes Level 2 — Communication and Release v0.2.

## Estimated Complexity

Medium-High — no new logic, but the broadest verification surface of any Level 2 sprint, spanning every prior one.

## Estimated Development Time

1.5–2 days.

## Risks

- **This sprint can only be as good as 2.1–2.13's actual implementation** — if any earlier sprint's Sprint Completion Report is missing or its acceptance criteria weren't genuinely verified (not just claimed), this sprint's own Acceptance Pass will surface that gap rather than paper over it; per the Sprint Workflow rule, that means stopping to resolve the earlier sprint, not proceeding to tag `0.2.0` regardless.
- **Real-hardware verification remains manual-only** for this entire Level, same as every individual sprint's own Testing Checklist — Level 6's Sprint 6.3 (Stress & Recovery Testing) is where sustained, repeated real-hardware testing becomes a formal, ongoing practice; this sprint performs it once, not continuously.

## Next Sprint

3.1 — Memory Store Foundation (SQLite + ChromaDB) (Level 3 — Intelligence; full sprint detail to be written when Level 3 becomes current, per [INDEX.md](INDEX.md), matching how Level 2's own detail was deferred until this task explicitly requested it).
