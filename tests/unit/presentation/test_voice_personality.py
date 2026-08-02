"""Unit tests for presentation.voice_personality (Sprint 5.11)."""

import pytest

from config.schema import PresentationConfig
from presentation.voice_personality import _BOUNDARY_PATTERN, VoicePersonalityModulator

_SAMPLE_TEXT = (
    "Hello there. I checked the report, and it looks fine. "
    "Would you like me to send it now? Let me know, please. "
    "Otherwise, I will wait; there is no rush."
)


@pytest.fixture
def config() -> PresentationConfig:
    return PresentationConfig(
        pacing_pause_marker="...",
        pacing_low_warmth_pause_weight=0.3,
        pacing_high_warmth_pause_weight=0.7,
    )


@pytest.fixture
def modulator(config) -> VoicePersonalityModulator:
    return VoicePersonalityModulator(config)


def _de_mark(shaped: str, marker: str) -> str:
    return shaped.replace(f"{marker} ", "")


# --- empty text (Acceptance Criteria) -----------------------------------------


def test_shape_pacing_returns_empty_text_unchanged(modulator):
    assert modulator.shape_pacing("", 0.5) == ""


def test_shape_pacing_never_raises_for_text_with_no_boundaries(modulator):
    assert modulator.shape_pacing("yes", 0.5) == "yes"


# --- de-marking invariant (Acceptance Criteria / Architecture Notes) ---------


@pytest.mark.parametrize("warmth", [0.0, 0.15, 0.3, 0.5, 0.7, 0.85, 1.0])
def test_de_marked_output_always_equals_the_input(modulator, config, warmth):
    shaped = modulator.shape_pacing(_SAMPLE_TEXT, warmth)
    assert _de_mark(shaped, config.pacing_pause_marker) == _SAMPLE_TEXT


def test_de_marking_invariant_holds_for_a_single_sentence(modulator, config):
    text = "This is one sentence."
    shaped = modulator.shape_pacing(text, 0.9)
    assert _de_mark(shaped, config.pacing_pause_marker) == text


def test_de_marking_invariant_holds_with_commas_and_semicolons(modulator, config):
    text = "First, we check; then, we confirm: it is done."
    shaped = modulator.shape_pacing(text, 0.6)
    assert _de_mark(shaped, config.pacing_pause_marker) == text


# --- marker-insertion frequency increases with voice_warmth (Acceptance Criteria) -


def _marker_count(shaped: str, marker: str) -> int:
    return shaped.count(marker)


def test_marker_frequency_increases_with_voice_warmth(modulator, config):
    low = modulator.shape_pacing(_SAMPLE_TEXT, 0.0)
    high = modulator.shape_pacing(_SAMPLE_TEXT, 1.0)

    low_count = _marker_count(low, config.pacing_pause_marker)
    high_count = _marker_count(high, config.pacing_pause_marker)

    assert high_count > low_count


def test_marker_frequency_is_monotonic_across_the_warmth_range(modulator, config):
    counts = [
        _marker_count(modulator.shape_pacing(_SAMPLE_TEXT, w), config.pacing_pause_marker)
        for w in (0.0, 0.25, 0.5, 0.75, 1.0)
    ]
    assert counts == sorted(counts)


def test_zero_weight_range_inserts_no_markers(config):
    zero_config = PresentationConfig(
        pacing_pause_marker="...",
        pacing_low_warmth_pause_weight=0.0,
        pacing_high_warmth_pause_weight=0.0,
    )
    modulator = VoicePersonalityModulator(zero_config)

    shaped = modulator.shape_pacing(_SAMPLE_TEXT, 0.5)

    assert shaped == _SAMPLE_TEXT
    assert zero_config.pacing_pause_marker not in shaped


def test_maximum_weight_inserts_a_marker_at_every_boundary(config):
    max_config = PresentationConfig(
        pacing_pause_marker="...",
        pacing_low_warmth_pause_weight=1.0,
        pacing_high_warmth_pause_weight=1.0,
    )
    modulator = VoicePersonalityModulator(max_config)

    shaped = modulator.shape_pacing(_SAMPLE_TEXT, 0.5)

    boundary_count = len(_BOUNDARY_PATTERN.findall(_SAMPLE_TEXT))
    assert boundary_count > 0
    assert shaped.count(max_config.pacing_pause_marker) == boundary_count


# --- voice_warmth is clamped defensively --------------------------------------


def test_voice_warmth_below_zero_is_clamped(modulator):
    shaped = modulator.shape_pacing(_SAMPLE_TEXT, -5.0)
    below = modulator.shape_pacing(_SAMPLE_TEXT, 0.0)
    assert shaped == below


def test_voice_warmth_above_one_is_clamped(modulator):
    shaped = modulator.shape_pacing(_SAMPLE_TEXT, 5.0)
    above = modulator.shape_pacing(_SAMPLE_TEXT, 1.0)
    assert shaped == above
