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
voice. Falls back to the exact Level 2 templated acknowledgement when
decision_trace is None.

Sprint 5.4 adds _select_tone_variant(): the same EmotionConfig-driven
EmotionalState selection JarvisPersona gained, but with thresholds
leaning toward ENCOURAGING more readily — Minie's own "casual, comfort,
wellness" identity (project_jarminei_architecture.md's Persona System
line) makes her the primary beneficiary of this sprint, not the only
participant. Still no wellness engine or emotional inference of its own
here — this sprint only ever *selects* among already-existing phrasing,
per personas/base.py's own ToneVariant docstring. Thresholds live in
EmotionConfig, not as hardcoded module constants — see personas/jarvis.py's
own docstring for the full "no hardcoded thresholds" reasoning.
"""

from config.schema import EmotionConfig, VoiceConfig
from decision.authority import AuthorityLevel, DecisionTrace
from emotion.state_manager import EmotionalState
from personas.base import Persona, ToneVariant
from voice.context_manager import ConversationContext

_ACKNOWLEDGEMENT_TEMPLATES: dict[ToneVariant, str] = {
    ToneVariant.NEUTRAL: 'Got it — you said: "{transcript}". I\'m here if you need anything else.',
    ToneVariant.CONCISE: 'Got it: "{transcript}". Let\'s keep this simple for now.',
    ToneVariant.ENCOURAGING: (
        'That sounds like a lot. You said: "{transcript}" — I\'m right here with you.'
    ),
}
_EMPTY_TRANSCRIPT_REPLY = "Hmm, I didn't quite catch that. Mind saying it again?"
_RECOMMEND_PREFIX = "Here's what I'd gently suggest: "
_EMERGENCY_ASSIST_PREFIX = "I can help with this directly: "


def _select_tone_variant(
    emotional_state: EmotionalState | None, config: EmotionConfig
) -> ToneVariant:
    """Module-private: Minie's own equivalent of JarvisPersona's
    _select_tone_variant() — same rule shape, warmer-leaning thresholds
    (EmotionConfig.minie_tone_low_mood_threshold/
    minie_tone_low_comfort_threshold). None (no read yet) always selects
    NEUTRAL."""
    if emotional_state is None:
        return ToneVariant.NEUTRAL
    if emotional_state.stress >= config.tone_high_stress_threshold:
        return ToneVariant.CONCISE
    if (
        emotional_state.mood <= config.minie_tone_low_mood_threshold
        or emotional_state.comfort <= config.minie_tone_low_comfort_threshold
    ):
        return ToneVariant.ENCOURAGING
    return ToneVariant.NEUTRAL


class MiniePersona(Persona):
    """Constructor DI per 03_Engineering_Standards.md: receives the
    VoiceConfig it reads minie_voice_id from, rather than hardcoding a
    speaker ID. emotion_config (Sprint 5.4) defaults to EmotionConfig()
    when not supplied — see JarvisPersona's own docstring for why."""

    def __init__(
        self, voice_config: VoiceConfig, emotion_config: EmotionConfig | None = None
    ) -> None:
        self._voice_config = voice_config
        self._emotion_config = emotion_config if emotion_config is not None else EmotionConfig()

    @property
    def name(self) -> str:
        return "minie"

    @property
    def voice_id(self) -> str:
        return self._voice_config.minie_voice_id

    def compose_reply(
        self,
        transcript: str,
        context: ConversationContext,
        decision_trace: DecisionTrace | None,
        emotional_state: EmotionalState | None = None,
    ) -> str:
        """A short, warm/caring-toned acknowledgement, augmented with
        decision_trace's retrieved memories/authority level when
        available, and tonally adapted by emotional_state when available
        (Sprint 5.4 — see _select_tone_variant()). No external model
        call, no wellness logic, no emotional inference of its own — see
        this module's own docstring."""
        stripped = transcript.strip()
        if not stripped:
            return _EMPTY_TRANSCRIPT_REPLY

        tone = _select_tone_variant(emotional_state, self._emotion_config)
        base = _ACKNOWLEDGEMENT_TEMPLATES[tone].format(transcript=stripped)
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
