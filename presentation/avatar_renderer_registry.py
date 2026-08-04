"""Avatar Renderer Registry — resolves PresentationConfig.avatar_backend
into a real, concrete AvatarRenderer implementation. Mirrors
internet/search_provider_registry.py's own precedent exactly: the one
place that maps a config-driven backend name to a real class, so
nothing else (MinieRenderer, main.py's own future composition) ever
hardcodes which avatar backend is active.

**Adding a new backend** (a direct Live2D Cubism SDK embed, an Unreal
bridge, a Unity bridge) takes exactly two steps:
1. Write one new class implementing the AvatarRenderer Protocol
   (presentation/avatar_renderer.py) — its own file, mirroring
   vtube_studio_renderer.py's shape (constructor DI on
   PresentationConfig, the four AvatarRenderer-specific methods plus
   Renderer's own three, never raising, degrading to a safe no-op when
   unavailable).
2. Add one entry to _BACKENDS below, keyed by the name users will set
   PresentationConfig.avatar_backend to.

This is a plain function-based registry, not a stateful class —
deliberately simpler than device_control/action_engine.py's
ActionRegistry, since a single AvatarRenderer is what's active at a
time (MinieRenderer holds exactly one). Do not generalize this into
something heavier before a real, concrete need for it exists.

**NullAvatarRenderer (Sprint 5.15, scenario e)**: a real, concrete,
always-inert `AvatarRenderer` implementation — used by `main.py`'s own
Level 5 Part A construction fallback when `_construct_level5_modules()`
itself raises (e.g. `create_avatar_renderer()` below raising
`UnknownAvatarBackendError` for a misconfigured `avatar_backend`), so a
broken avatar-backend construction never takes Levels 1-4 down with it.
Mirrors `presentation/transition_engine.py`'s own `NullTransitionOverlay`
precedent exactly: every method is a safe, logged no-op, `is_connected()`
always returns False. Not returned by `create_avatar_renderer()` itself
— that function's own "fail loud on an unknown backend" contract is
unchanged; `NullAvatarRenderer` is main.py's own fallback construction
tool, not a registered backend name.
"""

from collections.abc import Callable

from config.schema import PresentationConfig
from core.logging_setup import get_logger
from presentation.avatar_renderer import AvatarRenderer
from presentation.presentation_state import PresentationState
from presentation.vtube_studio_renderer import VTubeStudioAvatarRenderer

logger = get_logger(__name__)


class UnknownAvatarBackendError(Exception):
    """Raised when PresentationConfig.avatar_backend names a backend with
    no registered implementation — a construction-time configuration
    error, deliberately loud (never caught/degraded), matching this
    project's own "fail fast on a broken composition, fail gracefully
    on a runtime operation" split (mirrors
    internet/search_provider_registry.py's UnknownSearchProviderError
    exactly)."""


_BACKENDS: dict[str, Callable[[PresentationConfig], AvatarRenderer]] = {
    "vtube_studio": VTubeStudioAvatarRenderer,
}


def create_avatar_renderer(presentation_config: PresentationConfig) -> AvatarRenderer:
    """Constructs the AvatarRenderer implementation
    presentation_config.avatar_backend names ("vtube_studio" is the
    only real, registered value this sprint). Raises
    UnknownAvatarBackendError (never a raw KeyError) for an
    unregistered name, naming every real, available option in the
    message so a typo/misconfiguration is immediately actionable."""
    name = presentation_config.avatar_backend
    try:
        backend_cls = _BACKENDS[name]
    except KeyError:
        raise UnknownAvatarBackendError(
            f"Unknown avatar backend {name!r}. Registered backends: {sorted(_BACKENDS)}."
        ) from None
    return backend_cls(presentation_config)


class NullAvatarRenderer:
    """Sprint 5.15, scenario (e) — see this module's own docstring.
    Structurally implements AvatarRenderer (Protocol, no explicit
    inheritance needed), mirroring TransitionEngine's own
    NullTransitionOverlay: every method is a safe, logged no-op."""

    def mount(self) -> None:
        logger.info("NullAvatarRenderer.mount() — no real avatar backend available.")

    def unmount(self) -> None:
        pass

    def render_state(self, state: PresentationState) -> None:
        pass

    def set_expression(self, expression_id: str) -> None:
        pass

    def set_mouth_open(self, amount: float) -> None:
        pass

    def set_eye_target(self, x: float, y: float) -> None:
        pass

    def trigger_gesture(self, gesture_id: str) -> None:
        pass

    def is_connected(self) -> bool:
        return False
