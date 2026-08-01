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

## Sprint Completion Report (2026-08-01)

Implemented as specified, authorized directly ("continue with the sprint 4.20"). **This closes Level 4 Part B and, with it, all of Level 4 (Productivity) — `v0.4`.**

`tests/system/conftest.py`'s `app_harness` fixture was refactored into a builder function (`_app_harness_impl()`) plus two thin fixtures — `app_harness` (unchanged, `SchedulerConfig()`'s realistic 30s/3600s defaults, used by every existing system test) and a new `fast_scheduler_app_harness` (0.3s intervals, matching `tests/integration/conftest.py`'s own established fast-interval precedent) — so `tests/system/test_level4_part_b_acceptance.py` could observe real Part B background-job recurrence through the real, complete `CoreManager` graph, not a hand-assembled one. **A genuine design question was resolved before writing that fixture, not assumed safe**: `CoreManager.shutdown()` stops modules in exact reverse registration order, and `task_scheduler`/`calendar_store` are registered first (Sprint 4.18's own real ordering requirement), so with fast intervals a background job can genuinely still be executing against another store's `SqliteClient` connection at the exact moment that store's own `stop()` closes it — the identical shape of race Sprint 4.18 originally found and worked around by simply staying slow everywhere else. Verified directly rather than assumed: Sprint 4.19's `threading.Lock` on `SqliteClient` (added to fix a genuine concurrent-corruption bug, not this one) independently serializes `close()` against `execute()`/`query()` — confirmed with a standalone reproduction (a background thread hammering `execute()` while `close()` runs concurrently from another thread) before relying on it: `close()` returned in ~16ms with no hang, and the background thread's very next call cleanly raised `RuntimeError("SqliteClient.connect() must be called before use.")`, the same caught-and-logged-without-crashing outcome APScheduler's own default executor already guarantees for any job exception. This let `fast_scheduler_app_harness` use `CoreManager`'s own plain, unmodified reverse-order shutdown safely.

`tests/system/test_level4_part_b_acceptance.py`'s one continuous scripted scenario covers, in order: a representative Part A device-control action (live voice turn, real `hostname.exe` launch) and a representative workflow run (direct `WorkflowExecutor.run()` call, no confirmation needed); a scheduled reminder created via a real live voice turn (`SCHEDULER` routing, persisted via `CalendarStore`); a SEPARATE, already-due reminder genuinely, proactively announced while idle; a live research query (`INTERNET_AGENT` routing) producing a real cited summary; and a direct confirmation that all three periodic-maintenance passes fire more than once. **Reminder creation and reminder announcement are deliberately split into two different items, not chained into one 60+-second wait** — `_parse_relative_time()` only resolves "in N minutes"/"in N hours" phrasing, so a live-turn-created reminder is always genuinely ~1+ minute out; waiting a real 60+ seconds inside an already-composite system test would be honest but needlessly slow, when the identical "genuinely announced when due" capability is already provable, fast, via the same directly-persisted-already-due-item technique Sprint 4.18/4.19 already established. **One real, simple bug was caught in my own first draft of this test, not a deep architectural issue**: `FakeTextToSpeech.spoken_event` is a `threading.Event` that's `.set()` on every `speak()` call but never auto-cleared — my own test forgot to `.clear()` it between the scripted turns (an established pattern, e.g. `test_level2_acceptance.py`), so the second/third turns' own `.wait()` calls returned immediately using a STALE already-set event from an earlier turn, and the test raced ahead to check `speak_calls[-1]` before the actual new turn had finished processing. Fixed by adding the missing `.clear()` calls; the test also got ~4x faster as a side effect (19s vs. 80s) since it stopped waiting out unrelated background-job noise it had accidentally raced past the real assertion point for.

**The adversarial re-read of every `scheduler/`/`internet/` source file found one real, previously-unfixed gap**: `internet/brave_search_provider.py`'s `BraveSearchProvider.search()` parsed its HTTP response's JSON payload OUTSIDE the try/except wrapping the request itself — `payload.get("web", {}).get("results", [])` only falls back to `{}` when the `"web"` key is genuinely absent; a real (if malformed/degraded) response shaped `{"web": null, ...}` makes it return `None` instead, and `.get(...)` on that raised a raw `AttributeError` this method's own docstring already promised never to leak. Confirmed as real, not theoretical, via a direct interactive check before fixing anything. Already masked in practice by `ResearchEngine.research()`'s own broad `except Exception`, so no user-facing behavior was ever actually broken — but a real contract violation in `BraveSearchProvider`'s own code, worth fixing on its own terms rather than left to rely on the outer catch. Fixed by moving the parsing inside the same try block; 2 new regression tests. Documented as a Post-Sprint Fix on `sprint_4_16.md` (the sprint that owns `brave_search_provider.py`) and `backlog/technical_debt.md` item 32. **A second, structurally-identical but lower-confidence finding was noticed while fixing the first, and deliberately NOT fixed here**: `decision/llm_client.py`'s `OllamaClient.generate()` accesses `response.response` just outside its own try/except — the same shape of gap, but `decision/llm_client.py` is a Level 3 file, genuinely outside this sprint's own `scheduler/`/`internet/` scope, and `response` is a real, typed `ollama._types.GenerateResponse` object (confirmed via the library's own type signature) rather than raw external JSON, meaningfully lower risk than the Brave finding. Logged as `backlog/technical_debt.md` item 33 for whenever that file is next touched, not chased as scope creep.

**Sprint 4.19's six hardening scenarios were re-confirmed at the system level with the same reasoned judgment Sprint 3.14/4.13 already applied to their own six** — explicitly reasoned, not assumed: (a) `SearchClient`/network failure and (b) `LanguageModelClient` failure are purely component-level (no `CoreManager`-dependent behavior at all) and already proven through a full live turn at Sprint 4.19's own integration tests; (c) `TaskScheduler` job isolation's own guarantee comes from `APScheduler` itself, not from anything `CoreManager` adds, and this file's own maintenance-recurrence check already re-confirms real jobs keep firing through the complete graph as a natural side effect; (d) the reminder/session-transition race is naturally re-exercised by this scenario's own reminder-announcement step (a real session ending, a real idle transition) without needing a dedicated adversarial function. None of these four were re-tested as dedicated functions. (e) `CalendarStore` SQLite failure and (f) TTS failure mid-proactive-announcement ARE genuinely composition-dependent and were re-confirmed as two dedicated functions in the same file, both passing on the first real run.

A new, opt-in `tests/system/test_level4_part_b_real_verification.py` mirrors `test_level3_real_model_verification.py`'s own established shape: a real Brave Search API call, real `SourceValidator` corroboration, and a real local Ollama summarization pass, chained end to end — skipping cleanly (never failing) unless BOTH `JARMINEI_INTERNET_SEARCH_API_KEY` is set AND a real, reachable Ollama instance with the configured model pulled is available (neither is, in this development session), each dependency checked and reported separately for a clear, actionable skip reason. The real, short-interval reminder-announcement capability named in this sprint's own Objectives ("if timing allows") was deliberately NOT duplicated into this file — it has no real network/Ollama dependency of its own, so it belongs in, and is already covered by, the always-run acceptance test instead.

Full-suite run: 1060 total, 1042 passing, 2 skipped (both correct: no real search API key or local Ollama in this environment), 16 failed — 15 already-tracked `test_text_to_speech.py` failures (`backlog/technical_debt.md` item 29) plus one instance of `test_full_level2_acceptance_scripted_conversation`, confirmed passing standalone immediately after — the same already-established, repeatedly-confirmed host-load flake class this project has documented many times this session, not a regression. `ruff check .` clean.

`docs/STATUS.md` (Level 4's own top-level heading and Part B section header both updated to reflect full completion; new Sprint 4.20 narrative paragraph) and `docs/sprint_book/INDEX.md` (4.20 row → `Complete`, the last remaining unlinked Part B row) updated. `docs/changelog/0.4.0.md` created, covering both Parts (Part A by reference to its own `0.3.1` internal milestone note, Part B in full). `backlog/technical_debt.md` item 31 updated to note this sprint's own expanded (but still never-run-against-a-live-key) real-verification surface; items 32/33 added for this sprint's own adversarial-re-read findings.

**The one criterion no automated test can satisfy — a supervised, real-machine, human-observed verification pass (a real spoken research question producing a sensible cited answer; a real scheduled reminder genuinely spoken aloud at the right time, unprompted, while idle) — was explicitly NOT performed this session**, matching every prior Level-freeze sprint's own precedent of naming rather than assuming a manual step happened. **`v0.4`'s own git tag is correspondingly NOT created by this sprint** — per this project's own established precedent (`v0.2.0`/`v0.3.0` alike), the tag is created only once that manual verification has actually happened and the user explicitly authorizes it, never assumed or created preemptively by whichever sprint finishes the automated work. **This closes the Master Sprint Book's Level 4 entirely — no next sprint exists within it. Level 5 (Companion, target `v0.5`) is next, at roadmap-granularity only until it becomes current, per this project's established practice.**
