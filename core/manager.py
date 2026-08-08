"""JARMINEI Core — the orchestrator.

Lifecycle: a module is register_module()'d (state REGISTERED) -> startup()
calls start() on every registered module in registration order (state
RUNNING, or FAILED if start() raised) -> the app runs -> shutdown() calls
stop() on every module in reverse order (state STOPPED, or FAILED if stop()
raised). restart_module() stops then starts a single module without
touching the others.

Deliberately thin: Part 2 states Core's "primary purpose is orchestration"
with "minimal business logic." If a future sprint finds itself putting
decision logic (persona switching, intent handling, etc.) here, that logic
belongs in the relevant subsystem instead — Single Responsibility Rule.
See docs/sprint_book/sprint_1_5.md.
"""

import logging
import time

import psutil

from config.loader import ConfigLoader
from config.schema import AppConfig, UIConfig
from core.logging_setup import get_logger
from core.module_registry import ManagedModule, ModuleRegistry, ModuleState
from core.resource_monitor import ResourceMonitor, ResourceSnapshot
from core.runtime_manager import RuntimeManager, ServiceTier

logger = get_logger(__name__)

_process = psutil.Process()
"""Runtime Phase 1 (Baseline & Instrumentation) — cached once per process
rather than re-constructed per sample, since psutil.Process() itself does
a small amount of setup work; .memory_info() on an existing handle is
cheap. Used only for informational RSS-delta logging around module
start()/stop() and full startup()/shutdown() — never for any control-flow
decision (that arrives with a later Runtime Phase's resource-triggered
eviction logic)."""


def _rss_mb() -> float:
    return _process.memory_info().rss / (1024 * 1024)


class CoreManager:
    """Orchestrates JARMINEI's subsystems.

    Owns startup/shutdown sequencing, module registration, and — per the
    recommendation accepted after Sprint 1.4 — the resource-sampling
    cadence: check_resources() is the single place that decides how a
    reading is taken. It does not itself run a timer/thread; no event
    loop exists yet to drive one (that arrives with the GUI in Sprint
    1.6 / Status Panel in 1.7). Callers own *when* to call it; Core owns
    *how*.
    """

    def __init__(
        self,
        config: AppConfig,
        resource_monitor: ResourceMonitor,
        config_loader: ConfigLoader,
        runtime_manager: RuntimeManager | None = None,
    ) -> None:
        # `config` was unused when first added in Sprint 1.5 (retained for
        # forward compatibility per the documented constructor shape) —
        # ui_config() (1.7) and config() (1.8) are its real uses.
        self._config = config
        self._resource_monitor = resource_monitor
        self._config_loader = config_loader
        # Runtime Phase 3 (Runtime Refactor Sprint): keyword-only, defaults
        # to a fresh RuntimeManager() when the caller doesn't supply one —
        # keeps every existing 3-positional-arg construction site (this
        # class's own tests, tests/system/conftest.py, main.py today)
        # working completely unchanged. Purely additive wiring: nothing
        # below this point changes startup()'s observable order/behavior
        # yet — see register_module()'s own docstring.
        self._runtime_manager = runtime_manager if runtime_manager is not None else RuntimeManager()
        self._registry = ModuleRegistry()

    def register_module(
        self,
        name: str,
        module: ManagedModule,
        tier: ServiceTier | None = None,
        lazy: bool = False,
        idle_timeout_seconds: float | None = None,
    ) -> None:
        """Registers `module` with both the existing ModuleRegistry
        (unchanged — still the sole source of truth for ModuleState/
        start()-stop()-health_check() bookkeeping) and the new
        RuntimeManager (Runtime Phase 2), which tracks tier/lazy metadata
        for later Runtime Phases to act on.

        tier defaults to ServiceTier.ALWAYS_LOADED and lazy defaults to
        False when the caller doesn't specify otherwise — every one of
        today's 27 real call sites in main.py passes neither, so every
        existing module is tracked as "always loaded, not lazy" by
        default (this refactor's own governing principle: "anything not
        explicitly made lazy keeps today's eager behavior"). startup()
        still iterates ModuleRegistry in plain registration order,
        unchanged — RuntimeManager's tier/lazy bookkeeping has no live
        consumer for STARTUP ORDER yet (that arrived with Runtime Phase 4);
        idle_timeout_seconds (Runtime Phase 9) is forwarded straight
        through to RuntimeManager.register() unchanged — see that
        method's own docstring."""
        self._registry.register(name, module)
        self._runtime_manager.register(
            name,
            module,
            tier if tier is not None else ServiceTier.ALWAYS_LOADED,
            lazy=lazy,
            idle_timeout_seconds=idle_timeout_seconds,
        )
        logger.info("Module registered: %s", name)

    def startup(self) -> None:
        logger.info("JARMINEI Core starting up...")
        started_at = time.monotonic()
        info_enabled = logger.isEnabledFor(logging.INFO)
        start_rss_mb = _rss_mb() if info_enabled else 0.0
        for name in self._registry.names():
            self._start_module(name)
        elapsed = time.monotonic() - started_at
        if info_enabled:
            end_rss_mb = _rss_mb()
            logger.info(
                "JARMINEI Core startup complete. %d module(s) registered. "
                "Took %.3fs, RSS %.1f -> %.1f MB (%+.1f MB).",
                len(self._registry.names()),
                elapsed,
                start_rss_mb,
                end_rss_mb,
                end_rss_mb - start_rss_mb,
            )
        else:
            logger.info(
                "JARMINEI Core startup complete. %d module(s) registered. Took %.3fs.",
                len(self._registry.names()),
                elapsed,
            )

    def startup_tier(self, tier: ServiceTier) -> None:
        """Starts every registered module whose RuntimeManager tier
        matches `tier`, in the same relative order register_module() was
        called for them — a stable partition of the full registration
        order, never a re-sort (Runtime Refactor Sprint governing
        principle 4: documented ordering invariants elsewhere in this app,
        e.g. microphone before wake_word_detector, depend on this holding
        for any single tier's own subset).

        Deliberately separate from startup() (above), which is untouched
        and keeps starting every registered module in one pass, in plain
        registration order, ignoring tier entirely — every existing
        caller of the whole-graph startup() (this project's own test
        suite, and any future caller that doesn't care about tiers) keeps
        working exactly as before. startup_tier()'s own real caller is
        ui/app.py's run_app() (Runtime Phase 4): Tier A (ALWAYS_LOADED)
        runs synchronously via this method before window.show(), then a
        background thread calls this method again for WARM and COLD.
        """
        started_at = time.monotonic()
        names_in_tier = [
            name for name in self._registry.names() if self._runtime_manager.tier_of(name) is tier
        ]
        for name in names_in_tier:
            self._start_module(name)
        elapsed = time.monotonic() - started_at
        logger.info(
            "Tier %s startup complete. %d module(s) started. Took %.3fs.",
            tier.value,
            len(names_in_tier),
            elapsed,
        )

    def shutdown(self) -> None:
        logger.info("JARMINEI Core shutting down...")
        started_at = time.monotonic()
        info_enabled = logger.isEnabledFor(logging.INFO)
        start_rss_mb = _rss_mb() if info_enabled else 0.0
        for name in reversed(self._registry.names()):
            self._stop_module(name)
        elapsed = time.monotonic() - started_at
        if info_enabled:
            end_rss_mb = _rss_mb()
            logger.info(
                "JARMINEI Core shutdown complete. Took %.3fs, RSS %.1f -> %.1f MB (%+.1f MB).",
                elapsed,
                start_rss_mb,
                end_rss_mb,
                end_rss_mb - start_rss_mb,
            )
        else:
            logger.info("JARMINEI Core shutdown complete. Took %.3fs.", elapsed)

    def restart_module(self, name: str) -> bool:
        """Stop then start a single module. Used when a caller decides,
        typically from check_health() reporting failure, that a module
        needs restarting — restarting is a separate decision from
        detecting the failure (Single Responsibility)."""
        if not self._registry.has(name):
            logger.error("restart_module called for unregistered module: %s", name)
            return False
        logger.warning("Restarting module: %s", name)
        self._stop_module(name)
        return self._start_module(name)

    def check_health(self, name: str) -> bool:
        """Safely check one module's health; an exception counts as unhealthy
        rather than propagating (Fail Gracefully Rule). An unregistered
        name is treated the same way — a caller passing a stale/wrong name
        must never crash Core, it should just learn the module is
        unhealthy (in this case, nonexistent)."""
        if not self._registry.has(name):
            logger.error("check_health called for unregistered module: %s", name)
            return False
        module = self._registry.get(name)
        try:
            return module.health_check()
        except Exception:
            logger.exception("Health check failed for module: %s", name)
            return False

    def check_resources(self) -> ResourceSnapshot:
        """Sample resource usage via the injected ResourceMonitor."""
        return self._resource_monitor.sample()

    def module_states(self) -> dict[str, str]:
        """Read-only view of every registered module's current state."""
        return self._registry.states()

    def ui_config(self) -> UIConfig:
        """Expose the UI-relevant config slice, so UI-layer widgets (e.g.
        Status Panel) only need a CoreManager, never a direct AppConfig
        reference — keeps the Sprint 1.6 DI boundary intact."""
        return self._config.ui

    def config(self) -> AppConfig:
        """Expose the full current AppConfig. Broader than ui_config()'s
        narrow slice because Settings Window (Sprint 1.8) edits every
        section, not just one subsystem's."""
        return self._config

    def config_loader(self) -> ConfigLoader:
        """Expose the ConfigLoader so Settings Window can persist edits
        through the single established save path (Sprint 1.2) rather than
        Core Manager reimplementing config I/O itself."""
        return self._config_loader

    def runtime_manager(self) -> RuntimeManager:
        """Expose the RuntimeManager collaborator (Runtime Phase 3) —
        read-only access for diagnostics and tests. Every module
        registered via register_module() is also registered here; see
        that method's own docstring for today's ALWAYS_LOADED/non-lazy
        defaults. ui/runtime_diagnostics_panel.py's RuntimeDiagnosticsPanel
        (Runtime Phase 10) is this accessor's real UI caller, opened as
        its own window via MainWindow's Debug menu — the same
        "read-only, never mutates" discipline core/runtime_manager.py's
        own docstring already establishes for the underlying class."""
        return self._runtime_manager

    def _start_module(self, name: str) -> bool:
        module = self._registry.get(name)
        started_at = time.monotonic()
        # RSS sampling is gated behind isEnabledFor() rather than paid
        # unconditionally: psutil.Process().memory_info() is a real
        # syscall, and 27 modules x 2 samples adds up — paying it even
        # when nothing will ever read the resulting log line measurably
        # widened a real timing-sensitive window in tests/system's
        # acceptance tests (reproduced and fixed during Runtime Phase 1
        # of the Runtime Refactor Sprint Book: two full-suite runs failed
        # the same real-timing test with unconditional sampling, zero
        # failures with it gated).
        info_enabled = logger.isEnabledFor(logging.INFO)
        rss_before_mb = _rss_mb() if info_enabled else 0.0
        try:
            module.start()
            elapsed = time.monotonic() - started_at
            self._registry.set_state(name, ModuleState.RUNNING)
            if info_enabled:
                logger.info(
                    "Module started: %s (%.3fs, %+.1f MB RSS)",
                    name,
                    elapsed,
                    _rss_mb() - rss_before_mb,
                )
            return True
        except Exception:
            elapsed = time.monotonic() - started_at
            self._registry.set_state(name, ModuleState.FAILED)
            logger.exception("Module failed to start: %s (after %.3fs)", name, elapsed)
            return False

    def _stop_module(self, name: str) -> bool:
        module = self._registry.get(name)
        started_at = time.monotonic()
        info_enabled = logger.isEnabledFor(logging.INFO)
        rss_before_mb = _rss_mb() if info_enabled else 0.0
        try:
            module.stop()
            elapsed = time.monotonic() - started_at
            self._registry.set_state(name, ModuleState.STOPPED)
            if info_enabled:
                logger.info(
                    "Module stopped: %s (%.3fs, %+.1f MB RSS)",
                    name,
                    elapsed,
                    _rss_mb() - rss_before_mb,
                )
            return True
        except Exception:
            elapsed = time.monotonic() - started_at
            self._registry.set_state(name, ModuleState.FAILED)
            logger.exception("Module failed to stop cleanly: %s (after %.3fs)", name, elapsed)
            return False
