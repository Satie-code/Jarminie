"""MinieRenderer (Sprint 5.8 — Level 5 Part A).

The `Renderer` (Sprint 5.6) `PresentationController` actually holds for
Minie — a thin adapter translating a `PresentationState` into
`AvatarRenderer` (this sprint's own narrower interface) calls, so
`PresentationController` never needs to know avatars exist as a
distinct concept from Jarvis's dashboard; it only ever calls the
three-method `Renderer` contract.

    PresentationController --(Renderer)--> MinieRenderer
        --(AvatarRenderer)--> VTubeStudioAvatarRenderer

`render_state()` does two things: (1) delegates straight to
`AvatarRenderer.render_state()` (the `PresentationConfig.
vtube_studio_parameter_mapping`-driven parameter-injection path,
handled entirely inside the held `AvatarRenderer`); (2) derives a
coarse `expression_id` from `state.smile_intensity`/`.voice_warmth` via
`_derive_expression_id()`'s own config-driven threshold table
(`PresentationConfig.minie_expression_thresholds`), calling
`AvatarRenderer.set_expression()` only when that derived id actually
changes from the last one sent — never every tick, avoiding flooding
the avatar backend with redundant identical calls.

`set_mouth_open()`/`set_eye_target()` have no real caller yet from this
class — lip-sync (Sprint 5.11, driven by real TTS audio timing) and
eye-tracking are later sprints' own jobs, not built here.
`trigger_gesture()` (Sprint 5.9) forwards its gesture_id verbatim to
the held AvatarRenderer — MinieRenderer itself makes no attempt to
interpret or remap it, matching this class's own "thin adapter"
contract; the real per-id meaning lives entirely inside whatever the
user's own loaded Live2D model defines.
"""

from config.schema import PresentationConfig
from presentation.avatar_renderer import AvatarRenderer
from presentation.presentation_state import PresentationState


def _derive_expression_id(state: PresentationState, thresholds: dict[str, float]) -> str:
    """A small, config-driven threshold lookup — never a hardcoded
    vocabulary (03_Engineering_Standards.md's own "no hardcoded...
    thresholds" rule, the same discipline personas/jarvis.py's/
    personas/minie.py's own _select_tone_variant() already established
    at Sprint 5.4). expressiveness blends both named signals
    (this sprint's own Expected Functions: "derives... from
    state.smile_intensity/voice_warmth") since neither alone is named
    as the sole driver. The highest-threshold entry the current reading
    meets wins; PresentationConfig._validate_presentation() guarantees
    a 0.0-threshold entry always exists as a reachable floor."""
    expressiveness = (state.smile_intensity + state.voice_warmth) / 2.0
    for expression_id, threshold in sorted(
        thresholds.items(), key=lambda item: item[1], reverse=True
    ):
        if expressiveness >= threshold:
            return expression_id
    return "neutral"  # unreachable given a validated config; an honest fallback, not a crash


class MinieRenderer:
    """Constructor DI per 03_Engineering_Standards.md: receives an
    AvatarRenderer instance (via presentation/avatar_renderer_registry.py's
    create_avatar_renderer(), not constructed internally) and
    PresentationConfig. Implements Renderer (presentation/renderer.py)
    structurally (Protocol, no explicit inheritance needed)."""

    def __init__(
        self, avatar_renderer: AvatarRenderer, presentation_config: PresentationConfig
    ) -> None:
        self._avatar = avatar_renderer
        self._config = presentation_config
        self._last_expression_id: str | None = None

    def mount(self) -> None:
        self._avatar.mount()

    def unmount(self) -> None:
        self._avatar.unmount()
        # The avatar's own actual displayed expression is no longer
        # known to be current once unmounted — forget it so the first
        # render_state() after a remount always re-sends a fresh
        # set_expression() rather than potentially skipping it.
        self._last_expression_id = None

    def render_state(self, state: PresentationState) -> None:
        self._avatar.render_state(state)
        self._maybe_set_expression(state)

    def trigger_gesture(self, gesture_id: str) -> None:
        self._avatar.trigger_gesture(gesture_id)

    def _maybe_set_expression(self, state: PresentationState) -> None:
        expression_id = _derive_expression_id(state, self._config.minie_expression_thresholds)
        if expression_id == self._last_expression_id:
            return
        self._avatar.set_expression(expression_id)
        self._last_expression_id = expression_id
