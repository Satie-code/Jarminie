"""Level 4 Part B real-network/real-model verification (Sprint 4.20) —
opt-in, NOT part of the fast committed suite's usual guarantees, mirroring
test_level3_real_model_verification.py's own established shape (Sprint
3.14).

Every other test in this project fakes both the SearchProvider boundary
(Sprint 4.16) and the LanguageModelClient boundary (Sprint 3.7+) — no
automated fast-suite run has ever actually exercised a real search query
against the live internet, a real summarization pass over real search
results, or confirmed the chosen search provider (Brave, per Sprint
4.16's own stop-and-ask gate) still behaves as expected against its real
API, per that sprint's own Testing Checklist. This file is where that
real, skipped-by-default verification finally runs, per this sprint's
own Engineering Rationale.

Opt-in mechanism: skips (never fails) unless BOTH a real
JARMINEI_INTERNET_SEARCH_API_KEY is set AND a real, reachable Ollama
instance with the configured model actually pulled is available — the
same "advisory, not fatal" posture Sprint 3.13/3.14 established, now
combined across two independent external dependencies rather than one
(this sprint's own Potential Risks names this combination explicitly).
Each dependency is checked and reported separately, so a real failure of
just one is immediately actionable rather than a single vague skip
reason.

A real, short-interval reminder announcement (also named in this
sprint's own Objectives, "if timing allows") is deliberately NOT
duplicated here — it has no real network/Ollama dependency of its own
(TaskScheduler/CalendarStore/QuietModeController are all already real
everywhere), so it belongs in, and is already covered by, the always-run
tests/system/test_level4_part_b_acceptance.py instead; this file's own
job is exclusively the two dependencies nothing else in the fast suite
ever exercises for real.
"""

import os
from datetime import UTC

import pytest

from config.schema import InternetConfig, ModelConfig
from decision.llm_client import OllamaClient
from internet.research_engine import ResearchEngine
from internet.search_provider_registry import create_search_provider
from internet.source_validator import SourceValidator
from internet.summarizer import Summarizer


def _model_config() -> ModelConfig:
    """ollama_timeout_seconds=120.0 — the shipped default (10.0) is sized
    for a warm/already-loaded model; a real Ollama instance cold-loading
    a multi-GB model for its first call can genuinely take well over
    10s, the identical finding test_level3_real_model_verification.py's
    own _model_config() already documented empirically."""
    return ModelConfig(
        ollama_model=os.environ.get("JARMINEI_TEST_OLLAMA_MODEL", ModelConfig().ollama_model),
        ollama_timeout_seconds=120.0,
    )


def _real_internet_config() -> InternetConfig:
    return InternetConfig(search_api_key=os.environ.get("JARMINEI_INTERNET_SEARCH_API_KEY"))


@pytest.fixture(autouse=True)
def _skip_unless_both_real_dependencies_available():
    """Runs before every test in this file. Checks the search API key
    and Ollama reachability/model-pulled separately — matching test_
    level3_real_model_verification.py's own two-layer Ollama check (is
    it reachable at all, AND is the configured model actually pulled) —
    so a real failure of just one dependency produces a clear, specific,
    actionable skip reason rather than one that could be either."""
    if not os.environ.get("JARMINEI_INTERNET_SEARCH_API_KEY"):
        pytest.skip(
            "JARMINEI_INTERNET_SEARCH_API_KEY is not set — real Level 4 Part B "
            "verification skipped. Set it to a real Brave Search API key and "
            "re-run to actually exercise this file."
        )

    model_config = _model_config()
    client = OllamaClient(model_config)
    if not client.is_reachable():
        pytest.skip(
            "No reachable Ollama instance at the configured host — real Level 4 "
            "Part B verification skipped. Install Ollama and run `ollama pull "
            f"{model_config.ollama_model}` (or set JARMINEI_TEST_OLLAMA_MODEL to "
            "an already-pulled model), then re-run to actually exercise this file."
        )
    import ollama as _ollama_pkg

    pulled = [m.model for m in _ollama_pkg.Client(host=model_config.ollama_host).list().models]
    if not any(name.split(":")[0] == model_config.ollama_model for name in pulled):
        pytest.skip(
            f"Ollama is reachable but {model_config.ollama_model!r} is not pulled "
            f"(pulled models: {pulled}) — run `ollama pull {model_config.ollama_model}` "
            "or set JARMINEI_TEST_OLLAMA_MODEL to one of the pulled models above, "
            "then re-run to actually exercise this file."
        )


def test_real_search_and_real_summarization_produce_a_grounded_cited_answer():
    """The full real pipeline, end to end: a real Brave Search API call
    (via the real, provider-agnostic create_search_provider() —
    confirming the Sprint 4.16 stop-and-ask decision still behaves as
    expected against its live API, not just its published docs, per
    that sprint's own still-open Testing Checklist item), real
    SourceValidator term-overlap corroboration over the real results,
    then a real local Ollama summarization pass over them.

    Assertions here are deliberately about *reasonableness*, never exact
    wording — real search results and real LLM output are both
    non-deterministic, matching test_level3_real_model_verification.py's
    own established discipline for real-model assertions."""
    internet_config = _real_internet_config()
    model_config = _model_config()

    search_provider = create_search_provider(internet_config)
    research_engine = ResearchEngine(search_provider, internet_config)
    source_validator = SourceValidator(internet_config)
    llm_client = OllamaClient(model_config)
    summarizer = Summarizer(llm_client, internet_config, model_config)

    query = "Python programming language"
    results = research_engine.research(query)

    assert len(results) > 0, (
        "A real search for a well-known, unambiguous query returned zero "
        "results — either a genuine search-provider issue or a real, worth-"
        "reporting finding about the chosen provider (Sprint 4.16's own "
        "decision), not a test bug."
    )
    for result in results:
        assert result.title
        assert result.url.startswith("http")
        assert result.snippet
        assert result.retrieved_at.tzinfo is not None

    citations = source_validator.validate(results)
    assert len(citations) == len(results)

    summary = summarizer.summarize(query, results, citations)

    assert summary.query == query
    assert summary.summary_text.strip() != ""
    # A real model, grounded in real snippets about "Python programming
    # language", should mention Python by name — a loose, reasonable
    # sanity check, not an exact-wording assertion.
    assert "python" in summary.summary_text.lower(), (
        f"Real summary didn't mention 'Python' at all — possibly a real "
        f"grounding/prompt-quality issue worth investigating, not assumed a "
        f"test bug: {summary.summary_text!r}"
    )
    assert summary.citations == citations
    assert summary.generated_at.tzinfo == UTC
