# Sprint 4.13 — Integration Testing & Level Freeze (Part A)

## Sprint ID

4.13

## Sprint Name

Integration Testing & Level Freeze (Part A)

## Purpose

Formally close **Level 4 Part A — Device Control & Workflow Automation**, mirroring Sprint 2.14's role for Level 2 and Sprint 3.14's role for Level 3. A full acceptance pass confirming Part 4 Phase 4.1 ("Safe desktop control. Permissions respected.") and Phase 4.2 ("Complex workflows execute correctly.") together, in one real, continuous system.

**This sprint does NOT tag `v0.4`.** Per the explicit scoping decision made before this Sprint Book was written (recorded in `docs/sprint_book/INDEX.md`'s Level 4 breakdown-changes note), Level 4 as a whole spans two Sprint Books: Part A (this one — Device Control, Workflow Automation) and Part B (Scheduler, Internet Agent — roadmap-granularity only, full detail deferred to its own future Sprint Book). Part 4's Master Plan defines `v0.4` as "Complete productivity assistant," a definition this Sprint Book does not redefine or shrink — `v0.4` remains gated on Part B also reaching its own freeze. This sprint's own closing act is a `v0.3.1`-shaped internal milestone marker in `docs/STATUS.md`/`docs/sprint_book/INDEX.md` only — not a semver tag — precisely so the distinction between "Part A is real and verified" and "Level 4/v0.4 is complete" stays visible rather than implied.

## Engineering Rationale

Sprint 2.14 and 3.14 both established the template this sprint follows: a new system-test tier driving one continuous scripted scenario through a real `CoreManager.startup()`/`shutdown()` with the entire relevant module graph registered; re-confirmation of every hardening sprint's scenarios at the system level; and an adversarial re-read of every new source file, on the well-established basis that both prior Levels' own adversarial re-reads each found real bugs no targeted hardening sprint had caught. There is no reason to expect Level 4 Part A's `device_control/`/`workflow/`/`security/` code is less likely to have equivalent gaps — if anything, more likely, given this is the project's first Level whose real, non-mocked verification can materially affect the state of the machine running it.

That last point is the one genuine, load-bearing difference from both prior Levels' closing sprints, and it governs this sprint's entire testing posture: **Level 2's real verification (real audio/models) and Level 3's real verification (real Ollama/Chroma) were both read-only with respect to the developer's actual machine and files.** Level 4 Part A's is not — a real acceptance run that launches applications, moves/deletes files, and runs commands must be sandboxed as carefully as a security-sensitive integration test in any other software project, not run with the same casual "just run it for real" posture Sprint 2.12's smoke run used. This sprint's own Acceptance Criteria and Testing Checklist encode that constraint explicitly, not as an afterthought.

## Objectives

- A `tests/system/test_level4_part_a_acceptance.py` driving one continuous scripted scenario — launch an application, perform file operations, manage its window, run an approved command, define and execute a multi-step workflow (including one step that triggers Sprint 4.7's confirmation flow and one that deliberately fails to exercise `continue_on_failure`) — through a real `CoreManager` with the entire Level 1–4 Part A module graph registered, **entirely confined to a disposable `tmp_path`-scoped environment** (its own `allowed_file_roots`, its own disposable test application, its own minimal `approved_commands` set — never the developer's real Documents/Desktop/running applications).
- Re-confirmation of all six of Sprint 4.12's hardening scenarios at the system level.
- An adversarial re-read of every `device_control/`, `workflow/`, and `security/` source file, with particular attention to the path-scoping (4.3), command-allowlisting (4.5), and permission-classification (4.7) boundaries — the highest-consequence logic in this Sprint Book, given the same scrutiny Sprint 3.14 gave `AuthorityEvaluator.evaluate()`'s own fail-safe-down guarantee.
- A real, non-mocked, human-supervised verification pass on the actual target laptop, but restricted to genuinely safe, disposable operations only (opening/closing Notepad, file operations confined to a throwaway scratch folder created and destroyed for this purpose) — the Level 4 Part A equivalent of Sprint 2.14's "live human voice round trip," and, like that criterion, explicitly named as the one step no automated test can fully substitute for (a person confirming JARMINEI actually did the safe, correct, expected thing on a real machine).
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` updated to reflect Level 4 Part A's completion, explicitly distinct from Level 4/`v0.4` as a whole (per this file's own Purpose section above).

## Dependencies

4.12 (Error Handling & Recovery Hardening)

## Files to Create

- `tests/system/test_level4_part_a_acceptance.py`
- `docs/changelog/0.3.1-level4-part-a.md` (or an equivalent internal-milestone note — the exact filename/format is an implementation-time decision, made consistent with `docs/changelog/README.md`'s existing conventions, not a new versioning scheme invented without checking those conventions first).

## Files to Modify

- `docs/STATUS.md` — Level 4 section split into "Part A" (marked complete, with the same caveats-and-detail style every prior Level's entry uses) and "Part B" (unchanged, still `Planned`); the top-level Level 4 row's target version note clarified to "target: v0.4, Part B pending."
- `docs/sprint_book/INDEX.md` — Level 4 Part A table rows (4.1–4.13) marked **Complete**; Milestones table gains an explicit note that `0.4` is gated on Part B, not on 4.13 alone.
- Any source file where the adversarial re-read finds a real gap, each documented as a "Post-Sprint Fix" on the sprint file that owns the affected code — the exact precedent Sprint 2.14/3.14 both established.

## Expected Classes

None new.

## Expected Interfaces

None new.

## Expected Functions

None new at the production-code level — this sprint is testing and verification; any function-level fixes arise only from what the adversarial re-read or acceptance run actually finds, exactly as Sprints 2.14/3.14 found and fixed real gaps without any of them being predicted in their own specs.

## Data Flow

```
tests/system/test_level4_part_a_acceptance.py:
  CoreManager.startup() — full Level 1-4 Part A graph, tmp_path-scoped DeviceControlConfig/WorkflowConfig
      ↓
  "launch a disposable test application" → verified via ActionAuditLog query
      ↓
  file create/move/rename/delete within tmp_path → verified via filesystem state + recycle-bin recoverability
      ↓
  window focus/move/minimize on the launched test application
      ↓
  an approved (test-only) command executes, output captured
      ↓
  a defined multi-step workflow (mixing safe and HIGH-risk-classified steps) executes:
      one step triggers Sprint 4.7's confirmation flow (auto-confirmed by a test double ConfirmationService)
      one step deliberately fails, exercising continue_on_failure=True and =False in separate sub-cases
      ↓
  WorkflowRunResult / ActionAuditLog records inspected for correctness
      ↓
  CoreManager.shutdown() — clean, all modules STOPPED, tmp_path environment torn down
```

## Implementation Tasks

1. Write and run `tests/system/test_level4_part_a_acceptance.py`, exclusively against a disposable `tmp_path` environment.
2. Re-run and confirm Sprint 4.12's six scenarios at the system level (via this same acceptance test or dedicated companion tests).
3. Adversarial re-read of every `device_control/`, `workflow/`, `security/` source file; fix any real gap found, documented as a Post-Sprint Fix on the owning sprint.
4. Supervised real-machine verification pass (safe, disposable operations only, human present to observe and confirm).
5. `docs/STATUS.md`/`docs/sprint_book/INDEX.md`/changelog updates per Files to Modify/Create above.

## Architecture Notes

This sprint changes no architecture — it is verification and, where the adversarial re-read finds real gaps, targeted fixes to already-shipped Level 4 Part A code, exactly matching Sprint 2.14's/3.14's own scope discipline ("this sprint is testing and verification... any function-level fixes arise only from what the adversarial re-read or acceptance run actually finds").

The decision to **not** tag `v0.4` here (Purpose, above) is itself the one genuinely load-bearing architectural/process decision this sprint makes, and it is made explicitly, in writing, rather than left ambiguous — matching this project's consistent practice of treating versioning/release-boundary decisions (e.g. `v0.2.0`'s deferred tag, Sprint 2.14) as real decisions worth stating plainly rather than assuming.

## Integration Considerations

- This is Level 4 Part A's final sprint — nothing further in this Sprint Book depends on it. Level 4 Part B, when its own future Sprint Book is written, will depend on this sprint's completed, frozen Part A exactly as Sprint 4.1 depended on Level 3's freeze (3.14).
- The real-machine verification pass's own safe-scope constraint (disposable operations only) should inform Level 4 Part B's eventual equivalent sprint — Scheduler/Internet Agent's own real-world verification will have a different but comparably real risk shape (a Scheduler that fires a reminder at the wrong time is annoying, not destructive; an Internet Agent making real network requests has its own distinct safety/privacy considerations) that Part B's own future closing sprint must reason about fresh, not assume identical to this one.

## Potential Risks

- **The single largest risk in this entire Sprint Book**: a real acceptance/verification run that is insufficiently sandboxed could genuinely damage real user data or launch unwanted real applications on the actual target laptop. This sprint's own Acceptance Criteria make the `tmp_path`/disposable-scope requirement a hard gate, not a suggestion — any test or manual step that cannot be confined this way must be redesigned before this sprint is considered complete, not run anyway "carefully."
- **An adversarial re-read finding a real gap in `security/policy_engine.py` or `device_control/file_operations.py`'s path-scoping** is the single most consequential class of bug this sprint could uncover, given what those two files guard against. Any such finding should be treated with the same seriousness Sprint 3.14 gave `MemoryStore`'s missing SQLite failure handling — fixed immediately, documented fully, not deferred.
- **Deferring the `v0.4` tag** means Level 4 Part A ships "complete but untagged" for however long Part B's own future Sprint Book takes to plan and execute — an accepted, deliberate trade-off (shipping a real, working, safely-scoped increment sooner) over the alternative (holding all of Level 4 back until Scheduler and Internet Agent both also exist), consistent with the Split option this Sprint Book was explicitly commissioned under.

## Acceptance Criteria

- Every scripted step in `test_level4_part_a_acceptance.py` succeeds against the real (not mocked) Level 1–4 Part A module graph, entirely within a disposable `tmp_path` environment.
- All six of Sprint 4.12's hardening scenarios are re-confirmed at the system level.
- The adversarial re-read is completed and its findings (if any) are fixed and documented.
- The supervised real-machine verification pass is performed and its outcome recorded — matching Sprint 2.14's own precedent of naming a manual step explicitly rather than silently assuming it happened.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` accurately reflect Level 4 Part A as complete and Level 4/`v0.4` as still gated on Part B — verified by a direct reading of both files after the update, not assumed correct from the diff alone.
- Matches Part 4 Phase 4.1's "Safe desktop control. Permissions respected." and Phase 4.2's "Complex workflows execute correctly," demonstrated together in one real run.

## Testing Checklist

- [ ] System: `test_level4_part_a_acceptance.py` full scripted scenario, `tmp_path`-scoped throughout.
- [ ] System: all six Sprint 4.12 hardening scenarios re-confirmed at this level.
- [ ] Regression: full existing Level 1–4 Part A suite passes with zero regressions.
- [ ] Manual, real hardware, supervised, disposable-scope only: application launch/close, a scratch-folder-confined file operation, a window operation, and a two-step workflow (one step requiring confirmation) all verified correct by a human observer on the actual target laptop.

## Documentation Checklist

- [ ] `docs/STATUS.md` — Level 4 split into Part A (complete, detailed) / Part B (planned, unchanged); `v0.4` target note clarified.
- [ ] `docs/sprint_book/INDEX.md` — Level 4 Part A rows marked Complete; Milestones table's `0.4` row annotated as Part-B-gated.
- [ ] `docs/changelog/` — the Part A internal-milestone entry.
- [ ] Every Post-Sprint Fix from the adversarial re-read, documented on its owning sprint file, per Sprint 2.14's/3.14's own established pattern.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium-High — comparable in scope to Sprints 2.14/3.14, with added care required for the real-machine verification's safety scope.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

None within this Sprint Book — Level 4 Part A is complete. Level 4 Part B (Scheduler & Internet Agent, currently `docs/sprint_book/INDEX.md` sprints 4.14–4.20 at roadmap granularity) is the next work to receive full sprint-book detail, in its own future Sprint Book, when it becomes current — per this project's own established "expand to full detail only when a level/part becomes current" practice (see `docs/sprint_book/README.md`'s Detail Status note).

## Future Considerations

- Level 4 Part B's own future Sprint Book should explicitly decide its real-world-verification safety posture before writing its own closing sprint, informed by (but not assumed identical to) this sprint's own disposable-scope discipline.
- Once Part B also freezes, a dedicated "Level 4 Combined Freeze" pass (or simply Part B's own closing sprint, scoped to also re-confirm Part A hasn't regressed) is what should actually tag `v0.4` — not assumed to be automatic once Part B's own component sprints are done.
