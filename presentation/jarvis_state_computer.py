"""JarvisPresentationStateComputer (Sprint 5.5 — Level 5 Part A).

Expresses the brief's own locked Jarvis visual identity ("Minimal.
Confident. Adaptive... smooth, deliberate, purposeful [animations]. No
flashy cyberpunk effects.") as a narrow, low PresentationConfig range on
every field. Only animation_speed and avatar_focus meaningfully move
with EmotionalState/OperatingMode for this persona — every other field
is pinned to a fixed point within its own configured range rather than
tracking emotion continuously, a deliberate, disclosed implementation-time
reading of the spec's own "pinned low by default" language (explicit for
smile_intensity/particle_density; extended here to eye_openness/
voice_warmth/gesture_probability for the same "minimal, professional,
not a mood ring" reasoning — see this module's own _compute() body).

lighting_color/ui_accent are fixed to the locked electric-blue/cyan
palette (PresentationConfig.jarvis_lighting_color/jarvis_ui_accent) —
identity, not emotion-driven; see presentation/presentation_state.py's
own docstring.

No live caller until Sprint 5.6 (PresentationController). See
docs/sprint_book/sprint_5/sprint_5_5.md.
"""

from datetime import UTC, datetime

from config.schema import PresentationConfig
from emotion.state_manager import EmotionalState
from presentation.presentation_state import (
    PresentationState,
    avatar_focus_from_operating_mode,
    clamp,
    fraction_of,
    scale_into_range,
)
from voice.quiet_mode import OperatingMode


class JarvisPresentationStateComputer:
    """Constructor DI per 03_Engineering_Standards.md: receives only the
    PresentationConfig it reads its own jarvis_* range/color fields
    from. Implements PresentationStateComputer structurally (Protocol,
    no explicit inheritance needed)."""

    def __init__(self, presentation_config: PresentationConfig) -> None:
        self._config = presentation_config

    def compute(
        self, emotional_state: EmotionalState, operating_mode: OperatingMode
    ) -> PresentationState:
        """Never raises for any EmotionalState/OperatingMode input — every
        field is either a fixed configured point or a fraction of
        emotional_state.stress scaled into a configured range, both of
        which are always defined."""
        config = self._config

        # Only field that genuinely tracks emotion: higher stress ->
        # lower animation_speed (more deliberate, less hurried) — the
        # same direction this sprint's own Potential Risks names as the
        # cross-persona consistency check ("higher stress -> lower
        # animation_speed for both").
        stress_fraction = fraction_of(emotional_state.stress, 0.0, 100.0)
        speed_fraction = 1.0 - stress_fraction
        animation_speed = scale_into_range(
            speed_fraction, config.jarvis_animation_speed_min, config.jarvis_animation_speed_max
        )

        # Every other numeric field is pinned to a fixed point within
        # its own narrow configured range — "minimal, professional,
        # never a mood ring" for this persona (this module's own
        # docstring). smile_intensity/particle_density pin to their
        # range's own low bound (explicit in the spec: "pinned low by
        # default"); eye_openness/voice_warmth/gesture_probability pin
        # to their range's own midpoint (a neutral, alert-but-not-
        # expressive baseline — this sprint's own disclosed extension of
        # the same reasoning to fields the spec didn't individually
        # name).
        smile_intensity = config.jarvis_smile_intensity_min
        particle_density = config.jarvis_particle_density_min
        eye_openness = _midpoint(config.jarvis_eye_openness_min, config.jarvis_eye_openness_max)
        voice_warmth = _midpoint(config.jarvis_voice_warmth_min, config.jarvis_voice_warmth_max)
        gesture_probability = config.jarvis_gesture_probability_min

        return PresentationState(
            smile_intensity=clamp(smile_intensity, 0.0, 1.0),
            eye_openness=clamp(eye_openness, 0.0, 1.0),
            voice_warmth=clamp(voice_warmth, 0.0, 1.0),
            animation_speed=clamp(animation_speed, 0.5, 2.0),
            particle_density=clamp(particle_density, 0.0, 1.0),
            lighting_color=config.jarvis_lighting_color,
            ui_accent=config.jarvis_ui_accent,
            gesture_probability=clamp(gesture_probability, 0.0, 1.0),
            avatar_focus=avatar_focus_from_operating_mode(operating_mode),
            persona_name="jarvis",
            computed_at=datetime.now(UTC),
        )


def _midpoint(low: float, high: float) -> float:
    return (low + high) / 2.0
