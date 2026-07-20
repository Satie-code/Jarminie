"""ConfidenceScorer — the Dynamic Memory Formula in full, per
02_System_Architecture.md: "Every memory receives a confidence score.
Factors: Frequency, Recency, Importance, Category, Emotional
significance." Score bands: 0-29 Temporary, 30-49 Short-term, 50-69
Monthly review, 70-89 Long-term, 90-100 Permanent. Also implements the
User Override Rule: an explicit "remember this"/"never forget this"/"this
is important" immediately grants maximum confidence.

A pure, stateless-per-call class (no MemoryStore dependency) — it scores
whatever MemoryRecord it's handed; persisting the result is the caller's
job (Sprint 3.6's MemoryLifecycleManager, at scale).

Importance has no term in score()'s weighted formula below. Its only real
signal is the User Override Rule itself, handled as a total short-circuit
(a user_override=True record always scores exactly 100.0, before the
formula runs at all) rather than a weighted input — Part 2 says an
override "immediately receives maximum confidence," not "a boosted
score." importance_weight still counts toward MemoryConfig's five-weight
sum (documenting what "full confidence" is built from), but is never
multiplied against anything in the code path that actually executes when
user_override is False. The practical effect: an un-overridden record's
score can never exceed (frequency_weight + recency_weight + category_weight
+ emotional_weight) * 100 = 80 with the default weights — the Long-term
band's ceiling. Reaching Permanent (90-100) requires either an explicit
user override or Event Memory's separate is_permanent flag (Sprint 3.3),
never the ordinary formula alone. See config/schema.py's MemoryConfig
docstring and docs/sprint_book/sprint_3_5.md's Engineering Decisions.

Emotional significance is a fixed neutral placeholder (_NEUTRAL_EMOTIONAL_
SIGNIFICANCE below), not a real signal — Level 5's Emotion Engine (Phase
5.1) doesn't exist yet. Documented here plainly so no score is mistaken
for being emotionally informed before Sprint 5.2 exists.
"""

from dataclasses import replace
from datetime import UTC, datetime
from enum import Enum

from config.schema import MemoryConfig
from memory.models import MemoryRecord

# "No information available" — the deliberate midpoint of the [0, 1] range
# every other factor is expressed in, not a real emotional assessment.
# The single integration point for Sprint 5.2 (Emotion Inference) to
# replace with a real signal.
_NEUTRAL_EMOTIONAL_SIGNIFICANCE = 0.5


class ConfidenceBand(Enum):
    """Part 2's five confidence bands, ascending score order."""

    TEMPORARY = "temporary"
    SHORT_TERM = "short_term"
    MONTHLY_REVIEW = "monthly_review"
    LONG_TERM = "long_term"
    PERMANENT = "permanent"


class ConfidenceScorer:
    """Constructor DI: receives the MemoryConfig it depends on rather than
    constructing it. Not a ManagedModule — owns no resource of its own
    (same reasoning as ContextManager, Sprint 2.8)."""

    def __init__(self, memory_config: MemoryConfig) -> None:
        self._memory_config = memory_config

    def score(self, record: MemoryRecord) -> float:
        """Return record's confidence score, 0.0-100.0.

        user_override=True short-circuits to exactly 100.0, unchanged —
        the User Override Rule's "automatic deletion is disabled" implies
        the score itself must not silently drift back down either.
        Otherwise: a weighted sum of frequency (diminishing-returns curve
        over access_count), recency (exponential decay over
        last_accessed_at using recency_half_life_days), and category
        (category_importance lookup, falling back to
        category_default_weight), plus the fixed emotional placeholder —
        see this module's own docstring for why importance contributes no
        term here.

        Sprint 3.13 (Error Handling & Recovery Hardening) reviewed this
        method against two named edge cases — a record with
        last_accessed_at == created_at (zero elapsed time) and
        access_count == 0 (freshly-created, never-yet-read) — and found
        both already handled correctly with no code change needed:
        frequency_factor's denominator is access_count + 1 (never zero),
        and elapsed_days only ever appears in recency_factor's numerator,
        not its denominator (recency_half_life_days, the denominator, is
        a config value already validated > 0 at the config layer, not a
        per-record field). See
        tests/unit/memory/test_confidence_scorer.py's own
        test_zero_elapsed_time_since_last_accessed_does_not_raise and
        test_access_count_zero_produces_a_valid_low_frequency_term."""
        if record.user_override:
            return 100.0

        frequency_factor = record.access_count / (record.access_count + 1)

        elapsed_days = (
            datetime.now(UTC) - record.last_accessed_at
        ).total_seconds() / 86400
        recency_factor = 0.5 ** (elapsed_days / self._memory_config.recency_half_life_days)

        category_factor = self._memory_config.category_importance.get(
            record.category, self._memory_config.category_default_weight
        )

        emotional_factor = _NEUTRAL_EMOTIONAL_SIGNIFICANCE

        weighted = (
            frequency_factor * self._memory_config.frequency_weight
            + recency_factor * self._memory_config.recency_weight
            + category_factor * self._memory_config.category_weight
            + emotional_factor * self._memory_config.emotional_weight
        )
        return max(0.0, min(100.0, weighted * 100))

    def band(self, score: float) -> ConfidenceBand:
        """Pure range lookup against Part 2's five bands."""
        if score < 30:
            return ConfidenceBand.TEMPORARY
        if score < 50:
            return ConfidenceBand.SHORT_TERM
        if score < 70:
            return ConfidenceBand.MONTHLY_REVIEW
        if score < 90:
            return ConfidenceBand.LONG_TERM
        return ConfidenceBand.PERMANENT

    def detect_override_phrase(self, transcript: str) -> bool:
        """Case-insensitive substring match against
        MemoryConfig.override_trigger_phrases — identical technique to
        PersonaManager.detect_explicit_selection() (Sprint 2.11)."""
        lowered = transcript.lower()
        return any(
            phrase.lower() in lowered
            for phrase in self._memory_config.override_trigger_phrases
        )

    def apply_user_override(self, record: MemoryRecord) -> MemoryRecord:
        """Return a new record with confidence_score=100.0,
        user_override=True — does not mutate the input. The caller
        (Sprint 3.6, or Sprint 3.12's later integration) is responsible
        for persisting it via MemoryStore.update_confidence()."""
        return replace(record, confidence_score=100.0, user_override=True)
