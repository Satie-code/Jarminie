# Sprint 5.6 — Presentation Layer Foundation & Renderer Interface

## Sprint ID

5.6

## Sprint Name

Presentation Layer Foundation & Renderer Interface

## Purpose

Complete the brief's own mandated architecture — `Persona Controller -> Presentation State -> Renderer Interface -> {Jarvis Renderer, Minie Renderer}` — by building the coordinator (`PresentationController`) and the abstraction (`Renderer` Protocol) around Sprint 5.5's already-built middle node. After this sprint, the Presentation Layer has a real, testable seam ready for two independent, swappable concrete renderers (Sprint 5.7, 5.8) to plug into — neither of which exists yet, and neither of which this sprint depends on.

## Engineering Rationale

**New sprint.** Naming already resolved at Sprint 5.5 (see that sprint's Engineering Rationale): the brief's "Persona Controller" is built here as `PresentationController`, avoiding collision with the existing `PersonaManager` (`personas/persona_manager.py`).

**`Renderer` is deliberately minimal — three methods — mirroring `ManagedModule`'s own "kept deliberately minimal... to avoid over-fitting to subsystems that don't exist yet" precedent exactly** (`core/module_registry.py`'s own docstring for `ManagedModule`, Sprint 1.5). `render_state(state: PresentationState) -> None` is the one real per-frame/per-update call; `mount()`/`unmount()` handle setup/teardown (a renderer may own a widget, a window, a network connection — Sprint 5.8's VTube Studio renderer genuinely needs a connect/disconnect lifecycle Jarvis's in-process widget renderer does not, but both fit the same three-method shape). No `Renderer` method is persona-specific — `PresentationController` never asks a renderer "are you Jarvis or Minie," it simply always has the *currently correct* one mounted (Sprint 5.10's Persona Transition Engine owns swapping which one is mounted).

**`PresentationController` is a `ManagedModule`, following every other coordinator in this codebase** (`PersonaManager`, `MemoryLifecycleManager`, `ReminderEngine`) — it is constructed once at startup, owns no business logic of its own beyond composition (reads `PersonaManager.active_persona()`, calls the matching `PresentationStateComputer`, calls the currently-mounted `Renderer.render_state()`), and its own `health_check()` reflects whether the currently-mounted renderer is itself healthy.

## Objectives

- `presentation/renderer.py`: `Renderer` Protocol.
- `presentation/presentation_controller.py`: `PresentationController` (`ManagedModule`).
- `presentation/asset_manager.py`: `AssetManager` — a thin, shared helper both renderers use to resolve asset paths (color/icon/font resources under `assets/`, the existing top-level folder from Part 3's own repository structure) rather than each renderer hardcoding paths independently.
- No concrete `Renderer` implementation yet — that is Sprint 5.7/5.8's job; this sprint's own tests use a minimal in-memory fake renderer, the same "component before integration, test against a fake" discipline every prior Protocol-introducing sprint used (e.g. `SearchProvider`'s own Sprint 4.16 tests against a fake before `BraveSearchProvider` existed).

## Dependencies

5.5 (Presentation State Engine), 2.11 (Persona Switching — `PersonaManager.active_persona()`).

## Files to Create

- `presentation/renderer.py`
- `presentation/presentation_controller.py`
- `presentation/asset_manager.py`
- `tests/unit/presentation/test_presentation_controller.py`
- `tests/unit/presentation/test_asset_manager.py`

## Files to Modify

None outside `presentation/`/`tests/` this sprint — `main.py`/`CoreManager` registration is explicitly Sprint 5.14's job (Integration Considerations below).

## Expected Classes

- **`Renderer`** (`Protocol`, `presentation/renderer.py`): the abstraction every concrete renderer (Sprint 5.7's `JarvisRenderer`, Sprint 5.8's `VTubeStudioAvatarRenderer`) implements.
- **`PresentationController`** (`ManagedModule`): constructor DI receives `PersonaManager` (existing), `EmotionalStateManager` (5.2), a `dict[str, PresentationStateComputer]` keyed by persona name (5.5's two computers), and a `dict[str, Renderer]` keyed by persona name (populated by `main.py` at Sprint 5.14 — empty/absent bindings degrade gracefully per Sprint 5.15, not this sprint's own job to harden fully). Tracks which renderer is currently *mounted* separately from which persona is currently *active* (`PersonaManager`'s own state) — see Architecture Notes for why these are deliberately not conflated.
- **`AssetManager`**: constructor DI receives an `assets_root: Path` (defaulting to the existing `assets/` folder). No business logic beyond path resolution + existence checking — a real, if intentionally small, class rather than a bag of free functions, so it can be swapped/faked in renderer tests the same way `MemoryStore`/`SqliteClient` already are.

## Expected Interfaces

- **`Renderer`**: `mount() -> None` (called once when this renderer becomes the active one — Sprint 5.7/5.8 acquire whatever resource they need here: constructing a `QWidget`, opening a WebSocket), `unmount() -> None` (release that resource; must be safe to call even if `mount()` was never called or already failed — Fail Gracefully, exercised concretely in Sprint 5.15), `render_state(state: PresentationState) -> None` (apply one `PresentationState` snapshot; called repeatedly, must be cheap/non-blocking — a slow renderer must never stall the caller, an explicit constraint carried into Sprint 5.15's hardening).

## Expected Functions

- `PresentationController.start()`/`.stop()`/`.health_check()` — `start()` mounts whichever renderer matches `PersonaManager.active_persona().name` at startup time (mirrors `PersonaManager.start()`'s own "Jarvis is the default active persona" precedent — the renderer for whichever persona is already active gets mounted, no separate default logic of its own); `stop()` calls `unmount()` on the currently-mounted renderer; `health_check()` returns `False` if no renderer is currently mounted, or delegates to the mounted renderer's own liveness if `Renderer` gains a health signal in a later sprint (this sprint keeps `Renderer` at exactly three methods per Engineering Rationale — no `health_check()` on the Protocol itself yet, so `PresentationController.health_check()` this sprint only checks "is *something* mounted," a narrower but honest signal).
- `PresentationController.refresh() -> None` — the real per-tick entry point (called on a timer or per-turn, wiring decided at Sprint 5.14): reads `PersonaManager.active_persona()`, `EmotionalStateManager.current_state()`, computes a fresh `PresentationState` via the matching computer, calls the mounted renderer's `render_state()`. Never raises — any exception from the computer or the renderer is caught, logged, and skipped for that tick (Fail Gracefully; a dedicated regression test is this sprint's own job even though full hardening is Sprint 5.15's, the same "some hardening lands with the component, the rest at the dedicated hardening sprint" split this project has used before, e.g. Sprint 4.6's resource gate landing ahead of Sprint 4.12).
- `PresentationController.mount_renderer(persona_name: str) -> None` — explicit renderer swap, unmounting whatever was mounted first. The real intended caller is Sprint 5.10's `TransitionEngine`, not this sprint.
- `AssetManager.resolve(relative_path: str) -> Path` — joins against `assets_root`, raises a clear `FileNotFoundError` with the attempted path if the resource doesn't exist (a loud, specific failure at asset-resolution time is preferable to a renderer silently drawing nothing — the same "fail loud where the cost of silent failure is confusion, fail soft where the cost is a crashed session" judgment this project applies throughout, e.g. `DeviceControlConfig.use_recycle_bin_for_delete`'s own "refuse to run rather than silently downgrade" precedent).

## Data Flow

```
(per refresh tick — real trigger wired at Sprint 5.14)
        |
        v
PresentationController.refresh()
        |
        +--> PersonaManager.active_persona()  (existing, Sprint 2.11)
        +--> EmotionalStateManager.current_state()  (5.2)
        |
        v
   PresentationStateComputer[active_persona.name].compute(state, operating_mode)
        |
        v
   PresentationState  (5.5)
        |
        v
   Renderer[active_persona.name].render_state(state)
```

## Implementation Tasks

1. `presentation/renderer.py` — `Renderer` Protocol.
2. `presentation/asset_manager.py` — `AssetManager`.
3. `presentation/presentation_controller.py` — `PresentationController` per Expected Functions.
4. `tests/unit/presentation/test_presentation_controller.py` — a minimal fake `Renderer` (records `render_state()` calls, can be configured to raise); `refresh()`'s Fail-Gracefully behavior; `mount_renderer()` swap correctness (old renderer's `unmount()` called before new one's `mount()`); `health_check()` before/after a renderer is mounted.
5. `tests/unit/presentation/test_asset_manager.py` — resolution against a real temp directory fixture; missing-asset error clarity.

## Architecture Notes

**"Mounted renderer" is deliberately a separate concept from "active persona"** — during a transition (Sprint 5.10), the active persona can change an instant before the new renderer finishes mounting; conflating the two would make `PresentationController` briefly report an inconsistent state (active persona X, but still rendering Y's last frame) as if it were correct rather than a known, named, momentary transition state. `PresentationController` exposes both separately so Sprint 5.10's `TransitionEngine` — the one class that legitimately needs to observe "these are momentarily different" — can do its job; `refresh()` itself always renders through whatever IS currently mounted, never assuming it matches the active persona.

`presentation/asset_manager.py` deliberately does **not** load/decode any actual image, font, or audio asset this sprint — it only resolves and validates paths. Real asset loading is each concrete renderer's own job (Sprint 5.7 loads whatever Qt resources it needs directly; Sprint 5.8's VTube Studio integration doesn't load local avatar assets at all, since the avatar lives inside the external VTube Studio process — see that sprint's own Architecture Notes). Keeping `AssetManager` this thin avoids guessing at a loading API two renderers with genuinely different asset needs would both have to conform to.

## Integration Considerations

- **No live caller until Sprint 5.14** — `main.py`/`CoreManager` registration, and `refresh()`'s real trigger (a `QTimer`, or a call from `CommunicationPipeline`'s own turn-processing, decided at that sprint) are both explicitly out of this sprint's scope.
- **No concrete `Renderer` exists yet** — `PresentationController`'s `dict[str, Renderer]` is empty in every test this sprint writes except where a fake is explicitly supplied; Sprint 5.7/5.8 are what make this dict real.
- Sprint 5.9 (Gesture Engine) and Sprint 5.12 (Adaptive Workspace) both extend what a renderer does with a `PresentationState`/gesture trigger, but neither modifies `PresentationController`, `Renderer`, or `PresentationState` themselves — the abstraction this sprint builds is meant to be stable under both.

## Potential Risks

- **A three-method `Renderer` Protocol may prove too thin once two real renderers exist** (Sprint 5.7/5.8 might discover a real, shared need this sprint didn't anticipate — e.g. a shared "are you healthy" signal) — acceptable risk, the same "start minimal, extend when a real second implementation proves the need" discipline `ManagedModule` itself was built with; extending a `Protocol` with a new method later is a normal, low-cost change, not a redesign.
- **`refresh()`'s per-tick performance is unverified until a real renderer exists** — this sprint's own fake renderer is trivially fast, so "must be cheap/non-blocking" (Expected Interfaces) is asserted in prose here but only genuinely tested once Sprint 5.7/5.8 exist; flagged honestly rather than claimed proven early.

## Acceptance Criteria

- `PresentationController.refresh()` never raises regardless of computer/renderer failure, verified against a fake renderer configured to raise.
- `mount_renderer()` always calls the previous renderer's `unmount()` before the new one's `mount()`, verified via call-order assertions against the fake.
- `AssetManager.resolve()` succeeds for a real existing file and fails with a clear, specific error for a missing one.
- `ruff check .` clean; full existing suite unaffected.

## Testing Checklist

- [ ] Unit: `refresh()` happy path and Fail-Gracefully path (computer raises; renderer raises).
- [ ] Unit: `mount_renderer()` swap ordering and correctness.
- [ ] Unit: `health_check()` before/after mounting.
- [ ] Unit: `AssetManager.resolve()` success/failure paths.
- [ ] Full regression: existing suite unaffected.

## Documentation Checklist

- [ ] `presentation/renderer.py`'s `Renderer` docstring documents the "cheap, non-blocking `render_state()`" contract explicitly, since it's a real constraint future renderer authors must honor.
- [ ] `presentation/presentation_controller.py`'s docstring explains the "mounted renderer vs. active persona" distinction (Architecture Notes above) — the single most likely point of future confusion in this file.
- [ ] `docs/STATUS.md` — Level 5 Part A row updated; `presentation/` noted as a new top-level package (mirroring `emotion/`'s own `backlog/technical_debt.md` item 2 precedent — log this addition the same way once implementation actually happens).

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

Medium–High.

## Estimated Development Time

2 days.

## Risks

See Potential Risks above.

## Next Sprint

5.7 — Jarvis Renderer.

## Future Considerations

- If `Renderer` genuinely needs a `health_check()` of its own once two real implementations exist, add it then (Potential Risks above).
- A third persona (out of this project's stated scope, per `04_Master_Implementation_Plan.md`'s own Future Roadmap) would need only a new `PresentationStateComputer` + `Renderer` pair registered into `PresentationController`'s two dicts — no change to this sprint's own classes, confirming the abstraction holds.

## Sprint Completion Report (2026-08-02)

Implemented as specified, authorized directly ("continue sprint 5.6") right after Sprint 5.5 closed in the same session.

### Summary

`presentation/renderer.py`'s `Renderer` (a `Protocol`, exactly three methods) is the abstraction Sprint 5.7/5.8's concrete renderers will implement — no method is persona-specific. `presentation/asset_manager.py`'s `AssetManager` resolves paths under `assets/` (Part 3's own existing repository folder), raising a clear `FileNotFoundError` naming the full attempted path for a missing resource; it never loads/decodes an actual asset, by design. `presentation/presentation_controller.py`'s `PresentationController` (a `ManagedModule`) is the coordinator around both: `start()` mounts whichever renderer matches `PersonaManager.active_persona()`; `mount_renderer()` always unmounts the previous renderer (if any) before mounting the new one, and never raises even if `mount()`/`unmount()` itself does; `refresh()` composes `PersonaManager.active_persona()` + `EmotionalStateManager.current_state()` + (see Engineering Decision 1 below) into a fresh `PresentationState`, then renders it through whichever renderer is currently **mounted** — deliberately not necessarily the active persona's own renderer, since the two can briefly diverge mid-transition (Sprint 5.10's own future job); the entire body is wrapped in one broad Fail-Gracefully catch, verified against a fake computer/renderer each independently configured to raise.

Two real spec gaps/ambiguities were resolved explicitly, not guessed silently:

1. **Missing `OperatingMode` source.** `PresentationStateComputer.compute()` (Sprint 5.5) requires an `OperatingMode` as its second parameter, but this sprint's own Expected Classes constructor-DI list for `PresentationController` names only `PersonaManager`/`EmotionalStateManager`/the two dicts — no `OperatingMode` source at all — and the Data Flow diagram's own arrows don't show one either. `voice/quiet_mode.py`'s `QuietModeController` (Sprint 2.6) is this project's own existing, established single source of truth for `OperatingMode` — added as a fifth constructor parameter, read only via `current_mode()` inside `refresh()`. Real unit tests use a minimal fake (`_FakeQuietMode`) rather than a full `VoiceSessionManager` graph, the same "fake the narrow interface you actually need" precedent this Level's other tests already use for `Renderer`/`PresentationStateComputer`.
2. **Data Flow diagram's `Renderer[active_persona.name]` vs. Architecture Notes' "always render through whatever IS currently mounted."** The diagram's own literal indexing notation reads as if the renderer is selected by the active persona's name; the prose Architecture Notes explicitly say the opposite — `refresh()` must render through the *mounted* renderer, never assuming it matches the active persona, specifically so Sprint 5.10's `TransitionEngine` can observe a genuine momentary mismatch. Resolved in favor of the more detailed, deliberate prose explanation over the diagram's own simplification — `refresh()` selects the `PresentationStateComputer` by `active_persona.name` but the `Renderer` by `self._mounted_persona_name`, proven directly by a new dedicated test (`test_refresh_renders_through_the_mounted_renderer_not_the_active_persona`) that mounts a different persona's renderer than the currently-active one and confirms the correct (mismatched, intentional) routing.

`_clamp`-style module-private naming (this sprint's own Expected Functions doesn't literally name a `_clamp` here, but the same "genuinely shared across modules should be public" reasoning Sprint 5.5 already established) continues to apply — no new instance here needed it, noted only for consistency. `tests/unit/presentation/__init__.py` (again named in this sprint's own Files to Create, identically to Sprint 5.5's) was again deliberately not created, for the same documented "`tests/` has no `__init__.py`" convention reason.

### Files Created

- `presentation/renderer.py`
- `presentation/presentation_controller.py`
- `presentation/asset_manager.py`
- `tests/unit/presentation/test_presentation_controller.py`
- `tests/unit/presentation/test_asset_manager.py`

**Not created**: `tests/unit/presentation/__init__.py` — see Summary above and Sprint 5.5's own identical precedent.

### Files Modified

None outside `presentation/`/`tests/` — matches this sprint's own stated Files to Modify exactly (`main.py`/`CoreManager` registration is explicitly Sprint 5.14's job).

### Tests Added

- `tests/unit/presentation/test_presentation_controller.py` — 25 tests: `start()`/`stop()`/`health_check()` across bound/unbound-renderer cases; `mount_renderer()` swap ordering (call-log assertion proving unmount-before-mount across two different renderer instances) and its `mount()`/`unmount()`-raises degradation; `refresh()`'s happy path, its Fail-Gracefully behavior against a computer that raises and a renderer that raises, its no-op behavior when nothing is mounted, and its warn-and-skip behavior when no computer is bound for the active persona; the dedicated "mounted renderer vs. active persona" mismatch test (Engineering Decision 2 above); `mounted_persona_name` property correctness.
- `tests/unit/presentation/test_asset_manager.py` — 6 tests: resolution success for a real file, a real nested file, and a real directory; failure with a clear, path-naming error for a missing file (both a shallow and a nested missing path); the default `assets_root` genuinely points at the project's own `assets/` folder.

### Documentation Updated

- `presentation/renderer.py`'s `Renderer` docstring (the "cheap, non-blocking `render_state()`" contract, stated explicitly).
- `presentation/presentation_controller.py`'s module/class docstrings (the "mounted renderer vs. active persona" distinction, and both resolved spec gaps above, in full).
- `presentation/asset_manager.py`'s module/class docstrings.
- This Sprint Completion Report.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` updated (see below).

### Acceptance Criteria Checklist

- ✔ `PresentationController.refresh()` never raises regardless of computer/renderer failure — verified against a fake computer AND a fake renderer, each independently configured to raise.
- ✔ `mount_renderer()` always calls the previous renderer's `unmount()` before the new one's `mount()` — verified via a shared call-log list ordering assertion across two distinct renderer instances, not just per-renderer call counts.
- ✔ `AssetManager.resolve()` succeeds for a real existing file (and, additionally, a real nested file and a real directory) and fails with a clear, specific, path-naming error for a missing one.
- ✔ `ruff check .` clean; full existing suite unaffected — no file outside `presentation/`/`tests/unit/presentation/`/`tests/unit/config/` was touched, and even that file only gained new, additive tests already covered under Sprint 5.5's own docs (this sprint added no further `config/schema.py` changes of its own).

### Risks

- Same "three-method `Renderer` may prove too thin" and "`refresh()`'s per-tick performance is unverified until a real renderer exists" risks named in the spec — unchanged, both explicitly deferred to Sprint 5.7/5.8's own real implementations to prove or disprove.
- No live caller yet, and `PresentationController`'s own constructor now has a fifth parameter (`quiet_mode_controller`) beyond what this sprint's own spec named — a real, disclosed, additive change; Sprint 5.14's own wiring will need to supply a real `QuietModeController` (already constructed in `main.py`'s Level 2 graph) alongside the other four.

### Technical Debt

None introduced. Both spec gaps (missing `OperatingMode` source; the diagram/prose tension) were found and resolved within this sprint, not deferred or silently worked around.

### Recommendations

- Once Sprint 5.7/5.8 build real renderers, revisit whether `render_state()`'s "must be cheap/non-blocking" contract needs an enforced timeout inside `PresentationController.refresh()` itself, rather than remaining a documented-only expectation — a real measurement question this sprint's own fake renderer cannot answer (Potential Risks).
- Sprint 5.10's `TransitionEngine` should read `PresentationController.mounted_persona_name` directly (the property this sprint added specifically for that purpose) rather than re-deriving mount state some other way.

### Verification

Full suite: 1352 passing + 1 pre-existing failure (the same already-established real-Ollama-output nondeterminism flake from Sprint 5.2/5.3/5.5's own verification, in a file this sprint never touches) + 1 skipped + 1 deselected. `ruff check .` clean across the whole repository. A direct, non-mocked smoke script (real `PersonaManager`/`EmotionalStateManager`/`JarvisPresentationStateComputer`/`MiniePresentationStateComputer` instances, a hand-written fake `Renderer`/`QuietModeController`) confirmed `start()`/`refresh()`/`mount_renderer()`/`stop()` all behave as designed end-to-end, including the deliberate mounted-vs-active mismatch during a simulated transition.

**No git commit made** — per this project's own "only commit when explicitly asked" rule, changes left in the working tree; the user has not yet been asked whether to commit.

**Sprint 5.7 (Jarvis Renderer) is next.**
