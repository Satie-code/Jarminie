"""AdaptiveWorkspaceController (Sprint 5.12 — Level 5 Part A).

Makes Jarvis's dashboard rearrange itself for the user's current task —
Coding, Research, Study, Projects, General productivity — the brief's
own explicit requirement. Fills in the empty dashboard-panel container
Sprint 5.7 shipped as a placeholder (`JarvisRenderer.
apply_workspace_profile()`, this sprint's own Files to Modify).

**Config-driven keyword-to-layout mapping, not ML** — the identical,
deliberately-crude-and-named-as-such pattern this codebase already uses
for every comparable "classify a topic into a bucket" problem
(`PersonaManager.detect_context_heuristic()`'s topic keywords,
`MemoryConfig.short_term_salience_triggers`). `decision/context_analyzer.py`'s
`ContextAnalysis.primary_topic`/`mentioned_entities` (Sprint 3.8, already
real, already live) gives this sprint a topic signal for free —
`select_profile()` only maps that onto one of a small, fixed set of
`WorkspaceProfile`s. A real classifier would be new-feature-shaped work
this sprint doesn't need.

**Debounce, not a hair-trigger switch**: a single topic-shifted turn does
not necessarily justify a full dashboard rearrangement — visually
jarring on every minor topic drift within an otherwise-coding
conversation. `should_switch()` is a pure yes/no gate over a
caller-owned running consecutive-match count (Sprint 5.14 owns tracking
it live against real turns); this class holds no state of its own about
"how many turns in a row" — the one exception to "pure decision
function" purity here is none at all, unlike `GestureEngine`'s own
disclosed ambient-rate-limit state (Sprint 5.9).
"""

from enum import Enum

from config.schema import PresentationConfig
from decision.context_analyzer import ContextAnalysis


class WorkspaceProfile(Enum):
    """Declaration order is the tie-break order `select_profile()` uses
    when a `ContextAnalysis` matches more than one profile's keywords —
    deliberate and documented, not accidental. `GENERAL` is the
    safe-failure default: an unrecognized/ambiguous topic always
    resolves here, never a guess at one of the other four."""

    CODING = "coding"
    RESEARCH = "research"
    STUDY = "study"
    PROJECTS = "projects"
    GENERAL = "general"


class AdaptiveWorkspaceController:
    """Constructor DI per 03_Engineering_Standards.md: receives
    PresentationConfig only. Never reads `EmotionalState`/
    `PresentationState` — task context and emotional state are
    orthogonal signals (the brief itself separates "Adaptive Workspace"
    from the emotion-driven sprints), and conflating them here would
    make this class harder to reason about for no real benefit."""

    def __init__(self, presentation_config: PresentationConfig) -> None:
        self._config = presentation_config

    def select_profile(self, context_analysis: ContextAnalysis | None) -> WorkspaceProfile:
        """Never raises. `None` (a Decision Engine pipeline failure) or
        an empty `primary_topic`/`mentioned_entities` both resolve to
        `GENERAL`. Keyword-matches `primary_topic` and
        `mentioned_entities` (combined, case-insensitive substring, the
        same technique every comparable heuristic in this codebase
        already uses) against `PresentationConfig.
        workspace_profile_keywords`; the first matching profile in
        enum-declaration order wins on a tie."""
        if context_analysis is None:
            return WorkspaceProfile.GENERAL

        haystack = " ".join(
            part
            for part in (context_analysis.primary_topic, *context_analysis.mentioned_entities)
            if part
        ).lower()
        if not haystack:
            return WorkspaceProfile.GENERAL

        for profile in WorkspaceProfile:
            keywords = self._config.workspace_profile_keywords.get(profile.value, [])
            if any(keyword.lower() in haystack for keyword in keywords):
                return profile
        return WorkspaceProfile.GENERAL

    def should_switch(
        self,
        current: WorkspaceProfile,
        candidate: WorkspaceProfile,
        consecutive_match_count: int,
    ) -> bool:
        """A pure yes/no gate: candidate must genuinely differ from
        current, and consecutive_match_count must meet
        PresentationConfig.workspace_switch_debounce_turns. This method
        never tracks or mutates any count itself — the caller (Sprint
        5.14) owns that running total against real live turns."""
        if candidate == current:
            return False
        return consecutive_match_count >= self._config.workspace_switch_debounce_turns
