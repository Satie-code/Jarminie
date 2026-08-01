"""Unit tests for internet.summarizer.

LanguageModelClient is faked in every test — matching every other real
caller of that Protocol in this codebase (decision/intent_detector.py's
own test suite). The real, non-mocked model path is Sprint 4.20's own
opt-in real-model verification job, mirroring
test_level3_real_model_verification.py's precedent — see this file's
own adversarial test at the bottom for why that matters here
specifically.
"""

from datetime import UTC, datetime

from config.schema import InternetConfig, ModelConfig
from decision.llm_client import LlmError
from internet.search_provider import SearchResult
from internet.source_validator import Citation
from internet.summarizer import Summarizer

_NOW = datetime.now(UTC)


class FakeLanguageModelClient:
    """Local double implementing the LanguageModelClient Protocol —
    records every call it receives and returns/raises whatever the
    test configures."""

    def __init__(self, response: str = "A summary.", error: Exception | None = None):
        self._response = response
        self._error = error
        self.calls: list[tuple[str, float, list[str] | None]] = []

    def generate(
        self, prompt: str, timeout_seconds: float, stop: list[str] | None = None
    ) -> str:
        self.calls.append((prompt, timeout_seconds, stop))
        if self._error is not None:
            raise self._error
        return self._response


def make_result(title: str, snippet: str, url: str = "https://example.com") -> SearchResult:
    return SearchResult(title=title, url=url, snippet=snippet, retrieved_at=_NOW)


def make_citation(title: str, url: str, is_corroborated: bool = False) -> Citation:
    return Citation(title=title, url=url, is_corroborated=is_corroborated)


# --- happy path -----------------------------------------------------------------------


def test_summarize_returns_the_real_llm_response():
    fake = FakeLanguageModelClient(response="Python 3.13 adds free threading.")
    summarizer = Summarizer(fake, InternetConfig(), ModelConfig())
    results = [make_result("Python 3.13", "Python 3.13 introduces free threading")]
    citations = [make_citation("Python 3.13", "https://example.com")]

    summary = summarizer.summarize("What's new in Python 3.13?", results, citations)

    assert summary.summary_text == "Python 3.13 adds free threading."
    assert summary.query == "What's new in Python 3.13?"
    assert summary.generated_at is not None


def test_summarize_passes_citations_through_unchanged():
    fake = FakeLanguageModelClient()
    summarizer = Summarizer(fake, InternetConfig(), ModelConfig())
    citations = [
        make_citation("A", "https://a.com", True),
        make_citation("B", "https://b.com", False),
    ]

    summary = summarizer.summarize("query", [], citations)

    assert summary.citations == citations


def test_summarize_uses_ollama_timeout_seconds_from_model_config():
    fake = FakeLanguageModelClient()
    summarizer = Summarizer(fake, InternetConfig(), ModelConfig(ollama_timeout_seconds=42.0))

    summarizer.summarize("query", [], [])

    assert fake.calls[0][1] == 42.0


# --- prompt grounding -------------------------------------------------------------------


def test_prompt_contains_only_the_provided_snippets():
    fake = FakeLanguageModelClient()
    summarizer = Summarizer(fake, InternetConfig(), ModelConfig())
    results = [
        make_result("Result One", "This is the first unique snippet text."),
        make_result("Result Two", "This is the second unique snippet text."),
    ]

    summarizer.summarize("a research question", results, [])

    prompt = fake.calls[0][0]
    assert "a research question" in prompt
    assert "This is the first unique snippet text." in prompt
    assert "This is the second unique snippet text." in prompt
    assert "Result One" in prompt
    assert "Result Two" in prompt


def test_prompt_instructs_the_model_to_use_only_the_provided_information():
    fake = FakeLanguageModelClient()
    summarizer = Summarizer(fake, InternetConfig(), ModelConfig())

    summarizer.summarize("query", [make_result("T", "S")], [])

    prompt = fake.calls[0][0]
    assert "ONLY" in prompt
    assert "say so" in prompt.lower()


def test_prompt_with_no_results_still_contains_the_query():
    fake = FakeLanguageModelClient()
    summarizer = Summarizer(fake, InternetConfig(), ModelConfig())

    summarizer.summarize("a lonely query", [], [])

    assert "a lonely query" in fake.calls[0][0]


# --- degrade on LanguageModelClient failure -----------------------------------------------


def test_summarize_degrades_honestly_on_llm_error():
    fake = FakeLanguageModelClient(error=LlmError("ollama unreachable"))
    summarizer = Summarizer(fake, InternetConfig(), ModelConfig())

    summary = summarizer.summarize("query", [make_result("T", "S")], [])

    assert summary.summary_text == "I found some sources but couldn't summarize them right now."


def test_summarize_never_raises_on_llm_error():
    fake = FakeLanguageModelClient(error=LlmError("timeout"))
    summarizer = Summarizer(fake, InternetConfig(), ModelConfig())

    summarizer.summarize("query", [], [])  # must not raise


def test_summarize_degrade_still_returns_real_citations():
    fake = FakeLanguageModelClient(error=LlmError("boom"))
    summarizer = Summarizer(fake, InternetConfig(), ModelConfig())
    citations = [make_citation("A", "https://a.com")]

    summary = summarizer.summarize("query", [], citations)

    assert summary.citations == citations


# --- citation fidelity ------------------------------------------------------------------


def test_every_citation_traces_to_a_real_provided_source():
    fake = FakeLanguageModelClient()
    summarizer = Summarizer(fake, InternetConfig(), ModelConfig())
    real_citation = make_citation("Real Source", "https://real.com")

    summary = summarizer.summarize("query", [], [real_citation])

    assert len(summary.citations) == 1
    assert summary.citations[0] is real_citation


# --- adversarial: grounding is prompt-level only, not structurally verified here --------


def test_a_fabricated_llm_response_is_passed_through_unverified():
    """Documents a known, named limitation (see this sprint's own
    Engineering Rationale/Potential Risks): Summarizer has no
    structural mechanism to detect or reject a hallucinated claim not
    present in any provided snippet — only prompt-level grounding is
    attempted. A real adversarial check against an actual model is
    Sprint 4.20's job. This test proves the CURRENT, honest behavior
    (pass-through), not a desired one — if a future sprint adds real
    grounding verification, update this test to assert the new
    behavior instead of deleting it."""
    fabricated = "The moon is made of cheese, according to all sources."
    fake = FakeLanguageModelClient(response=fabricated)
    summarizer = Summarizer(fake, InternetConfig(), ModelConfig())
    results = [make_result("Unrelated", "This snippet says nothing about the moon or cheese.")]

    summary = summarizer.summarize("What is the moon made of?", results, [])

    assert summary.summary_text == fabricated
