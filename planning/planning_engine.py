"""Planning Engine — Level 6 Part A's Goal -> Milestone -> Task
decomposition layer. See docs/sprint_book/sprint_6/sprint_6_1.md.

Reuses decision/llm_client.py's existing LanguageModelClient Protocol/
OllamaClient rather than adding a second LLM integration — the same "one
LLM integration, many callers" precedent internet/summarizer.py,
internet/research_engine.py, and decision/response_generator.py already
established.

decompose_goal() produces a PROPOSED-only Goal and does nothing else: it
never persists (Sprint 6.2's TaskGraphStore), never dispatches a single
Action, and is never treated as accepted by anything in this module —
Level 6's own "Plan Before Executing" design principle applied to the
first sprint that could plausibly violate it.

Like ResponseGenerator (0.4.2), decompose_goal() raises LlmError on
failure rather than degrading to a safe default of its own — unlike
IntentDetector/ContextAnalyzer, this class has no safe fallback Goal
that belongs to it; the caller (Sprint 6.13) decides the user-facing
fallback, matching ResponseGenerator's own established call-site-owns-
the-fallback precedent.

Stop sequence: deliberately NOT stop=["\\n\\n"], despite the sprint
file's own Data Flow diagram showing that literal value. IntentDetector/
ContextAnalyzer's own "\\n\\n" stop sequence exists because their prompts
request a short, FIXED number of lines with no legitimate blank line
inside the real answer (0.4.3's own measured latency fix). A goal
decomposition is the opposite shape — a variable, potentially many-line
structured block (several milestones, each with several tasks) that a
real model is likely to visually separate with blank lines for
readability, which a "\\n\\n" stop sequence would truncate after the
first milestone, silently breaking multi-milestone decomposition. This
generation is structurally closer to ResponseGenerator's/Summarizer's
own free-form, longer output — both of which deliberately pass no stop
sequence at all (0.4.3's own established precedent, "a blank-line stop
would risk real truncation") — so decompose_goal() follows that
precedent instead, not the shorter-answer one.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from config.schema import ModelConfig, PlanningConfig
from core.logging_setup import get_logger
from decision.llm_client import LanguageModelClient, LlmError
from planning.planning_model import Goal, Milestone, Task

logger = get_logger(__name__)

_MILESTONE_PATTERN = re.compile(r"^MILESTONE:\s*(.+)$", re.IGNORECASE)
_TASK_PATTERN = re.compile(r"^TASK:\s*(.+)$", re.IGNORECASE)
_BLANK_EFFORT_VALUES = frozenset({"", "NONE", "UNKNOWN"})


class PlanningEngine:
    """Constructor DI: (llm_client, model_config, planning_config).
    model_config is accepted for constructor-shape consistency with
    every other LanguageModelClient caller in this codebase (all of
    which take ModelConfig), even though this class's own real per-call
    timeout comes from planning_config.decomposition_timeout_seconds
    instead of model_config.ollama_timeout_seconds — a deliberate,
    dedicated (and longer) timeout for this sprint's own larger
    generation, see config/schema.py's PlanningConfig docstring. Not a
    ManagedModule — no lifecycle of its own, matching
    internet/summarizer.py's/decision/response_generator.py's identical
    "wraps an LLM call, nothing to start/stop" shape."""

    def __init__(
        self,
        llm_client: LanguageModelClient,
        model_config: ModelConfig,
        planning_config: PlanningConfig,
    ) -> None:
        self._llm_client = llm_client
        self._model_config = model_config
        self._planning_config = planning_config

    def decompose_goal(self, statement: str) -> Goal:
        """Raises LlmError on an unreachable model or a response that
        fails to parse into at least one milestone with at least one
        task — never fabricates a plausible-looking but wrong Goal."""
        prompt = _build_prompt(statement)
        response = self._llm_client.generate(
            prompt, self._planning_config.decomposition_timeout_seconds
        )
        milestones = _parse_decomposition(response, self._planning_config)
        return Goal(
            goal_id=str(uuid.uuid4()),
            statement=statement,
            milestones=milestones,
            created_at=datetime.now(UTC),
        )


def _build_prompt(statement: str) -> str:
    return (
        "You are a planning assistant. Break the goal below into a small number of "
        "milestones, each with one or more concrete tasks.\n\n"
        f'Goal: "{statement}"\n\n'
        "Respond with only MILESTONE and TASK lines, one per line, in exactly this "
        "format and nothing else — no blank lines, no numbering, no extra commentary:\n"
        "MILESTONE: <a short milestone title>\n"
        "TASK: <a short task title> | <a one-sentence description> | <a rough effort "
        'estimate such as "15 minutes", or NONE if you cannot estimate>\n\n'
        "List every task for a milestone directly after that milestone's own MILESTONE "
        "line, before the next MILESTONE line."
    )


def _parse_decomposition(raw_text: str, planning_config: PlanningConfig) -> list[Milestone]:
    """The regex/section-split parser, isolated for direct unit testing
    against a fixed corpus of realistic (and deliberately malformed)
    model outputs — decompose_goal() itself never re-implements any of
    this logic. Truncates to planning_config's own bounds with a single
    logged warning per bound exceeded (not per discarded item); raises
    LlmError (never a new exception type, per this sprint's own single-
    failure-mode contract) when nothing usable was found."""
    milestones: list[Milestone] = []
    active_milestone: Milestone | None = None
    discarding_milestone = False
    truncated_milestones = False
    truncated_tasks = False

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        milestone_match = _MILESTONE_PATTERN.match(line)
        if milestone_match:
            if len(milestones) >= planning_config.max_milestones_per_goal:
                discarding_milestone = True
                truncated_milestones = True
                active_milestone = None
                continue
            discarding_milestone = False
            active_milestone = Milestone(
                milestone_id=str(uuid.uuid4()),
                title=milestone_match.group(1).strip(),
                tasks=[],
            )
            milestones.append(active_milestone)
            continue

        if discarding_milestone or active_milestone is None:
            continue

        task_match = _TASK_PATTERN.match(line)
        if not task_match:
            continue
        if len(active_milestone.tasks) >= planning_config.max_tasks_per_milestone:
            truncated_tasks = True
            continue
        active_milestone.tasks.append(_parse_task_line(task_match.group(1)))

    if truncated_milestones:
        logger.warning(
            "Goal decomposition produced more than %d milestones; truncated.",
            planning_config.max_milestones_per_goal,
        )
    if truncated_tasks:
        logger.warning(
            "A milestone in the goal decomposition produced more than %d tasks; truncated.",
            planning_config.max_tasks_per_milestone,
        )

    non_empty_milestones = [m for m in milestones if m.tasks]
    if not non_empty_milestones:
        raise LlmError(
            "Goal decomposition response did not parse into any milestone with at least "
            "one task."
        )
    return non_empty_milestones


def _parse_task_line(raw: str) -> Task:
    parts = [part.strip() for part in raw.split("|")]
    title = parts[0] if parts and parts[0] else "(untitled task)"
    description = parts[1] if len(parts) > 1 else ""
    effort: str | None = parts[2] if len(parts) > 2 else None
    if effort is not None and effort.upper() in _BLANK_EFFORT_VALUES:
        effort = None
    return Task(
        task_id=str(uuid.uuid4()),
        title=title,
        description=description,
        estimated_effort=effort,
    )
