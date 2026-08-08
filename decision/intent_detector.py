"""Intent Detection — the first stage of the Decision Engine pipeline
(02_System_Architecture.md: "Input -> Intent Detection -> Context
Analysis -> ..."). Classifies a transcript into a structured Intent using
a language model, independent of which persona is currently active.

This is the project's first genuinely non-deterministic component. The
Fail Gracefully Rule applies more strictly here than anywhere prior:
detect() must NEVER raise, for any input or any underlying failure,
matching PersonaManager.compose_reply_safely()'s established contract
(Sprint 2.11) exactly. Every failure path — a connection error, a
timeout, or a response that doesn't parse into a known category —
degrades to Intent(category=UNKNOWN, confidence=0.0), logged, never
raised, so a bad or unreachable LLM call can never block a live
conversation turn.

Prompt design (not specified by the Engineering Specification, a
genuine implementation-time decision per this sprint's own Potential
Risks): a plain-text two-line response format ("CATEGORY: ...\\n
CONFIDENCE: ...") rather than JSON. Ollama's client supports a
format= parameter that can force schema-constrained JSON output, but
using it would require widening LanguageModelClient.generate()'s
signature beyond the Sprint Book's specified (prompt, timeout_seconds)
-> str shape — parsing is instead done defensively here, tolerant of
any malformed response.
"""

import re
import time
from datetime import UTC, datetime

from config.schema import ModelConfig
from core.logging_setup import get_logger
from decision.llm_client import LanguageModelClient, LlmError
from decision.models import Intent, IntentCategory
from voice.context_manager import ConversationContext

logger = get_logger(__name__)

_CATEGORY_PATTERN = re.compile(r"CATEGORY:\s*([A-Za-z_]+)", re.IGNORECASE)
_CONFIDENCE_PATTERN = re.compile(r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
_CLASSIFIABLE_CATEGORIES = ", ".join(
    c.name for c in IntentCategory if c is not IntentCategory.UNKNOWN
)
_STOP_SEQUENCE = ["\n\n"]
"""0.4.3 latency fix — see decision/llm_client.py's LanguageModelClient
docstring for the real, measured finding this responds to. The prompt's
own "CATEGORY: ...\\nCONFIDENCE: ..." format has no blank line between
its two requested lines, so a real model's own blank line always marks
the boundary where it would otherwise start rambling past the requested
format — a genuine stop condition, not a guess."""


class IntentDetector:
    """Constructor DI per 03_Engineering_Standards.md: receives the
    LanguageModelClient it calls rather than constructing one itself, so
    a fake client can stand in for every unit test (fakes-at-the-ML-
    boundary convention established since Sprint 2.1)."""

    def __init__(self, llm_client: LanguageModelClient, model_config: ModelConfig) -> None:
        self._llm_client = llm_client
        self._timeout_seconds = model_config.ollama_timeout_seconds
        self._healthy = False

    def start(self) -> None:
        """Performs a lightweight readiness check (not a full generation
        call) against the configured Ollama host, via the injected
        client's optional is_reachable() capability if it has one (see
        decision/llm_client.py's OllamaClient docstring for why this
        isn't part of the shared Protocol). Deliberately does not raise
        on an unreachable host: unlike a model-loading component (e.g.
        WhisperSpeechToText), Ollama being briefly unreachable at
        startup doesn't stop detect() from working per-call once it
        comes back — marking this module FAILED would only prevent a
        recovery that already happens automatically."""
        is_reachable = getattr(self._llm_client, "is_reachable", None)
        probe_started_at = time.monotonic()
        self._healthy = is_reachable() if callable(is_reachable) else True
        probe_elapsed = time.monotonic() - probe_started_at
        if self._healthy:
            logger.info("Intent Detector ready (readiness probe took %.3fs).", probe_elapsed)
        else:
            logger.warning(
                "Intent Detector starting in a degraded state (Ollama unreachable; "
                "readiness probe took %.3fs).",
                probe_elapsed,
            )

    def stop(self) -> None:
        logger.info("Intent Detector stopped.")

    def health_check(self) -> bool:
        """Reports the last-known reachability state, cheaply — no live
        network call on every check, the same _healthy flag pattern
        established for WhisperSpeechToText/CoquiTextToSpeech (Sprint
        2.13)."""
        return self._healthy

    def detect(self, transcript: str, context: ConversationContext) -> Intent:
        """Classifies transcript + context into an Intent. Never raises:
        an empty transcript, an LlmError, a timeout, or an unparseable
        response all resolve to Intent(UNKNOWN, 0.0, transcript, now)."""
        detected_at = datetime.now(UTC)
        if not transcript or not transcript.strip():
            return Intent(IntentCategory.UNKNOWN, 0.0, transcript, detected_at)

        prompt = _build_prompt(transcript, context)
        try:
            response = self._llm_client.generate(
                prompt, self._timeout_seconds, stop=_STOP_SEQUENCE
            )
        except LlmError:
            logger.warning("Intent detection call failed; degrading to UNKNOWN.", exc_info=True)
            self._healthy = False
            return Intent(IntentCategory.UNKNOWN, 0.0, transcript, detected_at)

        self._healthy = True
        try:
            category, confidence = _parse_response(response)
        except Exception:
            logger.exception("Intent response parsing failed unexpectedly; degrading to UNKNOWN.")
            return Intent(IntentCategory.UNKNOWN, 0.0, transcript, detected_at)
        if category is IntentCategory.UNKNOWN:
            logger.debug("Could not parse a known intent category from: %s", response)
        return Intent(category, confidence, transcript, detected_at)


def _build_prompt(transcript: str, context: ConversationContext) -> str:
    if context.recent_turns:
        turns_text = "\n".join(
            f'User: "{turn.user_text}"\n{turn.persona_name}: "{turn.response_text}"'
            for turn in context.recent_turns
        )
    else:
        turns_text = "(no prior turns in this session)"
    return (
        "You are an intent classifier for a voice assistant with two personas, "
        "Jarvis and Minie. Classify the user's latest message into exactly one "
        f"of these categories: {_CLASSIFIABLE_CATEGORIES}.\n\n"
        f"Recent conversation (oldest first):\n{turns_text}\n\n"
        f'User\'s latest message: "{transcript}"\n\n'
        "Respond with exactly two lines and nothing else:\n"
        "CATEGORY: <one category name from the list above>\n"
        "CONFIDENCE: <a number from 0.0 to 1.0>"
    )


def _parse_response(response: str) -> tuple[IntentCategory, float]:
    category_match = _CATEGORY_PATTERN.search(response)
    if not category_match:
        return IntentCategory.UNKNOWN, 0.0
    try:
        category = IntentCategory[category_match.group(1).strip().upper()]
    except KeyError:
        return IntentCategory.UNKNOWN, 0.0

    confidence = 0.0
    confidence_match = _CONFIDENCE_PATTERN.search(response)
    if confidence_match:
        try:
            confidence = float(confidence_match.group(1))
        except ValueError:
            confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return category, confidence
