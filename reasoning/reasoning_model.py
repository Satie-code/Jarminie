"""Reasoning Engine data model — the structured output every
ReasoningEngine call produces. See docs/sprint_book/sprint_6/sprint_6_4.md.

confidence is scaled 0.0-1.0, deliberately distinct from
memory/confidence_scorer.py's ConfidenceScorer (a 0-100 band derived from
memory-record data) and learning/pattern_recognizer.py's own evidence-
count-based confidence float — this is a third, LLM-elicited confidence
source (the model's own stated certainty), never to be compared directly
against either of the other two without an explicit conversion. See
reasoning/reasoning_engine.py's own docstring for the full rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

QuestionType = Literal["why", "what_if", "alternatives", "confidence"]


@dataclass
class Alternative:
    """A single alternative surfaced by ReasoningEngine.alternatives() —
    deliberately a short human phrase, not a structured multi-field
    trade-off model; no basis in the brief's own text for anything
    richer."""

    description: str
    estimated_trade_off: str


@dataclass
class ReasoningTrace:
    """subject is what was reasoned about — a Goal.statement, a
    Task.title, or a free-form decision description, preserved verbatim
    (the Human First Rule applied to reasoning, mirroring Goal.statement's
    own identical precedent, planning/planning_model.py). alternatives is
    empty except for alternatives() calls.

    confidence is a real, model-elicited value only for
    ReasoningEngine.estimate_confidence() calls — the only one of the
    four reasoning shapes that actually asks the model to self-assess.
    explain_why()/what_if()/alternatives() never elicit a confidence
    value at all, so they set this field to 1.0 (a fixed, disclosed
    placeholder, never a fabricated self-assessment the model was never
    asked for) rather than widening the field to float | None, which
    would ripple an optionality check into every future caller for a
    distinction confidence's own 0.0-1.0 scale can express honestly on
    its own — see reasoning/reasoning_engine.py's own docstring for the
    full rationale."""

    subject: str
    question_type: QuestionType
    conclusion: str
    confidence: float
    reasoned_at: datetime
    alternatives: list[Alternative] = field(default_factory=list)
