"""Unit tests for emotion.state_manager."""

from datetime import UTC, datetime

import pytest

from config.schema import EmotionConfig
from decision.context_analyzer import SentimentHint
from emotion.models import EmotionEstimate, EmotionLabel, EmotionSignals
from emotion.state_manager import EmotionalState, EmotionalStateManager


@pytest.fixture
def emotion_config() -> EmotionConfig:
    return EmotionConfig()


@pytest.fixture
def manager(emotion_config: EmotionConfig) -> EmotionalStateManager:
    manager = EmotionalStateManager(emotion_config)
    manager.start()
    return manager


def _estimate(
    label: EmotionLabel,
    confidence: float = 1.0,
    pause_before_turn_seconds: float = 1.0,
) -> EmotionEstimate:
    signals = EmotionSignals(
        speaking_rate_wpm=150.0,
        pause_before_turn_seconds=pause_before_turn_seconds,
        sentiment_hint=SentimentHint.NEUTRAL,
        matched_lexical_markers=[],
        no_speech_probability=0.05,
        collected_at=datetime.now(UTC),
    )
    return EmotionEstimate(
        label=label, confidence=confidence, signals=signals, estimated_at=datetime.now(UTC)
    )


class TestLifecycle:
    def test_health_check_false_before_start(self, emotion_config: EmotionConfig) -> None:
        manager = EmotionalStateManager(emotion_config)
        assert manager.health_check() is False

    def test_health_check_true_after_start(self, manager: EmotionalStateManager) -> None:
        assert manager.health_check() is True

    def test_health_check_false_after_stop(self, manager: EmotionalStateManager) -> None:
        manager.stop()
        assert manager.health_check() is False


class TestInitialState:
    def test_default_state_is_neutral(self, manager: EmotionalStateManager) -> None:
        state = manager.current_state()
        assert state.mood == 0.0
        assert state.energy == 50.0
        assert state.stress == 50.0
        assert state.focus == 50.0
        assert state.comfort == 50.0
        assert state.social_energy == 50.0
        assert state.conversation_momentum == 50.0

    def test_current_state_returns_independent_copy(self, manager: EmotionalStateManager) -> None:
        state = manager.current_state()
        state.mood = 999.0
        assert manager.current_state().mood == 0.0


class TestApplyEstimate:
    def test_never_raises_for_unknown_label(self, manager: EmotionalStateManager) -> None:
        result = manager.apply_estimate(_estimate(EmotionLabel.UNKNOWN))
        assert isinstance(result, EmotionalState)

    def test_unknown_label_leaves_label_driven_dimensions_unchanged(
        self, manager: EmotionalStateManager
    ) -> None:
        before = manager.current_state()
        after = manager.apply_estimate(
            _estimate(EmotionLabel.UNKNOWN, pause_before_turn_seconds=1.0)
        )
        assert after.mood == before.mood
        assert after.stress == before.stress
        assert after.comfort == before.comfort

    def test_ema_converges_toward_target_without_overshooting(
        self, manager: EmotionalStateManager
    ) -> None:
        # STRESSED's default target pushes stress toward 85.0 (starting at 50.0).
        previous_stress = manager.current_state().stress
        for _ in range(50):
            state = manager.apply_estimate(_estimate(EmotionLabel.STRESSED))
            assert state.stress >= previous_stress  # monotonic approach
            assert state.stress <= 85.0  # never overshoots the target
            previous_stress = state.stress
        assert previous_stress > 80.0  # genuinely converged close to the target

    def test_low_confidence_estimate_nudges_less_than_high_confidence(
        self, manager: EmotionalStateManager, emotion_config: EmotionConfig
    ) -> None:
        low_conf_manager = EmotionalStateManager(emotion_config)
        low_conf_manager.start()
        high_conf_manager = EmotionalStateManager(emotion_config)
        high_conf_manager.start()

        low = low_conf_manager.apply_estimate(_estimate(EmotionLabel.STRESSED, confidence=0.4))
        high = high_conf_manager.apply_estimate(_estimate(EmotionLabel.STRESSED, confidence=1.0))

        assert (low.stress - 50.0) < (high.stress - 50.0)

    def test_dimension_clamping_never_exceeds_range(self, manager: EmotionalStateManager) -> None:
        for _ in range(200):
            state = manager.apply_estimate(_estimate(EmotionLabel.FRUSTRATED))
        assert -100.0 <= state.mood <= 100.0
        assert 0.0 <= state.stress <= 100.0
        assert 0.0 <= state.comfort <= 100.0

    def test_short_pause_increases_momentum(self, manager: EmotionalStateManager) -> None:
        before = manager.current_state().conversation_momentum
        after = manager.apply_estimate(
            _estimate(EmotionLabel.UNKNOWN, pause_before_turn_seconds=0.0)
        ).conversation_momentum
        assert after > before

    def test_long_pause_decreases_momentum(self, manager: EmotionalStateManager) -> None:
        before = manager.current_state().conversation_momentum
        after = manager.apply_estimate(
            _estimate(EmotionLabel.UNKNOWN, pause_before_turn_seconds=30.0)
        ).conversation_momentum
        assert after < before

    def test_updated_at_advances(self, manager: EmotionalStateManager) -> None:
        before = manager.current_state().updated_at
        after = manager.apply_estimate(_estimate(EmotionLabel.CALM)).updated_at
        assert after >= before


class TestDecayTowardBaseline:
    def test_zero_elapsed_is_a_noop(self, manager: EmotionalStateManager) -> None:
        manager.apply_estimate(_estimate(EmotionLabel.STRESSED))
        before = manager.current_state()
        after = manager.decay_toward_baseline(0.0)
        assert after.stress == before.stress

    def test_negative_elapsed_is_a_noop(self, manager: EmotionalStateManager) -> None:
        manager.apply_estimate(_estimate(EmotionLabel.STRESSED))
        before = manager.current_state()
        after = manager.decay_toward_baseline(-5.0)
        assert after.stress == before.stress

    def test_decay_pulls_displaced_state_back_toward_neutral(
        self, manager: EmotionalStateManager
    ) -> None:
        for _ in range(50):
            manager.apply_estimate(_estimate(EmotionLabel.STRESSED))
        displaced = manager.current_state()
        assert displaced.stress > 60.0  # confirm genuinely displaced from the 50.0 baseline

        decayed = manager.decay_toward_baseline(3600.0)  # a long gap
        assert decayed.stress < displaced.stress
        assert decayed.stress > 50.0  # decays toward, not past, neutral

    def test_longer_elapsed_decays_more(self, emotion_config: EmotionConfig) -> None:
        manager_a = EmotionalStateManager(emotion_config)
        manager_a.start()
        manager_b = EmotionalStateManager(emotion_config)
        manager_b.start()
        for _ in range(50):
            manager_a.apply_estimate(_estimate(EmotionLabel.STRESSED))
            manager_b.apply_estimate(_estimate(EmotionLabel.STRESSED))

        short_gap = manager_a.decay_toward_baseline(60.0)
        long_gap = manager_b.decay_toward_baseline(7200.0)
        assert long_gap.stress < short_gap.stress

    def test_half_life_decays_approximately_halfway(self, emotion_config: EmotionConfig) -> None:
        manager = EmotionalStateManager(emotion_config)
        manager.start()
        for _ in range(50):
            manager.apply_estimate(_estimate(EmotionLabel.STRESSED))
        displaced = manager.current_state()
        displacement = displaced.stress - 50.0

        decayed = manager.decay_toward_baseline(emotion_config.baseline_decay_half_life_seconds)
        remaining_displacement = decayed.stress - 50.0
        assert remaining_displacement == pytest.approx(displacement / 2, rel=0.05)

    def test_dimension_clamping_maintained_through_decay(
        self, manager: EmotionalStateManager
    ) -> None:
        for _ in range(50):
            manager.apply_estimate(_estimate(EmotionLabel.EXCITED))
        decayed = manager.decay_toward_baseline(10.0)
        assert -100.0 <= decayed.mood <= 100.0
        assert 0.0 <= decayed.energy <= 100.0

    def test_never_raises_on_extreme_elapsed(self, manager: EmotionalStateManager) -> None:
        result = manager.decay_toward_baseline(10**9)
        assert isinstance(result, EmotionalState)
