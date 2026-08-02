"""MiniePresentationStateComputer (Sprint 5.5 — Level 5 Part A).

Expresses the brief's own locked Minie visual identity ("Warm.
Comforting. Expressive... breathing, blinking, looking around, head
tilts, small smiles") as a wide PresentationConfig range on every field,
genuinely tracking EmotionalState rather than pinning to a fixed point
(contrast JarvisPresentationStateComputer's own "minimal, mostly static"
design — see that module's own docstring).

- smile_intensity/eye_openness/voice_warmth are driven by a blended
  "warmth" fraction of EmotionalState.comfort and .mood (higher
  comfort/mood -> warmer, more open, more expressive), per this
  sprint's own Expected Functions.
- animation_speed is driven by a blend of EmotionalState.energy
  (positively) and .stress (inversely) — energy alone would satisfy
  this sprint's own Expected Functions bullet in isolation, but adding
  the inverse-stress term is what makes "higher stress -> lower
  animation_speed" (this sprint's own Potential Risks cross-persona
  consistency check) hold for Minie too, not just Jarvis. A real,
  disclosed implementation-time resolution of that spec tension — see
  sprint_5_5.md's own Sprint Completion Report.
- particle_density is driven purely by EmotionalState.energy, per this
  sprint's own Expected Functions ("gentle particle ambiance scales
  with energy, never Jarvis's near-zero default").
- gesture_probability is driven by the same blend as animation_speed's
  energy term and the warmth fraction above (more comfortable/energetic
  -> more likely to gesture) — not individually named by this sprint's
  own Expected Functions, a disclosed implementation-time choice.

lighting_color/ui_accent are fixed to the locked lavender/rose-gold
palette (PresentationConfig.minie_lighting_color/minie_ui_accent) —
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


class MiniePresentationStateComputer:
    """Constructor DI per 03_Engineering_Standards.md: receives only the
    PresentationConfig it reads its own minie_* range/color fields from.
    Implements PresentationStateComputer structurally (Protocol, no
    explicit inheritance needed)."""

    def __init__(self, presentation_config: PresentationConfig) -> None:
        self._config = presentation_config

    def compute(
        self, emotional_state: EmotionalState, operating_mode: OperatingMode
    ) -> PresentationState:
        """Never raises for any EmotionalState/OperatingMode input —
        every field is a fraction of one or more EmotionalState
        dimensions (always defined, already clamped at the source)
        scaled into a configured range."""
        config = self._config

        comfort_fraction = fraction_of(emotional_state.comfort, 0.0, 100.0)
        mood_fraction = fraction_of(emotional_state.mood, -100.0, 100.0)
        energy_fraction = fraction_of(emotional_state.energy, 0.0, 100.0)
        stress_fraction = fraction_of(emotional_state.stress, 0.0, 100.0)

        warmth_fraction = (comfort_fraction + mood_fraction) / 2.0
        speed_fraction = (energy_fraction + (1.0 - stress_fraction)) / 2.0
        gesture_fraction = (warmth_fraction + energy_fraction) / 2.0

        smile_intensity = scale_into_range(
            warmth_fraction, config.minie_smile_intensity_min, config.minie_smile_intensity_max
        )
        eye_openness = scale_into_range(
            warmth_fraction, config.minie_eye_openness_min, config.minie_eye_openness_max
        )
        voice_warmth = scale_into_range(
            warmth_fraction, config.minie_voice_warmth_min, config.minie_voice_warmth_max
        )
        animation_speed = scale_into_range(
            speed_fraction, config.minie_animation_speed_min, config.minie_animation_speed_max
        )
        particle_density = scale_into_range(
            energy_fraction, config.minie_particle_density_min, config.minie_particle_density_max
        )
        gesture_probability = scale_into_range(
            gesture_fraction,
            config.minie_gesture_probability_min,
            config.minie_gesture_probability_max,
        )

        return PresentationState(
            smile_intensity=clamp(smile_intensity, 0.0, 1.0),
            eye_openness=clamp(eye_openness, 0.0, 1.0),
            voice_warmth=clamp(voice_warmth, 0.0, 1.0),
            animation_speed=clamp(animation_speed, 0.5, 2.0),
            particle_density=clamp(particle_density, 0.0, 1.0),
            lighting_color=config.minie_lighting_color,
            ui_accent=config.minie_ui_accent,
            gesture_probability=clamp(gesture_probability, 0.0, 1.0),
            avatar_focus=avatar_focus_from_operating_mode(operating_mode),
            persona_name="minie",
            computed_at=datetime.now(UTC),
        )
