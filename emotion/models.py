"""Emotion Detection Engine data shapes (Sprint 5.1 — Level 5 Part A).

EmotionLabel/EmotionEstimate are **behavioral estimates derived from
voice/text signals, never a medical or psychological diagnosis** — the
brief's own locked rule for this Level ("The AI never pretends to possess
human emotions. Behavioral estimation only. No medical diagnosis.").
Nothing in this module (or emotion/detection_engine.py) may grow a field
resembling a clinical severity score; if a future sprint needs one, that
is a real, separate product decision requiring explicit review, the same
discipline decision/authority.py's approved_emergency_procedures already
established for a different high-consequence content decision.

See docs/sprint_book/sprint_5_1.md.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from decision.context_analyzer import SentimentHint


class EmotionLabel(Enum):
    """Nine named behavioral states plus UNKNOWN, the universal
    safe-failure default (mirrors decision/models.py's own
    IntentCategory.UNKNOWN precedent) — every degrade path in
    EmotionDetectionEngine resolves here, never a guessed label."""

    HAPPY = "happy"
    CALM = "calm"
    STRESSED = "stressed"
    TIRED = "tired"
    EXCITED = "excited"
    FRUSTRATED = "frustrated"
    CONFUSED = "confused"
    CURIOUS = "curious"
    FOCUSED = "focused"
    UNKNOWN = "unknown"


@dataclass
class EmotionSignals:
    """Raw, per-turn behavioral signals collected before any inference —
    EmotionDetectionEngine.collect_signals()'s own output.

    speaking_rate_wpm is None whenever it can't be honestly computed
    (zero/unavailable transcription duration or empty text) — never a
    divide-by-zero guess. pause_before_turn_seconds is 0.0 for a
    session's first turn (nothing to compare against), never a negative
    value. sentiment_hint is decision/context_analyzer.py's own
    SentimentHint (Sprint 3.8), reused directly rather than duplicated —
    SentimentHint.NEUTRAL when no ContextAnalysis is available.
    matched_lexical_markers may contain the same EmotionLabel more than
    once (one entry per matching keyword) — a deliberate signal of
    support strength, not deduplicated here.
    """

    speaking_rate_wpm: float | None
    pause_before_turn_seconds: float
    sentiment_hint: SentimentHint
    matched_lexical_markers: list[EmotionLabel]
    no_speech_probability: float
    collected_at: datetime


@dataclass
class EmotionEstimate:
    """Result of estimating one turn's behavioral emotional state.

    confidence is this engine's own self-reported certainty (0.0-1.0) —
    unrelated to Level 3's Dynamic Memory confidence score, the same
    distinction Intent.confidence's own docstring already draws against
    a different, similarly-named score. signals is always carried along
    (Explainability Rule: an estimate always ships its own evidence).
    """

    label: EmotionLabel
    confidence: float
    signals: EmotionSignals
    estimated_at: datetime
