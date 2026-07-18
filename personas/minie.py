"""MiniePersona — JARMINEI's calm, caring, conversational companion
identity ("Minie — The calm, caring, conversational companion persona.",
01_Project_Vision.md). See personas/base.py for the shared Persona
contract.

Minie's finished-product responsibilities include wellness reminders,
hydration, and break reminders — but the Wellness Engine itself is Level 5
(Phase 5.2), and emotional inference is Level 5's Emotion Engine (Phase
5.1), both explicitly out of scope here.

compose_reply() (Sprint 3.12) draws on decision_trace when available,
the same real-input pattern as JarvisPersona but in Minie's own warmer
voice — no wellness- or emotion-specific logic yet. Falls back to the
exact Level 2 templated acknowledgement when decision_trace is None.
"""

from config.schema import VoiceConfig
from decision.authority import AuthorityLevel, DecisionTrace
from personas.base import Persona
from voice.context_manager import ConversationContext

_ACKNOWLEDGEMENT_TEMPLATE = (
    'Got it — you said: "{transcript}". I\'m here if you need anything else.'
)
_EMPTY_TRANSCRIPT_REPLY = "Hmm, I didn't quite catch that. Mind saying it again?"
_RECOMMEND_PREFIX = "Here's what I'd gently suggest: "
_EMERGENCY_ASSIST_PREFIX = "I can help with this directly: "


class MiniePersona(Persona):
    """Constructor DI per 03_Engineering_Standards.md: receives the
    VoiceConfig it reads minie_voice_id from, rather than hardcoding a
    speaker ID."""

    def __init__(self, voice_config: VoiceConfig) -> None:
        self._voice_config = voice_config

    @property
    def name(self) -> str:
        return "minie"

    @property
    def voice_id(self) -> str:
        return self._voice_config.minie_voice_id

    def compose_reply(
        self, transcript: str, context: ConversationContext, decision_trace: DecisionTrace | None
    ) -> str:
        """A short, warm/caring-toned acknowledgement, augmented with
        decision_trace's retrieved memories/authority level when
        available. No external model call, no wellness logic, no
        emotional inference — see this module's own docstring."""
        stripped = transcript.strip()
        if not stripped:
            return _EMPTY_TRANSCRIPT_REPLY

        base = _ACKNOWLEDGEMENT_TEMPLATE.format(transcript=stripped)
        if decision_trace is None:
            return base

        memory_clause = ""
        if decision_trace.retrieved_memories:
            top_memory = decision_trace.retrieved_memories[0]
            memory_clause = f" I remember: {top_memory.record.content}."

        if decision_trace.authority_level is AuthorityLevel.EMERGENCY_ASSIST:
            return f"{_EMERGENCY_ASSIST_PREFIX}{base}{memory_clause}"
        if decision_trace.authority_level is AuthorityLevel.RECOMMEND:
            return f"{_RECOMMEND_PREFIX}{base}{memory_clause}"
        return f"{base}{memory_clause}"

    def describe(self) -> str:
        return "Minie — companion persona"
