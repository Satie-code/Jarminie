"""Unit tests for presentation.presentation_state,
presentation.jarvis_state_computer, and presentation.minie_state_computer
(Sprint 5.5).

tests/ has no __init__.py by convention since Sprint 1.1 (see
tests/unit/personas/conftest.py's own docstring) — this sprint's own
Files to Create names tests/unit/presentation/__init__.py, but that
contradicts the established, documented convention with zero other
precedent anywhere in tests/; not created here, a disclosed deviation
(see sprint_5_5.md's own Sprint Completion Report).
"""

from dataclasses import replace

import pytest

from config.schema import PresentationConfig
from emotion.state_manager import EmotionalState
from presentation.jarvis_state_computer import JarvisPresentationStateComputer
from presentation.minie_state_computer import MiniePresentationStateComputer
from presentation.presentation_state import (
    AVATAR_FOCUS_IDLE,
    AVATAR_FOCUS_USER,
    PresentationState,
    avatar_focus_from_operating_mode,
    clamp,
    fraction_of,
    scale_into_range,
)
from voice.quiet_mode import OperatingMode

_CONFIG = PresentationConfig()

_REPRESENTATIVE_STATES: dict[str, EmotionalState] = {
    "neutral": EmotionalState(),
    "high_stress": replace(EmotionalState(), stress=95.0),
    "low_stress": replace(EmotionalState(), stress=5.0),
    "high_comfort": replace(EmotionalState(), comfort=95.0, mood=80.0),
    "low_comfort": replace(EmotionalState(), comfort=5.0, mood=-80.0),
    "low_energy": replace(EmotionalState(), energy=5.0),
    "high_energy": replace(EmotionalState(), energy=95.0),
}

_COMPUTERS = {
    "jarvis": JarvisPresentationStateComputer(_CONFIG),
    "minie": MiniePresentationStateComputer(_CONFIG),
}

_UNIT_RANGE_FIELDS = (
    "smile_intensity",
    "eye_openness",
    "voice_warmth",
    "particle_density",
    "gesture_probability",
)


# --- range/clamping enforcement (both boundaries, every field) ---------------


@pytest.mark.parametrize("computer_name", ["jarvis", "minie"])
@pytest.mark.parametrize("state_name", list(_REPRESENTATIVE_STATES))
@pytest.mark.parametrize("operating_mode", list(OperatingMode))
def test_every_field_within_documented_range(computer_name, state_name, operating_mode):
    computer = _COMPUTERS[computer_name]
    state = computer.compute(_REPRESENTATIVE_STATES[state_name], operating_mode)

    for field_name in _UNIT_RANGE_FIELDS:
        value = getattr(state, field_name)
        assert 0.0 <= value <= 1.0, f"{field_name}={value} out of [0.0, 1.0]"
    assert 0.5 <= state.animation_speed <= 2.0
    assert state.avatar_focus in (AVATAR_FOCUS_IDLE, AVATAR_FOCUS_USER)


@pytest.mark.parametrize("computer_name", ["jarvis", "minie"])
def test_extreme_emotional_state_boundaries_stay_within_range(computer_name):
    """Every EmotionalState dimension pushed to its own structural
    extreme (not just a representative spread) — the real adversarial
    sweep this sprint's own Acceptance Criteria asks for ("across the
    full range of possible EmotionalState/OperatingMode inputs")."""
    computer = _COMPUTERS[computer_name]
    extremes = [
        replace(EmotionalState(), mood=-100.0),
        replace(EmotionalState(), mood=100.0),
        replace(EmotionalState(), energy=0.0),
        replace(EmotionalState(), energy=100.0),
        replace(EmotionalState(), stress=0.0),
        replace(EmotionalState(), stress=100.0),
        replace(EmotionalState(), comfort=0.0),
        replace(EmotionalState(), comfort=100.0),
        replace(
            EmotionalState(), mood=-100.0, energy=0.0, stress=100.0, comfort=0.0
        ),  # worst case, all at once
        replace(
            EmotionalState(), mood=100.0, energy=100.0, stress=0.0, comfort=100.0
        ),  # best case, all at once
    ]
    for extreme_state in extremes:
        for operating_mode in OperatingMode:
            state = computer.compute(extreme_state, operating_mode)
            for field_name in _UNIT_RANGE_FIELDS:
                value = getattr(state, field_name)
                assert 0.0 <= value <= 1.0
            assert 0.5 <= state.animation_speed <= 2.0


# --- Jarvis "no flashy effects" vs Minie "expressive" (Acceptance Criteria) --


@pytest.mark.parametrize("state_name", list(_REPRESENTATIVE_STATES))
def test_jarvis_particle_density_always_lower_than_minie(state_name):
    state = _REPRESENTATIVE_STATES[state_name]
    jarvis_value = _COMPUTERS["jarvis"].compute(state, OperatingMode.ACTIVE).particle_density
    minie_value = _COMPUTERS["minie"].compute(state, OperatingMode.ACTIVE).particle_density

    assert jarvis_value < minie_value


@pytest.mark.parametrize("state_name", list(_REPRESENTATIVE_STATES))
def test_jarvis_smile_intensity_always_lower_than_minie(state_name):
    state = _REPRESENTATIVE_STATES[state_name]
    jarvis_value = _COMPUTERS["jarvis"].compute(state, OperatingMode.ACTIVE).smile_intensity
    minie_value = _COMPUTERS["minie"].compute(state, OperatingMode.ACTIVE).smile_intensity

    assert jarvis_value < minie_value


def test_jarvis_particle_density_structurally_below_minie_minimum():
    """Stronger than "typically lower" — Jarvis's own configured range
    ceiling sits below Minie's own configured range floor, so the
    inequality holds by construction, not just for the tested inputs."""
    assert _CONFIG.jarvis_particle_density_max < _CONFIG.minie_particle_density_min
    assert _CONFIG.jarvis_smile_intensity_max < _CONFIG.minie_smile_intensity_min


# --- direction consistency across personas (Potential Risks) -----------------


def test_higher_stress_produces_lower_animation_speed_for_both_personas():
    low_stress = replace(EmotionalState(), stress=10.0)
    high_stress = replace(EmotionalState(), stress=90.0)

    for computer in _COMPUTERS.values():
        low_stress_speed = computer.compute(low_stress, OperatingMode.ACTIVE).animation_speed
        high_stress_speed = computer.compute(high_stress, OperatingMode.ACTIVE).animation_speed
        assert high_stress_speed < low_stress_speed


# --- avatar_focus / operating_mode --------------------------------------------


@pytest.mark.parametrize("computer_name", ["jarvis", "minie"])
def test_dormant_operating_mode_produces_idle_focus(computer_name):
    state = _COMPUTERS[computer_name].compute(EmotionalState(), OperatingMode.DORMANT)
    assert state.avatar_focus == AVATAR_FOCUS_IDLE


@pytest.mark.parametrize("computer_name", ["jarvis", "minie"])
def test_active_operating_mode_produces_user_focus(computer_name):
    state = _COMPUTERS[computer_name].compute(EmotionalState(), OperatingMode.ACTIVE)
    assert state.avatar_focus == AVATAR_FOCUS_USER


def test_avatar_focus_from_operating_mode_shared_helper_covers_both_modes():
    assert avatar_focus_from_operating_mode(OperatingMode.DORMANT) == AVATAR_FOCUS_IDLE
    assert avatar_focus_from_operating_mode(OperatingMode.ACTIVE) == AVATAR_FOCUS_USER


# --- Minie: genuinely emotion-driven ------------------------------------------


def test_minie_smile_intensity_increases_with_comfort_and_mood():
    low = _COMPUTERS["minie"].compute(
        replace(EmotionalState(), comfort=5.0, mood=-80.0), OperatingMode.ACTIVE
    )
    high = _COMPUTERS["minie"].compute(
        replace(EmotionalState(), comfort=95.0, mood=80.0), OperatingMode.ACTIVE
    )
    assert high.smile_intensity > low.smile_intensity
    assert high.eye_openness > low.eye_openness
    assert high.voice_warmth > low.voice_warmth


def test_minie_particle_density_increases_with_energy():
    low = _COMPUTERS["minie"].compute(replace(EmotionalState(), energy=5.0), OperatingMode.ACTIVE)
    high = _COMPUTERS["minie"].compute(
        replace(EmotionalState(), energy=95.0), OperatingMode.ACTIVE
    )
    assert high.particle_density > low.particle_density


# --- Jarvis: mostly static, only animation_speed/avatar_focus move -----------


def test_jarvis_smile_intensity_does_not_move_with_comfort_or_mood():
    low = _COMPUTERS["jarvis"].compute(
        replace(EmotionalState(), comfort=5.0, mood=-80.0), OperatingMode.ACTIVE
    )
    high = _COMPUTERS["jarvis"].compute(
        replace(EmotionalState(), comfort=95.0, mood=80.0), OperatingMode.ACTIVE
    )
    assert low.smile_intensity == high.smile_intensity == _CONFIG.jarvis_smile_intensity_min


def test_jarvis_particle_density_does_not_move_with_energy():
    low = _COMPUTERS["jarvis"].compute(replace(EmotionalState(), energy=5.0), OperatingMode.ACTIVE)
    high = _COMPUTERS["jarvis"].compute(
        replace(EmotionalState(), energy=95.0), OperatingMode.ACTIVE
    )
    assert low.particle_density == high.particle_density == _CONFIG.jarvis_particle_density_min


# --- fixed identity palette (not emotion-driven) ------------------------------


def test_jarvis_colors_are_fixed_regardless_of_emotional_state():
    calm = _COMPUTERS["jarvis"].compute(EmotionalState(), OperatingMode.ACTIVE)
    distressed = _COMPUTERS["jarvis"].compute(
        replace(EmotionalState(), stress=100.0, mood=-100.0), OperatingMode.ACTIVE
    )
    assert calm.lighting_color == distressed.lighting_color == _CONFIG.jarvis_lighting_color
    assert calm.ui_accent == distressed.ui_accent == _CONFIG.jarvis_ui_accent


def test_minie_colors_are_fixed_regardless_of_emotional_state():
    calm = _COMPUTERS["minie"].compute(EmotionalState(), OperatingMode.ACTIVE)
    distressed = _COMPUTERS["minie"].compute(
        replace(EmotionalState(), stress=100.0, mood=-100.0), OperatingMode.ACTIVE
    )
    assert calm.lighting_color == distressed.lighting_color == _CONFIG.minie_lighting_color
    assert calm.ui_accent == distressed.ui_accent == _CONFIG.minie_ui_accent


# --- persona_name / computed_at -----------------------------------------------


def test_persona_name_identifies_which_computer_produced_the_state():
    jarvis_state = _COMPUTERS["jarvis"].compute(EmotionalState(), OperatingMode.ACTIVE)
    minie_state = _COMPUTERS["minie"].compute(EmotionalState(), OperatingMode.ACTIVE)
    assert jarvis_state.persona_name == "jarvis"
    assert minie_state.persona_name == "minie"


def test_computed_at_is_a_real_timestamp():
    state = _COMPUTERS["jarvis"].compute(EmotionalState(), OperatingMode.ACTIVE)
    assert state.computed_at is not None


# --- PresentationConfig genuinely drives output, not hardcoded ---------------


def test_output_ranges_are_genuinely_config_driven_not_hardcoded():
    custom_config = replace(
        _CONFIG, minie_smile_intensity_min=0.6, minie_smile_intensity_max=0.61
    )
    computer = MiniePresentationStateComputer(custom_config)

    low_comfort_state = computer.compute(
        replace(EmotionalState(), comfort=0.0, mood=-100.0), OperatingMode.ACTIVE
    )
    high_comfort_state = computer.compute(
        replace(EmotionalState(), comfort=100.0, mood=100.0), OperatingMode.ACTIVE
    )

    assert 0.6 <= low_comfort_state.smile_intensity <= 0.61
    assert 0.6 <= high_comfort_state.smile_intensity <= 0.61


# --- never raises --------------------------------------------------------------


@pytest.mark.parametrize("computer_name", ["jarvis", "minie"])
def test_compute_never_raises_across_every_representative_state_and_mode(computer_name):
    computer = _COMPUTERS[computer_name]
    for state in _REPRESENTATIVE_STATES.values():
        for operating_mode in OperatingMode:
            result = computer.compute(state, operating_mode)
            assert isinstance(result, PresentationState)


# --- shared helpers (presentation.presentation_state) -------------------------


def test_clamp_bounds_a_value_at_both_edges():
    assert clamp(5.0, 0.0, 1.0) == 1.0
    assert clamp(-5.0, 0.0, 1.0) == 0.0
    assert clamp(0.5, 0.0, 1.0) == 0.5


def test_fraction_of_maps_domain_to_unit_interval():
    assert fraction_of(0.0, 0.0, 100.0) == 0.0
    assert fraction_of(100.0, 0.0, 100.0) == 1.0
    assert fraction_of(50.0, 0.0, 100.0) == 0.5
    assert fraction_of(-100.0, -100.0, 100.0) == 0.0
    assert fraction_of(100.0, -100.0, 100.0) == 1.0


def test_fraction_of_clamps_out_of_domain_input():
    assert fraction_of(150.0, 0.0, 100.0) == 1.0
    assert fraction_of(-50.0, 0.0, 100.0) == 0.0


def test_scale_into_range_maps_unit_interval_to_target_range():
    assert scale_into_range(0.0, 10.0, 20.0) == 10.0
    assert scale_into_range(1.0, 10.0, 20.0) == 20.0
    assert scale_into_range(0.5, 10.0, 20.0) == 15.0
