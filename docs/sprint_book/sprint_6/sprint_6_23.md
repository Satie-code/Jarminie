# Sprint 6.23 — Full Test Suite Pass (unit/integration/system/UAT)

## Sprint ID

6.23

## Sprint Name

Full Test Suite Pass (Unit/Integration/System/UAT)

## Purpose

Close Level 6 Part B — and, joined with Sprint 6.15's own Part A freeze, all of Level 6 — with Phase 6.5's own full named list: "Unit Tests. Integration Tests. System Tests. Long-duration tests. Resource tests. User acceptance tests." The six-part closing ritual every prior Level/Part has used (2.14, 3.14, 4.13/4.20, 5.16/5.26, 6.15), plus the three test categories this project has named in its own locked spec since [04_Master_Implementation_Plan.md](../../04_Master_Implementation_Plan.md) was first written but never once built: Long-duration, Resource, and User acceptance tests. This is the sprint that gates `v1.0`.

## Engineering Rationale

Research confirms the current baseline precisely: 118 unit files (~2,005 tests), 13 integration files (~75 tests), 10 system files (~28 tests) — Unit/Integration/System are real, extensive, and current (Sprint 6.15's own last full run: 2,336 passing + 5 skipped). **Long-duration, Resource, and User acceptance tests have never existed as runnable artifacts in this codebase** — confirmed by a repo-wide search finding zero matches for any of the three shapes. Sprints 6.16 (a startup/resource baseline) and 6.18 (stress/recovery infrastructure) both already built real pieces of what Long-duration/Resource tests need; this sprint is where those pieces get extended into the locked spec's own two named categories for real, and where "User acceptance tests" — a category every prior freeze sprint has quietly satisfied only by *disclosing* an outstanding manual-verification gap (2.14's wake-word round trip through 6.15's planning/explanation/proactive checks), never by giving it a real, checkable shape — finally gets one: a single, consolidated, human-runnable UAT checklist naming every one of those disclosed items in one place for the first time, rather than scattered across nine separate freeze-sprint completion reports.

A second, disclosed correction: `pyproject.toml` registers exactly one pytest marker (`real_search_api`); the "real model" system tests instead self-skip via an ad hoc runtime Ollama-reachability check, not a marker — a real, minor inconsistency this sprint closes by registering a matching `real_model` marker, the same small, well-precedented polish item this sprint's own closing character invites.

## Objectives

- `tests/system/test_level6_part_b_acceptance.py` — one continuous scripted scenario through the real, complete Level 1–6 (Part A + Part B) `CoreManager` graph: a fresh startup timed and RSS-measured against Sprint 6.16's own documented baseline; a sustained multi-job window (reusing Sprint 6.18's own accelerated-interval harness) with a real induced-CRITICAL resource reading confirmed to pause only the `resource_sensitive=True` jobs (Sprint 6.19); a secret round-trip through `SecretStore` confirmed never touching plaintext `local.yaml` (Sprint 6.20); a real `KnowledgeGraphStore`/`UsageStore` purge cycle and an `InternetConfig.enabled=False` block confirmed for real (Sprint 6.21).
- Extend Sprint 6.18's stress scenario into a genuine "Long-duration test" (a longer, still-accelerated-interval sustained run, explicitly labeled and separated from the shorter stress scenario) and a genuine "Resource test" (an explicit assertion suite over RSS/CPU bounds across that sustained run, building directly on Sprint 6.16's own single-point baseline).
- `docs/UAT_CHECKLIST.md` — a new, single, consolidated, human-runnable User Acceptance Test document, naming every disclosed-but-unautomated manual-verification item from every prior freeze sprint (2.14 wake-word round trip; 3.14 memory/decision real-model verification; 4.13/4.20 device-control/workflow and scheduler/internet real-world checks; 5.16/5.26 presentation/companion real-hardware checks; 6.15 planning/explanation/proactive real-conversation checks) plus this Part's own new items (a real secret genuinely round-tripping through Windows Credential Manager; a real, sustained multi-hour run observed rather than just accelerated-interval-simulated) as one real checklist a human can run through and check off — giving "User acceptance tests" concrete shape for the first time in this project's history.
- Register a `real_model` pytest marker in `pyproject.toml`, matching `real_search_api`'s own existing precedent; migrate the ad hoc Ollama-reachability self-skip in `tests/system/test_level3_real_model_verification.py` and its siblings to use it.
- Full-suite verification (unit + integration + system, opt-in real-model/real-search markers excluded); `ruff check .` clean.
- `docs/STATUS.md`, `docs/sprint_book/INDEX.md`, `docs/sprint_book/README.md` updated to reflect Level 6 Part B — and all of Level 6 — fully `Complete`. Milestones table's `1.0` row confirmed reachable.

## Dependencies

6.22 (documentation must be current before this sprint's own closing narrative is written), 6.16–6.21 (everything this sprint's own acceptance scenario and UAT checklist verify).

## Files to Create

- `tests/system/test_level6_part_b_acceptance.py`
- `docs/UAT_CHECKLIST.md`

## Files to Modify

- `pyproject.toml` (`real_model` marker registration)
- `tests/system/test_level3_real_model_verification.py` and its siblings (marker migration)
- Determined further by the adversarial re-read (see Implementation Tasks) — any genuine gap found gets a Post-Sprint Fix on its owning sprint's own file, or a new `backlog/technical_debt.md` entry if sized beyond this sprint's own scope, matching this project's established convention.

## Expected Classes

None new.

## Expected Functions

None new — this sprint is verification and consolidation, not implementation, matching every prior freeze sprint's own precedent.

## Data Flow

The full Level 1–6 pipeline (Part A + Part B), exercised end-to-end — no new data flow, confirmation of every flow Sprints 6.16–6.22 already documented.

## Implementation Tasks

1. `tests/system/test_level6_part_b_acceptance.py` — the full scripted scenario described in Objectives.
2. Long-duration/Resource test extension of Sprint 6.18's own stress infrastructure, per Objectives.
3. `docs/UAT_CHECKLIST.md` — the consolidated checklist, per Objectives, cross-referencing each item back to the freeze sprint that first disclosed it.
4. `real_model` marker registration and migration.
5. Adversarial re-read of every Level 6 Part B file (6.16–6.22) plus a re-read of `main.py`/`voice/pipeline.py`'s own cumulative Level 6 Part B changes, matching every prior freeze sprint's own mandated "find at least one more thing" discipline.
6. Full-suite run(s), investigating any failure per this project's own established discipline (standalone re-run to distinguish a real regression from an already-documented flake class).
7. `docs/STATUS.md`/`docs/sprint_book/INDEX.md`/`docs/sprint_book/README.md` — Level 6 Part B and Level 6 overall → `Complete`; Milestones table's `1.0` row confirmed.
8. `changelog/1.0.0.md` — this project's first major-version changelog entry, matching the depth every prior release changelog has used, explicitly naming the UAT checklist as the one remaining gate before the tag itself.
9. Sprint Completion Report appended to this file once implemented, per every prior freeze sprint's own precedent.

## Architecture Notes

Like every prior freeze sprint, this sprint changes no production behavior by design beyond what a genuine adversarial-re-read finding requires — its own job is to verify, consolidate, and (for the first time) give "User acceptance tests" a real, checkable artifact, not to add new capability.

## Integration Considerations

- `v1.0` is **not** tagged by this sprint automatically — gated on a human actually running `docs/UAT_CHECKLIST.md` to completion plus explicit user authorization, the identical two-part-plus-manual-plus-authorization discipline `v0.2.0`/`v0.3.0`/`v0.4.0`/`v0.5` each already established, now extended to a genuinely two-Part Level for the first time at the scale of a full major version.
- No CI pipeline exists to run this sprint's own Long-duration/Resource tests on a recurring schedule — named explicitly in Future Considerations, not built speculatively here.

## Potential Risks

- **The UAT checklist's own real value depends entirely on a human actually running it** — this sprint can build and populate the document, but cannot itself perform the manual verification it names, the same honest limitation every prior freeze sprint's own "outstanding, not performed" disclosure has already carried; this sprint makes that gap concrete and actionable rather than resolving it.
- **A Long-duration/Resource test suite built without a CI host to run it repeatedly may drift stale** (a threshold tuned once, on one machine, at one point in time) — disclosed explicitly, matching Sprint 6.16's own already-disclosed threshold-generosity trade-off.

## Acceptance Criteria

- The full scripted scenario (Objectives, item 1) passes against the real, complete Level 1–6 `CoreManager` graph.
- Long-duration and Resource tests exist as real, runnable, separately-identifiable pytest artifacts (not merely a relabeling of Sprint 6.18's own stress scenario).
- `docs/UAT_CHECKLIST.md` exists, consolidating every prior freeze sprint's own disclosed manual-verification gap plus this Part's own new items, in one place, for the first time.
- The adversarial re-read either finds no new gap, or any gap found is disclosed and either fixed (if sized within this sprint's own scope) or logged to `backlog/technical_debt.md`.
- Full test suite passes with zero unexplained failures.
- `ruff check .` clean repository-wide.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md`/`docs/sprint_book/README.md` all accurately reflect Level 6 (both Parts) fully `Complete`.

## Testing Checklist

- [ ] System: full Level 6 Part B scripted acceptance scenario.
- [ ] Long-duration test.
- [ ] Resource test.
- [ ] `real_model` marker registered and migrated.
- [ ] Full unit + integration + system suite, opt-in markers excluded.
- [ ] `ruff check .`.

## Documentation Checklist

- [ ] `docs/UAT_CHECKLIST.md` created.
- [ ] `docs/STATUS.md` — Level 6 Part B and Level 6 overall → `Complete`.
- [ ] `docs/sprint_book/INDEX.md` — 6.16–6.23 rows → `Complete`; Milestones table's `1.0` row confirmed.
- [ ] `docs/sprint_book/README.md` — Detail Status note updated.
- [ ] `changelog/1.0.0.md` created, explicitly naming the UAT checklist as the remaining gate.
- [ ] `docs/backlog/technical_debt.md` — any new adversarial-re-read finding logged.
- [ ] Sprint Completion Report appended to this file.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

High.

## Estimated Development Time

3–4 days.

## Risks

See Potential Risks above.

## Next Sprint

None — this is the final sprint of this Sprint Book. `v1.0` follows, gated on `docs/UAT_CHECKLIST.md` plus explicit user authorization.

## Future Considerations

- A real CI pipeline (currently entirely absent from this repository — no `.github/workflows/`, no `tox.ini`, no scheduled runner of any kind) would let Long-duration/Resource tests run repeatedly and their own thresholds be tracked over time rather than tuned once — real, valuable future infrastructure work, deliberately not built speculatively inside a Stabilization sprint whose own locked-spec scope never named it.
- Beyond `v1.0`: the Future Roadmap named in [04_Master_Implementation_Plan.md](../../04_Master_Implementation_Plan.md) (desktop sync, Android, multi-device, cloud sync, smartwatch, vision, smart home, plugins, multi-user) — explicitly out of Version 1's own scope, unchanged by this sprint.
