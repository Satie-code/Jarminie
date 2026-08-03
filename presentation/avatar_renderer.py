"""AvatarRenderer Protocol (Sprint 5.8 — Level 5 Part A).

A narrower interface than Renderer (Sprint 5.6), purpose-built for
expressive avatar control (expression, lip sync, eye tracking,
gestures) — extends Renderer's three generic methods with four
avatar-specific ones, since render_state() alone would force every
avatar-specific concept (expression, mouth shape, gaze target) into one
opaque call.

**Swap-target guarantee** (mirrors internet/search_provider.py's own
docstring for its own, structurally identical guarantee): replacing
VTube Studio with a direct Live2D Cubism SDK embed, an Unreal bridge,
or a Unity bridge later needs one new AvatarRenderer implementation
(presentation/vtube_studio_renderer.py's own shape) plus one registry
entry (presentation/avatar_renderer_registry.py's create_avatar_renderer())
— MinieRenderer itself, and everything above it (PresentationController,
Sprint 5.6), is untouched. Nothing outside presentation/
vtube_studio_renderer.py may import anything VTube-Studio-specific —
a structural, mechanically-checked property (this sprint's own Testing
Checklist), the same guarantee internet/search_provider_registry.py
already gives the Internet Agent for its own provider choice.
"""

from typing import Protocol

from presentation.renderer import Renderer


class AvatarRenderer(Renderer, Protocol):
    """The four additional methods, plus the inherited mount()/
    unmount()/render_state() (Renderer, Sprint 5.6). Every method must
    degrade to a safe no-op (logged, never raised) when the underlying
    avatar backend is unavailable — see VTubeStudioAvatarRenderer's own
    docstring for the concrete "disconnected, never crash" contract."""

    def set_expression(self, expression_id: str) -> None:
        """A named Live2D expression/hotkey trigger (e.g. a smile, a
        concerned look). The exact vocabulary of expression_id values is
        config-driven, matched against whatever expressions/hotkeys the
        user's own loaded Live2D model actually defines inside VTube
        Studio — never assumed to exist."""
        ...

    def set_mouth_open(self, amount: float) -> None:
        """0.0-1.0 lip-sync target. The real per-frame-audio-driven
        caller is Sprint 5.11's Voice Personality/TTS integration, not
        Sprint 5.8."""
        ...

    def set_eye_target(self, x: float, y: float) -> None:
        """-1.0..1.0 normalized gaze direction on each axis; (0, 0) is
        forward. No real caller yet — Sprint 5.9's Gesture Engine or a
        later gaze-tracking sprint."""
        ...

    def trigger_gesture(self, gesture_id: str) -> None:
        """A one-shot animation (e.g. a head tilt or small wave). The
        real caller is Sprint 5.9's Gesture Engine, not Sprint 5.8."""
        ...

    def is_connected(self) -> bool:
        """Sprint 5.14: whether the underlying avatar backend is
        currently connected — MinieRenderer.status_widget()'s own real
        caller, so `PresentationHostWidget` can show an honest
        "Connected to VTube Studio" / "VTube Studio not detected" status
        instead of a fake in-app avatar standing in for the real one
        (Sprint 5.14's own Engineering Rationale). Never raises."""
        ...
