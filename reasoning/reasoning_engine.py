"""Reasoning Engine — Level 6 Part A's dedicated place to reason *about*
a plan, a decision, or a situation (Why?, What if?, Alternatives,
Trade-offs, Confidence estimation) rather than classify it (Level 3's
job) or decompose it (planning/planning_engine.py's job). See
docs/sprint_book/sprint_6/sprint_6_4.md.

Reuses decision/llm_client.py's existing LanguageModelClient Protocol/
OllamaClient rather than adding a second LLM integration — the fourth
caller of that Protocol (after IntentDetector, ContextAnalyzer,
ResponseGenerator/Summarizer), the same "one LLM integration, many
callers" precedent planning/planning_engine.py's own PlanningEngine
already established for Level 6 Part A.

Every method is a pure input->output call — no state, no memory of
prior reasoning calls within the class itself (a caller wanting
continuity re-supplies context each time via working_context/subject).
This mirrors internet/summarizer.py's/decision/response_generator.py's
own stateless-per-call shape exactly. Not a ManagedModule, matching
PlanningEngine's identical shape — nothing here has a lifecycle to
start/stop.

**Three different confidence scales in this codebase, deliberately kept
distinct, never to be compared directly without an explicit
conversion**: memory/confidence_scorer.py's ConfidenceScorer produces a
0-100 band derived from memory-record data; learning/pattern_recognizer.py's
own _confidence() produces an evidence-count-based float for detected
patterns; ReasoningTrace.confidence (this module) is a THIRD, LLM-
elicited source — the model's own stated certainty about a reasoning
conclusion — scaled 0.0-1.0 specifically to be visually and
programmatically distinct from ConfidenceScorer's 0-100. LLM-elicited
confidence is not a calibrated probability: a model stating "I am 90%
confident" carries no guarantee of matching real-world accuracy 90% of
the time — an advisory signal for Sprint 6.5/6.11, never a hard gate.

alternatives()/estimate_confidence() each need real, structured parsing
of the model's own response — isolated into module-level functions
mirroring planning/planning_engine.py's own _parse_decomposition()/
_parse_task_line() shape, tested only through the public method
contract (this codebase's own established convention, never importing
an underscore-prefixed parser by name — see test_planning_engine.py's
own docstring for the precedent this follows).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from config.schema import ModelConfig, ReasoningConfig
from context.context_model import WorkingContext
from core.logging_setup import get_logger
from decision.llm_client import LanguageModelClient
from reasoning.reasoning_model import Alternative, QuestionType, ReasoningTrace

logger = get_logger(__name__)

_CONCLUSION_PATTERN = re.compile(r"^CONCLUSION:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_ALTERNATIVE_PATTERN = re.compile(r"^ALTERNATIVE:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_CONFIDENCE_PATTERN = re.compile(r"^CONFIDENCE:\s*([-+]?\d*\.?\d+)", re.IGNORECASE | re.MULTILINE)

_DEFAULT_CONFIDENCE_ON_PARSE_FAILURE = 0.5


class ReasoningEngine:
    """Constructor DI: (llm_client, model_config, reasoning_config).
    model_config is accepted for constructor-shape consistency with
    every other LanguageModelClient caller in this codebase (all of
    which take ModelConfig), even though the real per-call timeout comes
    from reasoning_config.reasoning_timeout_seconds instead — the
    identical "dedicated, longer timeout for a larger generation"
    precedent PlanningEngine's own constructor docstring already
    established."""

    def __init__(
        self,
        llm_client: LanguageModelClient,
        model_config: ModelConfig,
        reasoning_config: ReasoningConfig,
    ) -> None:
        self._llm_client = llm_client
        self._model_config = model_config
        self._reasoning_config = reasoning_config

    def explain_why(
        self, subject: str, working_context: WorkingContext | None = None
    ) -> ReasoningTrace:
        """"Why does/should X happen" — the general-purpose reasoning
        call. Raises LlmError if llm_client.generate() does."""
        return self._reason("why", subject, working_context)

    def what_if(
        self, scenario: str, working_context: WorkingContext | None = None
    ) -> ReasoningTrace:
        """A hypothetical ("what happens if I skip this task / miss this
        deadline / do X instead of Y"). Raises LlmError if
        llm_client.generate() does."""
        return self._reason("what_if", scenario, working_context)

    def alternatives(
        self, subject: str, working_context: WorkingContext | None = None
    ) -> ReasoningTrace:
        """Populates ReasoningTrace.alternatives, bounded by
        reasoning_config.max_alternatives. Raises LlmError if
        llm_client.generate() does."""
        return self._reason("alternatives", subject, working_context)

    def estimate_confidence(
        self, subject: str, working_context: WorkingContext | None = None
    ) -> ReasoningTrace:
        """Asks the model to state its own confidence in a conclusion
        about subject, parsed into the 0.0-1.0 confidence field. A
        response the parser cannot extract a numeric confidence from
        defaults to 0.5 (an honest "uncertain," never fabricated false
        precision) with a logged warning, rather than raising —
        confidence estimation is explicitly advisory input to Sprint
        6.5, not a hard gate. Raises LlmError only if llm_client.
        generate() itself does."""
        return self._reason("confidence", subject, working_context)

    def _reason(
        self,
        question_type: QuestionType,
        subject: str,
        working_context: WorkingContext | None,
    ) -> ReasoningTrace:
        prompt = self._build_prompt(question_type, subject, working_context)
        response = self._llm_client.generate(
            prompt, self._reasoning_config.reasoning_timeout_seconds
        )
        conclusion = _extract_conclusion(response)
        alternatives_list: list[Alternative] = []
        # 1.0 is a fixed, disclosed placeholder for the three question
        # types that never ask the model to self-assess at all — see
        # reasoning_model.py's own ReasoningTrace.confidence docstring
        # for why this is not float | None instead.
        confidence = 1.0
        if question_type == "alternatives":
            alternatives_list = _parse_alternatives(response, self._reasoning_config)
        elif question_type == "confidence":
            confidence = _parse_confidence(response)
        return ReasoningTrace(
            subject=subject,
            question_type=question_type,
            conclusion=conclusion,
            confidence=confidence,
            reasoned_at=datetime.now(UTC),
            alternatives=alternatives_list,
        )

    def _build_prompt(
        self,
        question_type: QuestionType,
        subject: str,
        working_context: WorkingContext | None,
    ) -> str:
        """One shared prompt-builder, parameterized per question type,
        isolated for direct testing — mirrors decision/response_generator.py's
        own established shared-prompt-builder shape."""
        context_block = _build_context_block(working_context)
        instruction = _INSTRUCTIONS[question_type](subject, self._reasoning_config)
        return (
            "You are JARMINEI's reasoning engine — you reason about an already-stated "
            "plan, decision, or situation; you never invent new facts you don't actually "
            "know.\n\n"
            f"{context_block}"
            f"{instruction}"
        )


def _why_instruction(subject: str, _reasoning_config: ReasoningConfig) -> str:
    return (
        f'Explain clearly why this is or should be the case: "{subject}"\n\n'
        "Respond with exactly this format and nothing else:\n"
        "CONCLUSION: <your explanation, 1-3 sentences>"
    )


def _what_if_instruction(scenario: str, _reasoning_config: ReasoningConfig) -> str:
    return (
        f'Consider this hypothetical scenario and explain the likely outcome: "{scenario}"\n\n'
        "Respond with exactly this format and nothing else:\n"
        "CONCLUSION: <the likely outcome, 1-3 sentences>"
    )


def _alternatives_instruction(subject: str, reasoning_config: ReasoningConfig) -> str:
    return (
        f'Propose up to {reasoning_config.max_alternatives} real alternatives to this: '
        f'"{subject}"\n\n'
        "Respond with exactly this format, one alternative per line, and nothing else:\n"
        "CONCLUSION: <a one-sentence summary>\n"
        "ALTERNATIVE: <a short alternative description> | <a short trade-off phrase>\n"
        f"(one ALTERNATIVE line per alternative, up to {reasoning_config.max_alternatives})"
    )


def _confidence_instruction(subject: str, _reasoning_config: ReasoningConfig) -> str:
    return (
        f'State your own conclusion about this, and how confident you are in it: "{subject}"\n\n'
        "Respond with exactly this format and nothing else:\n"
        "CONCLUSION: <your conclusion, 1-2 sentences>\n"
        "CONFIDENCE: <a number between 0.0 and 1.0 representing how confident you are>"
    )


_INSTRUCTIONS = {
    "why": _why_instruction,
    "what_if": _what_if_instruction,
    "alternatives": _alternatives_instruction,
    "confidence": _confidence_instruction,
}


def _build_context_block(working_context: WorkingContext | None) -> str:
    """A soft, optional grounding summary — every ReasoningEngine method
    accepts working_context=None and still produces a real answer, so
    this returns "" rather than raising/guessing when it's absent."""
    if working_context is None:
        return ""
    lines: list[str] = []
    if working_context.conversation is not None and working_context.conversation.recent_turns:
        lines.append(f"- {len(working_context.conversation.recent_turns)} recent turn(s)")
    if working_context.recent_memories:
        lines.append(f"- {len(working_context.recent_memories)} relevant remembered fact(s)")
    if working_context.upcoming_scheduled_items:
        lines.append(
            f"- {len(working_context.upcoming_scheduled_items)} upcoming scheduled item(s)"
        )
    if working_context.recent_applications:
        lines.append(f"- {len(working_context.recent_applications)} recently-used application(s)")
    if not lines:
        return ""
    return "Current context:\n" + "\n".join(lines) + "\n\n"


def _extract_conclusion(raw_text: str) -> str:
    """Prefers the labeled CONCLUSION: line; falls back to the whole
    stripped response when the model didn't follow the requested format
    — never an empty conclusion for a genuinely non-empty response, the
    same "degrade gracefully, don't discard a real answer over a
    formatting slip" discipline _parse_task_line() (planning/
    planning_engine.py) already established."""
    match = _CONCLUSION_PATTERN.search(raw_text)
    if match:
        return match.group(1).strip()
    return raw_text.strip()


def _parse_alternatives(raw_text: str, reasoning_config: ReasoningConfig) -> list[Alternative]:
    """Truncates to reasoning_config.max_alternatives with a single
    logged warning (not per discarded item) — mirrors planning/
    planning_engine.py's _parse_decomposition() truncation discipline
    exactly."""
    matches = _ALTERNATIVE_PATTERN.findall(raw_text)
    truncated = len(matches) > reasoning_config.max_alternatives
    alternatives = [
        _parse_alternative_line(line) for line in matches[: reasoning_config.max_alternatives]
    ]
    if truncated:
        logger.warning(
            "Alternatives response produced more than %d alternatives; truncated.",
            reasoning_config.max_alternatives,
        )
    return alternatives


def _parse_alternative_line(raw: str) -> Alternative:
    parts = [part.strip() for part in raw.split("|", maxsplit=1)]
    description = parts[0] if parts and parts[0] else "(unspecified alternative)"
    estimated_trade_off = parts[1] if len(parts) > 1 else ""
    return Alternative(description=description, estimated_trade_off=estimated_trade_off)


def _parse_confidence(raw_text: str) -> float:
    """Extracts the CONFIDENCE: line's own number and clamps it to
    [0.0, 1.0] — an out-of-range value is clamped, not rejected. A
    response with no parseable CONFIDENCE: number at all defaults to
    0.5 (an honest "uncertain"), logged once, never raised."""
    match = _CONFIDENCE_PATTERN.search(raw_text)
    if not match:
        logger.warning(
            "Could not parse a numeric confidence from the reasoning response; "
            "defaulting to %.1f.",
            _DEFAULT_CONFIDENCE_ON_PARSE_FAILURE,
        )
        return _DEFAULT_CONFIDENCE_ON_PARSE_FAILURE
    value = float(match.group(1))
    return max(0.0, min(1.0, value))
