"""Minie display-emotion adapter (Minie Persona UI workstream).

ui/minie/emotion_panel.py shows four labeled bars — Happiness, Calmness,
Trust, Affection — matching the reference UI's own "Minie's Emotion"
panel. None of those four names exist on emotion/state_manager.py's own
EmotionalState (mood/energy/stress/focus/comfort/social_energy/
conversation_momentum) — this module is the presentation-layer adapter
that bridges the two, per the workstream's own resolved architecture
decision: "the only new emotion code is a presentation adapter, never a
second emotion engine." derive_display_emotions() reads real
EmotionalStateManager.current_state() output and reshapes it; it holds
no state of its own and consults no other data source.

The mapping (a real, disclosed, first-pass choice — same category as
this project's other tuned-but-unvalidated formulas, e.g.
presentation/minie_state_computer.py's own warmth_fraction blend):
- happiness <- mood (-100..100, rescaled to 0..100) — mood is this
  project's own closest existing "positive/negative overall feeling"
  dimension.
- calmness <- 100 - stress — the inverse of EmotionalState's own stress
  reading (0..100), so a calmer user (low stress) reads as high
  calmness.
- trust <- comfort — EmotionalState's own comfort dimension already
  means "how safe/at-ease does this feel," the closest existing analog
  to "trust."
- affection <- social_energy — EmotionalState's own social_energy
  dimension already means "how much does this user want connection/
  interaction right now," the closest existing analog to "affection."

Every output is clamped to 0..100 via presentation/presentation_state.py's
own shared clamp()/fraction_of() helpers (reused, not reimplemented) —
the same defensive-bounds discipline every PresentationStateComputer
already applies.
"""

from dataclasses import dataclass

from emotion.state_manager import EmotionalState
from presentation.presentation_state import clamp, fraction_of


@dataclass
class MinieDisplayEmotions:
    """Four 0.0-100.0 percentages, one per labeled bar
    ui/minie/emotion_panel.py renders — see this module's own docstring
    for the real EmotionalState field each is derived from."""

    happiness: float
    calmness: float
    trust: float
    affection: float


def derive_display_emotions(state: EmotionalState) -> MinieDisplayEmotions:
    """Never raises — every EmotionalState field is already clamped at
    the source (emotion/state_manager.py's own _clamp_dimension()), and
    fraction_of()/clamp() are defensive against any input regardless."""
    happiness = fraction_of(state.mood, -100.0, 100.0) * 100.0
    calmness = 100.0 - fraction_of(state.stress, 0.0, 100.0) * 100.0
    trust = fraction_of(state.comfort, 0.0, 100.0) * 100.0
    affection = fraction_of(state.social_energy, 0.0, 100.0) * 100.0

    return MinieDisplayEmotions(
        happiness=clamp(happiness, 0.0, 100.0),
        calmness=clamp(calmness, 0.0, 100.0),
        trust=clamp(trust, 0.0, 100.0),
        affection=clamp(affection, 0.0, 100.0),
    )
