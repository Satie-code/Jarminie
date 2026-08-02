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
"""

from collections.abc import Callable

from config.schema import PresentationConfig
from presentation.avatar_renderer import AvatarRenderer
from presentation.vtube_studio_renderer import VTubeStudioAvatarRenderer


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
