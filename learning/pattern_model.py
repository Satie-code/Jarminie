"""Pattern Recognition — the Learning Engine's data model. See
docs/sprint_book/sprint_5/sprint_5_21.md.

LearnedPattern.confidence is capped at 1.0 regardless of how far evidence
exceeds pattern_min_occurrences — more data past the threshold should
read as "still confident," never as a runaway, unbounded score. See
pattern_recognizer.py's own module docstring for why every LearnedPattern
this codebase produces comes from small, explainable arithmetic over
real stored data, never a trained model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class PatternType(Enum):
    """The three detection categories Sprint 5.21 built, plus
    CONVERSATION_STYLE (Sprint 5.23 — Preference Learning &
    Recommendations, learning/preference_learner.py's PreferenceLearner),
    plus four more (Sprint 6.7 — Learning Engine v2, Level 6 Part A):
    PREFERRED_WORKFLOW/PREFERRED_TOOL/DAILY_ROUTINE/STUDY_SCHEDULE, all
    four detected by learning/pattern_recognizer.py's own PatternRecognizer
    (unlike CONVERSATION_STYLE, which stays PreferenceLearner's alone).
    Part 2's own "Common workflows" is now realized as PREFERRED_WORKFLOW."""

    PREFERRED_TIME = "preferred_time"
    FREQUENT_APPLICATION = "frequent_application"
    WORK_HABIT = "work_habit"
    CONVERSATION_STYLE = "conversation_style"
    PREFERRED_WORKFLOW = "preferred_workflow"
    PREFERRED_TOOL = "preferred_tool"
    DAILY_ROUTINE = "daily_routine"
    STUDY_SCHEDULE = "study_schedule"


@dataclass
class LearnedPattern:
    """A single detected, persisted pattern. Identity for PatternStore.
    upsert() purposes is (pattern_type, subject) — pattern_id is
    generated on construction (UUID4) unless supplied, matching this
    codebase's own established id-field precedent, but is only ever
    actually PERSISTED for a genuinely new (pattern_type, subject) pair;
    an upsert against an existing pair keeps the database's own original
    pattern_id/first_observed_at (see pattern_store.py's own docstring).

    description is a plain, human-readable sentence (e.g. "Frequently
    active between 14:00 and 16:00") — the Explainability Rule's own
    deliverable applied here, matching decision/authority.py's
    DecisionTrace.reasoning_text precedent.
    """

    pattern_type: PatternType
    description: str
    subject: str
    confidence: float
    evidence_count: int
    first_observed_at: datetime
    last_updated_at: datetime
    pattern_id: str = field(default_factory=lambda: str(uuid4()))
