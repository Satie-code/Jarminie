"""Decision Engine data shapes shared across its pipeline stages
(Intent Detection, Context Analysis, ...). See
02_System_Architecture.md's Decision Engine diagram.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class IntentCategory(Enum):
    """What the user is asking for, independent of which persona is
    active (persona routing is Sprint 3.8's suggested_persona output).

    UNKNOWN is the universal safe-failure value — every degrade path in
    IntentDetector resolves here, never to a guessed category."""

    INFORMATIONAL = "informational"
    ACTION_REQUEST = "action_request"
    MEMORY_RECALL = "memory_recall"
    EMOTIONAL_SUPPORT = "emotional_support"
    EMERGENCY = "emergency"
    CASUAL_CONVERSATION = "casual_conversation"
    UNKNOWN = "unknown"


@dataclass
class Intent:
    """Result of classifying one transcript. confidence is the model's
    own self-reported certainty (0.0-1.0), unrelated to Level 3's Dynamic
    Memory confidence score — must not be conflated with it, same
    distinction TranscriptionResult.average_confidence already draws
    against Whisper's decode confidence (voice/speech_to_text.py)."""

    category: IntentCategory
    confidence: float
    raw_transcript: str
    detected_at: datetime
