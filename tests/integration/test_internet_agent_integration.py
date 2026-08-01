"""Integration tests for the Internet Agent's real, end-to-end wiring
(Sprint 4.18) — the first live exercise of `EngineSelection.INTERNET_
AGENT` actually reaching `ResearchEngine.research()` -> `SourceValidator.
validate()` -> `Summarizer.summarize()` through a full, real conversation
turn.

Uses the shared pipeline_harness (tests/integration/conftest.py) — this
file needs none of test_scheduler_integration.py's short-interval
timing, only its own two true external-service boundaries: the network
(FakeSearchProvider) and the LLM (FakeLanguageModelClient), matching
every prior integration test's own "fake only at the true hardware/
external-service boundary" precedent.
"""

from datetime import UTC, datetime

from internet.search_provider import SearchResult

_TURN_TIMEOUT = 5.0


def _set_internet_agent_request(h, topic: str) -> None:
    h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        f"TOPIC: {topic}\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )


def _result(title: str, url: str, snippet: str) -> SearchResult:
    return SearchResult(title=title, url=url, snippet=snippet, retrieved_at=datetime.now(UTC))


def test_live_turn_produces_a_real_cited_summary(
    pipeline_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Acceptance Criteria: "A live conversation turn asking for current/
    external information is correctly routed through EngineSelection.
    INTERNET_AGENT and produces a real, cited spoken summary."

    Three queued SearchResults: two (a, b) share enough significant
    terms to genuinely corroborate each other through SourceValidator's
    own real term-overlap logic (min_sources_for_corroboration=2,
    InternetConfig's own default), one (c) is unrelated and stays
    uncorroborated — proving the reply's own citation count is computed
    from SourceValidator's real output, not hardcoded.
    """
    h = pipeline_harness
    _set_internet_agent_request(h, "JARMINEI project news")
    h.fake_search_provider.queued_results = [
        _result(
            "JARMINEI Project Overview",
            "https://example.com/jarminei-overview",
            "JARMINEI is a voice assistant project with a modular architecture.",
        ),
        _result(
            "JARMINEI Architecture Update",
            "https://example.com/jarminei-architecture",
            "The JARMINEI architecture uses a modular voice assistant design.",
        ),
        _result(
            "Weather Forecast Tomorrow",
            "https://example.com/weather",
            "Expect sunny skies with mild temperatures across the region.",
        ),
    ]
    h.llm_client.summary_response = "JARMINEI is a modular, voice-first assistant project."

    wait_for_active_capture(h.mic)
    h.stt.pending_transcripts.append("what's the latest news on the jarminei project")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text == (
        "JARMINEI is a modular, voice-first assistant project. "
        "(Based on 3 source(s), 2 corroborated.)"
    )

    # The real ResearchEngine call actually reached FakeSearchProvider
    # with the turn's own resolved topic, not some placeholder.
    assert len(h.fake_search_provider.calls) == 1
    query, max_results = h.fake_search_provider.calls[0]
    assert query == "JARMINEI project news"
    assert max_results == h.internet_config.max_results_per_query

    # The summarizer's own prompt genuinely reached the real LLM client
    # boundary carrying the search results, not a canned shortcut.
    summarizer_prompts = [p for p in h.llm_client.calls if "Search results:" in p]
    assert len(summarizer_prompts) == 1
    assert "JARMINEI Project Overview" in summarizer_prompts[0]

    wait_for_dormant(h.quiet_mode_controller)


def test_live_turn_with_no_search_results_gets_an_honest_gap_reply(
    pipeline_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """A genuinely empty result set (not a provider failure) must never
    reach Summarizer at all — asking an LLM to "summarize" zero real
    results risks a worse, ungrounded hallucination than the honest
    "couldn't find anything" _handle_internet_agent_turn() returns
    instead (voice/pipeline.py's own documented reasoning)."""
    h = pipeline_harness
    _set_internet_agent_request(h, "an extremely obscure topic")
    h.fake_search_provider.queued_results = []

    wait_for_active_capture(h.mic)
    h.stt.pending_transcripts.append("search for an extremely obscure topic")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text == "I couldn't find anything for an extremely obscure topic."

    # Summarizer's own prompt template was never even built.
    assert not any("Search results:" in p for p in h.llm_client.calls)

    wait_for_dormant(h.quiet_mode_controller)


def test_live_turn_search_provider_failure_degrades_to_the_same_honest_reply(
    pipeline_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """ResearchEngine.research() (Sprint 4.16) never raises — a real
    SearchProvider failure (unreachable, timed out, rate-limited)
    degrades to an empty result list, which this sprint's own
    _handle_internet_agent_turn() then treats identically to a
    genuinely empty search: an honest gap reply, not a crash or a
    silently swallowed turn."""
    h = pipeline_harness
    _set_internet_agent_request(h, "a topic the search provider fails on")
    h.fake_search_provider.should_raise = True

    wait_for_active_capture(h.mic)
    h.stt.pending_transcripts.append("look up a topic the search provider fails on")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT)
    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text == "I couldn't find anything for a topic the search provider fails on."

    wait_for_dormant(h.quiet_mode_controller)
