"""MemoryLifecycleManager — turns Sprint 3.5's confidence bands into real
lifecycle behavior, per 04_Master_Implementation_Plan.md's Phase 3.2
tasks: "Confidence Score. User Override. Automatic cleanup. Monthly
review."

Band-to-action mapping (02_System_Architecture.md's Dynamic Memory
Formula bands):

    0-29   Temporary        run_cleanup_pass() deletes, once past
                             cleanup_grace_period_days
    30-49  Short-term       rescored only, left alone
    50-69  Monthly review   surfaced by run_monthly_review() for a human;
                             never mutated automatically
    70-89  Long-term        rescored only, left alone
    90-100 Permanent        reachable only via explicit user override or
                             Event Memory's is_permanent flag (Sprint 3.5's
                             own design) — never touched by either method
                             here regardless of band

is_permanent=True (Event Memory, Sprint 3.3) and user_override=True
(Sprint 3.5) records are structurally excluded from both run_cleanup_pass()
and run_monthly_review() — checked first, before a record is even
considered a candidate, not as an afterthought filter.

No periodic caller exists yet for either method. Sprint 3.12 (Decision
Engine Integration) invokes both once at startup — from start() itself:
CoreManager.startup() calls every registered module's start() once, in
registration order, and main.py registers this module after MemoryStore,
so start() is the one hook guaranteed to run exactly once, exactly after
MemoryStore is ready, without requiring any change to CoreManager or
ui/app.py (both outside this sprint's own Files to Modify). A real
recurring cadence is deferred to Sprint 4.9 (Reminder Engine) or wherever
APScheduler is first wired in — the same still-open gap already tracked
for ConversationSessionStore.purge_older_than() in
docs/backlog/technical_debt.md item 11 (see the new item this sprint adds
alongside it).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from config.schema import MemoryConfig
from core.logging_setup import get_logger
from memory.confidence_scorer import ConfidenceBand, ConfidenceScorer
from memory.memory_store import MemoryStore
from memory.models import MemoryRecord, MemoryType

logger = get_logger(__name__)

# MemoryStore.recent() requires an explicit limit — large enough that no
# realistic live record count per type would be truncated, the same
# reasoning as EventMemory/ShortTermMemory's _LARGE_LIMIT (Sprints 3.3/3.4).
_LARGE_LIMIT = 10_000

# Every MemoryType is scanned; is_permanent/user_override exclusion (not a
# MemoryType-level assumption) is what actually keeps Event Memory records
# out of both passes — see this module's own docstring.
_ALL_MEMORY_TYPES = tuple(MemoryType)


@dataclass
class CleanupReport:
    records_rescored: int = 0
    records_deleted: int = 0
    deleted_record_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ReviewReport:
    records: list[MemoryRecord]
    generated_at: datetime


class MemoryLifecycleManager:
    """Constructor DI: receives MemoryStore, ConfidenceScorer, and
    MemoryConfig rather than constructing any of them.

    A ManagedModule despite owning no resource of its own — start()/stop()
    log only; health_check() delegates to memory_store.health_check()
    rather than duplicating a liveness check MemoryStore already owns."""

    def __init__(
        self,
        memory_store: MemoryStore,
        confidence_scorer: ConfidenceScorer,
        memory_config: MemoryConfig,
    ) -> None:
        self._memory_store = memory_store
        self._confidence_scorer = confidence_scorer
        self._memory_config = memory_config

    def start(self) -> None:
        """Runs both lifecycle passes exactly once — see this module's
        own docstring for why start() is the correct, only-available hook
        for a startup-time-only invocation at this point in the codebase.
        Neither pass's own exceptions are expected to escape (both
        already catch per-record failures internally), so no additional
        try/except is added here — consistent with this sprint wiring
        the happy path first, hardening deferred to Sprint 3.13."""
        cleanup_report = self.run_cleanup_pass()
        review_report = self.run_monthly_review()
        logger.info(
            "Memory lifecycle manager started. Startup cleanup pass: %d rescored, "
            "%d deleted, %d error(s). Startup monthly review: %d record(s) surfaced.",
            cleanup_report.records_rescored,
            cleanup_report.records_deleted,
            len(cleanup_report.errors),
            len(review_report.records),
        )

    def stop(self) -> None:
        logger.info("Memory lifecycle manager stopped.")

    def health_check(self) -> bool:
        return self._memory_store.health_check()

    def run_cleanup_pass(self) -> CleanupReport:
        """Rescore every non-permanent, non-override record; delete any
        that land in the Temporary band once older than
        cleanup_grace_period_days. A single record's failure is caught,
        logged, and recorded in errors — the pass continues (Fail
        Gracefully at the per-record level, mirroring
        CoreManager.restart_module()'s isolation, Sprint 1.5)."""
        report = CleanupReport()
        now = datetime.now(UTC)
        for memory_type in _ALL_MEMORY_TYPES:
            for record in self._memory_store.recent(memory_type, limit=_LARGE_LIMIT):
                if record.is_permanent or record.user_override:
                    continue
                try:
                    self._rescore_and_maybe_delete(record, now, report)
                except Exception as exc:
                    message = f"Failed to process memory record {record.id}: {exc}"
                    logger.exception(message)
                    report.errors.append(message)
        return report

    def _rescore_and_maybe_delete(
        self, record: MemoryRecord, now: datetime, report: CleanupReport
    ) -> None:
        old_band = self._confidence_scorer.band(record.confidence_score)
        new_score = self._confidence_scorer.score(record)
        new_band = self._confidence_scorer.band(new_score)
        band_entered_at = now if new_band != old_band else record.band_entered_at

        self._memory_store.update_confidence(
            record.id, new_score, band_entered_at=band_entered_at
        )
        report.records_rescored += 1

        if new_band == ConfidenceBand.TEMPORARY:
            age_days = (now - record.created_at).total_seconds() / 86400
            if age_days > self._memory_config.cleanup_grace_period_days:
                self._memory_store.delete(record.id)
                report.records_deleted += 1
                report.deleted_record_ids.append(record.id)

    def run_monthly_review(self) -> ReviewReport:
        """A pure read query for records currently in the Monthly-review
        band that have sat there for at least monthly_review_min_band_days
        (MemoryRecord.band_entered_at). Performs zero writes — reads each
        record's already-persisted confidence_score/band_entered_at rather
        than rescoring anything."""
        now = datetime.now(UTC)
        matching: list[MemoryRecord] = []
        for memory_type in _ALL_MEMORY_TYPES:
            for record in self._memory_store.recent(memory_type, limit=_LARGE_LIMIT):
                if record.is_permanent or record.user_override:
                    continue
                if self._confidence_scorer.band(record.confidence_score) != (
                    ConfidenceBand.MONTHLY_REVIEW
                ):
                    continue
                days_in_band = (now - record.band_entered_at).total_seconds() / 86400
                if days_in_band >= self._memory_config.monthly_review_min_band_days:
                    matching.append(record)
        return ReviewReport(records=matching, generated_at=now)

    def apply_user_override(self, record_id: str) -> bool:
        """The real, persisted counterpart to ConfidenceScorer's pure
        apply_user_override(). Returns False (logged) if the record
        doesn't exist, rather than raising."""
        record = self._memory_store.get_by_id(record_id)
        if record is None:
            logger.warning("apply_user_override(): no such memory record %s.", record_id)
            return False
        overridden = self._confidence_scorer.apply_user_override(record)
        self._memory_store.update_confidence(
            record_id, overridden.confidence_score, user_override=overridden.user_override
        )
        return True
