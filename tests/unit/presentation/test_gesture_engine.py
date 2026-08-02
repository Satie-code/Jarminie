"""Unit tests for presentation.gesture_engine (Sprint 5.9).

GestureEngine is a pure decision class (no renderer/PersonaManager/
EmotionalStateManager reference) — these tests exercise trigger_event()/
maybe_roll_ambient_gesture() directly against a real PresentationConfig,
no fakes needed.
"""

import ast
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from config.schema import PresentationConfig
from presentation.gesture_engine import GestureEngine, GestureEvent, GestureTrigger


@pytest.fixture
def config() -> PresentationConfig:
    return PresentationConfig(
        gesture_vocabulary={
            "notification": ["glance", "pulse"],
            "ambient_idle": ["idle_blink"],
        },
        ambient_gesture_roll_interval_seconds=10.0,
    )


@pytest.fixture
def engine(config) -> GestureEngine:
    return GestureEngine(config)


# --- trigger_event() vocabulary selection/variety (Acceptance Criteria) ------


def test_trigger_event_returns_a_configured_candidate(engine):
    event = engine.trigger_event(GestureTrigger.NOTIFICATION, "jarvis")

    assert isinstance(event, GestureEvent)
    assert event.trigger is GestureTrigger.NOTIFICATION
    assert event.gesture_id in ("glance", "pulse")
    assert event.persona_name == "jarvis"
    assert isinstance(event.triggered_at, datetime)


def test_trigger_event_round_robins_through_the_configured_vocabulary(engine):
    first = engine.trigger_event(GestureTrigger.NOTIFICATION, "jarvis")
    second = engine.trigger_event(GestureTrigger.NOTIFICATION, "jarvis")
    third = engine.trigger_event(GestureTrigger.NOTIFICATION, "jarvis")

    assert [first.gesture_id, second.gesture_id, third.gesture_id] == ["glance", "pulse", "glance"]


def test_trigger_event_round_robin_is_independent_per_trigger(engine):
    notification_first = engine.trigger_event(GestureTrigger.NOTIFICATION, "jarvis")
    ambient_first = engine.trigger_event(GestureTrigger.AMBIENT_IDLE, "jarvis")
    notification_second = engine.trigger_event(GestureTrigger.NOTIFICATION, "jarvis")

    assert notification_first.gesture_id == "glance"
    assert ambient_first.gesture_id == "idle_blink"
    assert notification_second.gesture_id == "pulse"


def test_trigger_event_carries_the_given_persona_name(engine):
    event = engine.trigger_event(GestureTrigger.NOTIFICATION, "minie")
    assert event.persona_name == "minie"


# --- trigger_event() empty-vocabulary no-op (Acceptance Criteria) ------------


def test_trigger_event_returns_none_for_an_unconfigured_trigger(engine):
    # TURN_END has no entry at all in this fixture's own gesture_vocabulary.
    assert engine.trigger_event(GestureTrigger.TURN_END, "jarvis") is None


def test_trigger_event_returns_none_for_an_explicitly_empty_vocabulary():
    config = PresentationConfig(gesture_vocabulary={"notification": []})
    engine = GestureEngine(config)

    assert engine.trigger_event(GestureTrigger.NOTIFICATION, "jarvis") is None


def test_trigger_event_never_raises_for_every_trigger_value(engine):
    for trigger in GestureTrigger:
        engine.trigger_event(trigger, "jarvis")  # must not raise, configured or not


# --- maybe_roll_ambient_gesture() probability behavior -----------------------


def test_maybe_roll_ambient_gesture_fires_when_the_roll_succeeds(engine):
    with patch("presentation.gesture_engine.random.random", return_value=0.0):
        event = engine.maybe_roll_ambient_gesture(gesture_probability=1.0, persona_name="minie")

    assert event is not None
    assert event.trigger is GestureTrigger.AMBIENT_IDLE
    assert event.gesture_id == "idle_blink"
    assert event.persona_name == "minie"


def test_maybe_roll_ambient_gesture_does_not_fire_when_the_roll_fails(engine):
    with patch("presentation.gesture_engine.random.random", return_value=0.999):
        event = engine.maybe_roll_ambient_gesture(gesture_probability=0.0, persona_name="minie")

    assert event is None


def test_maybe_roll_ambient_gesture_returns_none_far_more_often_than_not(engine):
    # A real (unpatched) random roll at a low, realistic probability —
    # statistically overwhelmingly None across many independent calls,
    # each one bypassing the interval gate via a fresh engine.
    fire_count = 0
    for _ in range(200):
        fresh_engine = GestureEngine(engine._config)
        if fresh_engine.maybe_roll_ambient_gesture(gesture_probability=0.05, persona_name="x"):
            fire_count += 1

    assert fire_count < 100  # nowhere near "fires most of the time"


# --- maybe_roll_ambient_gesture() interval rate-limiting (Acceptance Criteria) -


def test_ambient_gesture_never_fires_twice_within_the_configured_interval(engine):
    with patch("presentation.gesture_engine.random.random", return_value=0.0):
        first = engine.maybe_roll_ambient_gesture(gesture_probability=1.0, persona_name="jarvis")
        second = engine.maybe_roll_ambient_gesture(gesture_probability=1.0, persona_name="jarvis")
        third = engine.maybe_roll_ambient_gesture(gesture_probability=1.0, persona_name="jarvis")

    assert first is not None
    assert second is None
    assert third is None


def test_ambient_gesture_can_fire_again_once_the_interval_has_elapsed(engine):
    interval = engine._config.ambient_gesture_roll_interval_seconds
    future = datetime.now(UTC) + timedelta(seconds=interval + 1)

    with patch("presentation.gesture_engine.random.random", return_value=0.0):
        first = engine.maybe_roll_ambient_gesture(gesture_probability=1.0, persona_name="jarvis")
        assert first is not None

        with patch("presentation.gesture_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = future
            second = engine.maybe_roll_ambient_gesture(
                gesture_probability=1.0, persona_name="jarvis"
            )

    assert second is not None


def test_a_failed_roll_does_not_consume_the_interval(engine):
    """A roll that fails (or whose vocabulary is empty) must not itself
    start the rate-limit window — only a genuine fire does (Expected
    Functions)."""
    with patch("presentation.gesture_engine.random.random", return_value=0.999):
        failed = engine.maybe_roll_ambient_gesture(gesture_probability=0.0, persona_name="jarvis")
    assert failed is None

    with patch("presentation.gesture_engine.random.random", return_value=0.0):
        succeeded = engine.maybe_roll_ambient_gesture(
            gesture_probability=1.0, persona_name="jarvis"
        )
    assert succeeded is not None  # not blocked by the earlier failed roll


def test_ambient_gesture_respects_the_interval_even_at_probability_one(engine):
    """The exact Acceptance Criteria scenario: a gesture_probability of
    1.0 still cannot fire more than once per configured interval."""
    with patch("presentation.gesture_engine.random.random", return_value=0.0):
        results = [
            engine.maybe_roll_ambient_gesture(gesture_probability=1.0, persona_name="jarvis")
            for _ in range(10)
        ]

    non_none = [r for r in results if r is not None]
    assert len(non_none) == 1


def test_maybe_roll_ambient_gesture_never_raises(engine):
    for _ in range(20):
        engine.maybe_roll_ambient_gesture(gesture_probability=0.5, persona_name="jarvis")


# --- mechanical: no renderer import (Acceptance Criteria) --------------------


def test_gesture_engine_imports_nothing_from_any_renderer_module():
    """AST-based, not a substring scan — the same precedent Sprint 5.8's
    own avatar-renderer-registry check established, so this module's own
    docstring prose (which legitimately names jarvis_renderer.py/
    minie_renderer.py/vtube_studio_renderer.py to explain the when/how
    split) is correctly not flagged, only real import statements are."""
    module_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "presentation", "gesture_engine.py"
    )
    with open(module_path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=module_path)

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    forbidden = ("jarvis_renderer", "minie_renderer", "vtube_studio_renderer")
    for module_name in imported_modules:
        assert not any(name in module_name for name in forbidden), module_name
