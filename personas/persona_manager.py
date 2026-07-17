"""PersonaManager — the switching mechanism enforcing "only one persona
may be active" and Part 2's priority-ordered switching rules
(02_System_Architecture.md's Persona Switching Rules):

    Priority | SwitchReason         | Status (Level 2)
    ---------|----------------------|----------------------------------
    1        | CRITICAL_EMERGENCY   | Reserved — needs the Authority
             |                      | System (Level 3, Sprint 3.10).
    2        | EXPLICIT_SELECTION   | Wired — configured trigger phrases
             |                      | (VoiceConfig.jarvis_trigger_phrases /
             |                      | minie_trigger_phrases), no NLU.
    3        | CONTEXT_DETECTION    | Wired — a crude keyword-list
             |                      | heuristic, an explicit placeholder
             |                      | for Sprint 3.8's real Context
             |                      | Analysis (built on Sprint 3.7 Intent
             |                      | Detection + Ollama).
    4        | DAILY_ROUTINE        | Reserved — needs the Scheduler
             |                      | (Level 4, Sprint 4.8+).

Only two of the four reasons have a real trigger in Level 2 (Explicit
Selection, Context Detection); the other two are named now — never wired
to a caller — so the priority mechanism doesn't need reshaping when
Sprint 3.10 and Sprint 4.8+ eventually supply them. Same pattern already
established for ActivationReason in Quiet Mode Controller (Sprint 2.6).

detect_context_heuristic()'s keyword lists are a known-crude placeholder,
likely to misclassify in practice — acceptable for Level 2, not a hidden
permanent limitation. It is topic-based only, never emotion-based; do not
conflate it with Level 5's Emotion Engine when that arrives.

resume_previous() tracks exactly one prior (persona, reason) pair, not a
stack — "resume-of-resume" (an interruption during an already-resuming
interruption) is under-specified by Part 2's text and deliberately not
solved here; if Sprint 3.10's real emergency wiring exposes a genuine
need for deeper nesting, that is the point to redesign this, not
something to over-engineer against speculatively now.
"""

from enum import Enum

from config.schema import VoiceConfig
from core.logging_setup import get_logger
from personas.base import Persona

logger = get_logger(__name__)

_MINIE_HEURISTIC_KEYWORDS: tuple[str, ...] = (
    "feel",
    "feeling",
    "tired",
    "stressed",
    "sad",
    "lonely",
    "worried",
    "anxious",
    "overwhelmed",
)
"""Casual/emotional words -> Minie. Crude, topic-based placeholder — see
this module's own docstring and Sprint 3.8's future replacement."""

_JARVIS_HEURISTIC_KEYWORDS: tuple[str, ...] = (
    "project",
    "deadline",
    "code",
    "schedule",
    "task",
    "report",
    "meeting",
    "bug",
)
"""Technical/project words -> Jarvis. Same placeholder caveat as above."""


class SwitchReason(Enum):
    """Declaration order encodes priority directly (most urgent first),
    matching Part 2's numbered list — see this module's docstring."""

    CRITICAL_EMERGENCY = "critical_emergency"
    EXPLICIT_SELECTION = "explicit_selection"
    CONTEXT_DETECTION = "context_detection"
    DAILY_ROUTINE = "daily_routine"


_PRIORITY_ORDER: tuple[SwitchReason, ...] = tuple(SwitchReason)


def _priority_rank(reason: SwitchReason) -> int:
    """Lower rank = higher priority (0 = CRITICAL_EMERGENCY, the most
    urgent reason)."""
    return _PRIORITY_ORDER.index(reason)


class PersonaManager:
    """Constructor DI per 03_Engineering_Standards.md: receives the two
    Persona instances and the VoiceConfig it reads trigger phrases from,
    rather than constructing any of them itself.

    Active state is tracked as a per-persona-name boolean flag dict
    (rather than a single reference) specifically so "exactly one active"
    is a real, checkable invariant — see health_check() and this sprint's
    own defensive Testing Checklist item.
    """

    def __init__(self, jarvis: Persona, minie: Persona, voice_config: VoiceConfig) -> None:
        self._personas: dict[str, Persona] = {jarvis.name: jarvis, minie.name: minie}
        self._voice_config = voice_config
        self._active_flags: dict[str, bool] = dict.fromkeys(self._personas, False)
        self._active_name: str | None = None
        self._active_reason: SwitchReason | None = None
        self._previous_name: str | None = None
        self._previous_reason: SwitchReason | None = None

    def start(self) -> None:
        """Jarvis is the default active persona — Part 1/2 characterize
        Jarvis as the general-purpose "system brain", with Minie
        activating contextually rather than by default."""
        self._set_active("jarvis")
        self._active_reason = None
        logger.info("Persona Manager started; default active persona: jarvis.")

    def stop(self) -> None:
        logger.info("Persona Manager stopped.")

    def health_check(self) -> bool:
        """Fails if internal state ever ends up with zero or more than one
        active flag set — a defensive check against a bug class, not an
        expected real path (every select()/resume_previous() call
        maintains this invariant via _set_active())."""
        return sum(self._active_flags.values()) == 1

    def active_persona(self) -> Persona:
        return self._personas[self._active_name]

    def select(self, persona_name: str, reason: SwitchReason) -> bool:
        """Switch the active persona if reason's priority is at or above
        whatever caused the currently active persona. Returns whether the
        switch was applied. A refusal is logged, never raised — a
        lower-priority switch attempt is an expected, not exceptional,
        occurrence."""
        if persona_name not in self._personas:
            logger.warning("select() called with unknown persona name: %s", persona_name)
            return False
        if self._active_reason is not None and _priority_rank(reason) > _priority_rank(
            self._active_reason
        ):
            logger.info(
                "select(%s, %s) refused — lower priority than active reason %s.",
                persona_name,
                reason.value,
                self._active_reason.value,
            )
            return False
        self._previous_name = self._active_name
        self._previous_reason = self._active_reason
        self._set_active(persona_name)
        self._active_reason = reason
        logger.info("Persona switched to %s (%s).", persona_name, reason.value)
        return True

    def resume_previous(self) -> None:
        """Restore whatever persona/reason was active before the most
        recent successful switch. A no-op (logged) if nothing is recorded
        to resume."""
        if self._previous_name is None:
            logger.info("resume_previous() called with nothing to resume.")
            return
        self._set_active(self._previous_name)
        self._active_reason = self._previous_reason
        self._previous_name = None
        self._previous_reason = None
        logger.info("Resumed previous persona: %s.", self._active_name)

    def detect_explicit_selection(self, transcript: str) -> str | None:
        """Case-insensitive substring match against configured trigger
        phrases — no NLU. Jarvis checked first; a transcript matching both
        lists (unlikely given the default phrases) resolves to Jarvis."""
        lowered = transcript.lower()
        if any(phrase.lower() in lowered for phrase in self._voice_config.jarvis_trigger_phrases):
            return "jarvis"
        if any(phrase.lower() in lowered for phrase in self._voice_config.minie_trigger_phrases):
            return "minie"
        return None

    def detect_context_heuristic(self, transcript: str) -> str | None:
        """Crude keyword-list placeholder — see this module's docstring.
        Minie's keywords checked first (an emotional cue is treated as a
        stronger signal than an incidental technical word appearing in
        the same sentence)."""
        lowered = transcript.lower()
        if any(word in lowered for word in _MINIE_HEURISTIC_KEYWORDS):
            return "minie"
        if any(word in lowered for word in _JARVIS_HEURISTIC_KEYWORDS):
            return "jarvis"
        return None

    def _set_active(self, name: str) -> None:
        for persona_name in self._active_flags:
            self._active_flags[persona_name] = persona_name == name
        self._active_name = name
