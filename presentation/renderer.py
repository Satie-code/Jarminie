"""Renderer Protocol (Sprint 5.6 — Level 5 Part A).

The abstraction every concrete renderer (Sprint 5.7's `JarvisRenderer`,
Sprint 5.8's `VTubeStudioAvatarRenderer`) implements — the last node of
the brief's own mandated architecture: `Persona Controller ->
Presentation State -> Renderer Interface -> {Jarvis Renderer, Minie
Renderer}`.

Deliberately minimal — three methods — mirroring `ManagedModule`'s own
"kept deliberately minimal... to avoid over-fitting to subsystems that
don't exist yet" precedent (`core/module_registry.py`, Sprint 1.5). No
method is persona-specific: `PresentationController` never asks a
renderer "are you Jarvis or Minie," it simply always has the currently
correct one mounted (Sprint 5.10's Persona Transition Engine owns
swapping which one is mounted).

If two real implementations (Sprint 5.7/5.8) discover a genuine shared
need this Protocol doesn't anticipate (e.g. a renderer-level
`health_check()`), extend it then — a normal, low-cost change, not a
redesign (this sprint's own Potential Risks).
"""

from typing import Protocol

from presentation.presentation_state import PresentationState


class Renderer(Protocol):
    """mount()/unmount() handle setup/teardown around this renderer's own
    resource (a widget, a window, a network connection — Sprint 5.8's
    VTube Studio renderer genuinely needs a connect/disconnect
    lifecycle Jarvis's in-process widget renderer does not, but both
    fit this same shape). unmount() must be safe to call even if
    mount() was never called or already failed (Fail Gracefully,
    exercised concretely in Sprint 5.15).

    render_state() applies one PresentationState snapshot and MUST be
    cheap/non-blocking — PresentationController.refresh() calls it
    synchronously, once per tick, with no timeout of its own; a slow
    renderer stalls every subsequent tick's caller, not just its own
    frame. This is a real constraint every future implementation must
    honor, not just documentation."""

    def mount(self) -> None: ...

    def unmount(self) -> None: ...

    def render_state(self, state: PresentationState) -> None: ...
