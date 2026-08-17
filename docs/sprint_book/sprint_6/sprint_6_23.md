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

- [x] System: full Level 6 Part B scripted acceptance scenario.
- [x] Long-duration test.
- [x] Resource test.
- [x] `real_model` marker registered and migrated.
- [x] Full unit + integration + system suite, opt-in markers excluded.
- [x] `ruff check .`.

## Documentation Checklist

- [x] `docs/UAT_CHECKLIST.md` created.
- [x] `docs/STATUS.md` — Level 6 Part B and Level 6 overall → `Complete`.
- [x] `docs/sprint_book/INDEX.md` — 6.16–6.23 rows → `Complete`; Milestones table's `1.0` row confirmed.
- [x] `docs/sprint_book/README.md` — Detail Status note updated.
- [x] `changelog/1.0.0.md` created, explicitly naming the UAT checklist as the remaining gate.
- [x] `docs/backlog/technical_debt.md` — any new adversarial-re-read finding logged.
- [x] Sprint Completion Report appended to this file.

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

## Sprint Completion Report (2026-08-17)

Implemented as specified, continued from a prior session's own "continue with the implementation of sprint 6.23." No `AskUserQuestion` gate was needed — every Objective was a direct, literal instruction. Closes Level 6 Part B — and, joined with Sprint 6.15's own Part A freeze, all of Level 6.

**Objective 1 (Implementation Task 1) — implemented, with a real, mid-implementation design correction.** New `tests/system/test_level6_part_b_acceptance.py` — one continuous scripted scenario through the real, complete Level 1–6 (Part A + Part B) `CoreManager` graph, per Objectives: a fresh startup timed/RSS-measured against Sprint 6.16's own 110s/1000MB baseline (reused directly, not a new threshold); a real induced-CRITICAL `ResourceMonitor` reading confirming only `resource_sensitive=True` jobs pause; a real secret round trip through `SecretStore` confirmed never touching plaintext `local.yaml`; a real `KnowledgeGraphStore`/`UsageStore` purge cycle; a real `InternetConfig.enabled=False` block confirmed through a live conversation turn with zero outbound `SearchProvider` calls.

Two real, disclosed bugs were found and fixed while getting this test to genuinely pass, both in the test's own design, not in already-shipped production code:

1. A monkeypatch installed on `UsageTracker._on_tick`/`ReminderEngine._poll_due_items` *after* `request.getfixturevalue("stress_app_harness")` had already run silently had no effect — `TaskScheduler.add_job()` captures whatever bound method it's handed at registration time, and APScheduler holds that exact reference forever; a class-level patch applied afterward changes nothing the already-scheduled job actually calls. The test's own first version passed anyway (the counting wrapper was simply never invoked, so `tick_counts["usage_sample"] == 0` was vacuously true) — caught by code review before it could ship as a false-positive test, not by a failure. Fixed by moving the patch to before harness construction, mirroring `test_level6_part_b_resource_protection.py`'s own `job_tick_counts` fixture precedent exactly.
2. Once the patch-ordering fix made the counting genuine, the same assertion failed for real (`4 == 0`, not vacuously passing): `stress_app_harness` (Sprint 6.18) constructs its own `TaskScheduler` with `resource_monitor=None` — a deliberate Sprint 6.19 design choice (that sprint's own completion report: "`stress_app_harness` was deliberately left at the default (unwired) to avoid re-opening that sprint's own already-verified, already-documented behavior"). `TaskScheduler.add_job()` decides whether to wrap a `resource_sensitive=True` job at all exactly once, at registration time, based on `self._resource_monitor is not None` — a job registered through `stress_app_harness` can therefore never be resource-gated, regardless of what `ResourceMonitor.sample()` later returns. Fixed by using `fast_resource_protection_app_harness` (Sprint 6.19's own dedicated, already-verified resource-aware fixture, still the real, complete Level 1–6 graph) for this step instead of `stress_app_harness`.

**Objective 2 (Implementation Task 2) — implemented, with one real, disclosed design correction found via an honest test failure.** New `tests/system/test_level6_part_b_long_duration_and_resource.py` (2 tests), both genuinely separate from Sprint 6.18's own stress test, not a relabeling: `test_long_duration_multiple_full_session_round_trips_stay_healthy` drives several full wake→active→reply→`DORMANT` round trips across a 300s window (2.5× the stress test's own 120s), proving the full session lifecycle — not just conversation throughput — stays healthy, including repeated real wake-word re-detection after a genuine return to `DORMANT`, which the stress test deliberately never exercises. `test_resource_bounds_stay_within_documented_budget_across_sustained_operation` samples RSS/CPU repeatedly across a 60s sustained run.

The Resource test's own CPU assertion needed two real fixes, found via two genuine, informative failures rather than assumed correct from the outset:

1. Its first version asserted at least one sample must dip below 90% CPU, assuming natural idle gaps between real work. A real run instead measured a consistent 97–100% on every one of 12 samples — `stress_app_harness`'s own 13 real jobs, each ticking every 1.0s, mean there is always at least one real job executing somewhere in this process throughout the whole window; no natural idle gap exists to observe with this specific harness, a genuine property of a "stress" harness, not a bug. Fixed by replacing the intermittency requirement with an upper-bound sanity ceiling on *average* CPU (300%, since `psutil.Process.cpu_percent()` is not core-count-normalized) — real margin above one core's worth of legitimate continuous load, while still catching a genuine multi-core-saturating regression.
2. A second run then failed with "Timed out waiting for the microphone to enter ACTIVE_CAPTURE" — this test's own initial `wait_for_active_capture()` call had no `h.wake_engine.calls = 0` reset before it (mirroring the *shape* of Sprint 6.18's own stress test opening lines), but this session's own real ~130s fixture-setup cost comfortably outlasts the harness's `session_timeout_seconds`, so by the time the test body ran the mic's own fixture-setup-time wake match had already round-tripped back to `DORMANT`. Fixed by adding the same `h.wake_engine.calls = 0` reset this file's own `_drive_one_full_round_trip()` helper (used by the Long-duration test) already applies before every wait.

**Objective 3 (Implementation Task 3) — implemented.** New `docs/UAT_CHECKLIST.md` consolidates every disclosed-but-unautomated manual-verification item from every prior freeze sprint (2.14's wake-word round trip; 4.13's device-control/workflow real-machine pass; 4.20's research-question/reminder pass plus its own real-network opt-in tier; 5.16's presentation/VTube-Studio pass plus its own real-connectivity opt-in tier; 5.26's companion-intelligence pass; 6.15's planning/explanation/proactive pass) plus two new Part B items (a real Windows Credential Manager round trip, a real un-accelerated multi-hour observed run) into one human-runnable, cross-referenced, checkbox document — the first time "User acceptance tests" has a real, checkable artifact in this project's history rather than a scattered disclosure. Sprint 3.14 is named explicitly as having no equivalent manual gap (Ollama is fully scriptable), a real, disclosed asymmetry rather than a forced entry.

**Objective 4 (Implementation Task 4) — implemented.** New `real_model` marker registered in `pyproject.toml`, matching `real_search_api`'s own existing precedent exactly. Applied as `pytestmark = pytest.mark.real_model` to `test_level3_real_model_verification.py`; `test_level4_part_b_real_verification.py` carries both `real_model` and `real_search_api` (it genuinely needs both dependencies at once). `test_level5_part_a_real_verification.py` was deliberately left unmarked — its own real dependency (a separately-launched GUI application, VTube Studio) is a different enough shape that this sprint's own literal Objectives text names only `real_model`, and it already self-skips correctly via a live socket check; logged as `backlog/technical_debt.md` item 65 rather than forced into scope.

**Implementation Task 5 (adversarial re-read) — two real, disclosed documentation-staleness gaps found and fixed directly; one further real gap disclosed and logged, not fixed.**

- `docs/sprint_book/README.md`'s own Detail Status note still read "6.22 ... and 6.23 ... remain," despite Sprint 6.22's own completion report explicitly claiming "`docs/sprint_book/README.md` (Detail Status corrected) all updated" — the correction evidently never actually landed in the file. Fixed directly.
- `docs/sprint_book/INDEX.md`'s 6.18 row still described `test_sustained_load_all_jobs_active_no_hang_no_crash_bounded_rss` as "honestly red — real gap deliberately deferred to 6.19," with no note that Sprint 6.19 actually fixed it (confirmed directly: that sprint's own completion report states "`test_sustained_load_all_jobs_active_no_hang_no_crash_bounded_rss` (Sprint 6.18) now passes for the first time since Sprint 6.19 introduced it" — the row simply never caught up). Fixed directly.
- `test_level5_part_a_real_verification.py`'s own missing marker (see Objective 4 above) — logged as `backlog/technical_debt.md` item 65.

A targeted re-read of `main.py`'s Level 6 Part B wiring (`usage_store=None`/`knowledge_graph_store=None` fallback paths in `_null_level5_part_b_modules()`/`_null_level6_part_a_modules()`) confirmed these are genuine, already-documented graceful-degradation fallbacks (Sprint 5.24's/6.13's own "a broken subsystem must not take the rest of startup down with it" discipline), not an oversight — no further action needed.

**Implementation Task 6 (full-suite run) — clean, zero failures.** `tests/unit/`: 2298 passed + 1 skipped (183.39s) — unchanged from Sprint 6.22's own baseline, confirming this sprint's own test/doc-only changes introduced zero production-code regressions. `tests/integration/`+`tests/system/` together, opt-in `real_model`/`real_search_api` markers excluded (`-m "not real_model and not real_search_api"`): **106 passed + 3 skipped + 7 deselected, zero failures**, in 1016.47s (16m56s) — the 7 deselected exactly match the 6 parametrized/plain tests in `test_level3_real_model_verification.py` plus the 1 in `test_level4_part_b_real_verification.py`; the 3 skipped are `test_level5_part_a_real_verification.py`'s own tests, self-skipping cleanly (no VTube Studio running in this session). `ruff check .` clean repository-wide.

**A real, disclosed host-load observation, investigated per this project's own established "standalone re-run, confirm real regression vs. transient host load" discipline.** This sprint's own new acceptance test's Step 1 initially failed at 135.04s against Sprint 6.16's own 110s budget. Rather than assume a regression, the pre-existing, completely unmodified `test_startup_performance.py` (Sprint 6.16's own artifact, untouched by this sprint) was re-run standalone and *also* failed, at 123.80s — direct proof the slowdown is environmental, not caused by anything in this sprint's own changes. Three further independent measurements (127.82s, 136.88s, 129.44s) across separate `python -m pytest` process invocations confirmed a consistent ~123–137s band for this session specifically — most plausibly cumulative host load from many consecutive heavy `CoreManager`-construction test runs performed back-to-back within this same long working session (no CI, no isolated benchmark run), a materially different condition from Sprint 6.16's own original three-run calibration session. The threshold itself (110s/1000MB) was left unchanged, per this sprint's own explicit instruction to reuse Sprint 6.16's baseline directly rather than invent a new one — a single heavily-loaded session's own measurements are not sufficient grounds to recalibrate an already multi-run-averaged value without a controlled, isolated re-measurement. Both the acceptance test and `test_startup_performance.py` passed cleanly once run without the cumulative back-to-back load of this session's own preceding validation runs (confirmed in the final full-suite run above, run as a fresh, standalone `pytest tests/integration/ tests/system/` invocation).

**Documentation (Objective 5 / Implementation Task 7).** `docs/STATUS.md` — Level 6 Part B header → "✔ Complete (2026-08-17, Sprint 6.23)"; Part B phase-status table's `6.23 Final Testing` row → `Complete`; full Sprint 6.23 narrative appended; a closing "Level 6 (both Part A and Part B) is now formally frozen" paragraph added. `docs/sprint_book/INDEX.md` — 6.23 row → **Complete**; the Milestones table's `1.0 | 6.23` row was already present, added predictively when the Sprint Book was first written. `docs/sprint_book/README.md` — Detail Status note corrected to reflect all of 6.16–6.23 implemented and Level 6 Part B formally frozen. `docs/backlog/technical_debt.md` — new item 65. `changelog/1.0.0.md` — created, explicitly naming `docs/UAT_CHECKLIST.md` plus explicit user authorization as the two remaining gates before the tag itself, matching every prior release's own two-part-plus-manual-plus-authorization gating discipline.

**Level 6 Part B (sprints 6.16–6.23) is now formally frozen. Joined with Sprint 6.15's own Part A freeze, all of Level 6 is now formally frozen.** `v1.0` remains gated on a human actually running `docs/UAT_CHECKLIST.md` to completion, plus explicit user authorization — neither performed by this automated session, both required, matching every prior Level-freeze sprint's own precedent of naming a real, unautomatable gap rather than glossing over it, starting with Sprint 2.14's own wake-word round trip.

**No git commit made** — per this project's own "only commit when explicitly asked" rule; changes left in the working tree alongside all of Level 6 Part A's (6.1–6.15) and Part B's (6.16–6.22) own still-uncommitted work. **This is the last sprint of the Master Sprint Book.** Next: the user decides whether to commit the large uncommitted 6.1–6.23 backlog, and whether/when to begin the manual UAT pass toward `v1.0`.
