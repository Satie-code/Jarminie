"""Unit tests for presentation.presentation_controller (Sprint 5.6).

Uses real PersonaManager/EmotionalStateManager instances (both simple,
hardware-free value-and-orchestration objects — no need for fakes, the
same precedent tests/unit/personas/test_persona_manager.py's own
docstring already established for PersonaManager) alongside minimal
fakes for QuietModeController (a real one needs a full VoiceSessionManager
graph this sprint has no reason to construct), the Renderer Protocol
(no concrete implementation exists until Sprint 5.7/5.8), and
PresentationStateComputer (so computer-failure scenarios can be tested
in isolation from Sprint 5.5's real formulas).
"""

from datetime import UTC, datetime

import pytest

from config.schema import EmotionConfig, VoiceConfig
from emotion.state_manager import EmotionalStateManager
from personas.jarvis import JarvisPersona
from personas.minie import MiniePersona
from personas.persona_manager import PersonaManager
from presentation.gesture_engine import GestureEvent, GestureTrigger
from presentation.presentation_controller import PresentationController
from presentation.presentation_state import PresentationState
from voice.quiet_mode import OperatingMode


class _FakeQuietMode:
    def __init__(self, mode: OperatingMode = OperatingMode.ACTIVE) -> None:
        self._mode = mode

    def current_mode(self) -> OperatingMode:
        return self._mode


class _FakeRenderer:
    """Records every call (locally and, optionally, into a shared
    call_log list so cross-renderer ordering can be asserted) and can be
    configured to raise from any of its three methods."""

    def __init__(self, name: str, call_log: list | None = None, raise_on: set | None = None):
        self.name = name
        self.calls: list[str] = []
        self._call_log = call_log if call_log is not None else []
        self._raise_on = raise_on or set()

    def mount(self) -> None:
        self.calls.append("mount")
        self._call_log.append((self.name, "mount"))
        if "mount" in self._raise_on:
            raise RuntimeError(f"{self.name}.mount() exploded")

    def unmount(self) -> None:
        self.calls.append("unmount")
        self._call_log.append((self.name, "unmount"))
        if "unmount" in self._raise_on:
            raise RuntimeError(f"{self.name}.unmount() exploded")

    def render_state(self, state: PresentationState) -> None:
        self.calls.append("render_state")
        self._call_log.append((self.name, "render_state"))
        if "render_state" in self._raise_on:
            raise RuntimeError(f"{self.name}.render_state() exploded")

    def trigger_gesture(self, gesture_id: str) -> None:
        self.calls.append("trigger_gesture")
        self._call_log.append((self.name, "trigger_gesture"))
        if "trigger_gesture" in self._raise_on:
            raise RuntimeError(f"{self.name}.trigger_gesture() exploded")


class _FakeGestureEngine:
    """Configurable stand-in for GestureEngine — records every
    maybe_roll_ambient_gesture() call's own arguments and returns
    whatever result was configured (a GestureEvent | None), so refresh()'s
    own dispatch-when-non-None behavior can be tested deterministically
    without depending on real randomness/timing."""

    def __init__(self, result: GestureEvent | None = None) -> None:
        self.result = result
        self.calls: list[tuple[float, str]] = []

    def maybe_roll_ambient_gesture(
        self, gesture_probability: float, persona_name: str
    ) -> GestureEvent | None:
        self.calls.append((gesture_probability, persona_name))
        return self.result


class _FakeComputer:
    def __init__(self, raise_error: bool = False, result: PresentationState | None = None):
        self._raise_error = raise_error
        self._result = result if result is not None else _sample_state()
        self.calls = 0

    def compute(self, emotional_state, operating_mode) -> PresentationState:
        self.calls += 1
        if self._raise_error:
            raise RuntimeError("compute() exploded")
        return self._result


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
def persona_manager() -> PersonaManager:
    voice_config = VoiceConfig()
    manager = PersonaManager(JarvisPersona(voice_config), MiniePersona(voice_config), voice_config)
    manager.start()
    return manager


@pytest.fixture
def emotional_state_manager() -> EmotionalStateManager:
    manager = EmotionalStateManager(EmotionConfig())
    manager.start()
    return manager


def _make_controller(
    persona_manager,
    emotional_state_manager,
    quiet_mode=None,
    state_computers=None,
    renderers=None,
    gesture_engine=None,
) -> PresentationController:
    return PresentationController(
        persona_manager,
        emotional_state_manager,
        quiet_mode if quiet_mode is not None else _FakeQuietMode(),
        state_computers if state_computers is not None else {"jarvis": _FakeComputer()},
        renderers if renderers is not None else {},
        gesture_engine if gesture_engine is not None else _FakeGestureEngine(),
    )


# --- start()/stop()/health_check() --------------------------------------------


def test_start_mounts_the_renderer_for_the_active_persona(persona_manager, emotional_state_manager):
    jarvis_renderer = _FakeRenderer("jarvis")
    controller = _make_controller(
        persona_manager, emotional_state_manager, renderers={"jarvis": jarvis_renderer}
    )

    controller.start()

    assert controller.mounted_persona_name == "jarvis"
    assert jarvis_renderer.calls == ["mount"]


def test_start_with_no_bound_renderer_leaves_nothing_mounted(
    persona_manager, emotional_state_manager
):
    controller = _make_controller(persona_manager, emotional_state_manager, renderers={})

    controller.start()

    assert controller.mounted_persona_name is None


def test_health_check_false_before_start(persona_manager, emotional_state_manager):
    controller = _make_controller(persona_manager, emotional_state_manager)
    assert controller.health_check() is False


def test_health_check_true_after_start_with_a_bound_renderer(
    persona_manager, emotional_state_manager
):
    controller = _make_controller(
        persona_manager, emotional_state_manager, renderers={"jarvis": _FakeRenderer("jarvis")}
    )
    controller.start()
    assert controller.health_check() is True


def test_health_check_false_after_start_with_no_bound_renderer(
    persona_manager, emotional_state_manager
):
    controller = _make_controller(persona_manager, emotional_state_manager, renderers={})
    controller.start()
    assert controller.health_check() is False


def test_stop_unmounts_the_current_renderer(persona_manager, emotional_state_manager):
    jarvis_renderer = _FakeRenderer("jarvis")
    controller = _make_controller(
        persona_manager, emotional_state_manager, renderers={"jarvis": jarvis_renderer}
    )
    controller.start()

    controller.stop()

    assert jarvis_renderer.calls == ["mount", "unmount"]
    assert controller.mounted_persona_name is None


def test_stop_with_nothing_mounted_does_not_raise(persona_manager, emotional_state_manager):
    controller = _make_controller(persona_manager, emotional_state_manager, renderers={})
    controller.stop()  # never started, nothing mounted
    assert controller.mounted_persona_name is None


# --- mount_renderer() swap ordering/correctness (Acceptance Criteria) --------


def test_mount_renderer_unmounts_old_before_mounting_new(persona_manager, emotional_state_manager):
    call_log: list = []
    jarvis_renderer = _FakeRenderer("jarvis", call_log)
    minie_renderer = _FakeRenderer("minie", call_log)
    controller = _make_controller(
        persona_manager,
        emotional_state_manager,
        renderers={"jarvis": jarvis_renderer, "minie": minie_renderer},
    )
    controller.start()
    call_log.clear()

    controller.mount_renderer("minie")

    assert call_log == [("jarvis", "unmount"), ("minie", "mount")]
    assert controller.mounted_persona_name == "minie"


def test_mount_renderer_with_no_binding_leaves_nothing_mounted(
    persona_manager, emotional_state_manager
):
    jarvis_renderer = _FakeRenderer("jarvis")
    controller = _make_controller(
        persona_manager, emotional_state_manager, renderers={"jarvis": jarvis_renderer}
    )
    controller.start()

    controller.mount_renderer("minie")  # no "minie" binding

    assert jarvis_renderer.calls == ["mount", "unmount"]
    assert controller.mounted_persona_name is None


def test_mount_renderer_raising_on_mount_leaves_nothing_mounted_and_does_not_raise(
    persona_manager, emotional_state_manager
):
    broken_renderer = _FakeRenderer("jarvis", raise_on={"mount"})
    controller = _make_controller(
        persona_manager, emotional_state_manager, renderers={"jarvis": broken_renderer}
    )

    controller.mount_renderer("jarvis")  # must not raise

    assert broken_renderer.calls == ["mount"]
    assert controller.mounted_persona_name is None


def test_mount_renderer_raising_on_unmount_still_mounts_the_new_renderer(
    persona_manager, emotional_state_manager
):
    broken_jarvis = _FakeRenderer("jarvis", raise_on={"unmount"})
    minie_renderer = _FakeRenderer("minie")
    controller = _make_controller(
        persona_manager,
        emotional_state_manager,
        renderers={"jarvis": broken_jarvis, "minie": minie_renderer},
    )
    controller.start()

    controller.mount_renderer("minie")  # must not raise despite jarvis.unmount() exploding

    assert broken_jarvis.calls == ["mount", "unmount"]
    assert minie_renderer.calls == ["mount"]
    assert controller.mounted_persona_name == "minie"


# --- refresh() Fail Gracefully (Acceptance Criteria) --------------------------


def test_refresh_happy_path_calls_render_state_with_the_computed_state(
    persona_manager, emotional_state_manager
):
    renderer = _FakeRenderer("jarvis")
    state = _sample_state("jarvis")
    controller = _make_controller(
        persona_manager,
        emotional_state_manager,
        state_computers={"jarvis": _FakeComputer(result=state)},
        renderers={"jarvis": renderer},
    )
    controller.start()

    controller.refresh()

    assert renderer.calls == ["mount", "render_state"]


def test_refresh_never_raises_when_the_computer_raises(persona_manager, emotional_state_manager):
    renderer = _FakeRenderer("jarvis")
    controller = _make_controller(
        persona_manager,
        emotional_state_manager,
        state_computers={"jarvis": _FakeComputer(raise_error=True)},
        renderers={"jarvis": renderer},
    )
    controller.start()

    controller.refresh()  # must not raise

    assert "render_state" not in renderer.calls


def test_refresh_never_raises_when_the_renderer_raises(persona_manager, emotional_state_manager):
    renderer = _FakeRenderer("jarvis", raise_on={"render_state"})
    controller = _make_controller(
        persona_manager,
        emotional_state_manager,
        state_computers={"jarvis": _FakeComputer()},
        renderers={"jarvis": renderer},
    )
    controller.start()

    controller.refresh()  # must not raise


def test_refresh_is_a_noop_when_nothing_is_mounted(persona_manager, emotional_state_manager):
    computer = _FakeComputer()
    controller = _make_controller(
        persona_manager, emotional_state_manager, state_computers={"jarvis": computer}, renderers={}
    )

    controller.refresh()

    assert computer.calls == 0


def test_refresh_warns_and_skips_when_no_computer_bound_for_active_persona(
    persona_manager, emotional_state_manager, caplog
):
    renderer = _FakeRenderer("jarvis")
    controller = _make_controller(
        persona_manager, emotional_state_manager, state_computers={}, renderers={"jarvis": renderer}
    )
    controller.start()

    controller.refresh()

    assert "render_state" not in renderer.calls


# --- last_state_for()/apply_state() (Sprint 5.10) -----------------------------


def test_last_state_for_is_none_before_any_refresh(persona_manager, emotional_state_manager):
    controller = _make_controller(persona_manager, emotional_state_manager)
    assert controller.last_state_for("jarvis") is None


def test_last_state_for_returns_the_most_recently_computed_state(
    persona_manager, emotional_state_manager
):
    state = _sample_state("jarvis")
    controller = _make_controller(
        persona_manager,
        emotional_state_manager,
        state_computers={"jarvis": _FakeComputer(result=state)},
        renderers={"jarvis": _FakeRenderer("jarvis")},
    )
    controller.start()

    controller.refresh()

    assert controller.last_state_for("jarvis") is state


def test_last_state_for_is_still_none_when_refresh_never_ran_for_that_persona(
    persona_manager, emotional_state_manager
):
    controller = _make_controller(
        persona_manager,
        emotional_state_manager,
        state_computers={"jarvis": _FakeComputer(result=_sample_state("jarvis"))},
        renderers={"jarvis": _FakeRenderer("jarvis")},
    )
    controller.start()
    controller.refresh()

    assert controller.last_state_for("minie") is None


def test_apply_state_renders_through_the_mounted_renderer(
    persona_manager, emotional_state_manager
):
    renderer = _FakeRenderer("jarvis")
    controller = _make_controller(
        persona_manager, emotional_state_manager, renderers={"jarvis": renderer}
    )
    controller.start()
    state = _sample_state("jarvis")

    controller.apply_state(state)

    assert renderer.calls == ["mount", "render_state"]


def test_apply_state_is_a_noop_when_nothing_is_mounted(persona_manager, emotional_state_manager):
    controller = _make_controller(persona_manager, emotional_state_manager, renderers={})
    controller.apply_state(_sample_state("jarvis"))  # must not raise


def test_apply_state_never_raises_when_the_renderer_raises(
    persona_manager, emotional_state_manager
):
    broken_renderer = _FakeRenderer("jarvis", raise_on={"render_state"})
    controller = _make_controller(
        persona_manager, emotional_state_manager, renderers={"jarvis": broken_renderer}
    )
    controller.start()

    controller.apply_state(_sample_state("jarvis"))  # must not raise


# --- dispatch_gesture() (Sprint 5.9) ------------------------------------------


def test_dispatch_gesture_calls_trigger_gesture_on_the_mounted_renderer(
    persona_manager, emotional_state_manager
):
    renderer = _FakeRenderer("jarvis")
    controller = _make_controller(
        persona_manager, emotional_state_manager, renderers={"jarvis": renderer}
    )
    controller.start()
    event = GestureEvent(
        trigger=GestureTrigger.NOTIFICATION,
        gesture_id="glance",
        persona_name="jarvis",
        triggered_at=datetime.now(UTC),
    )

    controller.dispatch_gesture(event)

    assert "trigger_gesture" in renderer.calls


def test_dispatch_gesture_is_a_noop_when_nothing_is_mounted(
    persona_manager, emotional_state_manager
):
    controller = _make_controller(persona_manager, emotional_state_manager, renderers={})
    event = GestureEvent(
        trigger=GestureTrigger.NOTIFICATION,
        gesture_id="glance",
        persona_name="jarvis",
        triggered_at=datetime.now(UTC),
    )

    controller.dispatch_gesture(event)  # must not raise


def test_dispatch_gesture_never_raises_when_the_renderer_raises(
    persona_manager, emotional_state_manager
):
    broken_renderer = _FakeRenderer("jarvis", raise_on={"trigger_gesture"})
    controller = _make_controller(
        persona_manager, emotional_state_manager, renderers={"jarvis": broken_renderer}
    )
    controller.start()
    event = GestureEvent(
        trigger=GestureTrigger.NOTIFICATION,
        gesture_id="glance",
        persona_name="jarvis",
        triggered_at=datetime.now(UTC),
    )

    controller.dispatch_gesture(event)  # must not raise


# --- refresh() ambient-gesture rolling (Sprint 5.9) ---------------------------


def test_refresh_rolls_an_ambient_gesture_using_the_computed_states_own_values(
    persona_manager, emotional_state_manager
):
    state = _sample_state("jarvis")
    state.gesture_probability = 0.42
    gesture_engine = _FakeGestureEngine()
    controller = _make_controller(
        persona_manager,
        emotional_state_manager,
        state_computers={"jarvis": _FakeComputer(result=state)},
        renderers={"jarvis": _FakeRenderer("jarvis")},
        gesture_engine=gesture_engine,
    )
    controller.start()

    controller.refresh()

    assert gesture_engine.calls == [(0.42, "jarvis")]


def test_refresh_dispatches_a_non_none_ambient_gesture(persona_manager, emotional_state_manager):
    renderer = _FakeRenderer("jarvis")
    event = GestureEvent(
        trigger=GestureTrigger.AMBIENT_IDLE,
        gesture_id="idle_blink",
        persona_name="jarvis",
        triggered_at=datetime.now(UTC),
    )
    controller = _make_controller(
        persona_manager,
        emotional_state_manager,
        state_computers={"jarvis": _FakeComputer()},
        renderers={"jarvis": renderer},
        gesture_engine=_FakeGestureEngine(result=event),
    )
    controller.start()

    controller.refresh()

    assert renderer.calls == ["mount", "render_state", "trigger_gesture"]


def test_refresh_does_not_dispatch_when_no_ambient_gesture_fires(
    persona_manager, emotional_state_manager
):
    renderer = _FakeRenderer("jarvis")
    controller = _make_controller(
        persona_manager,
        emotional_state_manager,
        state_computers={"jarvis": _FakeComputer()},
        renderers={"jarvis": renderer},
        gesture_engine=_FakeGestureEngine(result=None),
    )
    controller.start()

    controller.refresh()

    assert renderer.calls == ["mount", "render_state"]


def test_refresh_never_raises_when_the_gesture_engine_raises(
    persona_manager, emotional_state_manager
):
    class _BrokenGestureEngine:
        def maybe_roll_ambient_gesture(self, gesture_probability, persona_name):
            raise RuntimeError("gesture engine exploded")

    controller = _make_controller(
        persona_manager,
        emotional_state_manager,
        state_computers={"jarvis": _FakeComputer()},
        renderers={"jarvis": _FakeRenderer("jarvis")},
        gesture_engine=_BrokenGestureEngine(),
    )
    controller.start()

    controller.refresh()  # must not raise


# --- mounted renderer vs. active persona (Architecture Notes) ----------------


def test_refresh_renders_through_the_mounted_renderer_not_the_active_persona(
    persona_manager, emotional_state_manager
):
    """The transitional-mismatch scenario this module's own docstring
    names explicitly: PersonaManager's active persona is still "jarvis"
    but "minie"'s renderer has already been mounted (e.g. mid-transition,
    Sprint 5.10's future job) — refresh() must render through minie's
    renderer using jarvis's own computed state, never silently switch to
    minie's computer just because minie's renderer happens to be
    mounted."""
    jarvis_state = _sample_state("jarvis")
    jarvis_renderer = _FakeRenderer("jarvis")
    minie_renderer = _FakeRenderer("minie")
    controller = _make_controller(
        persona_manager,
        emotional_state_manager,
        state_computers={
            "jarvis": _FakeComputer(result=jarvis_state),
            "minie": _FakeComputer(result=_sample_state("minie")),
        },
        renderers={"jarvis": jarvis_renderer, "minie": minie_renderer},
    )
    controller.start()  # mounts jarvis (PersonaManager's default active persona)
    controller.mount_renderer("minie")  # simulates a transition already swapping the renderer

    controller.refresh()

    assert controller.mounted_persona_name == "minie"
    assert persona_manager.active_persona().name == "jarvis"  # unchanged
    assert minie_renderer.calls[-1] == "render_state"
    assert jarvis_renderer.calls[-1] != "render_state"


# --- mounted_persona_name property ---------------------------------------------


def test_mounted_persona_name_is_none_before_start(persona_manager, emotional_state_manager):
    controller = _make_controller(persona_manager, emotional_state_manager, renderers={})
    assert controller.mounted_persona_name is None


def test_mounted_persona_name_updates_after_mount_renderer(
    persona_manager, emotional_state_manager
):
    controller = _make_controller(
        persona_manager,
        emotional_state_manager,
        renderers={"jarvis": _FakeRenderer("jarvis"), "minie": _FakeRenderer("minie")},
    )
    controller.start()
    assert controller.mounted_persona_name == "jarvis"

    controller.mount_renderer("minie")
    assert controller.mounted_persona_name == "minie"
