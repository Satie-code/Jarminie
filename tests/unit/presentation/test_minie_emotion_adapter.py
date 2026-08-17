"""Unit tests for presentation.minie_emotion_adapter."""

from emotion.state_manager import EmotionalState
from presentation.minie_emotion_adapter import MinieDisplayEmotions, derive_display_emotions


def test_neutral_state_maps_to_midpoint_values():
    result = derive_display_emotions(EmotionalState())

    assert result == MinieDisplayEmotions(happiness=50.0, calmness=50.0, trust=50.0, affection=50.0)


def test_positive_mood_raises_happiness():
    result = derive_display_emotions(EmotionalState(mood=100.0))

    assert result.happiness == 100.0


def test_negative_mood_lowers_happiness():
    result = derive_display_emotions(EmotionalState(mood=-100.0))

    assert result.happiness == 0.0


def test_low_stress_raises_calmness():
    result = derive_display_emotions(EmotionalState(stress=0.0))

    assert result.calmness == 100.0


def test_high_stress_lowers_calmness():
    result = derive_display_emotions(EmotionalState(stress=100.0))

    assert result.calmness == 0.0


def test_comfort_maps_directly_to_trust():
    result = derive_display_emotions(EmotionalState(comfort=87.0))

    assert result.trust == 87.0


def test_social_energy_maps_directly_to_affection():
    result = derive_display_emotions(EmotionalState(social_energy=99.0))

    assert result.affection == 99.0


def test_every_field_is_clamped_to_0_100():
    result = derive_display_emotions(
        EmotionalState(mood=100.0, stress=0.0, comfort=100.0, social_energy=100.0)
    )

    for value in (result.happiness, result.calmness, result.trust, result.affection):
        assert 0.0 <= value <= 100.0


def test_never_raises_for_a_boundary_state():
    derive_display_emotions(
        EmotionalState(mood=-100.0, stress=100.0, comfort=0.0, social_energy=0.0)
    )
