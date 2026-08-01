# Sprint 5.8 — Minie Renderer & Avatar Renderer Interface

## Sprint ID

5.8

## Sprint Name

Minie Renderer & Avatar Renderer Interface

## Purpose

Build Minie's avatar presentation — a narrower `AvatarRenderer` interface purpose-built for expressive avatar control (expression, lip sync, eye tracking, gestures), and its first concrete implementation, `VTubeStudioAvatarRenderer`, which drives a locally-running VTube Studio instance and its loaded Live2D model through VTube Studio's own documented local API. JARMINEI never embeds, bundles, or redistributes Live2D's own SDK — it only talks to an already-running external application the user owns and configures independently.

## Engineering Rationale

**New sprint.** The decision to build behind a dedicated `AvatarRenderer` interface (narrower than Sprint 5.6's general `Renderer`) rather than have `VTubeStudioAvatarRenderer` implement `Renderer` directly was made explicitly, via `AskUserQuestion`, before this Sprint Book was written: *"Keep the renderer independent from the core architecture. Design the renderer around a generic Avatar Renderer interface. The first implementation should target VTube Studio/Live2D integration through its supported API or communication mechanism. The rest of JARMINEI must never depend directly on VTube-Studio-specific code."*

Two layers, not one, because Minie's renderer genuinely has operations `Renderer`'s three generic methods can't express well (`render_state()` alone would force every avatar-specific concept — expression, mouth shape, gaze target — into one opaque call): `AvatarRenderer` extends `Renderer` with four additional, avatar-specific methods; `MinieRenderer` (the `Renderer` this project registers with `PresentationController`, Sprint 5.6) is a thin adapter that *translates* a `PresentationState` into the four calls, so `PresentationController` never needs to know avatars exist as a distinct concept from Jarvis's dashboard — it only ever calls the three-method `Renderer` contract. `VTubeStudioAvatarRenderer` is the first (and, this sprint, only) concrete `AvatarRenderer`.

```
PresentationController  --(Renderer)-->  MinieRenderer  --(AvatarRenderer)-->  VTubeStudioAvatarRenderer
```

This gives exactly the swap-target the brief asked for: replacing VTube Studio with a direct Live2D Cubism SDK embed, Unreal, or Unity later needs one new `AvatarRenderer` implementation plus one registry entry (`presentation/avatar_renderer_registry.py`'s `create_avatar_renderer()`, mirroring `internet/search_provider_registry.py`'s `create_search_provider()` precedent exactly) — `MinieRenderer` itself, and everything above it, is untouched.

**The concrete WebSocket client is a deliberate stop-and-ask gate, not decided in this Sprint Book** — named explicitly in `docs/sprint_book/INDEX.md`'s "Level 5 breakdown changes" note, mirroring Sprint 4.16's own precedent for the search-provider choice. Part 3 names no WebSocket library at all. At implementation time, resolve via `AskUserQuestion` between (a) a plain `websockets` client hand-rolled against VTube Studio's own documented JSON request/response protocol (full control, more code to write and maintain), or (b) a community wrapper such as `pyvts` (less code, an unreviewed third-party dependency this project has not yet vetted the way it vetted `coqui-tts`/`Send2Trash`). Do not guess a specific package/version in this Sprint Book — the same "don't decide a real external-dependency choice in the spec, decide it at implementation time with the user" discipline Sprint 4.16 already established.

## Objectives

- `presentation/avatar_renderer.py`: `AvatarRenderer` Protocol (extends `Renderer`'s three methods with four avatar-specific ones).
- `presentation/vtube_studio_renderer.py`: `VTubeStudioAvatarRenderer` — the first concrete `AvatarRenderer`, communicating with a local VTube Studio instance over its WebSocket Plugin API.
- `presentation/avatar_renderer_registry.py`: `create_avatar_renderer()` — resolves a config-selected avatar backend to a concrete class, mirroring `internet/search_provider_registry.py`.
- `presentation/minie_renderer.py`: `MinieRenderer` (implements `Renderer`) — the thin `PresentationState -> AvatarRenderer calls` adapter `PresentationController` actually holds.
- Authentication, connection-loss, and "VTube Studio not running" are all real, named failure modes this sprint's own component-level tests cover (full cross-cutting hardening remains Sprint 5.15's job, the same split every prior renderer/integration sprint uses).

## Dependencies

5.6 (Presentation Layer Foundation & Renderer Interface).

## Files to Create

- `presentation/avatar_renderer.py`
- `presentation/vtube_studio_renderer.py`
- `presentation/avatar_renderer_registry.py`
- `presentation/minie_renderer.py`
- `tests/unit/presentation/test_vtube_studio_renderer.py`
- `tests/unit/presentation/test_minie_renderer.py`
- `tests/unit/presentation/test_avatar_renderer_registry.py`

## Files to Modify

- `config/schema.py` — `PresentationConfig` (5.5) gains `avatar_backend: str = "vtube_studio"`, `vtube_studio_host: str = "localhost"`, `vtube_studio_port: int = 8001`, `vtube_studio_plugin_name: str = "JARMINEI"`, `vtube_studio_plugin_developer: str = "JARMINEI Project"`, `vtube_studio_auth_token_path: str = "config/vtube_studio_token.json"` (a locally-persisted, VTube-Studio-issued auth token — never committed to git, matching `InternetConfig.search_api_key`'s own "a real secret, never written to a shared file" discipline, though this one, unlike an API key, is inherently local-only by VTube Studio's own protocol design and stored on disk rather than read from an env var, since VTube Studio's own authentication flow issues it interactively on first connect, not something a user pre-generates), `vtube_studio_connection_timeout_seconds: float = 5.0`; `_validate_presentation()` extended.
- `requirements.txt` — the chosen WebSocket client dependency, added only once the stop-and-ask gate above resolves at implementation time.

## Expected Classes

- **`AvatarRenderer`** (`Protocol`, extends `Renderer`): the four additional methods below, plus the inherited `mount()`/`unmount()`/`render_state()`.
- **`VTubeStudioAvatarRenderer`** (implements `AvatarRenderer`): constructor DI receives `PresentationConfig`. `mount()` opens the WebSocket connection and performs VTube Studio's own one-time plugin authentication handshake (requesting a token on first run, persisting it via the configured `vtube_studio_auth_token_path`, reusing it on subsequent runs); `unmount()` closes the connection cleanly.
- **`MinieRenderer`** (implements `Renderer`): constructor DI receives an `AvatarRenderer` instance (via the registry, not constructed internally — Dependency Injection, per `03_Engineering_Standards.md`) and `PresentationConfig`.

## Expected Interfaces

- **`AvatarRenderer`** (extends `Renderer`): `set_expression(expression_id: str) -> None` (a named Live2D expression/hotkey trigger — e.g. a smile, a concerned look — the exact vocabulary of `expression_id` values is config-driven, matched against whatever expressions/hotkeys the user's own loaded Live2D model actually defines inside VTube Studio, never assumed to exist), `set_mouth_open(amount: float) -> None` (0.0–1.0, lip-sync target — the real per-frame-audio-driven caller is Sprint 5.11's Voice Personality/TTS integration, not this sprint), `set_eye_target(x: float, y: float) -> None` (-1.0..1.0 normalized gaze direction; `(0, 0)` is forward), `trigger_gesture(gesture_id: str) -> None` (a one-shot animation, e.g. a head tilt or small wave — the real caller is Sprint 5.9's Gesture Engine, not this sprint).

## Expected Functions

- `VTubeStudioAvatarRenderer.mount()` — connects, authenticates (or reuses a persisted token), raises no exception on failure — instead sets an internal `_connected: bool = False` and logs a clear warning; every other method checks this flag first and no-ops (logged at DEBUG, not WARNING, to avoid log spam) when disconnected, the exact "degrade, never crash the app because an external, optional program isn't running" contract this sprint's own Acceptance Criteria requires. A real reconnection attempt (not just a one-shot failure) is explicitly Sprint 5.15's hardening job, not this sprint's.
- `VTubeStudioAvatarRenderer.render_state(state: PresentationState)` — translates the generic `PresentationState` into VTube Studio parameter-injection calls (`smile_intensity`/`eye_openness`/`voice_warmth` mapped onto whichever Live2D model parameters the user's model exposes, via VTube Studio's own `InjectParameterDataRequest`-shaped call — parameter *names* are config-driven, `PresentationConfig.vtube_studio_parameter_mapping: dict[str, str]`, since a Live2D model's own parameter names are author-defined and not something JARMINEI can assume).
- `create_avatar_renderer(config: PresentationConfig) -> AvatarRenderer` (`presentation/avatar_renderer_registry.py`) — resolves `config.avatar_backend` ("vtube_studio" is the only real value this sprint; an unrecognized value raises a clear `UnknownAvatarBackendError` at construction time, matching `search_provider_registry.py`'s own established error-shape precedent, never a silent fallback).
- `MinieRenderer.mount()`/`.unmount()`/`.render_state()` — thin passthrough to the held `AvatarRenderer`, plus the `PresentationState -> {set_expression, set_mouth_open, set_eye_target}` translation for the parts `AvatarRenderer.render_state()` (inherited from `Renderer`) doesn't itself cover — concretely: `MinieRenderer.render_state()` calls `self._avatar.render_state(state)` (the parameter-mapping path above) AND derives a coarse `expression_id` from `state.smile_intensity`/`voice_warmth` via a small, config-driven threshold table, calling `set_expression()` once per meaningful change (not every tick — avoids flooding VTube Studio with redundant identical calls).

## Data Flow

```
PresentationController.refresh()  (5.6)
        |
        v
MinieRenderer.render_state(state: PresentationState)
        |
        +--> AvatarRenderer.render_state(state)       --> VTube Studio: InjectParameterDataRequest
        +--> _maybe_set_expression(state) --> AvatarRenderer.set_expression(expression_id)
        |                                          --> VTube Studio: hotkey/expression trigger
        v
   (mouth-open / eye-target are NOT driven from render_state() this sprint —
    see Integration Considerations: their real callers are Sprint 5.9/5.11)
```

## Implementation Tasks

1. Resolve the WebSocket client stop-and-ask gate with the user (Engineering Rationale) before any other implementation task.
2. `config/schema.py`/`config/defaults.yaml` — `PresentationConfig` extensions per Files to Modify.
3. `presentation/avatar_renderer.py` — `AvatarRenderer` Protocol.
4. `presentation/vtube_studio_renderer.py` — `VTubeStudioAvatarRenderer`: connect/authenticate/token-persist, `render_state()`'s parameter-injection mapping, `set_expression()`/`set_mouth_open()`/`set_eye_target()`/`trigger_gesture()`, the disconnected-no-op contract.
5. `presentation/avatar_renderer_registry.py` — `create_avatar_renderer()`.
6. `presentation/minie_renderer.py` — `MinieRenderer`.
7. Tests: `VTubeStudioAvatarRenderer` against a fake WebSocket server/transport (never a real running VTube Studio instance in the fast/default test suite — mirrors `test_level4_part_b_real_verification.py`'s own "real network call is opt-in only" precedent exactly, since VTube Studio is a real external GUI application no CI/automated environment can be assumed to have running); `MinieRenderer` against a fake `AvatarRenderer`; `create_avatar_renderer()` resolution/error cases.

## Architecture Notes

**JARMINEI never embeds or redistributes Live2D's own SDK, and does not itself render the avatar** — `VTubeStudioAvatarRenderer` only sends parameter/expression/hotkey requests to an already-running, separately-installed VTube Studio process that the user owns, configures, and loads their own Live2D model into independently. This is a real, disclosed product/licensing boundary, not an implementation detail — `PresentationConfig`'s own docstring and this sprint's Documentation Checklist must state plainly that Minie's avatar visuals require the user to have VTube Studio installed and running separately, the same "log a real external dependency and its implications honestly" discipline `InternetConfig`'s own docstring already applies to the Internet Agent's outbound-network boundary.

**"Nothing outside `presentation/vtube_studio_renderer.py` imports anything VTube-Studio-specific"** is a structural, checkable property this sprint's own Testing Checklist verifies mechanically (a grep-shaped check: no other file under `presentation/`, and nothing outside `presentation/` at all, references `vtube_studio`/VTube-Studio-specific types) — the same swap-target guarantee `internet/search_provider_registry.py` already gives the Internet Agent for its own provider choice.

## Integration Considerations

- **`set_mouth_open()`/`set_eye_target()`/`trigger_gesture()` have no real caller this sprint** — `MinieRenderer.render_state()` only drives the `render_state()`/`set_expression()` path this sprint; lip-sync (driven by real TTS audio timing) is Sprint 5.11's job, eye-tracking/gaze targeting and gesture triggering are Sprint 5.9's — both explicitly deferred, not silently missing.
- **No live caller of `MinieRenderer` itself until Sprint 5.14** — `PresentationController`'s renderer dict (5.6) gains a real `"minie": MinieRenderer(...)` entry only at that integration sprint.
- **Real-VTube-Studio verification is explicitly Sprint 5.16's opt-in job**, mirroring `test_level4_part_b_real_verification.py`'s established shape — this sprint's own fast test suite never requires a real running VTube Studio instance.

## Potential Risks

- **VTube Studio may not be running, may not have a Live2D model loaded, or may have a model whose parameter names don't match `vtube_studio_parameter_mapping`'s configured expectations** — all three degrade to the same honest no-op-and-log behavior (Expected Functions), never a crash; a mismatched parameter name specifically logs a clear, named warning (surfaced once per session, not per tick, to avoid log flooding) rather than silently doing nothing with no trace.
- **The stop-and-ask WebSocket-client gate could stall implementation if not resolved early** — named as Implementation Task 1, explicitly ordered first, the same discipline Sprint 4.16 applied to its own provider gate.
- **VTube Studio's own API surface/versioning is outside this project's control** — a real, disclosed third-party dependency risk, the same category `InternetConfig`'s own "first outbound-network code in this project's history" disclosure already established for a different boundary.

## Acceptance Criteria

- `VTubeStudioAvatarRenderer` never raises for any method call, connected or not — verified against both a working fake transport and a deliberately-failing one.
- `MinieRenderer.render_state()` calls `set_expression()` only on a meaningful change, not every tick — verified via call-count assertions across repeated near-identical states.
- `create_avatar_renderer()` raises a clear, specific error for an unrecognized `avatar_backend` value, never a silent fallback.
- Mechanical check: no file outside `presentation/vtube_studio_renderer.py` imports anything VTube-Studio-specific.
- `ruff check .` clean; full existing suite unaffected.

## Testing Checklist

- [ ] Unit: `VTubeStudioAvatarRenderer` connect/authenticate/token-persist/reuse, against a fake WebSocket transport.
- [ ] Unit: `VTubeStudioAvatarRenderer` disconnected-no-op behavior for every method.
- [ ] Unit: `VTubeStudioAvatarRenderer.render_state()`'s parameter-mapping translation, including an unmapped/unknown parameter name's own warning path.
- [ ] Unit: `MinieRenderer.render_state()` expression-change-detection (calls `set_expression()` only when the derived expression actually changes).
- [ ] Unit: `create_avatar_renderer()` success and unknown-backend error cases.
- [ ] Mechanical: no VTube-Studio-specific import outside `presentation/vtube_studio_renderer.py`.
- [ ] Full regression: existing suite unaffected.

## Documentation Checklist

- [ ] `presentation/vtube_studio_renderer.py` module docstring states plainly that this requires a separately-installed, separately-running VTube Studio instance with a loaded Live2D model, and that JARMINEI neither embeds nor redistributes Live2D's own SDK.
- [ ] `config/schema.py`'s `PresentationConfig` docstring documents every new VTube-Studio field, including the token-persistence file's own location and why it isn't committed to git.
- [ ] `presentation/avatar_renderer.py`'s `AvatarRenderer` docstring documents the swap-target guarantee (Architecture Notes) explicitly, the same way `internet/search_provider.py`'s own docstring documents it for search providers.
- [ ] `docs/STATUS.md` — Level 5 Part A row updated.
- [ ] `backlog/technical_debt.md`-shaped entry drafted (added for real once this sprint is actually implemented) recording the chosen WebSocket client dependency and the stop-and-ask decision that picked it, mirroring Sprint 4.16's own item for its own provider choice.

## Definition of Done

Per `docs/CODING_STANDARDS.md`.

## Estimated Complexity

High.

## Estimated Development Time

3 days.

## Risks

See Potential Risks above.

## Next Sprint

5.9 — Gesture Engine.

## Future Considerations

- A second `AvatarRenderer` implementation (a direct Live2D Cubism SDK embed, or an Unreal/Unity bridge) needs one new class plus one registry entry — not built here, the entire point of this sprint's own abstraction.
- Real lip-sync (`set_mouth_open()`) driven by actual TTS audio amplitude/timing is Sprint 5.11's job.
- Real gaze-tracking (`set_eye_target()`) toward, e.g., the user's own on-screen cursor or a notification's screen position is plausible future work once a real signal for "what should Minie be looking at" exists — not built here.
