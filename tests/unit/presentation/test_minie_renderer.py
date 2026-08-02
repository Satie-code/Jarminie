"""Unit tests for presentation.minie_renderer.

Uses a minimal fake AvatarRenderer — MinieRenderer's own contract is
"thin adapter," so these tests verify the translation/delegation logic
itself, never a real VTube Studio connection (that's
test_vtube_studio_renderer.py's own job).
"""

from datetime import UTC, datetime

import pytest

from config.schema import PresentationConfig
from presentation.minie_renderer import MinieRenderer, _derive_expression_id
from presentation.presentation_state import PresentationState


class _FakeAvatarRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def mount(self) -> None:
        self.calls.append(("mount",))

    def unmount(self) -> None:
        self.calls.append(("unmount",))

    def render_state(self, state: PresentationState) -> None:
        self.calls.append(("render_state", state))

    def set_expression(self, expression_id: str) -> None:
        self.calls.append(("set_expression", expression_id))

    def set_mouth_open(self, amount: float) -> None:
        self.calls.append(("set_mouth_open", amount))

    def set_eye_target(self, x: float, y: float) -> None:
        self.calls.append(("set_eye_target", x, y))

    def trigger_gesture(self, gesture_id: str) -> None:
        self.calls.append(("trigger_gesture", gesture_id))


def _sample_state(smile_intensity: float = 0.5, voice_warmth: float = 0.5) -> PresentationState:
    return PresentationState(
        smile_intensity=smile_intensity,
        eye_openness=0.6,
        voice_warmth=voice_warmth,
        animation_speed=1.0,
        particle_density=0.3,
        lighting_color="#C8A8E9",
        ui_accent="#B76E79",
        gesture_probability=0.2,
        avatar_focus="user",
        persona_name="minie",
        computed_at=datetime.now(UTC),
    )


@pytest.fixture
def config() -> PresentationConfig:
    return PresentationConfig()


@pytest.fixture
def avatar() -> _FakeAvatarRenderer:
    return _FakeAvatarRenderer()


@pytest.fixture
def renderer(avatar, config) -> MinieRenderer:
    return MinieRenderer(avatar, config)


# --- mount()/unmount() delegate straight through ------------------------------


def test_mount_delegates_to_the_avatar_renderer(renderer, avatar):
    renderer.mount()
    assert avatar.calls == [("mount",)]


def test_unmount_delegates_to_the_avatar_renderer(renderer, avatar):
    renderer.unmount()
    assert avatar.calls == [("unmount",)]


# --- render_state() delegates the parameter-mapping path ----------------------


def test_render_state_delegates_to_the_avatar_renderers_own_render_state(renderer, avatar):
    state = _sample_state()

    renderer.render_state(state)

    render_calls = [c for c in avatar.calls if c[0] == "render_state"]
    assert render_calls == [("render_state", state)]


# --- expression-change detection (Acceptance Criteria) ------------------------


def test_render_state_calls_set_expression_on_first_call(renderer, avatar):
    renderer.render_state(_sample_state(smile_intensity=0.8, voice_warmth=0.8))

    expression_calls = [c for c in avatar.calls if c[0] == "set_expression"]
    assert len(expression_calls) == 1
    assert expression_calls[0][1] == "big_smile"


def test_render_state_does_not_repeat_set_expression_for_an_unchanged_expression(
    renderer, avatar
):
    renderer.render_state(_sample_state(smile_intensity=0.8, voice_warmth=0.8))
    renderer.render_state(_sample_state(smile_intensity=0.79, voice_warmth=0.81))  # same bucket

    expression_calls = [c for c in avatar.calls if c[0] == "set_expression"]
    assert len(expression_calls) == 1


def test_render_state_calls_set_expression_again_when_the_derived_expression_changes(
    renderer, avatar
):
    renderer.render_state(_sample_state(smile_intensity=0.8, voice_warmth=0.8))  # big_smile
    renderer.render_state(_sample_state(smile_intensity=0.1, voice_warmth=0.1))  # neutral

    expression_calls = [c[1] for c in avatar.calls if c[0] == "set_expression"]
    assert expression_calls == ["big_smile", "neutral"]


def test_render_state_across_many_near_identical_states_calls_set_expression_once(
    renderer, avatar
):
    """The exact Acceptance Criteria scenario: repeated near-identical
    states must not flood the avatar backend with redundant identical
    calls."""
    for _ in range(20):
        renderer.render_state(_sample_state(smile_intensity=0.5, voice_warmth=0.5))

    expression_calls = [c for c in avatar.calls if c[0] == "set_expression"]
    render_state_calls = [c for c in avatar.calls if c[0] == "render_state"]
    assert len(expression_calls) == 1
    assert len(render_state_calls) == 20  # render_state itself is NOT deduplicated


def test_unmount_resets_expression_memory_so_remount_resends_it(renderer, avatar):
    renderer.render_state(_sample_state(smile_intensity=0.8, voice_warmth=0.8))
    renderer.unmount()
    renderer.mount()

    renderer.render_state(_sample_state(smile_intensity=0.8, voice_warmth=0.8))  # same expression

    expression_calls = [c for c in avatar.calls if c[0] == "set_expression"]
    assert len(expression_calls) == 2  # sent again after the reset, not deduplicated across it


# --- trigger_gesture() forwards verbatim (Sprint 5.9) -------------------------


def test_trigger_gesture_forwards_the_gesture_id_verbatim(renderer, avatar):
    renderer.trigger_gesture("head_tilt")

    gesture_calls = [c for c in avatar.calls if c[0] == "trigger_gesture"]
    assert gesture_calls == [("trigger_gesture", "head_tilt")]


def test_trigger_gesture_does_not_touch_expression_memory(renderer, avatar):
    renderer.render_state(_sample_state(smile_intensity=0.8, voice_warmth=0.8))
    renderer.trigger_gesture("wave")
    renderer.render_state(_sample_state(smile_intensity=0.8, voice_warmth=0.8))  # same expression

    expression_calls = [c for c in avatar.calls if c[0] == "set_expression"]
    assert len(expression_calls) == 1  # unaffected by the gesture call in between


# --- set_mouth_open()/set_eye_target() have no caller here --------------------


def test_minie_renderer_never_calls_set_mouth_open_itself(renderer, avatar):
    """Integration Considerations: lip-sync is Sprint 5.11's own job —
    MinieRenderer itself must not invent a caller for it."""
    for _ in range(5):
        renderer.render_state(_sample_state())
    assert all(c[0] != "set_mouth_open" for c in avatar.calls)


def test_minie_renderer_never_calls_set_eye_target_itself(renderer, avatar):
    for _ in range(5):
        renderer.render_state(_sample_state())
    assert all(c[0] != "set_eye_target" for c in avatar.calls)


def test_minie_renderer_never_calls_trigger_gesture_itself(renderer, avatar):
    for _ in range(5):
        renderer.render_state(_sample_state())
    assert all(c[0] != "trigger_gesture" for c in avatar.calls)


# --- _derive_expression_id() -----------------------------------------------------


def test_derive_expression_id_picks_the_highest_met_threshold():
    thresholds = {"neutral": 0.0, "smile": 0.45, "big_smile": 0.75}
    assert _derive_expression_id(_sample_state(0.0, 0.0), thresholds) == "neutral"
    assert _derive_expression_id(_sample_state(0.5, 0.5), thresholds) == "smile"
    assert _derive_expression_id(_sample_state(0.9, 0.9), thresholds) == "big_smile"


def test_derive_expression_id_blends_smile_intensity_and_voice_warmth():
    thresholds = {"neutral": 0.0, "big_smile": 0.75}
    # Neither alone reaches 0.75, but the average of 0.9 and 0.7 does.
    assert _derive_expression_id(_sample_state(0.9, 0.7), thresholds) == "big_smile"


def test_derive_expression_id_falls_back_to_neutral_if_no_threshold_is_met():
    """A defensively-unreachable path given a validated config (which
    guarantees a 0.0-threshold floor) — still an honest fallback, not a
    crash, for a hand-constructed dict bypassing validation."""
    thresholds = {"big_smile": 0.9}
    assert _derive_expression_id(_sample_state(0.0, 0.0), thresholds) == "neutral"
