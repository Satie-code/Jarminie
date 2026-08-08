"""Unit tests for reasoning.reasoning_model."""

from datetime import UTC, datetime

from reasoning.reasoning_model import Alternative, ReasoningTrace


def test_alternative_carries_description_and_trade_off():
    alt = Alternative(description="Do it now", estimated_trade_off="Faster, but riskier")

    assert alt.description == "Do it now"
    assert alt.estimated_trade_off == "Faster, but riskier"


def test_reasoning_trace_defaults_alternatives_to_empty_list():
    trace = ReasoningTrace(
        subject="Learn to code",
        question_type="why",
        conclusion="Because it opens career opportunities.",
        confidence=1.0,
        reasoned_at=datetime.now(UTC),
    )

    assert trace.alternatives == []


def test_reasoning_trace_preserves_subject_verbatim():
    now = datetime.now(UTC)
    trace = ReasoningTrace(
        subject="  Skip the code review  ",
        question_type="what_if",
        conclusion="Bugs are more likely to reach production.",
        confidence=1.0,
        reasoned_at=now,
    )

    assert trace.subject == "  Skip the code review  "
    assert trace.reasoned_at == now


def test_reasoning_trace_can_carry_alternatives():
    alt = Alternative(description="Refactor incrementally", estimated_trade_off="Slower, safer")
    trace = ReasoningTrace(
        subject="Rewrite the module",
        question_type="alternatives",
        conclusion="Two viable alternatives exist.",
        confidence=1.0,
        reasoned_at=datetime.now(UTC),
        alternatives=[alt],
    )

    assert trace.alternatives == [alt]
