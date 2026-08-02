"""Unit tests for presentation.adaptive_workspace (Sprint 5.12)."""

from datetime import UTC, datetime

import pytest

from config.schema import PresentationConfig
from decision.context_analyzer import ContextAnalysis, SentimentHint
from presentation.adaptive_workspace import AdaptiveWorkspaceController, WorkspaceProfile


def _context_analysis(
    primary_topic: str = "", mentioned_entities: list[str] | None = None
) -> ContextAnalysis:
    return ContextAnalysis(
        primary_topic=primary_topic,
        mentioned_entities=mentioned_entities or [],
        references_past_memory=False,
        suggested_persona=None,
        sentiment_hint=SentimentHint.NEUTRAL,
        analyzed_at=datetime.now(UTC),
    )


@pytest.fixture
def config() -> PresentationConfig:
    return PresentationConfig(
        workspace_profile_keywords={
            "coding": ["code", "bug", "debug"],
            "research": ["research", "article"],
            "study": ["exam", "homework"],
            "projects": ["deadline", "milestone"],
        },
        workspace_switch_debounce_turns=2,
    )


@pytest.fixture
def controller(config) -> AdaptiveWorkspaceController:
    return AdaptiveWorkspaceController(config)


# --- select_profile() never raises, including None (Acceptance Criteria) -----


def test_select_profile_returns_general_for_none(controller):
    assert controller.select_profile(None) is WorkspaceProfile.GENERAL


def test_select_profile_returns_general_for_empty_topic_and_entities(controller):
    analysis = _context_analysis(primary_topic="", mentioned_entities=[])
    assert controller.select_profile(analysis) is WorkspaceProfile.GENERAL


def test_select_profile_never_raises_for_a_variety_of_inputs(controller):
    for analysis in (
        None,
        _context_analysis(),
        _context_analysis(primary_topic="   "),
        _context_analysis(primary_topic="something unrelated entirely"),
        _context_analysis(mentioned_entities=["", "", ""]),
    ):
        controller.select_profile(analysis)  # must not raise


# --- select_profile() across representative fixtures (Testing Checklist) -----


def test_select_profile_matches_coding_from_primary_topic(controller):
    analysis = _context_analysis(primary_topic="fixing a bug in the code")
    assert controller.select_profile(analysis) is WorkspaceProfile.CODING


def test_select_profile_matches_research_from_mentioned_entities(controller):
    analysis = _context_analysis(primary_topic="something", mentioned_entities=["research"])
    assert controller.select_profile(analysis) is WorkspaceProfile.RESEARCH


def test_select_profile_matches_study(controller):
    analysis = _context_analysis(primary_topic="reviewing for the exam")
    assert controller.select_profile(analysis) is WorkspaceProfile.STUDY


def test_select_profile_matches_projects(controller):
    analysis = _context_analysis(primary_topic="the deadline is approaching")
    assert controller.select_profile(analysis) is WorkspaceProfile.PROJECTS


def test_select_profile_matches_case_insensitively(controller):
    analysis = _context_analysis(primary_topic="Fixing a BUG in the code")
    assert controller.select_profile(analysis) is WorkspaceProfile.CODING


def test_select_profile_falls_back_to_general_for_unmatched_topic(controller):
    analysis = _context_analysis(primary_topic="what's the weather like today")
    assert controller.select_profile(analysis) is WorkspaceProfile.GENERAL


def test_select_profile_combines_topic_and_entities_for_matching(controller):
    # Neither field alone contains a keyword, but combined they still
    # don't — this test instead confirms a keyword *only* present in
    # mentioned_entities is still found (not just primary_topic).
    analysis = _context_analysis(
        primary_topic="a plain sentence", mentioned_entities=["milestone"]
    )
    assert controller.select_profile(analysis) is WorkspaceProfile.PROJECTS


# --- tie-break ordering (Testing Checklist) -----------------------------------


def test_select_profile_tie_break_prefers_earlier_declared_profile(controller):
    """CODING is declared before RESEARCH — a ContextAnalysis matching
    both must resolve to CODING."""
    analysis = _context_analysis(primary_topic="debug the research article's code")
    assert controller.select_profile(analysis) is WorkspaceProfile.CODING


def test_select_profile_tie_break_prefers_research_over_study(controller):
    analysis = _context_analysis(primary_topic="research for the exam")
    assert controller.select_profile(analysis) is WorkspaceProfile.RESEARCH


def test_select_profile_tie_break_prefers_study_over_projects(controller):
    analysis = _context_analysis(primary_topic="homework due before the deadline")
    assert controller.select_profile(analysis) is WorkspaceProfile.STUDY


# --- should_switch() debounce behavior (Acceptance Criteria) -----------------


def test_should_switch_false_for_a_single_matching_turn(controller):
    assert controller.should_switch(WorkspaceProfile.GENERAL, WorkspaceProfile.CODING, 1) is False


def test_should_switch_true_once_the_debounce_threshold_is_met(controller):
    assert controller.should_switch(WorkspaceProfile.GENERAL, WorkspaceProfile.CODING, 2) is True


def test_should_switch_true_beyond_the_debounce_threshold(controller):
    assert controller.should_switch(WorkspaceProfile.GENERAL, WorkspaceProfile.CODING, 5) is True


def test_should_switch_false_when_candidate_equals_current(controller):
    assert controller.should_switch(WorkspaceProfile.CODING, WorkspaceProfile.CODING, 10) is False


def test_should_switch_false_at_zero_count(controller):
    assert controller.should_switch(WorkspaceProfile.GENERAL, WorkspaceProfile.STUDY, 0) is False


def test_should_switch_respects_a_custom_debounce_threshold():
    custom_config = PresentationConfig(workspace_switch_debounce_turns=5)
    custom_controller = AdaptiveWorkspaceController(custom_config)
    general, coding = WorkspaceProfile.GENERAL, WorkspaceProfile.CODING

    assert custom_controller.should_switch(general, coding, 4) is False
    assert custom_controller.should_switch(general, coding, 5) is True


def test_should_switch_never_raises(controller):
    for count in (-5, 0, 1, 2, 100):
        for profile_a in WorkspaceProfile:
            for profile_b in WorkspaceProfile:
                controller.should_switch(profile_a, profile_b, count)  # must not raise
