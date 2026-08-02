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

Sprint 5.4 (Persona Behavioral Adaptation) adds a second, independent
optional input: emotional_state. It lets the user's emotional state
(Sprint 5.2's EmotionalState) influence *tone selection within the
existing template*, never new template text and never a fact the reply
conveys — "Presentation never changes intelligence" is a literal design
constraint here, not just a description. A concrete implementation
(JarvisPersona/MiniePersona, Sprint 2.9/2.10) selects a ToneVariant from
emotional_state and picks among a small, fixed set of already-existing
phrasing templates accordingly; it never inserts a first-person claim
about JARMINEI's own feelings, and never states the user's estimated
emotional label back to them as a flat assertion. emotional_state is
typed | None, defaulting to None, for the identical reason
decision_trace is: there is exactly one real caller
(PersonaManager.compose_reply_safely()), and it has no EmotionalState to
pass until Sprint 5.14 wires one in.
"""

from abc import ABC, abstractmethod
from enum import Enum

from decision.authority import DecisionTrace
from emotion.state_manager import EmotionalState
from voice.context_manager import ConversationContext


class ToneVariant(Enum):
    """Which of a persona's own already-existing phrasing templates to
    use for a given reply (Sprint 5.4) — selected from an EmotionalState
    reading, never generated fresh. Shared across every concrete Persona
    so PersonaManager/tests can reason about tone selection without
    depending on a specific persona's own private variant set.

    NEUTRAL     - the default; identical to every pre-Sprint-5.4 reply.
    CONCISE     - shorter phrasing, selected when stress reads high.
    ENCOURAGING - warmer phrasing, selected when mood/comfort reads low.
    """

    NEUTRAL = "neutral"
    CONCISE = "concise"
    ENCOURAGING = "encouraging"


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
        self,
        transcript: str,
        context: ConversationContext,
        decision_trace: DecisionTrace | None,
        emotional_state: EmotionalState | None = None,
    ) -> str:
        """Return a reply to a transcribed utterance, informed by
        decision_trace when available and tonally adapted by
        emotional_state when available (Sprint 5.4 — adaptation only,
        never a new fact or a new sentence structure an LLM would have
        to produce). Must never raise for any input, including an empty
        transcript, decision_trace=None, or emotional_state=None (Fail
        Gracefully — a persona reply failure must not break a live
        conversation turn)."""

    @abstractmethod
    def describe(self) -> str:
        """Short identity string suitable for direct display in Debug
        Console / Status Panel (Sprint 1.9), without further formatting."""
