# Sprint 4.20 — Integration Testing & Level Freeze (Part B)

## Sprint ID

4.20

## Sprint Name

Integration Testing & Level Freeze (Part B)

## Purpose

Formally close Level 4 Part B — Scheduler & Internet Agent — and, with it, all of Level 4 (Productivity), mirroring Sprint 2.14/3.14/4.13's own identical role for their respective Levels/Parts. **This is the sprint `v0.4` itself is gated on** (`docs/sprint_book/INDEX.md`'s own Milestones table: *"0.4 | 4.20 | Complete productivity assistant (gated on BOTH Part A/4.13 AND Part B/4.20)"*) — no earlier sprint in this Sprint Book, including Sprint 4.13, is authorized to create that tag.

## Engineering Rationale

**New sprint**, following the exact precedent Sprint 2.14/3.14/4.13 already established for themselves: one final, broad-scope sprint combining a full system-level acceptance pass, a re-confirmation of the prior hardening sprint's (4.19) scenarios at the fully-integrated level, and an adversarial re-read of every source file this Sprint Book touched — no new architecture, the widest verification surface of the whole Sprint Book.

**This sprint's own acceptance pass must cover Level 4 as a *whole*, not just Part B in isolation** — `v0.4`'s own definition ("Complete productivity assistant") spans both parts, and this is the first sprint with the standing and the full, fully-composed graph to actually confirm that together. Concretely: this sprint's own system test re-drives representative scenarios from Sprint 4.13's own acceptance pass (a device-control action, a workflow run) *alongside* new Part B scenarios (a scheduled reminder, a research query) in one continuous scripted run through the real, complete Level 1–4 `CoreManager` graph — the same "one continuous scripted conversation through everything" shape every prior Level-freeze sprint has used, now spanning two Sprint Books' worth of capability for the first time.

**A real, opt-in network-and-model verification tier is required, not optional**, mirroring `tests/system/test_level3_real_model_verification.py`'s own established precedent (Sprint 3.14) for exactly the same reason: Sprint 4.16/4.17's own fast test suites necessarily fake the `SearchClient`/`LanguageModelClient` boundary, so no automated fast-suite run has ever actually exercised a real search query, a real summarization pass over real search results, or (per Sprint 4.16's own Testing Checklist) confirmed the chosen search provider still behaves as expected against the live internet. This sprint is where that real, skipped-by-default verification finally runs.

**The adversarial re-read must specifically check `scheduler/`'s and `internet/`'s own SQLite/network failure handling against the real, fully-wired graph** — matching Sprint 3.14's own discovery (`MemoryStore`'s SQLite operations had zero failure handling despite a hardened sibling) and Sprint 4.13's own discovery (`WorkflowStore`'s deferred hardening, resolved once a second real caller existed) as the two most directly analogous precedents for what this kind of re-read tends to actually find.

## Objectives

- A new `tests/system/test_level4_part_b_acceptance.py`: one continuous scripted scenario spanning both Part A and Part B capability through the real, full `CoreManager` graph.
- A new, opt-in `tests/system/test_level4_part_b_real_verification.py`: a real network search, a real local-Ollama summarization pass, and (if timing allows within a bounded test window) a real, short-interval reminder announcement — mirroring `test_level3_real_model_verification.py`'s own skip-by-default shape.
- Re-confirmation of all six Sprint 4.19 hardening scenarios at the system level, matching Sprint 3.14's/4.13's own precedent (re-testing what's genuinely worth re-testing at a higher level, explicitly reasoning about which of the six don't need a third repetition, the same judgment call Sprint 3.14/4.13 both made and documented).
- An adversarial re-read of every `scheduler/`/`internet/` source file, per Engineering Rationale above.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` updated to mark Level 4 (both parts) fully `Complete`; `docs/changelog/0.4.0.md` drafted.
- The one criterion no automated test can satisfy — a supervised, real-machine verification pass (a real spoken research question producing a sensible cited answer; a real scheduled reminder genuinely spoken aloud at the right time, unprompted, while the system is idle) — is named as outstanding, not performed automatically, matching every prior Level-freeze sprint's own identical treatment of its own equivalent manual step.

## Dependencies

4.19 (Error Handling & Recovery Hardening, Part B).

## Files to Create

- `tests/system/test_level4_part_b_acceptance.py`
- `tests/system/test_level4_part_b_real_verification.py` (opt-in, skipped by default)
- `docs/changelog/0.4.0.md`

## Files to Modify

- `docs/STATUS.md` — Level 4 marked fully `Complete` (both Part A and Part B); the top-level Level 4 heading's own "Part B pending" qualifier removed.
- `docs/sprint_book/INDEX.md` — all Part B rows (4.14–4.20) marked `Complete`, each linked to its own now-detailed file (mirroring how Part A's rows were updated at Sprint 4.13).
- `backlog/technical_debt.md` — any items closed or newly logged by this sprint's own adversarial re-read.

## Expected Classes

None new — this sprint is testing and documentation, the same "no new architecture" shape Sprint 2.14/3.14/4.13 all shared.

## Expected Interfaces

None new.

## Expected Functions

None new at the public API level, beyond whatever narrow fixes the adversarial re-read finds genuinely necessary (documented as Post-Sprint Fixes on the owning sprint files, per this project's own established convention).

## Data Flow

Not applicable in the way earlier sprints used this section — this sprint verifies existing data flows end-to-end rather than introducing new ones; see `sprint_4_18.md`'s own Data Flow diagrams for what's being verified here.

## Implementation Tasks

1. `tests/system/test_level4_part_b_acceptance.py` — one continuous scripted scenario: a live device-control action (re-confirming Part A still works through the complete graph), a workflow run, a scheduled reminder created via a live turn and genuinely announced when due while idle, a live research query producing a real (fake-boundary) cited summary, and a direct verification that the three periodic-maintenance passes (items 11/15) each fire more than once within the test's own bounded window.
2. `tests/system/test_level4_part_b_real_verification.py` — real network search, real local Ollama summarization, skip-cleanly-if-unavailable (matching `test_level3_real_model_verification.py`'s own two-layer skip-check precedent: reachability AND the configured provider/model actually being usable).
3. Re-confirm Sprint 4.19's six hardening scenarios at the system level — explicitly reason about and document which, if any, don't need a third repetition, mirroring Sprint 3.14's/4.13's own precedent.
4. Adversarial re-read of every `scheduler/`/`internet/` source file for unhandled-exception paths and untested documented risks, fixing what's found (documented as Post-Sprint Fixes on the owning sprint files) and logging what's deliberately deferred.
5. `docs/STATUS.md`, `docs/sprint_book/INDEX.md`, `docs/changelog/0.4.0.md` updates.
6. Full regression run across the entire Level 1–4 suite.

## Architecture Notes

No new architecture is introduced by this sprint, per its own Purpose — matching every prior Level-freeze sprint's own identical constraint. Any real gap the adversarial re-read finds gets a narrow, targeted fix (never a redesign) at the file that owns it, documented as a Post-Sprint Fix, the same discipline Sprint 3.14/4.13 both already established and this Sprint Book has followed consistently since.

## Integration Considerations

- This sprint is the last one in Level 4 Part B — no further Part B sprint exists after it. Level 5 (Companion) is next, still at roadmap-granularity only per `docs/sprint_book/INDEX.md`, expanded to full detail only when it becomes current, per this project's own established practice.
- `v0.4`'s own tag creation is explicitly **not** automatic even once this sprint's own automated work is done — per every prior release's own precedent (`v0.2.0`'s tag deferred until a human wake-to-reply round trip; `v0.3.0`'s tag created only after the user explicitly said so in the same session as its own real-verification pass), the tag is created only once (a) this sprint's own outstanding manual real-machine verification has actually happened, and (b) the user explicitly authorizes creating it — never assumed or created preemptively by whichever sprint merely finishes the automated work.

## Potential Risks

- **The real-verification tier (Task 2) depends on external, non-deterministic state** (a live network, a live search provider, a live local Ollama instance) in a way no prior Level's own real-verification tier has combined this many simultaneously-required external dependencies — a clean, honest skip (not a failure) when any one of them is unavailable is essential, the same discipline `test_level3_real_model_verification.py` already established for a smaller set of dependencies.
- **The full scripted acceptance scenario (Task 1) is now the longest, most composite system test in this project's history**, spanning two Sprint Books' worth of capability in one continuous run — real timing-sensitivity risk (the same "passes standalone, occasionally times out under full-suite load" flake class already documented for `test_full_level2/3_acceptance_scripted_conversation`) is a plausible, acceptable outcome to find and document, not necessarily a sign of a real bug, matching this project's own established judgment call for that flake class.
- **`backlog/technical_debt.md` item 17 remains only partially resolved even after this sprint** (only the `SCHEDULED_REMINDER` source is wired; `IMPORTANT_ALERT`/`WELLNESS`/`GENERAL_SUGGESTION` sources still have no live producer) — this sprint's own documentation update must state that honestly, not overstate full resolution the way an earlier documentation pass once had to be corrected for this exact item (Sprint 3.14's own finding).
- **The search-provider decision from Sprint 4.16 is now load-bearing for `v0.4` itself** — if that provider proves unreliable or rate-limited during this sprint's own real-verification pass, that is a genuine, real finding worth surfacing to the user rather than silently working around (e.g. by loosening test assertions), the same "investigate and report, don't quietly paper over" discipline this project has applied to every prior real-environment surprise (the Python 3.12 reinstall, the PySide6/shiboken6/six bug, etc.).

## Acceptance Criteria

- Phase 4.3 ("Scheduling reliable. No duplicate reminders.") and Phase 4.4 ("Reliable research. Clear citations.") acceptance criteria, per `04_Master_Implementation_Plan.md`, are both confirmed together via the full scripted system test.
- Every Sprint 4.19 hardening scenario is re-confirmed correct at the system level (or explicitly, reasonedly not re-tested a third time).
- The real, opt-in verification tier passes when its external dependencies are available, and skips cleanly (never fails) when they are not.
- Full Level 1–4 (Part A + Part B) test suite passes with no regressions.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` accurately reflect Level 4's complete, frozen state; `docs/changelog/0.4.0.md` exists.
- The one criterion no automated test can satisfy is named explicitly as outstanding in this sprint's own completion report, not silently omitted or assumed done.

## Testing Checklist

- [ ] System: full scripted Part A + Part B scenario through the real, complete `CoreManager` graph.
- [ ] System: a scheduled reminder is genuinely, proactively announced while idle, within the test's own bounded window.
- [ ] System: the three periodic-maintenance passes each fire more than once within the test's own bounded window.
- [ ] Opt-in/real: a real network search + real local summarization, skip-clean if unavailable.
- [ ] Re-confirmation: all six Sprint 4.19 scenarios at the system level (or explicit, documented reasoning for skipping a repeat).
- [ ] Adversarial: every `scheduler/`/`internet/` source file re-read for unhandled-exception paths and untested documented risks.
- [ ] Full regression: entire Level 1–4 suite passes.

## Documentation Checklist

- [ ] `docs/STATUS.md` — Level 4 marked fully `Complete` (Part A + Part B).
- [ ] `docs/sprint_book/INDEX.md` — all Part B rows marked `Complete` and linked.
- [ ] `docs/changelog/0.4.0.md` — created, mirroring `0.1.0.md`/`0.2.0.md`/`0.3.0.md`'s own structure.
- [ ] `backlog/technical_debt.md` — items closed/updated per this sprint's own real findings, including an honest, precise final state for item 17.
- [ ] Any Post-Sprint Fixes documented on their owning sprint files, per this project's established convention.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium–High.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

None within this Sprint Book — Level 4 (Productivity) is complete. Level 5 (Companion, target `v0.5`) is next, at roadmap-granularity only in `docs/sprint_book/INDEX.md` until it becomes current, per this project's established "expand when current" practice (see `docs/sprint_book/README.md`'s own Detail Status note).

## Future Considerations

- Level 5's Wellness Engine (5.2–5.5) is expected to reuse `ReminderEngine.postpone()` and the proactive-announcement mechanism (4.15/4.18) directly, per those sprints' own named forward-compatibility notes — not built here.
- `backlog/technical_debt.md` item 17's remaining open sources (`IMPORTANT_ALERT`/`WELLNESS`/`GENERAL_SUGGESTION`) — real future work for whichever sprint first produces one of those signals, not this Sprint Book's own job.
- A second, redundant search provider, result caching, recurring/repeating calendar items — every Future Consideration named in Sprints 4.14–4.17 remains open and un-actioned by this freeze sprint, listed here only as a pointer back to where each was originally named, not repeated in full.
