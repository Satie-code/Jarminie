# Sprint 5.12 — Adaptive Workspace

## Sprint ID

5.12

## Sprint Name

Adaptive Workspace

## Purpose

Make Jarvis's dashboard rearrange itself for the user's current task — Coding, Research, Study, Projects, General productivity — the brief's own explicit requirement. Fills in the empty dashboard-panel container Sprint 5.7 shipped as a placeholder.

## Engineering Rationale

**New sprint.** Config-driven keyword-to-layout mapping, not ML — the identical, deliberately-crude-and-named-as-such pattern this codebase already uses for every comparable "classify a topic into a bucket" problem (`PersonaManager.detect_context_heuristic()`'s topic keywords, `MemoryConfig.short_term_salience_triggers`). A real classifier would be new-feature-shaped work this sprint doesn't need: `decision/context_analyzer.py`'s `ContextAnalysis.primary_topic`/`mentioned_entities` (Sprint 3.8, already real, already live) already gives this sprint a topic signal for free — `AdaptiveWorkspaceController` only has to map that topic onto one of a small, fixed set of `WorkspaceProfile`s.

## Objectives

- `presentation/adaptive_workspace.py`: `WorkspaceProfile` enum (`CODING`, `RESEARCH`, `STUDY`, `PROJECTS`, `GENERAL`), `AdaptiveWorkspaceController` — `select_profile(context_analysis: ContextAnalysis | None) -> WorkspaceProfile`.
- `presentation/jarvis_renderer.py` gains a real dashboard-panel layout per `WorkspaceProfile`, replacing Sprint 5.7's empty placeholder container.

## Dependencies

5.7 (Jarvis Renderer), 3.8 (Context Analysis).

## Files to Create

- `presentation/adaptive_workspace.py`
- `tests/unit/presentation/test_adaptive_workspace.py`

## Files to Modify

- `presentation/jarvis_renderer.py` — `JarvisRenderer.apply_workspace_profile(profile: WorkspaceProfile) -> None`, real panel layout per profile (a small, fixed set of already-planned dashboard widgets — e.g. a project-status panel, a research-notes panel, a system-status panel reusing `ui/status_panel.py`'s own existing data source via a thin adapter, never duplicating `StatusPanel`'s own logic).
- `config/schema.py` — `PresentationConfig` gains `workspace_profile_keywords: dict[str, list[str]]` (per-`WorkspaceProfile.value` keyword list, the same shape as `EmotionConfig.lexical_markers`).

## Expected Classes

- **`WorkspaceProfile`** (`Enum`): `CODING`, `RESEARCH`, `STUDY`, `PROJECTS`, `GENERAL` (the safe-failure default — an unrecognized/ambiguous topic always resolves here, never a guess at one of the other four).
- **`AdaptiveWorkspaceController`**: constructor DI receives `PresentationConfig` only.

## Expected Interfaces

None new.

## Expected Functions

- `AdaptiveWorkspaceController.select_profile(context_analysis: ContextAnalysis | None) -> WorkspaceProfile` — never raises; `None` (Decision Engine pipeline failure) or an empty `primary_topic`/`mentioned_entities` both resolve to `GENERAL`. Keyword-matches `primary_topic` and `mentioned_entities` (combined, case-insensitive substring, the same technique every comparable heuristic in this codebase already uses) against `workspace_profile_keywords`; the first matching profile in enum-declaration order wins on a tie (declaration order = `CODING, RESEARCH, STUDY, PROJECTS, GENERAL` — a deliberate, documented tie-break, not an accidental one).
- `AdaptiveWorkspaceController.should_switch(current: WorkspaceProfile, candidate: WorkspaceProfile, consecutive_match_count: int) -> bool` — a small debounce: a single topic-shifted turn does not necessarily justify a full dashboard rearrangement (visually jarring on every minor topic drift within an otherwise-coding conversation); requires `consecutive_match_count >= PresentationConfig.workspace_switch_debounce_turns` (new field, default a real, small value) matching turns before actually recommending a switch — the caller (Sprint 5.14) owns tracking the running count, this method is a pure yes/no gate over it.

## Data Flow

```
ContextAnalysis | None  (existing, Sprint 3.8, per live turn)
        |
        v
AdaptiveWorkspaceController.select_profile() -> WorkspaceProfile (candidate)
        |
        v
AdaptiveWorkspaceController.should_switch(current, candidate, count) -> bool
        |
        v (only if True)
JarvisRenderer.apply_workspace_profile(candidate)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `workspace_profile_keywords` (a real, reviewable default set per profile) and `workspace_switch_debounce_turns: int = 2`.
2. `presentation/adaptive_workspace.py` — `WorkspaceProfile`, `AdaptiveWorkspaceController`.
3. `presentation/jarvis_renderer.py` — `apply_workspace_profile()`, real per-profile panel layouts.
4. `tests/unit/presentation/test_adaptive_workspace.py` — profile selection across representative `ContextAnalysis` fixtures including `None`; tie-break ordering; debounce gating (a single matching turn does not trigger, a run of consecutive matching turns does).

## Architecture Notes

`AdaptiveWorkspaceController` never reads `EmotionalState`/`PresentationState` — task context and emotional state are orthogonal signals (the brief itself separates "Adaptive Workspace" from the emotion-driven sprints), and conflating them here would make this class harder to reason about for no real benefit; `JarvisRenderer.apply_workspace_profile()` and `JarvisRenderer.render_state()` (Sprint 5.7) are two independent update paths on the same widget tree, called from two independent triggers.

## Integration Considerations

- **No live caller until Sprint 5.14** — `select_profile()`/`should_switch()` need a real per-turn `ContextAnalysis` and a real running debounce counter, both supplied by `CommunicationPipeline`'s own turn loop at that sprint.
- The `StatusPanel`-adapter panel (Files to Modify) reuses `ui/status_panel.py`'s existing data-reading logic via a thin read-only adapter — this sprint does not modify `ui/status_panel.py` itself.

## Potential Risks

- **Keyword-based topic-to-profile mapping is the same honestly-crude category as every other heuristic in this codebase** — documented, not oversold.
- **A fixed five-profile set may not fit every real task shape** — acceptable for a first version; `GENERAL`'s own safe-default role absorbs anything that doesn't cleanly fit one of the other four, rather than forcing a bad classification.

## Acceptance Criteria

- `select_profile()` never raises, including for `context_analysis=None`.
- Debounce gating verified directly: a lone matching turn never triggers a switch; a configured run of consecutive matches does.
- `ruff check .` clean; full existing suite unaffected.

## Testing Checklist

- [ ] Unit: `select_profile()` across representative fixtures and the `None` case.
- [ ] Unit: tie-break ordering (a `ContextAnalysis` matching two profiles' keywords resolves to the earlier-declared one).
- [ ] Unit: `should_switch()` debounce behavior.
- [ ] Unit (regression): `JarvisRenderer.apply_workspace_profile()` produces the expected panel set per profile.
- [ ] Full regression: existing suite unaffected.

## Documentation Checklist

- [ ] `presentation/adaptive_workspace.py` docstring documents the keyword-heuristic limitation and the debounce rationale.
- [ ] `docs/STATUS.md` — Level 5 Part A row updated.

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

Medium.

## Estimated Development Time

1.5 days.

## Risks

See Potential Risks above.

## Next Sprint

5.13 — Companion Experience.

## Future Considerations

- A richer, per-profile panel set (more than this sprint's own starting handful) is real future content work.
- If `ContextAnalysis` itself ever grows a dedicated "workspace category" field (rather than this sprint inferring one from `primary_topic`/`mentioned_entities`), `select_profile()` should prefer it the same way `PersonaManager.select_from_context()` already prefers `suggested_persona` over its own cruder heuristic — not built speculatively now.

---

## Sprint Completion Report (2026-08-03)

**Delivered exactly this sprint's own spec.** `presentation/adaptive_workspace.py`'s `WorkspaceProfile` (the exact five values, declaration order `CODING, RESEARCH, STUDY, PROJECTS, GENERAL` doubling as the tie-break order) and `AdaptiveWorkspaceController` are in place: `select_profile()` combines `primary_topic`/`mentioned_entities` into one lowercased haystack and keyword-matches it against `PresentationConfig.workspace_profile_keywords`, returning the first profile (in declaration order) whose configured keyword list matches, or `GENERAL` for `None`/empty/no-match — never raising, verified across representative fixtures, three distinct tie-break pairs, and a `None`/empty/whitespace/blank-entity sweep. `should_switch()` is a pure yes/no gate — `candidate == current` short-circuits to `False` (a small, obviously-correct addition beyond the spec's own literal text, since leaving `current` otherwise unused in the signature would have been a real code smell), otherwise gated on `consecutive_match_count >= workspace_switch_debounce_turns`; verified at the exact threshold boundary (one below, at, and above), plus a custom non-default threshold.

**A real, necessary DI/architecture question resolved directly**: the spec's own Files to Modify describes `JarvisRenderer`'s new system-status panel as reusing `ui/status_panel.py`'s "existing data source... via a thin adapter" — read literally as "embed a real `StatusPanel` instance," this would have made `presentation/jarvis_renderer.py` import from `ui/status_panel.py`, inverting this project's own established dependency direction (`ui/main_window.py` is what will embed `JarvisRenderer.widget()` at Sprint 5.14, not the reverse). Resolved by building `_SystemStatusPanel` as a genuinely separate, presentation-owned `QWidget` that calls the exact same `CoreManager.module_states()`/`check_resources()`/`ui_config()` methods `StatusPanel` itself calls — the real *data source* is reused, `StatusPanel`'s own class is never imported or wrapped, and the dependency direction stays correct. This is also why `JarvisRenderer` gained a new required constructor parameter, `core_manager: CoreManager` — a real, necessary DI addition beyond the sprint's own original signature, the same "found a real gap, resolved it directly, disclosed it here" precedent `PresentationController`'s own Sprint 5.6/5.9/5.10 additions already used, this time landing on `JarvisRenderer` for the first time.

`apply_workspace_profile()` rebuilds the dashboard-panel area (`_clear_panel_container()` removes and `deleteLater()`s any previous panels first, so a live `_SystemStatusPanel`'s own `QTimer` doesn't leak across repeated profile switches) with `_SystemStatusPanel` always present plus one profile-specific placeholder panel (`Coding Workspace`/`Research Notes`/`Study Session`/`Project Status`) — `GENERAL` gets no placeholder at all, matching its own safe-failure role structurally, not just by convention. The placeholder panels are honestly empty content (`"Coming soon."`) — real per-profile data sources (`WorkflowStore`, `ResearchEngine`, etc.) are outside this sprint's own named Dependencies (only 5.7/3.8) and are named explicitly as Future Considerations, not built speculatively. `_ensure_widgets_built()` now gives `_panel_container` a real `QVBoxLayout` at construction (previously an inert placeholder with none) so `apply_workspace_profile()` has somewhere to add widgets.

**Test coverage**: `select_profile()`/`should_switch()` verified in isolation (17 tests, no Qt dependency, matching this class's own pure-decision-function shape); `JarvisRenderer.apply_workspace_profile()` verified with a real `qtbot`-managed widget tree — panel counts per profile (2 for the four named profiles, 1 for `GENERAL`), profile switching replacing rather than accumulating panels, building the widget hierarchy lazily if `widget()`/`mount()` were never called first (matching this class's own established laziness contract), and `_SystemStatusPanel`'s own real data reflection plus its own Fail-Gracefully behavior under a simulated `CoreManager` failure — using a local `_fake_core_manager()` helper mirroring `tests/unit/ui/conftest.py`'s own `mock_core_manager` fixture shape (not reused directly, since `tests/unit/presentation/` has no shared `conftest.py` of its own yet and one file's own need didn't justify adding one).

**Full suite**: 1562 total (1558 passing, 2 pre-existing failures, 1 skipped, 1 deselected), `ruff check .` clean. Both failures individually re-run standalone and confirmed pre-existing, unrelated to this sprint's own files (`presentation/adaptive_workspace.py`, `presentation/jarvis_renderer.py`, `config/schema.py`, `config/defaults.yaml` — `git status` confirms nothing in `decision/`/`memory/`/`tests/integration/` was touched): `test_context_analyzer_extracts_a_nonempty_topic_for_real_input` is the same real-Ollama-output nondeterminism flake documented since Sprint 5.2; `test_full_turn_completes_when_chromadb_entirely_unreachable` (`tests/integration/test_decision_engine_hardening.py`) is a *new* specific victim of the same general "passes standalone, times out only under full-suite host-resource load" flake class this project has documented repeatedly since Sprint 3.13 — passed cleanly standalone, confirming genuine host contention rather than a regression.

**No live caller of `select_profile()`/`should_switch()`/`apply_workspace_profile()` yet** — Sprint 5.14's job, per this sprint's own Integration Considerations (a real per-turn `ContextAnalysis` and a real running debounce counter, both supplied by `CommunicationPipeline`'s own turn loop). `docs/STATUS.md`'s Level 5 Part A row updated; `docs/sprint_book/INDEX.md`'s 5.12 row marked Complete (link corrected to the `sprint_5/sprint_5_12.md` pattern, same fix-in-passing precedent every sprint since 5.9 has applied to its own row). **Sprint 5.13 (Companion Experience) is next.**
