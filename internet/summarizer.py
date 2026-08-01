"""Summarizer — turns ResearchEngine's (4.16) raw SearchResults into one
grounded ResearchSummary. See docs/sprint_book/sprint_4_17.md.

Reuses decision/llm_client.py's existing LanguageModelClient Protocol/
OllamaClient rather than adding a second LLM integration — the same
local Ollama runtime IntentDetector/ContextAnalyzer already call. This
is a deliberate, one-directional internet/ -> decision/llm_client.py
dependency, the identical shape workflow/ -> device_control/ already
established as this project's accepted pattern for one subsystem
genuinely reusing another's real capability. See sprint_4_17.md's own
Engineering Rationale.

**Grounding/hallucination is this sprint's single largest engineering
risk** (see sprint_4_17.md's own Engineering Rationale at length) — an
LLM asked to summarize search results can fabricate content not present
in the source snippets at all, the same class of risk
backlog/technical_debt.md item 9 already found for Whisper's
transcription. _build_prompt() structurally constrains the model to
only the provided snippets, with an explicit "only use the information
below... if it doesn't answer the question, say so" instruction — the
same defensive-prompting discipline ModelConfig.whisper_initial_prompt
already uses for a different failure mode. This is a PROMPT-LEVEL
mitigation only: nothing in this sprint's own fast test suite (which
fakes LanguageModelClient) can prove a real model actually obeys it —
that real, adversarial verification is explicitly Sprint 4.20's job,
mirroring test_level3_real_model_verification.py's own opt-in
precedent. Treat a fabricated real-model summary as a known, named,
not-yet-closed risk until that verification happens.

Constructor DI takes ModelConfig (for ollama_timeout_seconds) in
addition to InternetConfig — a deliberate, small addition beyond this
sprint's own originally-specified (llm_client, internet_config)
signature, matching the identical pattern every other real
LanguageModelClient caller in this codebase already uses
(IntentDetector/ContextAnalyzer both read their own call timeout from
ModelConfig.ollama_timeout_seconds) — LanguageModelClient.generate()
requires a timeout_seconds argument on every call, and InternetConfig's
own fields (per this sprint's own spec) name no timeout of its own.

InternetConfig.summarization_model is deliberately NOT read by this
class — LanguageModelClient.generate() has no per-call model-selection
parameter (the model is bound at whichever OllamaClient instance was
constructed and passed in), so summarization_model is informational
only, meant to guide Sprint 4.18's own main.py wiring (which concrete
OllamaClient to build for the Summarizer it constructs), not something
this class can act on directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from config.schema import InternetConfig, ModelConfig
from core.logging_setup import get_logger
from decision.llm_client import LanguageModelClient, LlmError
from internet.search_provider import SearchResult
from internet.source_validator import Citation

logger = get_logger(__name__)

_DEGRADED_SUMMARY_TEXT = "I found some sources but couldn't summarize them right now."

_PROMPT_TEMPLATE = (
    "Answer the question below using ONLY the search result snippets "
    "provided — do not use any other knowledge. If the snippets don't "
    "contain enough information to answer the question, say so honestly "
    "instead of guessing.\n\n"
    "Question: {query}\n\n"
    "Search results:\n{results_block}\n\n"
    "Write a concise, honest answer based only on the information above."
)


@dataclass
class ResearchSummary:
    query: str
    summary_text: str
    citations: list[Citation]
    generated_at: datetime


class Summarizer:
    """Constructor DI: (llm_client, internet_config, model_config) — see
    this module's own docstring for why model_config was added beyond
    this sprint's own originally-specified signature. Stateless per
    call, the same shape SourceValidator/ContextManager already
    establish."""

    def __init__(
        self,
        llm_client: LanguageModelClient,
        internet_config: InternetConfig,
        model_config: ModelConfig,
    ) -> None:
        self._llm_client = llm_client
        self._config = internet_config
        self._timeout_seconds = model_config.ollama_timeout_seconds

    def summarize(
        self, query: str, results: list[SearchResult], citations: list[Citation]
    ) -> ResearchSummary:
        """Never raises: an LlmError degrades to an honest, plain
        "couldn't summarize" ResearchSummary — mirroring
        IntentDetector's own safe-UNKNOWN-on-failure precedent.
        `citations` is passed straight through unchanged, so every
        Citation in the result traces back to a real, caller-provided
        source — this method has no way to invent a phantom one."""
        prompt = self._build_prompt(query, results)
        try:
            summary_text = self._llm_client.generate(prompt, self._timeout_seconds)
        except LlmError:
            logger.warning(
                "Summarization call failed for query %r; degrading.", query, exc_info=True
            )
            summary_text = _DEGRADED_SUMMARY_TEXT
        return ResearchSummary(
            query=query,
            summary_text=summary_text,
            citations=citations,
            generated_at=datetime.now(UTC),
        )

    def _build_prompt(self, query: str, results: list[SearchResult]) -> str:
        results_block = "\n".join(
            f"{i}. {result.title}\n   {result.snippet}\n   Source: {result.url}"
            for i, result in enumerate(results, start=1)
        )
        return _PROMPT_TEMPLATE.format(query=query, results_block=results_block)
