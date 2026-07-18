# Sprint 3.14 — Integration Testing & Level Freeze

## Sprint ID

3.14

## Sprint Name

Integration Testing & Level Freeze

## Purpose

Formally close Level 3 — Intelligence and Release v0.3, mirroring Sprint 2.14's role for Level 2. A full Level 3 Acceptance Pass confirming Phase 3.1 ("Memory stored correctly. Retrieval accurate."), Phase 3.2 ("Scores update correctly. Memory lifecycle functions."), and Phase 3.3 ("Correct subsystem selected. Explainability preserved.") all hold together, in one real, continuous system — not just per-sprint in isolation.

## Engineering Rationale

Sprint 2.14 established the template this sprint follows exactly: a new system-test tier driving one continuous scripted scenario through a real `CoreManager.startup()`/`shutdown()` with the entire Level graph registered; re-confirmation of every hardening sprint's scenarios at the integration level (not just the unit/integration level they originally shipped at); and an adversarial re-read of every new source file, on the well-established basis that Level 2's own adversarial re-read found two real bugs (`QuietModeController`, `ConversationSessionStore.purge_older_than()`) that no targeted hardening sprint had caught. There is no reason to expect Level 3's `memory/`/`decision/` code is less likely to have equivalent gaps — if anything, more likely, given this Level introduced the project's first non-deterministic (LLM-based) and first dual-backend-persistence components.

One genuine, notable difference from Level 2's own closing sprint: Level 2's one irreducibly-manual acceptance criterion was a live human voice round trip, because no automated test can make a person speak. **Level 3 has no equivalent irreducible manual step.** Ollama inference is text-in/text-out and fully scriptable — a real model call, unlike a real human voice, can be exercised by an automated test without a person in the loop. This is recorded explicitly as a genuine, positive difference in verification posture between the two Levels, not an oversight: this sprint's real-model verification (Ollama with the actual `gemma3` model pulled and running) is automatable, though still kept in a separate, longer-running, opt-in test tier rather than the fast committed suite — consistent with the "fakes for CI, real models for dedicated verification" split established since Sprint 2.1 (real model loads are slow; routine CI runs need to stay fast). ChromaDB's real embedding model falls into the same opt-in tier for the same reason.

## Objectives

- A `tests/system/test_level3_acceptance.py` driving one continuous scripted multi-turn conversation exercising memory storage, recall, confidence scoring, lifecycle cleanup, and the full Decision Engine pipeline together, through a real `CoreManager` with the entire Level 1+2+3 module graph registered.
- Re-confirmation of all six of Sprint 3.13's hardening scenarios at the system level.
- An adversarial re-read of every `memory/`/`decision/` source file.
- A separate, opt-in real-model verification pass (real Ollama + real ChromaDB embedding model, no fakes) confirming Intent Detection and Context Analysis produce sensible output against real conversational input.
- The `v0.3.0` git tag, created only after the above are complete.

## Dependencies

3.13 (Error Handling & Recovery Hardening)

## Files to Create

- `tests/system/test_level3_acceptance.py`
- `docs/changelog/0.3.0.md`

## Files to Modify

- `docs/STATUS.md` — Level 3 marked `✔ RELEASED`, mirroring the exact structure of the existing Level 1/Level 2 entries.
- `docs/sprint_book/INDEX.md` — Level 3 table rows marked **Complete**; Milestones table's `0.3` row confirmed against the actual closing sprint (`3.14`, not `3.10` — see this sprint's own note on the milestone table correction).
- Any source file where the adversarial re-read finds a real gap, each documented as a "Post-Sprint Fix" on the sprint file that owns the affected code — the exact precedent `sprint_2_6.md`/`sprint_2_7.md` established during Sprint 2.14's own re-read.

## Expected Classes

None new.

## Expected Interfaces

None new.

## Expected Functions

None new at the production-code level — this sprint is testing and verification; any function-level fixes arise only from what the adversarial re-read or acceptance run actually finds, exactly as Sprint 2.14 found and fixed real gaps without any of them being predicted in its own spec.

## Data Flow

```
tests/system/test_level3_acceptance.py:
  CoreManager.startup() — full Level 1+2+3 graph
      ↓
  scripted multi-turn conversation:
    turn 1: user states a fact worth remembering ("remember this: ...")
      → User Override Rule triggers → confidence_score=100, user_override=True
    turn 2: user asks a casual question → Minie persona selected via ContextAnalysis
    turn 3: user asks a technical question referencing turn 1's fact
      → MemoryRetrievalEngine surfaces the overridden memory → reply reflects it
    turn 4: a simulated critical ResourceMonitor alert arrives mid-conversation
      → PriorityQueueManager classifies IMPORTANT_ALERT correctly
      ↓
  MemoryLifecycleManager.run_cleanup_pass() invoked directly — confirms the
  turn-1 memory is excluded (user_override=True) while an unrelated low-
  confidence fixture record is correctly removed
      ↓
  CoreManager.shutdown() — clean, all modules STOPPED
```

## Implementation Tasks

1. `tests/system/test_level3_acceptance.py` — the full scripted scenario above, using fakes at the Ollama/Chroma boundary (consistent with every other committed test in this Sprint Book).
2. Re-run and confirm all six Sprint 3.13 hardening scenarios at the system level (real `CoreManager`, not isolated unit fixtures).
3. Adversarial re-read of every file created/modified by Sprints 3.1–3.13 — specifically checking for the same bug classes Sprint 2.14 found: a state machine that can get stuck mid-transition (parallel to `QuietModeController`), a method with no failure handling despite a sibling method having some (parallel to `purge_older_than()`), and any newly-introduced code path this Sprint Book's own risk sections flagged but didn't yet verify.
4. A separate, opt-in `tests/system/test_level3_real_model_verification.py` (not part of the fast committed suite — mirrors how real Whisper/Coqui verification was kept separate through Level 2) exercising `IntentDetector`/`ContextAnalyzer` against a real running Ollama instance with `gemma3` pulled, and `MemoryStore`/`ChromaMemoryClient` against a real embedding model — confirming classification/extraction is *reasonable* for a small fixed set of unambiguous example inputs (not asserting exact wording, since real LLM output isn't deterministic).
5. `docs/changelog/0.3.0.md` — written in the same structure as `changelog/0.2.0.md` (Summary, What Shipped, Verification, Notable Bugs Found and Fixed, Known Deferred Work, Next).
6. `docs/STATUS.md`, `docs/sprint_book/INDEX.md` updates.
7. Create the `v0.3.0` tag — **only after** steps 1–6 are complete and passing, per the same ordering discipline Sprint 2.14 itself established for `v0.2.0`.

## Architecture Notes

This sprint produces no new architecture — it is exclusively verification, documentation, and whatever fixes the verification surfaces. Every fix found here is recorded as a Post-Sprint Fix on the sprint file that owns the affected code, never folded silently into this sprint's own file, preserving the project's established practice of attributing each real bug to the component that had it.

## Integration Considerations

- This sprint is the natural point to reconsider `backlog/technical_debt.md`'s open items relevant to Level 3 — specifically the deferred periodic cadence for `MemoryLifecycleManager` (Sprint 3.6) and `ConversationSessionStore.purge_older_than()` (item 11, Sprint 2.7) — both remain legitimately deferred to a real Scheduler (Level 4), not resolved here, but this sprint's changelog should note both explicitly under Known Deferred Work, the same way `changelog/0.2.0.md` did.
- If the real-model verification pass (step 4) reveals `IntentDetector`/`ContextAnalyzer` prompt quality is inadequate, that is prompt-tuning feedback for those sprints' own future iteration, not a Level 3 blocker — Reliability over Intelligence means the *fail-safe paths* being correct matters more at this stage than classification being highly accurate.

## Potential Risks

- **Real-model verification (step 4) requires a running Ollama instance with `gemma3` pulled and a real ChromaDB embedding model download** — both genuinely new environment setup steps, tracked in `backlog/technical_debt.md` item 1 the same way Whisper/Coqui/openWakeWord's installations were tracked through Level 2.
- **The adversarial re-read may find real gaps requiring rework** — budgeted for explicitly in this sprint's time estimate, exactly as Sprint 2.14's did (it found and fixed two real bugs beyond its original spec).
- **Milestone table correction**: `sprint_book/INDEX.md`'s original Milestones table listed `0.3` as landing "After Sprint: 3.10" — that number predates this Sprint Book's expansion to 14 sprints and must be corrected to `3.14` as part of this sprint's own documentation update, the same kind of correction Level 2's milestone entry needed none of (it was already `2.14` from the start of that expansion). Flagged explicitly so it isn't missed.

## Acceptance Criteria

- The full Level 3 Acceptance Pass (`tests/system/test_level3_acceptance.py`) passes, exercising memory storage/recall, confidence scoring, user override, lifecycle cleanup, and the full Decision Engine pipeline together in one continuous run.
- All six Sprint 3.13 hardening scenarios re-confirmed passing at the system level.
- The adversarial re-read is completed and its findings (fixes or "no issues found") are documented, per file.
- The opt-in real-model verification pass runs successfully at least once against a real Ollama instance and a real ChromaDB embedding model, with results recorded in this sprint's own completion report.
- Phase 3.1, 3.2, and 3.3's Acceptance Criteria (per `04_Master_Implementation_Plan.md`) are each explicitly confirmed met, in combination, not just individually per sprint.
- `docs/changelog/0.3.0.md` is written and accurate.
- The `v0.3.0` tag exists only after every item above is complete.

## Testing Checklist

- [ ] System: full scripted multi-turn Level 3 acceptance scenario.
- [ ] System: all six Sprint 3.13 hardening scenarios, re-confirmed end-to-end.
- [ ] System (opt-in, not part of fast CI): real Ollama + real ChromaDB embedding model verification.
- [ ] Full project test suite (Levels 1–3) passing, `ruff check .` clean.

## Documentation Checklist

- [ ] `docs/changelog/0.3.0.md` written.
- [ ] `docs/STATUS.md` — Level 3 marked `✔ RELEASED`.
- [ ] `docs/sprint_book/INDEX.md` — Level 3 rows marked **Complete**; Milestones table's `0.3` entry corrected to sprint `3.14`.
- [ ] Any adversarial-re-read fixes documented as Post-Sprint Fixes on their owning sprint files.
- [ ] `docs/backlog/technical_debt.md` — Level 3's known deferred items (periodic lifecycle cadence, real-model environment setup) confirmed still accurately tracked.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md). This sprint closes Level 3 — Intelligence and Release v0.3.

## Estimated Complexity

Medium-High.

## Estimated Development Time

2–2.5 days (excluding whatever rework the adversarial re-read surfaces, budgeted separately per Potential Risks, consistent with how Sprint 2.14's own actuals exceeded its initial estimate).

## Next Sprint

4.1 — Application Control (Level 4 — Productivity begins; per `sprint_book/INDEX.md`'s existing roadmap-granularity plan, to be expanded to full detail when Level 4 becomes current, per the same Detail Status convention this Sprint Book itself followed for Level 3).

## Future Considerations

- Level 4's Device Control sprint (4.1) is the first real candidate to populate `AuthorityEvaluator`'s `approved_emergency_procedures` whitelist (Sprint 3.11) — flagged here as the concrete handoff point between Level 3's Decision Engine and Level 4's first real "engine" to select.
- A real periodic cadence for `MemoryLifecycleManager` (Sprint 3.6) and `ConversationSessionStore.purge_older_than()` (Sprint 2.7) both remain open, best resolved together once Level 4's Scheduler (Sprint 4.8+) exists — do not resolve one without considering the other, since both are instances of the same underlying gap (no periodic-task infrastructure exists before Level 4).
