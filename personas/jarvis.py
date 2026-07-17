"""JarvisPersona — JARMINEI's professional, logical, productivity-focused
identity ("Jarvis — The logical, professional, productivity-focused system
brain.", 01_Project_Vision.md). See personas/base.py for the shared
Persona contract and the Level 2 placeholder-reply caveat this class's
compose_reply() is subject to.
"""

from config.schema import VoiceConfig
from personas.base import Persona
from voice.context_manager import ConversationContext

_ACKNOWLEDGEMENT_TEMPLATE = 'Understood. You said: "{transcript}".'
_EMPTY_TRANSCRIPT_REPLY = "I didn't catch anything that time. Could you repeat that?"


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

    def compose_reply(self, transcript: str, context: ConversationContext) -> str:
        """Level 2 placeholder: a short, professional-toned acknowledgement
        of what was heard. No external model call, no business logic
        beyond template formatting — see personas/base.py."""
        stripped = transcript.strip()
        if not stripped:
            return _EMPTY_TRANSCRIPT_REPLY
        return _ACKNOWLEDGEMENT_TEMPLATE.format(transcript=stripped)

    def describe(self) -> str:
        return "Jarvis — professional execution persona"
