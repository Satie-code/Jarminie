"""MiniePersona — JARMINEI's calm, caring, conversational companion
identity ("Minie — The calm, caring, conversational companion persona.",
01_Project_Vision.md). See personas/base.py for the shared Persona
contract and the Level 2 placeholder-reply caveat this class's
compose_reply() is subject to.

Minie's finished-product responsibilities include wellness reminders,
hydration, and break reminders — but the Wellness Engine itself is Level 5
(Phase 5.2), and emotional inference is Level 5's Emotion Engine (Phase
5.1), both explicitly out of scope here. This sprint gives Minie an
identity and voice with the same placeholder compose_reply() pattern as
JarvisPersona (Sprint 2.9) — nothing wellness- or emotion-specific yet.
"""

from config.schema import VoiceConfig
from personas.base import Persona
from voice.context_manager import ConversationContext

_ACKNOWLEDGEMENT_TEMPLATE = (
    'Got it — you said: "{transcript}". I\'m here if you need anything else.'
)
_EMPTY_TRANSCRIPT_REPLY = "Hmm, I didn't quite catch that. Mind saying it again?"


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

    def compose_reply(self, transcript: str, context: ConversationContext) -> str:
        """Level 2 placeholder: a short, warm/caring-toned acknowledgement
        of what was heard. No external model call, no wellness logic, no
        emotional inference — see personas/base.py and this module's own
        docstring."""
        stripped = transcript.strip()
        if not stripped:
            return _EMPTY_TRANSCRIPT_REPLY
        return _ACKNOWLEDGEMENT_TEMPLATE.format(transcript=stripped)

    def describe(self) -> str:
        return "Minie — companion persona"
