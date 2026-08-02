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

## Sprint Completion Report (2026-08-02)

Implemented as specified, authorized directly ("continue with sprint 5.8") right after Sprint 5.7 closed in the same session. Implementation Task 1's own stop-and-ask gate was resolved first, via `AskUserQuestion`, before any file was written: the user chose a hand-rolled client against the plain `websockets` library over the community `pyvts` wrapper.

### Summary

`presentation/avatar_renderer.py`'s `AvatarRenderer` (a `Protocol` extending Sprint 5.6's `Renderer` with `set_expression`/`set_mouth_open`/`set_eye_target`/`trigger_gesture`) is the interface `presentation/vtube_studio_renderer.py`'s `VTubeStudioAvatarRenderer` (the first, and this sprint's only, concrete implementation) satisfies. `presentation/minie_renderer.py`'s `MinieRenderer` (implements the plain `Renderer` contract, holds an `AvatarRenderer` via constructor DI) is the thin adapter `PresentationController` will actually register — it delegates `render_state()`'s parameter-injection path straight to the held `AvatarRenderer`, and separately derives a coarse `expression_id` from a blended `(smile_intensity + voice_warmth) / 2` "expressiveness" reading against `PresentationConfig.minie_expression_thresholds`, calling `set_expression()` only when that derived id changes from the last one sent. `presentation/avatar_renderer_registry.py`'s `create_avatar_renderer()` mirrors `internet/search_provider_registry.py`'s own established shape exactly — `UnknownAvatarBackendError`, never a silent fallback.

`VTubeStudioAvatarRenderer` connects over `ws://{host}:{port}` via `websockets.sync.client.connect()`, performs VTube Studio's own one-time plugin-authentication handshake (`AuthenticationTokenRequest` → persist → `AuthenticationRequest`, reusing a persisted token on later runs and only requesting a fresh one if the persisted one is rejected), and never raises from any public method regardless of connection state — `mount()`'s own broad catch degrades to `_connected = False` with a logged warning (VTube Studio not running is an expected, common case); every other method checks `_connected` first and no-ops at DEBUG when disconnected; a mid-session send/recv failure on an already-mounted connection is caught per-call, logs a WARNING, and marks the renderer disconnected again (a real reconnection attempt is explicitly named as Sprint 5.15's own job, not built here). A VTube-Studio-side rejection of an injected parameter (a model that doesn't define one of the configured `vtube_studio_parameter_mapping` names) and a locally-misconfigured mapping (a `PresentationState` field name that doesn't exist) each log a warning exactly once per session via a small `_warned_keys` set, never per tick.

Two real implementation-time decisions, not fully spelled out by the spec, were resolved and are worth naming explicitly:

1. **`set_mouth_open()`/`set_eye_target()`'s own Live2D parameter names.** `vtube_studio_parameter_mapping` (the spec's own named config field) only covers the three `PresentationState`-driven fields (`smile_intensity`/`eye_openness`/`voice_warmth`); no config field was named for mouth-open/eye-target's own parameter names. Resolved by using real, disclosed constants (`ParamMouthOpenY`, `ParamEyeBallX`/`ParamEyeBallY` — VTube Studio's own standard built-in parameter names) rather than adding further config surface the spec's own Files to Modify list didn't ask for — these are structural face-tracking concepts unlikely to need per-model reconfiguration the way the `PresentationState`-driven ones genuinely do.
2. **`MinieRenderer._maybe_set_expression()`'s own threshold table needing to be config-driven.** The spec's own Expected Functions says the expression is derived "via a small, config-driven threshold table" but names no new config field for it. `03_Engineering_Standards.md`'s "no hardcoded... thresholds" rule (the same one Sprint 5.4's `_select_tone_variant()` and Sprint 5.7's animation constants already had to resolve) applies here too — `PresentationConfig.minie_expression_thresholds` was added, validated (including a structural "must include a `0.0`-threshold floor" guarantee so `_derive_expression_id()` always has a reachable fallback), and defaulted to a real, disclosed, first-pass expression vocabulary (`neutral`/`smile`/`big_smile`).

The mechanical "nothing outside the registry imports `VTubeStudioAvatarRenderer`" check (Architecture Notes/Acceptance Criteria) is implemented via real AST parsing, not a substring grep — a grep would have false-flagged this project's own established documentation style, where several files' docstrings *mention* `VTubeStudioAvatarRenderer` by name as the swap-target example (`presentation/renderer.py`, `presentation/avatar_renderer.py`, `presentation/asset_manager.py`, `presentation/minie_renderer.py`, `config/schema.py`'s own `PresentationConfig` docstring all do this, confirmed directly before writing the test) — those are prose, not code dependencies, and the test correctly does not flag them.

### Files Created

- `presentation/avatar_renderer.py`
- `presentation/vtube_studio_renderer.py`
- `presentation/avatar_renderer_registry.py`
- `presentation/minie_renderer.py`
- `tests/unit/presentation/test_vtube_studio_renderer.py`
- `tests/unit/presentation/test_minie_renderer.py`
- `tests/unit/presentation/test_avatar_renderer_registry.py`

### Files Modified

- `config/schema.py` — `PresentationConfig` gains `avatar_backend`/`vtube_studio_host`/`vtube_studio_port`/`vtube_studio_plugin_name`/`vtube_studio_plugin_developer`/`vtube_studio_auth_token_path`/`vtube_studio_connection_timeout_seconds`/`vtube_studio_parameter_mapping` (exactly as spec'd) plus `minie_expression_thresholds` (Engineering Decision 2 above, not explicitly named by the spec's own Files to Modify); `_validate_presentation()` extended for all of them.
- `config/defaults.yaml` — matching new field defaults.
- `requirements.txt` — `websockets>=12.0`, per the resolved stop-and-ask gate.
- `.gitignore` — `config/vtube_studio_token.json` (a real secret, never committed).
- `tests/unit/config/test_schema.py` — new validation coverage for every new `PresentationConfig` field. **Not named in the sprint file's own Files to Modify** — follows directly from the `config/schema.py` additions above, same pattern every prior Level 5 config-adding sprint has used.

### Tests Added

- `tests/unit/presentation/test_vtube_studio_renderer.py` — 27 tests: connect/authenticate/token-persist/reuse (including the persisted-token-rejected-so-request-a-new-one path) against a fully-controlled fake `websockets.sync.client` connection; `mount()` never raises for a connection failure, an authentication failure, or a token-less response; every method's disconnected-no-op behavior; `render_state()`'s parameter-mapping translation, its own once-per-session warning paths (both an unknown `PresentationState` field and a VTube-Studio-side `APIError` rejection), and its mid-session-disconnect handling; `set_expression()`/`trigger_gesture()`'s `HotkeyTriggerRequest` shape; `set_mouth_open()`/`set_eye_target()`'s own parameter injection; `unmount()`'s idempotency and its own never-raises-even-if-close-fails guarantee; the AST-based mechanical "no file outside the registry imports `VTubeStudioAvatarRenderer`" check.
- `tests/unit/presentation/test_minie_renderer.py` — 14 tests: `mount()`/`unmount()` delegate straight through; `render_state()` delegates the parameter-mapping path and separately drives expression-change detection (first call always sends, an unchanged derived expression is deduplicated, a genuinely different one re-sends, 20 repeated near-identical states produce exactly one `set_expression()` call while `render_state()` itself is called all 20 times); `unmount()` resets expression memory so a remount always re-sends fresh; `MinieRenderer` itself never calls `set_mouth_open`/`set_eye_target`/`trigger_gesture` (Integration Considerations: no real caller this sprint); `_derive_expression_id()`'s threshold-picking, its blending of both named signals, and its honest fallback for a hand-constructed table missing a floor.
- `tests/unit/presentation/test_avatar_renderer_registry.py` — 5 tests: default resolution, config passthrough, unknown-backend error (naming both the bad value and every registered option), a typo never silently falling back to the default.
- `tests/unit/config/test_schema.py` — 15 new tests covering every new `PresentationConfig` field's own validation, plus a shipped-defaults-are-valid sanity check.

### Documentation Updated

- `presentation/vtube_studio_renderer.py`'s module docstring (the VTube-Studio-installed-separately disclosure, the "disconnected, never crash" contract, the best-effort-protocol-implementation disclosure, the synchronous-`websockets`-API rationale).
- `presentation/avatar_renderer.py`'s docstring (the swap-target guarantee, mirroring `internet/search_provider.py`'s own).
- `config/schema.py`'s `PresentationConfig` docstring (every new field, including why the token path is a file, not an env var).
- `backlog/technical_debt.md` — new item 37, recording the stop-and-ask WebSocket-client decision and the disclosed not-verified-against-a-real-instance limitation.
- This Sprint Completion Report.
- `docs/STATUS.md`/`docs/sprint_book/INDEX.md` updated (see below).

### Acceptance Criteria Checklist

- ✔ `VTubeStudioAvatarRenderer` never raises for any method call, connected or not — verified against both a working fake transport and multiple deliberately-failing ones (connection failure, auth failure, no-token response, mid-session disconnect, close()-itself-fails).
- ✔ `MinieRenderer.render_state()` calls `set_expression()` only on a meaningful change — verified via a 20-call repeated-near-identical-state sweep producing exactly one call.
- ✔ `create_avatar_renderer()` raises a clear, specific `UnknownAvatarBackendError` for an unrecognized `avatar_backend`, never a silent fallback.
- ✔ Mechanical check: no file outside `presentation/vtube_studio_renderer.py`/`avatar_renderer_registry.py` imports anything VTube-Studio-specific — verified via real AST parsing across the entire repository, not a naive grep.
- ✔ `ruff check .` clean; full existing suite unaffected.

### Risks

- Same "VTube Studio may not be running/may not match the configured parameter mapping" risk named in the spec — mitigated exactly as designed (a uniform, logged, once-per-session degrade, never a crash).
- **The exact VTube Studio JSON protocol shapes are unverified against a real instance** — logged as `backlog/technical_debt.md` item 37, the same disclosed-limitation category as item 31's Brave Search response parsing; real verification is explicitly Sprint 5.16's own opt-in job.
- No live caller of `MinieRenderer` until Sprint 5.14 populates `PresentationController`'s renderer dict with a real `"minie": MinieRenderer(...)` entry.

### Technical Debt

One new item logged (37) — the stop-and-ask WebSocket-client decision and its disclosed real-verification gap, per this sprint's own Documentation Checklist. No other technical debt introduced; the `minie_expression_thresholds` config gap was found and resolved within this sprint, not deferred.

### Recommendations

- Once a real VTube Studio instance with a loaded Live2D model is available, run a real, supervised connection test (Sprint 5.16's own job) to confirm the request/response shapes actually match — see `backlog/technical_debt.md` item 37's own Resolve-by column for the specifics.
- Whether `set_mouth_open()`'s/`set_eye_target()`'s own hardcoded parameter-name constants should eventually move into `PresentationConfig` too (matching `vtube_studio_parameter_mapping`'s own treatment) is a real, deliberately-deferred question — revisit once Sprint 5.11/5.9 give them a real caller and a real need for per-model reconfiguration is confirmed, not assumed now.

### Verification

Full suite: 1438 passing + 1 pre-existing failure (the same already-established real-Ollama-output nondeterminism flake from Sprint 5.2/5.3/5.5/5.6/5.7's own verification, in a file this sprint never touches) + 1 skipped + 1 deselected. `ruff check .` clean across the whole repository. A direct, non-mocked smoke script (a real `PresentationConfig`, a fully-controlled fake WebSocket connection standing in for VTube Studio) confirmed the entire chain — `create_avatar_renderer()` → `VTubeStudioAvatarRenderer.mount()`/token persistence → `MinieRenderer.render_state()`'s parameter injection and expression-change-detection (a second identical `render_state()` call sent one fewer message than the first, confirming deduplication) → `UnknownAvatarBackendError` for a bad backend name — behaves as designed end-to-end.

**No git commit made** — per this project's own "only commit when explicitly asked" rule, changes left in the working tree; the user has not yet been asked whether to commit.

**Sprint 5.9 (Gesture Engine) is next.**
