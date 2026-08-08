"""Runtime Manager — owns lazy-module lifecycle: registration, tier
bookkeeping, on-demand loading, and unloading.

The collaborator CoreManager delegates to once Runtime Phase 3 wires it
in; deliberately unwired from the real running app in this phase
(Runtime Phase 2) — nothing in main.py or core/manager.py constructs or
calls into this class yet, so it carries zero behavior-change risk to
the existing 27-module startup graph. Fully testable in isolation
against LazyModule test doubles.

See core/module_registry.py's own ServiceState/LazyModule docstrings for
the state vocabulary and extended contract this class operates on.

Runtime Phase 9: sweep_idle_services()/evict_least_recently_used() below
are the real idle-timeout/resource-pressure eviction mechanisms this
refactor's whole "unload what isn't being used" purpose has been
building toward since Phase 2 — both are pure mechanism, no policy about
WHEN to call them (that's CommunicationPipeline's own new housekeeping
TaskScheduler job, voice/pipeline.py, mirroring ResourceMonitor's own
"pure probe, doesn't decide what to throttle" separation).
"""

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from core.logging_setup import get_logger
from core.module_registry import LazyModule, ManagedModule, ServiceState

logger = get_logger(__name__)


class ServiceTier(Enum):
    """Module-loading priority — distinct from decision/priority_queue.py's
    PriorityLevel (conversational/announcement priority: SCHEDULED_REMINDER,
    WELLNESS, etc. — a different axis entirely, never to be conflated with
    this one, per the Runtime Refactor Sprint plan's own governing
    principle 3).

    ALWAYS_LOADED (Tier A): started synchronously before the window is
    shown and never unloaded — Core, Config, Logger, Wake Word,
    Microphone, UI, Security, Task Scheduler, and (per governing
    principle 2) every module this refactor doesn't explicitly name.
    WARM (Tier B): started on a background thread shortly after the
    window is shown (Runtime Phase 4), eligible for idle-unload (Runtime
    Phase 9's sweep_idle_services()/evict_least_recently_used(), below).
    COLD (Tier C): loaded strictly on first real use, eligible for
    idle-unload the same way.
    """

    ALWAYS_LOADED = "always_loaded"
    WARM = "warm"
    COLD = "cold"


@dataclass
class _ServiceEntry:
    module: ManagedModule
    tier: ServiceTier
    lazy: bool
    idle_timeout_seconds: float | None = None


class RuntimeManager:
    """Registers services alongside a ServiceTier and an explicit lazy
    flag, and — for the ones registered lazy=True — owns deciding when
    their start()/stop() actually run, via ensure_started()/
    stop_service() below.

    A legacy module (lazy=False) is tracked here for tier/diagnostics
    visibility only; RuntimeManager never calls start()/stop() on it
    itself — CoreManager already owns that module's exact timing,
    unchanged, per this refactor's own governing principle 2 ("anything
    not explicitly made lazy keeps today's eager behavior").
    """

    def __init__(self) -> None:
        self._entries: dict[str, _ServiceEntry] = {}
        # Runtime Phase 4: same reasoning as core/module_registry.py's
        # own ModuleRegistry._lock — RuntimeManager becomes reachable
        # from more than one thread once CoreManager.startup_tier() runs
        # Tier B/C in the background (ui/app.py's run_app()).
        self._lock = threading.RLock()

    def register(
        self,
        name: str,
        module: ManagedModule,
        tier: ServiceTier,
        lazy: bool = False,
        idle_timeout_seconds: float | None = None,
    ) -> None:
        """lazy=True asserts `module` also satisfies LazyModule (see
        core/module_registry.py) — RuntimeManager trusts this rather than
        checking defensively, since it's an internal contract between
        this class and the handful of subsystems later Runtime Phases
        convert, not a boundary against an unreliable external system
        (contrast decision/intent_detector.py's defensive getattr-based
        is_reachable() check, which guards a genuinely optional
        capability on an external client).

        idle_timeout_seconds (Runtime Phase 9) is meaningless for a
        non-lazy module (never eviction-eligible — see sweep_idle_
        services() below) and silently ignored for one; when given for a
        lazy module, it's both stored here (LazyModule's own Protocol has
        no getter for what mark_idle_timeout() stored, so RuntimeManager
        must remember its own value to compare last_used_at() against
        later) and forwarded via module.mark_idle_timeout(), so the
        module's own last_used_at()/state() bookkeeping and RuntimeManager's
        eviction decision always agree on the same configured value."""
        with self._lock:
            if name in self._entries:
                raise ValueError(f"Service already registered: {name}")
            self._entries[name] = _ServiceEntry(
                module=module, tier=tier, lazy=lazy, idle_timeout_seconds=idle_timeout_seconds
            )
            if lazy and idle_timeout_seconds is not None:
                lazy_module: LazyModule = module  # type: ignore[assignment]
                lazy_module.mark_idle_timeout(idle_timeout_seconds)
        logger.info("Service registered: %s (tier=%s, lazy=%s)", name, tier.value, lazy)

    def names(self) -> list[str]:
        with self._lock:
            return list(self._entries.keys())

    def tier_of(self, name: str) -> ServiceTier:
        with self._lock:
            return self._entries[name].tier

    def is_lazy(self, name: str) -> bool:
        with self._lock:
            return self._entries[name].lazy

    def state_of(self, name: str) -> ServiceState:
        """A legacy (lazy=False) module has no lifecycle vocabulary of its
        own beyond ManagedModule's plain start()/stop() — reported as
        READY unconditionally, reflecting that CoreManager (not this
        class) owns its exact timing."""
        with self._lock:
            entry = self._entries[name]
            if entry.lazy:
                lazy_module: LazyModule = entry.module  # type: ignore[assignment]
                return lazy_module.state()
            return ServiceState.READY

    def ensure_started(self, name: str) -> None:
        """Idempotent: starts `name` if it's lazy and not already loaded;
        no-ops for an already-READY/ACTIVE/LOADING lazy module or for a
        legacy module entirely (CoreManager already started it). This is
        the one method a future transparent proxy (Runtime Phase 5) calls
        before delegating to the real subsystem — "no subsystem should
        directly decide when it loads," this refactor's own founding
        requirement."""
        with self._lock:
            entry = self._entries[name]
            if not entry.lazy:
                return
            lazy_module: LazyModule = entry.module  # type: ignore[assignment]
            if lazy_module.state() in (
                ServiceState.NOT_LOADED,
                ServiceState.UNLOADED,
                ServiceState.SUSPENDED,
            ):
                logger.info("Loading service on demand: %s", name)
                lazy_module.start()

    def stop_service(self, name: str) -> None:
        """The unload half of ensure_started() — for a lazy module not
        already NOT_LOADED/UNLOADED, calls stop(). No-ops for a legacy
        module (CoreManager owns its stop() timing, unchanged). The real
        caller — an idle-timeout sweep or a ResourceMonitor-driven
        eviction — arrives with Runtime Phase 9; this method is the
        stable primitive that phase calls, not a feature in itself yet."""
        with self._lock:
            entry = self._entries[name]
            if not entry.lazy:
                return
            lazy_module: LazyModule = entry.module  # type: ignore[assignment]
            if lazy_module.state() not in (ServiceState.NOT_LOADED, ServiceState.UNLOADED):
                logger.info("Unloading service: %s", name)
                lazy_module.stop()

    def sweep_idle_services(self) -> list[str]:
        """Unloads every lazy, currently-READY service that has sat idle
        past its own configured idle_timeout_seconds. Returns the names
        actually evicted, for the caller's own logging/tests.

        Only READY is eligible — ACTIVE (a real call in flight) is never
        touched, the exact mid-request eviction race every LazyModule
        implementation's own state()/last_used_at() docstrings have been
        guarding against since Runtime Phase 5/6. A service with no
        idle_timeout_seconds configured (None — never passed at
        register() time) or that has never actually been used
        (last_used_at() still None) is never a sweep candidate; the
        latter can only happen for a WARM-but-not-yet-first-used service,
        which stop_service() would just reload again on next
        ensure_started() anyway, so there is nothing to save by evicting
        it early."""
        with self._lock:
            now = datetime.now(UTC)
            evicted: list[str] = []
            for name, entry in self._entries.items():
                if not entry.lazy or entry.idle_timeout_seconds is None:
                    continue
                lazy_module: LazyModule = entry.module  # type: ignore[assignment]
                if lazy_module.state() is not ServiceState.READY:
                    continue
                last_used = lazy_module.last_used_at()
                if last_used is None:
                    continue
                idle_seconds = (now - last_used).total_seconds()
                if idle_seconds < entry.idle_timeout_seconds:
                    continue
                logger.info(
                    "Idle-timeout sweep evicting %s (idle %.1fs >= %.1fs).",
                    name,
                    idle_seconds,
                    entry.idle_timeout_seconds,
                )
                self.stop_service(name)
                evicted.append(name)
            return evicted

    def evict_least_recently_used(self, max_count: int) -> list[str]:
        """Unloads up to `max_count` currently-READY lazy services, oldest
        last_used_at() first — the resource-pressure eviction mechanism.
        Pure mechanism, no policy: the caller (CommunicationPipeline's own
        new housekeeping job) decides WHEN to call this and how many to
        ask for, typically after ResourceMonitor.is_over_threshold()
        reports real pressure, the same "probe reports, something else
        decides" separation ResourceMonitor's own docstring already
        establishes. A service never actually used (last_used_at() is
        None) sorts first — pure dead weight, evicted before anything
        with real recent activity. Returns the names actually evicted,
        which may be fewer than max_count if fewer than that many
        READY lazy services exist."""
        with self._lock:
            candidates = [
                (name, entry.module.last_used_at())  # type: ignore[attr-defined]
                for name, entry in self._entries.items()
                if entry.lazy and entry.module.state() is ServiceState.READY  # type: ignore[attr-defined]
            ]
            candidates.sort(key=lambda item: item[1] or datetime.min.replace(tzinfo=UTC))
            evicted: list[str] = []
            for name, _ in candidates[:max_count]:
                logger.info("Resource-pressure eviction: %s", name)
                self.stop_service(name)
                evicted.append(name)
            return evicted
