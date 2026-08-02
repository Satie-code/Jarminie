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

Sprint 5.4 adds _select_tone_variant(): a small, conservative
EmotionConfig-driven threshold read of EmotionalState picking among
_ACKNOWLEDGEMENT_TEMPLATES' three already-existing phrasing variants —
a warmer, ENCOURAGING opening when mood/comfort reads low, a shorter,
CONCISE one when stress reads high, NEUTRAL (identical to every
pre-Sprint-5.4 reply) otherwise, including whenever emotional_state is
None. Never affects the authority-driven prefixes/memory clause below —
tone variant and authority level are orthogonal and compose together.
Thresholds live in EmotionConfig, not as hardcoded module constants,
per 03_Engineering_Standards.md's "no hardcoded... thresholds" rule and
emotion/detection_engine.py's own established precedent
(_match_lexical_markers(text, config)) for a pure function reading its
tunable numbers from an injected config rather than a literal.
"""

from config.schema import EmotionConfig, VoiceConfig
from decision.authority import AuthorityLevel, DecisionTrace
from emotion.state_manager import EmotionalState
from personas.base import Persona, ToneVariant
from voice.context_manager import ConversationContext

_ACKNOWLEDGEMENT_TEMPLATES: dict[ToneVariant, str] = {
    ToneVariant.NEUTRAL: 'Understood. You said: "{transcript}".',
    ToneVariant.CONCISE: 'Understood: "{transcript}".',
    ToneVariant.ENCOURAGING: (
        'I hear you. You said: "{transcript}" — let\'s work through it together.'
    ),
}
_EMPTY_TRANSCRIPT_REPLY = "I didn't catch anything that time. Could you repeat that?"
_RECOMMEND_PREFIX = "Here's my recommendation: "
_EMERGENCY_ASSIST_PREFIX = "I'm authorized to assist directly: "


def _select_tone_variant(
    emotional_state: EmotionalState | None, config: EmotionConfig
) -> ToneVariant:
    """Module-private: a small, fixed rule selecting among Jarvis's own
    already-existing phrasing templates — never a new template generated
    at request time (sprint_5_4.md's own locked rule). None (no read
    yet) always selects NEUTRAL, the identical behavior every
    pre-Sprint-5.4 caller already gets. Thresholds come from config
    (EmotionConfig.tone_high_stress_threshold/
    jarvis_tone_low_mood_threshold/jarvis_tone_low_comfort_threshold),
    never hardcoded — see this module's own docstring."""
    if emotional_state is None:
        return ToneVariant.NEUTRAL
    if emotional_state.stress >= config.tone_high_stress_threshold:
        return ToneVariant.CONCISE
    if (
        emotional_state.mood <= config.jarvis_tone_low_mood_threshold
        or emotional_state.comfort <= config.jarvis_tone_low_comfort_threshold
    ):
        return ToneVariant.ENCOURAGING
    return ToneVariant.NEUTRAL


class JarvisPersona(Persona):
    """Constructor DI per 03_Engineering_Standards.md: receives the
    VoiceConfig it reads jarvis_voice_id from, rather than hardcoding a
    speaker ID. emotion_config (Sprint 5.4) defaults to EmotionConfig()
    when not supplied — additive-in-effect, matching every real existing
    caller (main.py, every pre-Sprint-5.4 test) that has no reason to
    pass one yet; see this module's own docstring for why the values it
    holds must not be hardcoded instead."""

    def __init__(
        self, voice_config: VoiceConfig, emotion_config: EmotionConfig | None = None
    ) -> None:
        self._voice_config = voice_config
        self._emotion_config = emotion_config if emotion_config is not None else EmotionConfig()

    @property
    def name(self) -> str:
        return "jarvis"

    @property
    def voice_id(self) -> str:
        return self._voice_config.jarvis_voice_id

    def compose_reply(
        self,
        transcript: str,
        context: ConversationContext,
        decision_trace: DecisionTrace | None,
        emotional_state: EmotionalState | None = None,
    ) -> str:
        """A short, professional-toned acknowledgement, augmented with
        decision_trace's retrieved memories/authority level when
        available, and tonally adapted by emotional_state when available
        (Sprint 5.4 — see _select_tone_variant()). No external model
        call — see this module's own docstring."""
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
            memory_clause = f" I recall: {top_memory.record.content}."

        if decision_trace.authority_level is AuthorityLevel.EMERGENCY_ASSIST:
            return f"{_EMERGENCY_ASSIST_PREFIX}{base}{memory_clause}"
        if decision_trace.authority_level is AuthorityLevel.RECOMMEND:
            return f"{_RECOMMEND_PREFIX}{base}{memory_clause}"
        return f"{base}{memory_clause}"

    def describe(self) -> str:
        return "Jarvis — professional execution persona"
