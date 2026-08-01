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
