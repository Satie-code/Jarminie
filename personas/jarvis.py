"""JarvisPersona — JARMINEI's professional, logical, productivity-focused
identity ("Jarvis — The logical, professional, productivity-focused system
brain.", 01_Project_Vision.md). See personas/base.py for the shared
Persona contract.

compose_reply() (Sprint 3.12) draws on decision_trace when available:
the top retrieved memory's content (if any), and a tone matching
authority_level (a recommendation is framed differently from a plain
acknowledgement). Falls back to the exact Level 2 templated
acknowledgement when decision_trace is None (Decision Engine pipeline
unavailable) — see docs/sprint_book/sprint_3_12.md's Engineering
Decisions for why this composition stays template-based rather than a
new LLM call of its own.
"""

from config.schema import VoiceConfig
from decision.authority import AuthorityLevel, DecisionTrace
from personas.base import Persona
from voice.context_manager import ConversationContext

_ACKNOWLEDGEMENT_TEMPLATE = 'Understood. You said: "{transcript}".'
_EMPTY_TRANSCRIPT_REPLY = "I didn't catch anything that time. Could you repeat that?"
_RECOMMEND_PREFIX = "Here's my recommendation: "
_EMERGENCY_ASSIST_PREFIX = "I'm authorized to assist directly: "


class JarvisPersona(Persona):
    """Constructor DI per 03_Engineering_Standards.md: receives the
    VoiceConfig it reads jarvis_voice_id from, rather than hardcoding a
    speaker ID."""

    def __init__(self, voice_config: VoiceConfig) -> None:
        self._voice_config = voice_config

    @property
    def name(self) -> str:
        return "jarvis"

    @property
    def voice_id(self) -> str:
        return self._voice_config.jarvis_voice_id

    def compose_reply(
        self, transcript: str, context: ConversationContext, decision_trace: DecisionTrace | None
    ) -> str:
        """A short, professional-toned acknowledgement, augmented with
        decision_trace's retrieved memories/authority level when
        available. No external model call — see this module's own
        docstring."""
        stripped = transcript.strip()
        if not stripped:
            return _EMPTY_TRANSCRIPT_REPLY

        base = _ACKNOWLEDGEMENT_TEMPLATE.format(transcript=stripped)
        if decision_trace is None:
            return base

        memory_clause = ""
        if decision_trace.retrieved_memories:
            top_memory = decision_trace.retrieved_memories[0]
            memory_clause = f" I recall: {top_memory.record.content}."

        if decision_trace.authority_level is AuthorityLevel.EMERGENCY_ASSIST:
            return f"{_EMERGENCY_ASSIST_PREFIX}{base}{memory_clause}"
        if decision_trace.authority_level is AuthorityLevel.RECOMMEND:
            return f"{_RECOMMEND_PREFIX}{base}{memory_clause}"
        return f"{base}{memory_clause}"

    def describe(self) -> str:
        return "Jarvis — professional execution persona"
