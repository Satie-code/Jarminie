"""Persona — the shared identity-and-voice-binding contract every concrete
persona (JarvisPersona, Sprint 2.10's MiniePersona) implements.

Per 01_Project_Vision.md, JARMINEI is "one intelligence that expresses
itself through two personas" — a Persona in this architecture is an
identity and voice binding, not a separate reasoning system. Real
language understanding lives in the Decision Engine (Level 3, Phase
3.3, Sprints 3.7-3.11): Intent Detection, Context Analysis, Memory
Retrieval, Priority Evaluation, and Authority Evaluation all happen
before compose_reply() is ever called, and their combined result — a
DecisionTrace (decision/authority.py) — is what compose_reply() now
receives and draws on.

compose_reply() is still template-based, not a new LLM call of its own
(Sprint 3.12's Architecture Notes: "there is no separate Level 3
'Execution Engine' to build... compose_reply() IS the pipeline's
Response Generation stage at Level 3") — but it is no longer a
context-blind acknowledgement. It now weaves in decision_trace's
retrieved memories and authority level, so its output measurably
differs from Level 2's templated placeholder whenever real decision
input is available. decision_trace is typed | None because the Decision
Engine pipeline can itself fail (Sprint 3.13 hardens this case) —
compose_reply() must still produce something reasonable with no trace
at all (Fail Gracefully).
"""

from abc import ABC, abstractmethod

from decision.authority import DecisionTrace
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
    def compose_reply(
        self, transcript: str, context: ConversationContext, decision_trace: DecisionTrace | None
    ) -> str:
        """Return a reply to a transcribed utterance, informed by
        decision_trace when available. Must never raise for any input,
        including an empty transcript or decision_trace=None (Fail
        Gracefully — a persona reply failure must not break a live
        conversation turn)."""

    @abstractmethod
    def describe(self) -> str:
        """Short identity string suitable for direct display in Debug
        Console / Status Panel (Sprint 1.9), without further formatting."""
