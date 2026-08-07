"""Unit tests for planning.planning_engine.

Uses only a local, in-file fake LanguageModelClient — no real Ollama call
is made, the same convention as test_intent_detector.py/
test_context_analyzer.py/test_response_generator.py. Parsing behavior
(_parse_decomposition/_parse_task_line) is exercised only through the
public decompose_goal() contract, never by importing the underscore-
prefixed helpers directly — matching test_context_analyzer.py's/
test_intent_detector.py's own established convention (their own private
_parse_response()/_build_prompt() are never imported by name either),
a small, disclosed correction from this sprint file's own Testing
Checklist wording ("isolated for direct unit testing"), which described
the general intent but not this codebase's own real precedent for how
that intent is actually satisfied.
"""

import pytest

from config.schema import ModelConfig, PlanningConfig
from decision.llm_client import LlmError
from planning.planning_engine import PlanningEngine
from planning.planning_model import PlanningStatus


class FakeLanguageModelClient:
    """Implements ONLY the LanguageModelClient Protocol (no is_reachable)
    — same convention as every other real caller's own fake in this
    codebase."""

    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[tuple[str, float, list[str] | None]] = []

    def generate(
        self, prompt: str, timeout_seconds: float, stop: list[str] | None = None
    ) -> str:
        self.calls.append((prompt, timeout_seconds, stop))
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


@pytest.fixture
def model_config() -> ModelConfig:
    return ModelConfig(ollama_timeout_seconds=5.0)


@pytest.fixture
def planning_config() -> PlanningConfig:
    return PlanningConfig(
        max_milestones_per_goal=2, max_tasks_per_milestone=2, decomposition_timeout_seconds=45.0
    )


_WELL_FORMED_TWO_MILESTONE_RESPONSE = (
    "MILESTONE: Set up the project\n"
    "TASK: Create the repository | Initialize a new git repository | 5 minutes\n"
    "TASK: Install dependencies | Run the package manager | 10 minutes\n"
    "MILESTONE: Write the first feature\n"
    "TASK: Implement the core logic | Write the main function | 1 hour\n"
)

_SINGLE_MILESTONE_RESPONSE = (
    "MILESTONE: Learn the basics\nTASK: Read the docs | Read the getting-started guide | NONE\n"
)


# --- happy path -----------------------------------------------------------------------


def test_decompose_goal_returns_a_goal_with_the_exact_input_statement(
    model_config, planning_config
):
    fake = FakeLanguageModelClient(response=_SINGLE_MILESTONE_RESPONSE)
    engine = PlanningEngine(fake, model_config, planning_config)

    goal = engine.decompose_goal("Learn to code")

    assert goal.statement == "Learn to code"
    assert goal.status is PlanningStatus.PROPOSED


def test_decompose_goal_parses_multiple_milestones_and_tasks(model_config, planning_config):
    fake = FakeLanguageModelClient(response=_WELL_FORMED_TWO_MILESTONE_RESPONSE)
    engine = PlanningEngine(fake, model_config, planning_config)

    goal = engine.decompose_goal("Build a small app")

    assert len(goal.milestones) == 2
    assert goal.milestones[0].title == "Set up the project"
    assert len(goal.milestones[0].tasks) == 2
    assert goal.milestones[0].tasks[0].title == "Create the repository"
    assert goal.milestones[0].tasks[0].description == "Initialize a new git repository"
    assert goal.milestones[0].tasks[0].estimated_effort == "5 minutes"
    assert goal.milestones[1].title == "Write the first feature"
    assert len(goal.milestones[1].tasks) == 1


def test_decompose_goal_treats_a_none_effort_as_no_estimate(model_config, planning_config):
    fake = FakeLanguageModelClient(response=_SINGLE_MILESTONE_RESPONSE)
    engine = PlanningEngine(fake, model_config, planning_config)

    goal = engine.decompose_goal("Learn to code")

    assert goal.milestones[0].tasks[0].estimated_effort is None


# --- truncation -------------------------------------------------------------------------


def test_decompose_goal_truncates_excess_milestones_and_logs_a_warning(
    model_config, planning_config, caplog
):
    response = (
        "MILESTONE: One\nTASK: A | | NONE\n"
        "MILESTONE: Two\nTASK: B | | NONE\n"
        "MILESTONE: Three\nTASK: C | | NONE\n"
    )
    fake = FakeLanguageModelClient(response=response)
    engine = PlanningEngine(fake, model_config, planning_config)  # max_milestones_per_goal=2

    with caplog.at_level("WARNING"):
        goal = engine.decompose_goal("A goal with too many milestones")

    assert len(goal.milestones) == 2
    assert goal.milestones[0].title == "One"
    assert goal.milestones[1].title == "Two"
    assert "milestones" in caplog.text.lower()


def test_decompose_goal_truncates_excess_tasks_per_milestone_and_logs_a_warning(
    model_config, planning_config, caplog
):
    response = (
        "MILESTONE: One\n"
        "TASK: A | | NONE\n"
        "TASK: B | | NONE\n"
        "TASK: C | | NONE\n"  # max_tasks_per_milestone=2, this one is discarded
    )
    fake = FakeLanguageModelClient(response=response)
    engine = PlanningEngine(fake, model_config, planning_config)

    with caplog.at_level("WARNING"):
        goal = engine.decompose_goal("A goal with too many tasks")

    assert len(goal.milestones[0].tasks) == 2
    assert "tasks" in caplog.text.lower()


# --- unparseable / malformed response ----------------------------------------------------


def test_decompose_goal_raises_llm_error_for_a_response_with_no_milestones(
    model_config, planning_config
):
    fake = FakeLanguageModelClient(response="I'm not sure how to break that down.")
    engine = PlanningEngine(fake, model_config, planning_config)

    with pytest.raises(LlmError):
        engine.decompose_goal("Do something vague")


def test_decompose_goal_raises_llm_error_for_an_empty_response(model_config, planning_config):
    fake = FakeLanguageModelClient(response="")
    engine = PlanningEngine(fake, model_config, planning_config)

    with pytest.raises(LlmError):
        engine.decompose_goal("Do something")


def test_decompose_goal_raises_llm_error_when_every_milestone_has_no_tasks(
    model_config, planning_config
):
    fake = FakeLanguageModelClient(response="MILESTONE: An empty milestone\n")
    engine = PlanningEngine(fake, model_config, planning_config)

    with pytest.raises(LlmError):
        engine.decompose_goal("Do something")


def test_decompose_goal_ignores_a_task_line_before_any_milestone(model_config, planning_config):
    response = "TASK: Orphaned task | | NONE\n" + _SINGLE_MILESTONE_RESPONSE
    fake = FakeLanguageModelClient(response=response)
    engine = PlanningEngine(fake, model_config, planning_config)

    goal = engine.decompose_goal("Learn to code")

    assert len(goal.milestones) == 1
    assert all(task.title != "Orphaned task" for task in goal.milestones[0].tasks)


# --- failure propagation / call shape ----------------------------------------------------


def test_decompose_goal_propagates_llm_error_from_generate(model_config, planning_config):
    fake = FakeLanguageModelClient(error=LlmError("ollama unreachable"))
    engine = PlanningEngine(fake, model_config, planning_config)

    with pytest.raises(LlmError):
        engine.decompose_goal("Do something")


def test_decompose_goal_uses_the_dedicated_decomposition_timeout_not_model_config(
    model_config, planning_config
):
    fake = FakeLanguageModelClient(response=_SINGLE_MILESTONE_RESPONSE)
    engine = PlanningEngine(fake, model_config, planning_config)

    engine.decompose_goal("Learn to code")

    assert fake.calls[0][1] == planning_config.decomposition_timeout_seconds
    assert fake.calls[0][1] != model_config.ollama_timeout_seconds


def test_decompose_goal_does_not_pass_a_stop_sequence(model_config, planning_config):
    """Deliberately unlike IntentDetector/ContextAnalyzer — see this
    module's own docstring for why a variable-length, multi-line
    decomposition follows ResponseGenerator's/Summarizer's own
    no-stop-sequence precedent instead."""
    fake = FakeLanguageModelClient(response=_SINGLE_MILESTONE_RESPONSE)
    engine = PlanningEngine(fake, model_config, planning_config)

    engine.decompose_goal("Learn to code")

    assert fake.calls[0][2] is None


def test_decompose_goal_prompt_contains_the_statement(model_config, planning_config):
    fake = FakeLanguageModelClient(response=_SINGLE_MILESTONE_RESPONSE)
    engine = PlanningEngine(fake, model_config, planning_config)

    engine.decompose_goal("Learn to juggle")

    assert "Learn to juggle" in fake.calls[0][0]
