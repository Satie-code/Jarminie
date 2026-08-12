"""Unit tests for reasoning.explainability.

Uses only a local, in-file fake LanguageModelClient wired into a real
ReasoningEngine — no real Ollama call is made, the same convention as
test_reasoning_engine.py/test_self_evaluator.py. A DecisionTrace is built
by hand here rather than imported from tests/unit/personas/conftest.py's
own decision_trace_factory fixture — tests/ has no __init__.py (Sprint
1.1's own convention), so fixtures aren't shared across directories;
mirrors test_self_evaluator.py's own self-contained-helper precedent.
"""

from datetime import UTC, datetime

import pytest

from config.schema import ModelConfig, PlanningConfig, ReasoningConfig
from database.sqlite_client import SqliteClient
from decision.authority import AuthorityLevel, DecisionTrace, EngineSelection
from decision.context_analyzer import ContextAnalysis, SentimentHint
from decision.models import Intent, IntentCategory
from decision.priority_queue import PriorityLevel
from planning.planning_model import Goal, Milestone, PlanningStatus, Task
from planning.self_evaluator import EvaluationOutcome, EvaluationRecord
from planning.task_graph_store import TaskGraphStore
from reasoning.explainability import ExplainabilityLayer, Explanation, ExplanationRequest
from reasoning.reasoning_engine import ReasoningEngine


class FakeLanguageModelClient:
    """Implements ONLY the LanguageModelClient Protocol (no is_reachable)
    — matches test_reasoning_engine.py's own established fake."""

    def __init__(self, response: str | None = None) -> None:
        self._response = response
        self.calls: list[str] = []

    def generate(
        self, prompt: str, timeout_seconds: float, stop: list[str] | None = None
    ) -> str:
        self.calls.append(prompt)
        assert self._response is not None
        return self._response


@pytest.fixture
def model_config() -> ModelConfig:
    return ModelConfig(ollama_timeout_seconds=5.0)


@pytest.fixture
def store(tmp_path) -> TaskGraphStore:
    client = SqliteClient(str(tmp_path / "planning.db"))
    task_graph_store = TaskGraphStore(client, PlanningConfig())
    task_graph_store.start()
    yield task_graph_store
    task_graph_store.stop()


def make_layer(
    response: str = "CONCLUSION: A fresh explanation.",
    task_graph_store: TaskGraphStore | None = None,
    decision_trace_lookup=None,
    reasoning_config: ReasoningConfig | None = None,
    model_config: ModelConfig | None = None,
) -> tuple[ExplainabilityLayer, FakeLanguageModelClient]:
    fake_client = FakeLanguageModelClient(response=response)
    reasoning_config = reasoning_config or ReasoningConfig()
    reasoning_engine = ReasoningEngine(
        fake_client, model_config or ModelConfig(ollama_timeout_seconds=5.0), reasoning_config
    )
    layer = ExplainabilityLayer(
        reasoning_engine, task_graph_store, decision_trace_lookup, reasoning_config
    )
    return layer, fake_client


def make_decision_trace(
    reasoning_text: str = "Because it matched the user's request.",
) -> DecisionTrace:
    now = datetime.now(UTC)
    return DecisionTrace(
        intent=Intent(
            category=IntentCategory.INFORMATIONAL,
            confidence=0.9,
            raw_transcript="x",
            detected_at=now,
        ),
        context_analysis=ContextAnalysis(
            primary_topic="",
            mentioned_entities=[],
            references_past_memory=False,
            suggested_persona=None,
            sentiment_hint=SentimentHint.NEUTRAL,
            analyzed_at=now,
        ),
        retrieved_memories=[],
        priority_level=PriorityLevel.GENERAL_SUGGESTION,
        authority_level=AuthorityLevel.INFORM,
        selected_engine=EngineSelection.CONVERSATIONAL_RESPONSE,
        reasoning_text=reasoning_text,
        decided_at=now,
    )


def make_goal_with_task(
    goal_id: str, task_status: PlanningStatus = PlanningStatus.COMPLETED
) -> Goal:
    return Goal(
        goal_id=goal_id,
        statement="Ship the feature",
        milestones=[
            Milestone(
                milestone_id=f"{goal_id}-m1",
                title="Build it",
                tasks=[
                    Task(
                        task_id=f"{goal_id}-t1",
                        title="Write the code",
                        description="Implement the feature end to end",
                        status=task_status,
                    ),
                ],
            ),
        ],
        created_at=datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC),
        status=PlanningStatus.ACCEPTED,
    )


# --- ExplanationRequest/Explanation construction ------------------------------------------


def test_explanation_request_construction():
    request = ExplanationRequest(subject_id="t1", subject_kind="task")
    assert request.subject_id == "t1"
    assert request.subject_kind == "task"


def test_explanation_construction():
    explanation = Explanation(
        subject_id="t1", narrative="Because.", sources=["Task"], confidence=None
    )
    assert explanation.narrative == "Because."
    assert explanation.sources == ["Task"]
    assert explanation.confidence is None


# --- explain() with only a DecisionTrace available ----------------------------------------


def test_explain_with_only_decision_trace_makes_no_llm_call():
    trace = make_decision_trace("Because it matched the user's request.")
    layer, fake_client = make_layer(decision_trace_lookup=lambda subject_id: trace)

    explanation = layer.explain(
        ExplanationRequest(subject_id="turn-1", subject_kind="decision_trace")
    )

    assert fake_client.calls == []
    assert explanation.sources == ["DecisionTrace"]
    assert explanation.confidence is None
    assert "Because it matched the user's request." in explanation.narrative


def test_explain_decision_trace_lookup_returning_none_falls_through_to_llm():
    layer, fake_client = make_layer(
        response="CONCLUSION: No prior decision was found.",
        decision_trace_lookup=lambda subject_id: None,
    )

    explanation = layer.explain(
        ExplanationRequest(subject_id="turn-1", subject_kind="decision_trace")
    )

    assert len(fake_client.calls) == 1
    assert explanation.sources == ["ReasoningTrace"]


# --- explain() with multiple available trace objects composed together --------------------


def test_explain_task_composes_task_and_evaluation_record(store):
    goal = make_goal_with_task("g1")
    store.save_goal(goal)
    task = goal.milestones[0].tasks[0]
    store.save_evaluation(
        EvaluationRecord(
            record_id="e1",
            subject_id=task.task_id,
            outcome=EvaluationOutcome.SUCCESS,
            summary="Finished cleanly.",
            improvement_note=None,
            evaluated_at=datetime.now(UTC),
        )
    )
    layer, fake_client = make_layer(task_graph_store=store)

    explanation = layer.explain(ExplanationRequest(subject_id=task.task_id, subject_kind="task"))

    assert fake_client.calls == []
    assert explanation.sources == ["Task", "EvaluationRecord"]
    assert "Write the code" in explanation.narrative
    assert "Finished cleanly." in explanation.narrative


def test_explain_goal_composes_goal_and_its_evaluations(store):
    goal = make_goal_with_task("g1")
    store.save_goal(goal)
    task = goal.milestones[0].tasks[0]
    store.save_evaluation(
        EvaluationRecord(
            record_id="e1",
            subject_id=task.task_id,
            outcome=EvaluationOutcome.SUCCESS,
            summary="Went well.",
            improvement_note=None,
            evaluated_at=datetime.now(UTC),
        )
    )
    layer, fake_client = make_layer(task_graph_store=store)

    explanation = layer.explain(ExplanationRequest(subject_id="g1", subject_kind="goal"))

    assert fake_client.calls == []
    assert explanation.sources == ["Goal", "EvaluationRecord"]
    assert "Ship the feature" in explanation.narrative


def test_explain_goal_with_no_evaluations_composes_goal_alone(store):
    goal = make_goal_with_task("g1")
    store.save_goal(goal)
    layer, fake_client = make_layer(task_graph_store=store)

    explanation = layer.explain(ExplanationRequest(subject_id="g1", subject_kind="goal"))

    assert fake_client.calls == []
    assert explanation.sources == ["Goal"]


def test_explain_evaluation_kind_scans_across_goals_for_matching_subject_id(store):
    goal_a = make_goal_with_task("g-a")
    goal_b = make_goal_with_task("g-b")
    store.save_goal(goal_a)
    store.save_goal(goal_b)
    target_task = goal_b.milestones[0].tasks[0]
    store.save_evaluation(
        EvaluationRecord(
            record_id="e1",
            subject_id=target_task.task_id,
            outcome=EvaluationOutcome.FAILURE,
            summary="Ran out of time.",
            improvement_note="allocate more time",
            evaluated_at=datetime.now(UTC),
        )
    )
    layer, fake_client = make_layer(task_graph_store=store)

    explanation = layer.explain(
        ExplanationRequest(subject_id=target_task.task_id, subject_kind="evaluation")
    )

    assert fake_client.calls == []
    assert explanation.sources == ["EvaluationRecord"]
    assert "Ran out of time." in explanation.narrative
    assert "allocate more time" in explanation.narrative


# --- explain() with nothing available falls through to the LLM ----------------------------


def test_explain_with_nothing_available_falls_through_to_llm():
    layer, fake_client = make_layer(response="CONCLUSION: Nothing was recorded about this.")

    explanation = layer.explain(ExplanationRequest(subject_id="unknown", subject_kind="task"))

    assert len(fake_client.calls) == 1
    assert explanation.sources == ["ReasoningTrace"]
    assert explanation.confidence == 1.0
    assert explanation.narrative == "Nothing was recorded about this."


def test_explain_task_graph_store_none_degrades_task_and_goal_lookups_to_fallback():
    layer, fake_client = make_layer(response="CONCLUSION: No store was available.")

    explanation = layer.explain(ExplanationRequest(subject_id="g1", subject_kind="goal"))

    assert len(fake_client.calls) == 1
    assert explanation.sources == ["ReasoningTrace"]


def test_explain_unknown_task_id_falls_through_to_llm(store):
    layer, fake_client = make_layer(response="CONCLUSION: Unknown task.", task_graph_store=store)

    explanation = layer.explain(
        ExplanationRequest(subject_id="does-not-exist", subject_kind="task")
    )

    assert len(fake_client.calls) == 1
    assert explanation.sources == ["ReasoningTrace"]


def test_explain_ranked_action_always_falls_through_to_llm(store):
    """No RankedAction store exists anywhere in this codebase — see this
    module's own docstring. Confirmed here even with a real
    task_graph_store/decision_trace_lookup wired up, neither of which
    can resolve a "ranked_action" subject."""
    layer, fake_client = make_layer(
        response="CONCLUSION: No ranking record exists.",
        task_graph_store=store,
        decision_trace_lookup=lambda subject_id: make_decision_trace(),
    )

    explanation = layer.explain(
        ExplanationRequest(subject_id="action-1", subject_kind="ranked_action")
    )

    assert len(fake_client.calls) == 1
    assert explanation.sources == ["ReasoningTrace"]


# --- narrative truncation -------------------------------------------------------------------


def test_narrative_truncated_to_max_explanation_sentences():
    reasoning_config = ReasoningConfig(max_explanation_sentences=2)
    layer, fake_client = make_layer(
        response="CONCLUSION: One. Two. Three. Four.", reasoning_config=reasoning_config
    )

    explanation = layer.explain(ExplanationRequest(subject_id="unknown", subject_kind="task"))

    assert explanation.narrative == "One. Two."


def test_composed_narrative_is_also_truncated(store):
    reasoning_config = ReasoningConfig(max_explanation_sentences=1)
    trace = make_decision_trace("First sentence. Second sentence. Third sentence.")
    layer, fake_client = make_layer(
        decision_trace_lookup=lambda subject_id: trace, reasoning_config=reasoning_config
    )

    explanation = layer.explain(
        ExplanationRequest(subject_id="turn-1", subject_kind="decision_trace")
    )

    assert explanation.narrative == "First sentence."


# --- _compose() in isolation -----------------------------------------------------------------


def test_compose_stitches_multiple_sources_into_one_paragraph():
    layer, _ = make_layer()

    result = layer._compose([("A", "Hello world."), ("B", "Second part.")])

    assert result == "Hello world. Second part."


def test_compose_skips_blank_source_text():
    layer, _ = make_layer()

    result = layer._compose([("A", "  "), ("B", "Real content.")])

    assert result == "Real content."


def test_compose_truncates_to_max_explanation_sentences():
    reasoning_config = ReasoningConfig(max_explanation_sentences=2)
    layer, _ = make_layer(reasoning_config=reasoning_config)

    result = layer._compose([("A", "One."), ("B", "Two."), ("C", "Three.")])

    assert result == "One. Two."
