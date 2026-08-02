"""Presentation State Engine (Sprint 5.5 — Level 5 Part A).

The intermediate layer the brief mandates explicitly: "Renderers consume
this state. They do not determine emotion themselves." This module
defines `PresentationState` — one concrete, renderer-agnostic set of
numeric/enum outputs (smile intensity, eye openness, voice warmth,
animation speed, particle density, lighting color, UI accent, gesture
probability, avatar focus) computed from an `EmotionalState` (5.2) and
the active persona — and `PresentationStateComputer`, the Protocol one
concrete computer per persona (`presentation/jarvis_state_computer.py`/
`presentation/minie_state_computer.py`) implements. This is the middle
node of the brief's own architecture diagram: `Persona Controller ->
Presentation State -> Renderer Interface -> {Jarvis Renderer, Minie
Renderer}` — Sprint 5.6 builds the coordinator around this seam.

"Renderers consume this state. They do not determine emotion
themselves" is enforced structurally here, not just by convention:
`PresentationState` carries no reference back to `EmotionalState`,
`Intent`, or `ContextAnalysis` — a renderer given only a
`PresentationState` object cannot re-derive or second-guess the
emotional read that produced it.

No live caller until Sprint 5.6 (`PresentationController`) — the
tightest "component then integration" gap in this Sprint Book, since
5.5/5.6 are two halves of one architectural seam split for testability,
not for a long standalone lifespan. See docs/sprint_book/sprint_5/sprint_5_5.md.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from emotion.state_manager import EmotionalState
from voice.quiet_mode import OperatingMode

AVATAR_FOCUS_IDLE = "idle"
AVATAR_FOCUS_USER = "user"
AVATAR_FOCUS_TASK = "task"
"""The three avatar_focus values named by this sprint's own Expected
Classes. AVATAR_FOCUS_TASK has no real producer yet — Sprint 5.12
(Adaptive Workspace) is named as the sprint that gives it one; every
compute() in this Level until then can only ever return IDLE or USER,
never TASK — an honest capability gap, not a hidden one."""


@dataclass
class PresentationState:
    """One renderer-agnostic snapshot of what a persona should currently
    look/sound like — the nine brief-mandated fields, persona-agnostic
    in shape (the same fields exist regardless of which persona is
    active) but persona-aware in the values a given
    PresentationStateComputer produces (see that Protocol below).

    smile_intensity/eye_openness/voice_warmth/particle_density/
    gesture_probability: float, 0.0-1.0. animation_speed: float,
    0.5-2.0 (a multiplier against each renderer's own base animation
    timing; 1.0 is neutral/default speed). lighting_color/ui_accent:
    "#RRGGBB" hex color strings — the brief's own locked per-persona
    palettes (identity, not mood-driven; see this module's own
    docstring and PresentationConfig's). avatar_focus: one of
    AVATAR_FOCUS_IDLE/AVATAR_FOCUS_USER/AVATAR_FOCUS_TASK above.
    persona_name: which persona this state was computed for — carried
    along so a renderer receiving a stale/mismatched state can detect
    and discard it (a defensive check exercised in Sprint 5.15).
    """

    smile_intensity: float
    eye_openness: float
    voice_warmth: float
    animation_speed: float
    particle_density: float
    lighting_color: str
    ui_accent: str
    gesture_probability: float
    avatar_focus: str
    persona_name: str
    computed_at: datetime


class PresentationStateComputer(Protocol):
    """A single-method contract, deliberately minimal — the same "kept
    deliberately minimal" precedent SpeechToText/SearchProvider/
    LanguageModelClient already established. One implementation per
    persona (JarvisPresentationStateComputer/MiniePresentationStateComputer)
    since the *mapping* from EmotionalState to visual output genuinely
    differs enough per persona's own locked identity that a single
    shared formula would either be bland for both or require ad hoc
    persona-name branching inside one method — see this sprint's own
    Engineering Rationale."""

    def compute(
        self, emotional_state: EmotionalState, operating_mode: OperatingMode
    ) -> PresentationState: ...


def clamp(value: float, low: float, high: float) -> float:
    """Shared defensive-bounds helper — every computed field is clamped
    to its documented valid range before being placed on
    PresentationState, the same discipline EmotionalState's own
    dimension clamping (Sprint 5.2, emotion/state_manager.py's
    _clamp_dimension()) already established. Public (not module-private)
    since both persona computers, in separate modules, share it."""
    return max(low, min(high, value))


def fraction_of(value: float, domain_low: float, domain_high: float) -> float:
    """Normalize value from [domain_low, domain_high] to [0.0, 1.0],
    clamped defensively against an out-of-domain input (EmotionalState's
    own dimensions are already clamped at the source, but this helper
    makes no assumption about its caller)."""
    if domain_high == domain_low:
        return 0.0
    return clamp((value - domain_low) / (domain_high - domain_low), 0.0, 1.0)


def scale_into_range(fraction: float, low: float, high: float) -> float:
    """Map a 0.0-1.0 fraction into a persona's configured [low, high]
    output range, clamped defensively."""
    return clamp(low + fraction * (high - low), low, high)


def avatar_focus_from_operating_mode(operating_mode: OperatingMode) -> str:
    """Shared by both persona computers so the DORMANT->idle/ACTIVE->user
    mapping cannot drift between them (this sprint's own Potential Risks:
    "two independent per-persona formulas risk drifting inconsistently").
    AVATAR_FOCUS_TASK is not reachable here — see AVATAR_FOCUS_TASK's own
    module-level comment above."""
    if operating_mode is OperatingMode.DORMANT:
        return AVATAR_FOCUS_IDLE
    return AVATAR_FOCUS_USER
