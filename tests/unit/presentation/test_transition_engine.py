"""Unit tests for presentation.transition_engine (Sprint 5.10).

TransitionEngine's own dependency is PresentationController — faked here
(a _FakePresentationController spy exposing exactly the three methods
TransitionEngine calls: last_state_for()/mount_renderer()/apply_state())
so this module's own choreography logic (phase order, budget handling,
resume-replay) is verified in isolation, the same "component before
integration" level test_minie_renderer.py's own _FakeAvatarRenderer
already established for a structurally identical seam.
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from config.schema import PresentationConfig
from presentation.presentation_state import PresentationState
from presentation.transition_engine import (
    NullTransitionOverlay,
    TransitionEngine,
    TransitionPhase,
)


class _FakePresentationController:
    def __init__(self) -> None:
        self.mount_calls: list[str] = []
        self.apply_state_calls: list[PresentationState] = []
        self._last_states: dict[str, PresentationState] = {}

    def set_last_state(self, persona_name: str, state: PresentationState) -> None:
        self._last_states[persona_name] = state

    def last_state_for(self, persona_name: str) -> PresentationState | None:
        return self._last_states.get(persona_name)

    def mount_renderer(self, persona_name: str) -> None:
        self.mount_calls.append(persona_name)

    def apply_state(self, state: PresentationState) -> None:
        self.apply_state_calls.append(state)


class _SpyOverlay:
    def __init__(self, raise_on: set | None = None) -> None:
        self.calls: list[str] = []
        self._raise_on = raise_on or set()

    def show(self) -> None:
        self.calls.append("show")
        if "show" in self._raise_on:
            raise RuntimeError("overlay.show() exploded")

    def set_phase(self, phase: TransitionPhase) -> None:
        self.calls.append(f"set_phase:{phase.value}")
        if "set_phase" in self._raise_on:
            raise RuntimeError("overlay.set_phase() exploded")

    def hide(self) -> None:
        self.calls.append("hide")
        if "hide" in self._raise_on:
            raise RuntimeError("overlay.hide() exploded")


def _sample_state(persona_name: str = "jarvis") -> PresentationState:
    return PresentationState(
        smile_intensity=0.0,
        eye_openness=0.5,
        voice_warmth=0.3,
        animation_speed=1.0,
        particle_density=0.0,
        lighting_color="#000000",
        ui_accent="#111111",
        gesture_probability=0.1,
        avatar_focus="user",
        persona_name=persona_name,
        computed_at=datetime.now(UTC),
    )


@pytest.fixture
def fast_config() -> PresentationConfig:
    """A generous budget and a tiny particle-phase hold — real elapsed
    time, but fast enough to keep this test file quick, no budget
    overrun under normal execution."""
    return PresentationConfig(
        transition_max_duration_seconds=5.0, transition_particle_phase_seconds=0.01
    )


@pytest.fixture
def controller() -> _FakePresentationController:
    return _FakePresentationController()


# --- full seven-phase sequence, correct order (Testing Checklist) ------------


def test_transition_runs_all_seven_phases_in_order(fast_config, controller):
    overlay = _SpyOverlay()
    engine = TransitionEngine(controller, fast_config, overlay)

    engine.transition("jarvis", "minie")

    phase_calls = [c for c in overlay.calls if c.startswith("set_phase:")]
    assert phase_calls == [
        "set_phase:saving_state",
        "set_phase:syncing_memory",
        "set_phase:showing_core",
        "set_phase:particle_transition",
        "set_phase:loading_target",
        "set_phase:restoring_conversation",
        "set_phase:complete",
    ]


def test_transition_calls_overlay_show_before_any_phase_and_hide_last(fast_config, controller):
    overlay = _SpyOverlay()
    engine = TransitionEngine(controller, fast_config, overlay)

    engine.transition("jarvis", "minie")

    assert overlay.calls[0] == "show"
    assert overlay.calls[-1] == "hide"


def test_transition_mounts_the_new_persona_renderer(fast_config, controller):
    engine = TransitionEngine(controller, fast_config)

    engine.transition("jarvis", "minie")

    assert controller.mount_calls == ["minie"]


# --- mount_renderer() exactly once (Acceptance Criteria) ---------------------


def test_mount_renderer_called_exactly_once_on_the_happy_path(fast_config, controller):
    engine = TransitionEngine(controller, fast_config)
    engine.transition("jarvis", "minie")
    assert controller.mount_calls == ["minie"]


def test_mount_renderer_called_exactly_once_when_the_overlay_raises_everywhere(
    fast_config, controller
):
    overlay = _SpyOverlay(raise_on={"show", "set_phase", "hide"})
    engine = TransitionEngine(controller, fast_config, overlay)

    engine.transition("jarvis", "minie")  # must not raise

    assert controller.mount_calls == ["minie"]


# --- never raises, even when the overlay itself raises (Acceptance Criteria) -


def test_transition_never_raises_when_every_overlay_method_raises(fast_config, controller):
    overlay = _SpyOverlay(raise_on={"show", "set_phase", "hide"})
    engine = TransitionEngine(controller, fast_config, overlay)

    engine.transition("jarvis", "minie")  # must not raise


def test_transition_never_raises_when_presentation_controller_last_state_for_raises(
    fast_config,
):
    class _BrokenController(_FakePresentationController):
        def last_state_for(self, persona_name):
            raise RuntimeError("last_state_for() exploded")

    engine = TransitionEngine(_BrokenController(), fast_config)

    engine.transition("jarvis", "minie")  # must not raise


def test_transition_still_mounts_when_presentation_controller_last_state_for_raises(fast_config):
    class _BrokenController(_FakePresentationController):
        def last_state_for(self, persona_name):
            raise RuntimeError("last_state_for() exploded")

    controller = _BrokenController()
    engine = TransitionEngine(controller, fast_config)

    engine.transition("jarvis", "minie")

    assert controller.mount_calls == ["minie"]  # exactly once, even via the failure path


def test_transition_never_raises_when_mount_renderer_itself_raises(fast_config):
    class _BrokenController(_FakePresentationController):
        def mount_renderer(self, persona_name):
            raise RuntimeError("mount_renderer() exploded")

    engine = TransitionEngine(_BrokenController(), fast_config)

    engine.transition("jarvis", "minie")  # must not raise


# --- budget-overrun degrade path (Testing Checklist) --------------------------
#
# Real elapsed time is too unreliable to force a genuine overrun
# deterministically (a real system's own time.monotonic() resolution
# can be coarser than a tiny configured budget, making "1e-9 seconds"
# indistinguishable from "0 seconds elapsed" on some hosts) — these
# tests patch time.monotonic() directly instead: the first call
# establishes the deadline, every call after it reports far past that
# deadline, deterministically forcing the overrun path regardless of
# host timing.


def _patched_monotonic_forcing_overrun():
    return patch("presentation.transition_engine.time.monotonic", side_effect=[0.0] + [1e9] * 10)


def test_budget_overrun_still_calls_mount_renderer(fast_config, controller):
    overlay = _SpyOverlay()
    engine = TransitionEngine(controller, fast_config, overlay)

    with _patched_monotonic_forcing_overrun():
        engine.transition("jarvis", "minie")

    assert controller.mount_calls == ["minie"]


def test_budget_overrun_skips_syncing_memory_showing_core_and_particle_transition(
    fast_config, controller
):
    overlay = _SpyOverlay()
    engine = TransitionEngine(controller, fast_config, overlay)

    with _patched_monotonic_forcing_overrun():
        engine.transition("jarvis", "minie")

    phase_calls = [c for c in overlay.calls if c.startswith("set_phase:")]
    assert "set_phase:syncing_memory" not in phase_calls
    assert "set_phase:showing_core" not in phase_calls
    assert "set_phase:particle_transition" not in phase_calls
    assert phase_calls == [
        "set_phase:saving_state",
        "set_phase:loading_target",
        "set_phase:complete",
    ]


def test_budget_overrun_also_skips_restoring_conversation(fast_config, controller):
    """The sprint's own spec names phases 5 and 7 specifically as the
    overrun path — phase 6 (RESTORING_CONVERSATION) is skipped too, so
    a cached state must not be applied on an overrun."""
    # Prime a cached state for "jarvis" via a first, normal (non-overrun)
    # transition away from it.
    controller.set_last_state("jarvis", _sample_state("jarvis"))
    priming_engine = TransitionEngine(controller, fast_config)
    priming_engine.transition("jarvis", "minie")
    controller.apply_state_calls.clear()
    controller.mount_calls.clear()

    engine = TransitionEngine(controller, fast_config)
    with _patched_monotonic_forcing_overrun():
        engine.transition("minie", "jarvis")  # jarvis has a cached state from priming above

    assert controller.apply_state_calls == []  # skipped — budget overrun
    assert controller.mount_calls == ["jarvis"]  # the swap itself still happens


# --- resume-replay (Testing Checklist) ----------------------------------------


def test_resume_replay_applies_the_cached_state_on_the_second_mount(fast_config, controller):
    jarvis_state = _sample_state("jarvis")
    controller.set_last_state("jarvis", jarvis_state)
    engine = TransitionEngine(controller, fast_config)

    engine.transition("jarvis", "minie")  # SAVING_STATE caches jarvis's own last state
    assert controller.apply_state_calls == []  # nothing cached for minie yet

    engine.transition("minie", "jarvis")  # RESTORING_CONVERSATION replays jarvis's cached state

    assert controller.apply_state_calls == [jarvis_state]
    assert controller.mount_calls == ["minie", "jarvis"]


def test_first_time_switch_applies_no_cached_state(fast_config, controller):
    """No prior SAVING_STATE has ever run for "minie" — a first-time
    switch must not call apply_state() at all."""
    engine = TransitionEngine(controller, fast_config)

    engine.transition("jarvis", "minie")

    assert controller.apply_state_calls == []


# --- NullTransitionOverlay (default) ------------------------------------------


def test_default_overlay_is_null_transition_overlay(fast_config, controller):
    engine = TransitionEngine(controller, fast_config)
    assert isinstance(engine._overlay, NullTransitionOverlay)


def test_null_transition_overlay_methods_never_raise():
    overlay = NullTransitionOverlay()
    overlay.show()
    overlay.set_phase(TransitionPhase.SAVING_STATE)
    overlay.hide()


def test_transition_with_the_default_null_overlay_never_raises(fast_config, controller):
    engine = TransitionEngine(controller, fast_config)
    engine.transition("jarvis", "minie")  # must not raise
    assert controller.mount_calls == ["minie"]


# --- scenario (d): overlapping transition supersession (Sprint 5.15) ---------
#
# A re-entrant transition() call from inside the first's own overlay
# callback simulates "a second switch arrives while the first is still
# mid-sequence" deterministically, on a single thread — the most direct
# way to test cooperative phase-boundary cancellation without flaky
# real threading (this codebase's own only real caller today is
# sequential/single-threaded, per this module's own docstring).


class _ReentrantOverlay:
    """Calls back into the same TransitionEngine instance's own
    transition() from inside set_phase(), exactly once, the moment the
    named trigger_phase is reached."""

    def __init__(self, engine: TransitionEngine, trigger_phase: TransitionPhase) -> None:
        self._engine = engine
        self._trigger_phase = trigger_phase
        self._reentered = False
        self.calls: list[str] = []

    def show(self) -> None:
        self.calls.append("show")

    def set_phase(self, phase: TransitionPhase) -> None:
        self.calls.append(f"set_phase:{phase.value}")
        if phase is self._trigger_phase and not self._reentered:
            self._reentered = True
            self._engine.transition("minie", "jarvis")

    def hide(self) -> None:
        self.calls.append("hide")


def test_a_second_transition_arriving_mid_sequence_supersedes_the_first(fast_config, controller):
    engine = TransitionEngine(controller, fast_config)
    overlay = _ReentrantOverlay(engine, TransitionPhase.SYNCING_MEMORY)
    engine.set_overlay(overlay)

    engine.transition("jarvis", "minie")

    # Exactly one mount_renderer() call total, for the superseding
    # transition's own target — never the superseded one's "minie".
    assert controller.mount_calls == ["jarvis"]


def test_a_superseded_transition_never_calls_finish_a_second_time(fast_config, controller):
    """The overlay must end in a clean, non-stuck state: show() called
    once (by the superseded transition's own start), hide() called once
    (by the superseding transition's own end) — never twice, never
    zero."""
    engine = TransitionEngine(controller, fast_config)
    overlay = _ReentrantOverlay(engine, TransitionPhase.SYNCING_MEMORY)
    engine.set_overlay(overlay)

    engine.transition("jarvis", "minie")

    assert overlay.calls.count("show") == 1
    assert overlay.calls.count("hide") == 1


def test_supersession_at_the_very_first_phase_boundary_still_mounts_exactly_once(
    fast_config, controller
):
    """Supersession triggered as early as possible (right after
    SAVING_STATE, before SYNCING_MEMORY even runs) — the earliest real
    phase-boundary check in _run_choreography()."""
    engine = TransitionEngine(controller, fast_config)
    overlay = _ReentrantOverlay(engine, TransitionPhase.SAVING_STATE)
    engine.set_overlay(overlay)

    engine.transition("jarvis", "minie")

    assert controller.mount_calls == ["jarvis"]


def test_superseding_transition_still_replays_a_cached_state_for_its_own_target(
    fast_config, controller
):
    """The superseding call's own _finish() runs with skip_restore=True
    (matching the budget-overrun path's own precedent) — a cached state
    for the superseding transition's target is intentionally NOT
    replayed, since skipping straight to LOADING_TARGET/COMPLETE means
    RESTORING_CONVERSATION never runs either."""
    controller.set_last_state("jarvis", _sample_state("jarvis"))
    engine = TransitionEngine(controller, fast_config)
    overlay = _ReentrantOverlay(engine, TransitionPhase.SYNCING_MEMORY)
    engine.set_overlay(overlay)

    engine.transition("jarvis", "minie")  # superseded partway; B: minie -> jarvis wins

    assert controller.mount_calls == ["jarvis"]
    assert controller.apply_state_calls == []
