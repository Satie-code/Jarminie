"""Context Analysis — the Decision Engine's second pipeline stage
(02_System_Architecture.md: "Intent Detection -> Context Analysis ->
Memory Retrieval -> ..."). Deepens Sprint 3.7's Intent classification
into a structured read of the conversation: topic, entities, whether a
past memory is being referenced, which persona actually suits the
request, and a coarse conversational-tone hint.

suggested_persona is the real, intended replacement for
PersonaManager.detect_context_heuristic()'s keyword-list placeholder
(personas/persona_manager.py, Sprint 2.11) — that heuristic's own
docstring names this sprint as its scheduled replacement. The heuristic
itself is NOT removed here: Sprint 3.13 hardens the fallback path (if
Context Analysis is unavailable, fall back to the Level 2 heuristic
rather than losing context-based persona switching entirely), and
wiring suggested_persona in as the primary source is Sprint 3.12's job,
not this sprint's.

sentiment_hint is deliberately coarse and conversational, never
clinical — Level 5's Emotion Engine (Phase 5.1) is explicitly required
to "never perform medical diagnosis," and nothing here may produce
output that could later be mistaken for a diagnostic or wellbeing
assessment. Any future temptation to make this field richer or more
clinically framed belongs to Phase 5.1, not this sprint.

Like IntentDetector (Sprint 3.7), analyze() must NEVER raise: any LLM
failure or unparseable response degrades to a neutral-default
ContextAnalysis, logged, never raised — identical fail-safe contract.
"""

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from config.schema import ModelConfig
from core.logging_setup import get_logger
from decision.llm_client import LanguageModelClient, LlmError
from decision.models import Intent
from voice.context_manager import ConversationContext

logger = get_logger(__name__)

_TOPIC_PATTERN = re.compile(r"TOPIC:\s*(.+)", re.IGNORECASE)
_ENTITIES_PATTERN = re.compile(r"ENTITIES:\s*(.+)", re.IGNORECASE)
_REFERENCES_PAST_PATTERN = re.compile(r"REFERENCES_PAST:\s*(YES|NO)", re.IGNORECASE)
_PERSONA_PATTERN = re.compile(r"PERSONA:\s*(JARVIS|MINIE|NONE)", re.IGNORECASE)
_SENTIMENT_PATTERN = re.compile(r"SENTIMENT:\s*([A-Za-z_]+)", re.IGNORECASE)

_STOP_SEQUENCE = ["\n\n"]
"""0.4.3 latency fix — see decision/llm_client.py's LanguageModelClient
docstring for the real, measured finding this responds to: a real
Ollama call for this exact prompt was directly observed emitting the
correct 5 requested lines, then an entire unsolicited extra paragraph
afterward (thrown away by _parse_response() below, but still fully
generated and timed) — roughly two-thirds of this stage's own real
per-call latency. The model's own blank line between its structured
answer and its own rambling is the real, observed stop boundary."""


class SentimentHint(Enum):
    """A conversational-tone hint only — deliberately coarse, never
    clinical. See this module's own docstring."""

    NEUTRAL = "neutral"
    POSITIVE = "positive"
    STRESSED = "stressed"
    FRUSTRATED = "frustrated"
    TIRED = "tired"


@dataclass
class ContextAnalysis:
    """Result of analyzing one turn's Intent + ConversationContext."""

    primary_topic: str
    mentioned_entities: list[str]
    references_past_memory: bool
    suggested_persona: str | None
    sentiment_hint: SentimentHint
    analyzed_at: datetime


class ContextAnalyzer:
    """Constructor DI per 03_Engineering_Standards.md: receives the same
    LanguageModelClient Sprint 3.7's IntentDetector uses, unchanged —
    this sprint modifies no files from 3.7 (Files to Modify: None)."""

    def __init__(self, llm_client: LanguageModelClient, model_config: ModelConfig) -> None:
        self._llm_client = llm_client
        self._timeout_seconds = model_config.ollama_timeout_seconds
        self._healthy = False

    def start(self) -> None:
        """Same lightweight readiness check as IntentDetector.start()
        (Sprint 3.7) — see decision/llm_client.py's OllamaClient
        docstring for why is_reachable() is looked up defensively
        rather than being part of the shared Protocol."""
        is_reachable = getattr(self._llm_client, "is_reachable", None)
        probe_started_at = time.monotonic()
        self._healthy = is_reachable() if callable(is_reachable) else True
        probe_elapsed = time.monotonic() - probe_started_at
        if self._healthy:
            logger.info("Context Analyzer ready (readiness probe took %.3fs).", probe_elapsed)
        else:
            logger.warning(
                "Context Analyzer starting in a degraded state (Ollama unreachable; "
                "readiness probe took %.3fs).",
                probe_elapsed,
            )

    def stop(self) -> None:
        logger.info("Context Analyzer stopped.")

    def health_check(self) -> bool:
        return self._healthy

    def analyze(self, intent: Intent, context: ConversationContext) -> ContextAnalysis:
        """Never raises: an empty transcript, an LlmError, a timeout, or
        an unparseable response all resolve to a neutral-default
        ContextAnalysis, identical fail-safe contract to
        IntentDetector.detect() (Sprint 3.7)."""
        analyzed_at = datetime.now(UTC)
        if not intent.raw_transcript or not intent.raw_transcript.strip():
            return _neutral_default(analyzed_at)

        prompt = _build_prompt(intent, context)
        try:
            response = self._llm_client.generate(
                prompt, self._timeout_seconds, stop=_STOP_SEQUENCE
            )
        except LlmError:
            logger.warning(
                "Context analysis call failed; degrading to neutral default.", exc_info=True
            )
            self._healthy = False
            return _neutral_default(analyzed_at)

        self._healthy = True
        try:
            return _parse_response(response, analyzed_at)
        except Exception:
            logger.exception(
                "Context analysis response parsing failed; degrading to neutral default."
            )
            return _neutral_default(analyzed_at)


def _neutral_default(analyzed_at: datetime) -> ContextAnalysis:
    return ContextAnalysis(
        primary_topic="",
        mentioned_entities=[],
        references_past_memory=False,
        suggested_persona=None,
        sentiment_hint=SentimentHint.NEUTRAL,
        analyzed_at=analyzed_at,
    )


def _build_prompt(intent: Intent, context: ConversationContext) -> str:
    if context.recent_turns:
        turns_text = "\n".join(
            f'User: "{turn.user_text}"\n{turn.persona_name}: "{turn.response_text}"'
            for turn in context.recent_turns
        )
    else:
        turns_text = "(no prior turns in this session)"
    return (
        "You are a context analyzer for a voice assistant with two personas: "
        "Jarvis (technical, task-focused) and Minie (warm, casual, supportive). "
        f"The user's latest message was classified as intent category {intent.category.name}.\n\n"
        f"Recent conversation (oldest first):\n{turns_text}\n\n"
        f"Currently active persona: {context.active_persona_name}\n"
        f'User\'s latest message: "{intent.raw_transcript}"\n\n'
        "Respond with exactly five lines and nothing else:\n"
        "TOPIC: <a short phrase naming the primary topic>\n"
        "ENTITIES: <comma-separated specific things/people/places mentioned, or NONE>\n"
        "REFERENCES_PAST: <YES if this references a prior conversation or memory, else NO>\n"
        "PERSONA: <JARVIS if best suited to a technical/task-focused reply, "
        "MINIE if best suited to a warm/casual/supportive reply, or NONE if unclear>\n"
        "SENTIMENT: <one of NEUTRAL, POSITIVE, STRESSED, FRUSTRATED, TIRED>"
    )


def _parse_response(response: str, analyzed_at: datetime) -> ContextAnalysis:
    topic_match = _TOPIC_PATTERN.search(response)
    primary_topic = topic_match.group(1).strip() if topic_match else ""

    entities: list[str] = []
    entities_match = _ENTITIES_PATTERN.search(response)
    if entities_match:
        raw_entities = entities_match.group(1).strip()
        if raw_entities.upper() != "NONE":
            entities = [e.strip() for e in raw_entities.split(",") if e.strip()]

    references_past_memory = False
    references_match = _REFERENCES_PAST_PATTERN.search(response)
    if references_match:
        references_past_memory = references_match.group(1).strip().upper() == "YES"

    suggested_persona: str | None = None
    persona_match = _PERSONA_PATTERN.search(response)
    if persona_match:
        raw_persona = persona_match.group(1).strip().upper()
        if raw_persona in ("JARVIS", "MINIE"):
            suggested_persona = raw_persona.lower()

    sentiment_hint = SentimentHint.NEUTRAL
    sentiment_match = _SENTIMENT_PATTERN.search(response)
    if sentiment_match:
        try:
            sentiment_hint = SentimentHint[sentiment_match.group(1).strip().upper()]
        except KeyError:
            sentiment_hint = SentimentHint.NEUTRAL

    return ContextAnalysis(
        primary_topic=primary_topic,
        mentioned_entities=entities,
        references_past_memory=references_past_memory,
        suggested_persona=suggested_persona,
        sentiment_hint=sentiment_hint,
        analyzed_at=analyzed_at,
    )
