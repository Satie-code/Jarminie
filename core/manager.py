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

from config.loader import ConfigLoader
from config.schema import AppConfig, UIConfig
from core.logging_setup import get_logger
from core.module_registry import ManagedModule, ModuleRegistry, ModuleState
from core.resource_monitor import ResourceMonitor, ResourceSnapshot

logger = get_logger(__name__)


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
        self, config: AppConfig, resource_monitor: ResourceMonitor, config_loader: ConfigLoader
    ) -> None:
        # `config` was unused when first added in Sprint 1.5 (retained for
        # forward compatibility per the documented constructor shape) —
        # ui_config() (1.7) and config() (1.8) are its real uses.
        self._config = config
        self._resource_monitor = resource_monitor
        self._config_loader = config_loader
        self._registry = ModuleRegistry()

    def register_module(self, name: str, module: ManagedModule) -> None:
        self._registry.register(name, module)
        logger.info("Module registered: %s", name)

    def startup(self) -> None:
        logger.info("JARMINEI Core starting up...")
        for name in self._registry.names():
            self._start_module(name)
        logger.info(
            "JARMINEI Core startup complete. %d module(s) registered.",
            len(self._registry.names()),
        )

    def shutdown(self) -> None:
        logger.info("JARMINEI Core shutting down...")
        for name in reversed(self._registry.names()):
            self._stop_module(name)
        logger.info("JARMINEI Core shutdown complete.")

    def restart_module(self, name: str) -> bool:
        """Stop then start a single module. Used when a caller decides,
        typically from check_health() reporting failure, that a module
        needs restarting — restarting is a separate decision from
        detecting the failure (Single Responsibility)."""
        logger.warning("Restarting module: %s", name)
        self._stop_module(name)
        return self._start_module(name)

    def check_health(self, name: str) -> bool:
        """Safely check one module's health; an exception counts as unhealthy
        rather than propagating (Fail Gracefully Rule)."""
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

    def _start_module(self, name: str) -> bool:
        module = self._registry.get(name)
        try:
            module.start()
            self._registry.set_state(name, ModuleState.RUNNING)
            logger.info("Module started: %s", name)
            return True
        except Exception:
            self._registry.set_state(name, ModuleState.FAILED)
            logger.exception("Module failed to start: %s", name)
            return False

    def _stop_module(self, name: str) -> bool:
        module = self._registry.get(name)
        try:
            module.stop()
            self._registry.set_state(name, ModuleState.STOPPED)
            logger.info("Module stopped: %s", name)
            return True
        except Exception:
            self._registry.set_state(name, ModuleState.FAILED)
            logger.exception("Module failed to stop cleanly: %s", name)
            return False
