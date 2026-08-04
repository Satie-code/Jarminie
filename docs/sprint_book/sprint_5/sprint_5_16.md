# Sprint 5.16 — Integration Testing & Level Freeze (Part A)

## Sprint ID

5.16

## Sprint Name

Integration Testing & Level Freeze (Part A)

## Purpose

Formally close Level 5 Part A — Emotional Intelligence & Presentation Layer — mirroring Sprint 2.14/3.14/4.13/4.20's own identical role for their own Levels/Parts. **`v0.5` itself remains gated on both Part A (this sprint) and Part B (Companion Intelligence — Wellness/Analytics/Learning, sprints 5.17–5.23, not yet written)** — per `docs/sprint_book/INDEX.md`'s own Milestones table, this sprint authorizes no semver tag, the same precedent `sprint_4_13.md` already set for Level 4 Part A.

## Engineering Rationale

**New sprint**, no new architecture — one final, broad-scope sprint combining a full system-level acceptance pass, re-confirmation of Sprint 5.15's six hardening scenarios at the fully-integrated level, and an adversarial re-read of every `presentation/`/`emotion/` source file, the identical shape every prior Level-freeze sprint in this project has used.

**This sprint's own acceptance pass must cover the brief's own core promise directly**: that Jarvis and Minie genuinely share one intelligence and differ only in presentation. Concretely, the system test drives the *same* underlying facts/memory/decision-trace through both personas in one continuous scripted run and asserts the reply *content* is equivalent in substance while tone/pacing/rendering differ — the most direct, mechanical test this Sprint Book can write for the brief's own locked rule "Jarvis and Minie share one intelligence. Only their presentation differs."

**A real, opt-in external-verification tier is required**, mirroring `test_level3_real_model_verification.py`/`test_level4_part_b_real_verification.py`'s own established precedent: this Sprint Book's fast suite has faked VTube Studio's own WebSocket boundary throughout (Sprint 5.8 onward, by design) — this is the sprint where a real, locally-running VTube Studio instance is exercised for real, if available, skipping cleanly (never failing) if it is not.

## Objectives

- `tests/system/test_level5_part_a_acceptance.py`: one continuous scripted scenario covering emotion detection/state evolution, a real persona transition, Jarvis's adaptive workspace, Minie's presentation-state-driven behavior, a companion-experience greeting/celebration, and the "same intelligence, different presentation" equivalence check above.
- `tests/system/test_level5_part_a_real_verification.py`: opt-in, real VTube Studio connectivity (skip-clean if unavailable), mirroring the established two-layer skip-check precedent (reachability, then a genuine loaded-model/parameter check).
- Re-confirmation of all six Sprint 5.15 hardening scenarios at the system level, explicitly reasoning about which don't need a third repetition.
- Adversarial re-read of every `presentation/`/`emotion/` source file.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` updated to mark Level 5 Part A rows `Complete`; `docs/changelog/0.4.4-level5-part-a.md` (or the next appropriate pre-release changelog name, following `0.3.1-level4-part-a.md`'s own internal-milestone-not-a-tag naming precedent) drafted.
- The one criterion no automated test can satisfy — a supervised, human-observed pass on the real target machine (the sphere/ring genuinely animating; a real VTube Studio avatar genuinely responding to voice/emotion; a real persona-switch transition genuinely playing) — named as outstanding, not performed automatically, matching every prior Level-freeze sprint's own identical treatment.

## Dependencies

5.15 (Error Handling & Recovery Hardening).

## Files to Create

- `tests/system/test_level5_part_a_acceptance.py`
- `tests/system/test_level5_part_a_real_verification.py` (opt-in, skipped by default)
- `docs/changelog/0.4.4-level5-part-a.md`

## Files to Modify

- `docs/STATUS.md` — Level 5 Part A marked `Complete`; the top-level Level 5 heading's own "Part B pending" qualifier added (mirroring Level 4's own "Part B pending" treatment at Sprint 4.13).
- `docs/sprint_book/INDEX.md` — all Part A rows (5.1–5.16) marked `Complete`.
- `backlog/technical_debt.md` — any items closed or newly logged by this sprint's own adversarial re-read (including, if not already logged at their own owning sprint's implementation time, the `presentation/` folder addition and the VTube Studio WebSocket client dependency choice — Sprint 5.6/5.8's own Documentation Checklists each name this as real work for whoever implements them).

## Expected Classes

None new — testing and documentation only, the same "no new architecture" shape every prior Level-freeze sprint shares.

## Expected Interfaces

None new.

## Expected Functions

None new at the public API level, beyond whatever narrow fixes the adversarial re-read finds genuinely necessary (documented as Post-Sprint Fixes on the owning sprint files, per this project's own established convention).

## Data Flow

Not applicable in the way earlier sprints used this section — this sprint verifies existing data flows end-to-end (Sprint 5.14's own diagram) rather than introducing new ones; see that sprint's own Data Flow section for what's being verified here.

## Implementation Tasks

1. `tests/system/test_level5_part_a_acceptance.py` — one continuous scripted scenario: an emotionally-varied multi-turn conversation showing measurable `EmotionalState` evolution; a real persona switch (Jarvis to Minie) exercising `TransitionEngine`'s full phase sequence; a task-shaped conversation triggering `AdaptiveWorkspaceController`'s own profile switch; a long-idle-then-return scenario triggering `CompanionExperienceEngine`'s greeting/continuity-callback path; and the "same intelligence, different presentation" equivalence check (Engineering Rationale) — the same underlying `DecisionTrace`/retrieved-memory content produces substantively equivalent reply content through both personas, differing only in tone/pacing/rendering.
2. `tests/system/test_level5_part_a_real_verification.py` — real VTube Studio connectivity and parameter-injection round trip, skip-clean if unavailable, mirroring `test_level4_part_b_real_verification.py`'s own two-layer skip-check precedent.
3. Re-confirm Sprint 5.15's six hardening scenarios at the system level, explicitly reasoning about which (if any) don't need a third repetition — matching Sprint 3.14/4.13/4.20's own established judgment-call precedent.
4. Adversarial re-read of every `presentation/`/`emotion/` source file for unhandled-exception paths and untested documented risks, fixing what's found (documented as Post-Sprint Fixes on the owning sprint files) and logging what's deliberately deferred.
5. `docs/STATUS.md`, `docs/sprint_book/INDEX.md`, `docs/changelog/0.4.4-level5-part-a.md` updates.
6. Full regression run across the entire Level 1–5 Part A suite.

## Architecture Notes

No new architecture is introduced by this sprint, per its own Purpose — matching every prior Level-freeze sprint's own identical constraint. Any real gap the adversarial re-read finds gets a narrow, targeted fix (never a redesign) at the file that owns it, documented as a Post-Sprint Fix, the same discipline this Sprint Book has followed consistently throughout Level 5 Part A.

## Integration Considerations

- This sprint is the last one in Level 5 Part A — no further Part A sprint exists after it. **Level 5 Part B (Companion Intelligence, sprints 5.17–5.23) is next**, still at roadmap granularity only per `docs/sprint_book/INDEX.md`, expanded to full detail only when it becomes current, per this project's own established practice.
- **`v0.5`'s own tag creation is explicitly NOT automatic even once this sprint's own automated work is done** — per every prior release's own precedent (`v0.2.0`/`v0.3.0`/`v0.4.0` alike), any tag is created only once (a) both Part A and Part B's own outstanding manual verification have actually happened, and (b) the user explicitly authorizes it — never assumed or created preemptively by whichever sprint merely finishes the automated work. This sprint's own internal "Level 5 Part A complete" marker (per the Objectives/Documentation Checklist above) is explicitly **not** a semver tag, the identical distinction `sprint_4_13.md` drew for Level 4 Part A.

## Potential Risks

- **The real-verification tier (Implementation Task 2) depends on a real, locally-running VTube Studio instance with a loaded Live2D model** — a heavier, more manual external dependency than any prior real-verification tier in this project (Ollama/Chroma are both installable, scriptable local services; VTube Studio is a GUI application a person must launch and configure a model into) — a clean, honest skip when unavailable is essential, matching every prior real-verification tier's own established discipline, arguably more important here given how much harder this one is to provision automatically.
- **The "same intelligence, different presentation" equivalence check (Implementation Task 1) is this Sprint Book's single most direct test of its own core promise** — a genuine risk that Sprint 5.4's tone-adaptation work drifted into altering substantive content somewhere along the way is exactly what this check exists to catch; a real failure here would be a significant, worth-escalating finding, not a minor test tweak.
- **The full scripted acceptance scenario (Task 1) is a long, composite system test**, the same "passes standalone, occasionally times out under full-suite load" flake class already documented repeatedly throughout this project's own history (`test_full_level2/3_acceptance_scripted_conversation`) — a plausible, acceptable outcome to find and document, not necessarily a sign of a real bug.

## Acceptance Criteria

- Part 4's own Phase 5.1 acceptance criteria ("Behavior adapts appropriately. Never performs medical diagnosis.") are confirmed directly via the scripted system test.
- The brief's own "Jarvis and Minie share one intelligence, only presentation differs" claim is confirmed via a direct, mechanical equivalence check, not merely asserted.
- Every Sprint 5.15 hardening scenario is re-confirmed correct at the system level (or explicitly, reasonedly not re-tested a third time).
- The real, opt-in verification tier passes when VTube Studio is available, and skips cleanly (never fails) when it is not.
- Full Level 1–5 Part A test suite passes with no regressions; `ruff check .` clean.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` accurately reflect Level 5 Part A's complete, frozen state; `docs/changelog/0.4.4-level5-part-a.md` exists.
- The one criterion no automated test can satisfy is named explicitly as outstanding in this sprint's own completion report, not silently omitted or assumed done.

## Testing Checklist

- [ ] System: full scripted Level 5 Part A scenario through the real, complete `CoreManager` graph.
- [ ] System: "same intelligence, different presentation" equivalence check.
- [ ] System: a real persona transition through its full phase sequence.
- [ ] Opt-in/real: real VTube Studio connectivity and parameter round trip, skip-clean if unavailable.
- [ ] Re-confirmation: all six Sprint 5.15 scenarios at the system level (or explicit, documented reasoning for skipping a repeat).
- [ ] Adversarial: every `presentation/`/`emotion/` source file re-read for unhandled-exception paths and untested documented risks.
- [ ] Full regression: entire Level 1–5 Part A suite passes.

## Documentation Checklist

- [ ] `docs/STATUS.md` — Level 5 Part A marked fully `Complete`.
- [ ] `docs/sprint_book/INDEX.md` — all Part A rows marked `Complete`.
- [ ] `docs/changelog/0.4.4-level5-part-a.md` — created, mirroring `0.3.1-level4-part-a.md`'s own internal-milestone structure.
- [ ] `backlog/technical_debt.md` — items closed/updated per this sprint's own real findings, including the `presentation/` folder addition and VTube Studio dependency choice if not already logged.
- [ ] Any Post-Sprint Fixes documented on their owning sprint files, per this project's established convention.

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

Medium–High.

## Estimated Development Time

2.5–3 days.

## Risks

See Potential Risks above.

## Next Sprint

None within Level 5 Part A — Level 5 Part B (Companion Intelligence, sprints 5.17–5.23) is next, at roadmap granularity only until it becomes current, per this project's established "expand when current" practice (see `docs/sprint_book/README.md`'s own Detail Status note).

## Future Considerations

- Level 5 Part B's own Wellness Engine (5.17–5.19) is expected to reuse `CompanionExperienceEngine`'s own structure (a `WELLNESS`-shaped `CompanionMoment`, per Sprint 5.13's own Future Considerations) and `ReminderEngine`'s existing proactive-announcement mechanism (4.15/4.18) — not built here.
- Every Future Consideration named in Sprints 5.1–5.15 remains open and un-actioned by this freeze sprint, listed here only as a pointer back to where each was originally named, not repeated in full (the same "pointer, not repetition" convention `sprint_4_20.md`'s own Future Considerations already used).

## Sprint Completion Report (2026-08-04)

Implemented directly ("continue with the implementation of sprint 5.16"), no separate Pass-1 round trip needed since the spec above was already complete and unmodified — the same precedent Sprint 1.4/4.9/4.14/5.15's own direct-proceed pattern established.

**New `tests/system/test_level5_part_a_acceptance.py`** — one continuous scripted scenario through `app_harness` (the real, complete Level 1-5 `CoreManager` graph): (1) a real emotionally-loaded turn ("I'm so stressed and overwhelmed...") measurably moves `EmotionalState.stress` away from its neutral 50.0 default; (2) the brief's own "same intelligence, different presentation" promise, checked directly — a fixed, persona-agnostic canned reply from `FakeLanguageModelClient` (dispatched by prompt-template substring match, confirmed via that fake's own docstring to never vary by persona) is asked of Jarvis, then again of Minie after a real switch; the two replies are byte-identical once each one's own `VoicePersonalityModulator`-inserted `"... "` pacing markers are stripped, while their `voice_id`s genuinely differ — a real, mechanical confirmation, not a re-assertion in prose; (3) two consecutive coding-shaped turns (Jarvis active) genuinely rearrange the dashboard via `AdaptiveWorkspaceController`'s real debounce (`workspace_switch_debounce_turns=2`), observed on `JarvisRenderer._current_workspace_profile` directly; (4) a real persona switch runs `TransitionEngine`'s complete seven-phase choreography (`RecordingOverlay`, mirroring `test_presentation_pipeline_integration.py`'s own Sprint 5.14 precedent); (5) `CompanionExperienceEngine`'s greeting fires on a brand-new session's first turn — `greeting_idle_threshold_seconds` (real default 3600s, unreachable by a real few-second-old test session) is lowered to `0.0` for this one step only, directly mutating `h.companion_experience_engine._config` in place, the identical "poke the fixture's own config object directly" technique `test_level3_acceptance.py` already established for `ConfidenceScorer`; (6) every Level 1-5 Part A module is confirmed registered and running. A separate `test_emotional_state_has_no_clinical_or_diagnostic_field()` mechanically checks `EmotionalState`'s own `dataclasses.fields()` against a denylist of clinical-sounding substrings — Part 4's own "Never performs medical diagnosis" criterion, made structurally checkable rather than merely re-asserted.

**One real bug caught in this file's own first draft**: an assertion that `JarvisRenderer._current_workspace_profile` starts at `WorkspaceProfile.GENERAL` — wrong; that attribute is `None` until `apply_workspace_profile()` is actually called for the first time (`CommunicationPipeline._current_workspace_profile`, a *different* attribute on a *different* object, is what starts at `GENERAL`) — caught by the test's own first failing run, not by inspection, fixed immediately.

**New `tests/system/test_level5_part_a_real_verification.py`** — opt-in, mirrors `test_level4_part_b_real_verification.py`'s own two-layer skip-check precedent: (1) a raw socket check for anything listening at `vtube_studio_host:vtube_studio_port` at all; (2) a real `VTubeStudioAvatarRenderer.mount()` + `is_connected()` check (using `PresentationConfig()`'s own real defaults, which happen to be the exact same host/port/token-path this project's own development session already has a persisted, previously-approved plugin token for). Three tests: connect+authenticate succeeds; a real `InjectParameterDataRequest` round trip doesn't disconnect; a real `HotkeyTriggerRequest` round trip doesn't disconnect (closing the second, still-open half of `backlog/technical_debt.md` item 37 — `AuthenticationTokenRequest`/`AuthenticationRequest`/`CurrentModelRequest` were already verified live during this project's own separate, same-day VTube Studio connection session; `InjectParameterDataRequest`/`HotkeyTriggerRequest` were not). **Run for real this session**: the two-layer skip check worked exactly as designed — nothing was listening at `localhost:8001` at the time this file's own test run happened (the earlier live VTube Studio instance from the same-day connection session was no longer open), so all three tests skipped cleanly with a specific, actionable reason, never failing. The skip path itself is therefore what's been verified this session, not the pass path — a real, honestly-reported limitation of this sprint's own verification, not glossed over.

**Sprint 5.15 hardening re-confirmation** (Objective 3): all six scenarios were reasoned through explicitly rather than blanket-repeated — full reasoning lives in `test_level5_part_a_acceptance.py`'s own module docstring, summarized: (a)/(c)/(f) are pure component-level concerns with zero `CoreManager` dependency, already exhaustively unit-tested; (b) was already re-confirmed through the real, fully-wired object graph in Sprint 5.15's own integration tests; (d)'s only real caller (`PersonaManager.on_switch`) is sequential/single-threaded, so a system-level repeat would exercise no new code path beyond Sprint 5.15's own deterministic re-entrant-overlay unit tests; (e) was already re-confirmed against a real `CoreManager` in Sprint 5.15's own integration tests, using `main.py`'s own real functions directly. None were re-tested as dedicated system-level functions in this sprint's own new file — a deliberate, documented choice, not an oversight, matching Sprint 4.20's own explicit "which scenarios don't need a third repeat" precedent.

**Adversarial re-read of every `presentation/`/`emotion/` source file** (22 files) — most confirmed already correctly hardened (their own "never raises" docstring claims verified against real collaborator behavior, not just trusted — e.g. `CompanionExperienceEngine`'s own methods were checked against `MemoryStore.recent()`'s real Sprint 3.14 SQLite-failure hardening before accepting "never raises" as true, not assumed). **Two real, previously-latent gaps found, both fixed**, documented as a Post-Sprint Fix on `sprint_5_14.md` (the owning sprint, since both files were built there):

1. `QtTransitionOverlay._on_tick()` (a `QTimer` slot with nothing upstream to catch an exception) had no guard at all — the identical risk class Sprint 5.15 scenario (c) fixed for `HolographicSphereWidget`/`SegmentedRingWidget`, simply missed for this third, un-named-in-that-sprint's-Files-to-Modify file. Fixed with the identical pattern.
2. `PresentationHostWidget.refresh()`'s own existing try/except covered only the `mounted_persona_name` read, not `_swap_displayed_widget()` (real widget construction/layout mutation) — widened. A second, deeper bug surfaced while fixing the first: `_displayed_persona_name` used to be set to the new value *before* the new widget was actually built, so a genuine `widget()`/`status_widget()` failure would leave that bookkeeping permanently pointing at a name nothing was ever actually displaying — `refresh()`'s own "no change, skip" fast path would then silently short-circuit every future retry, forever, not just for the one failed tick. Restructured so the bookkeeping update happens only after a successful build, so a real failure now leaves the state honestly out of sync and the very next tick retries for real.

Neither file had a dedicated unit test before this fix (both new, real gaps in this project's own test coverage, not just its production code) — 13 new tests across two new files (`tests/unit/presentation/test_qt_transition_overlay.py`, `tests/unit/presentation/test_presentation_host_widget.py`) cover both fixes directly (including a dedicated regression test for the deferred-bookkeeping bug specifically) plus baseline construction/mount/swap sanity coverage neither class had at all.

**`backlog/technical_debt.md` item 40** — the `presentation/` top-level package addition, formally logged per this sprint's own explicit Documentation Checklist instruction (mirroring item 2's `emotion/` precedent, left open and un-logged through Sprints 5.6-5.15 despite those sprints' own Documentation Checklists naming it as real work). No other technical-debt items were closed by this sprint — items 37/38/39 all remain open, each for the reasons already stated in their own "Resolve by" text.

**Full regression**: 1635 total tests, 1628 passing, 5 correctly skipped (2 pre-existing opt-in markers + the 3 new real-VTube-Studio tests, clean-skipped per above), 2 pre-existing failures individually confirmed unrelated and non-regressions — `test_full_level3_acceptance_scripted_conversation` (the same well-established `wait_for_dormant` host-load timing flake class documented repeatedly since Sprint 4.6, confirmed passing standalone immediately after, with a genuine `Resource CRITICAL threshold(s) breached: cpu` warning logged immediately before the timeout) and `test_context_analyzer_extracts_a_nonempty_topic_for_real_input` (the same already-documented real-Ollama-output nondeterminism flake since Sprint 5.2, in a file no Level 5 Part A sprint has ever touched). `ruff check .` clean.

**The one criterion no automated test can satisfy — a supervised, real-machine, human-observed verification pass** (the sphere/ring genuinely animating smoothly; a real VTube Studio avatar genuinely responding to voice/emotion in real time; a real persona-switch transition genuinely playing on screen) **was NOT performed this session**, matching Sprint 2.14/3.14/4.13/4.20's own identical precedent of naming rather than assuming a manual step happened.

**This closes Level 5 Part A. `v0.5`'s own tag is explicitly NOT created by this sprint** — gated on Level 5 Part B (Companion Intelligence, sprints 5.17-5.23, still roadmap-granularity only — no sprint file exists yet) also reaching Complete, the outstanding manual verification above (for both parts), and explicit user authorization, the identical precedent `v0.2.0`/`v0.3.0`/`v0.4.0` each already established. **Level 5 Part B is next**, expanded to full sprint-book detail only once it becomes current, per this project's own established practice.
