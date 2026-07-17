"""Persona — the shared identity-and-voice-binding contract every concrete
persona (JarvisPersona, Sprint 2.10's MiniePersona) implements.

Per 01_Project_Vision.md, JARMINEI is "one intelligence that expresses
itself through two personas" — a Persona in this architecture is an
identity and voice binding, not a separate reasoning system. Real language
understanding and response generation belong to the Decision Engine
(Level 3, Phase 3.3, Sprint 3.7+), which does not exist yet and is
explicitly out of Level 2's scope.

compose_reply() in every Level 2 persona is therefore a DELIBERATELY
MINIMAL PLACEHOLDER: a short, templated acknowledgement, never a
fabricated "smart" response that could be mistaken for real reasoning. It
exists solely so the Communication Pipeline (Sprint 2.12) has something
real to speak through Text-to-Speech end-to-end — see
docs/sprint_book/sprint_2_9.md's Engineering Rationale. Sprint 3.7 (Intent
Detection) / the Decision Engine will replace this placeholder with real
generated output; this interface itself is not expected to change beyond
the anticipated (not yet added) extra parameter flagged in that sprint's
Risks.
"""

from abc import ABC, abstractmethod

from voice.context_manager import ConversationContext


class Persona(ABC):
    """The interface PersonaManager (Sprint 2.11) and VoiceSessionManager/
    CommunicationPipeline (Sprint 2.12) depend on — neither ever
    references a concrete persona type directly."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def voice_id(self) -> str: ...

    @abstractmethod
    def compose_reply(self, transcript: str, context: ConversationContext) -> str:
        """Return a reply to a transcribed utterance. Must never raise for
        any input, including an empty transcript (Fail Gracefully — a
        persona reply failure must not break a live conversation turn)."""

    @abstractmethod
    def describe(self) -> str:
        """Short identity string suitable for direct display in Debug
        Console / Status Panel (Sprint 1.9), without further formatting."""
