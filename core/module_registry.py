"""Module registry — tracks the subsystems Core Manager orchestrates.

See docs/sprint_book/sprint_1_5.md for the ManagedModule contract rationale.
"""

import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


class ManagedModule(Protocol):
    """Contract every Core-managed subsystem implements.

    Kept deliberately minimal (3 methods) to avoid over-fitting to
    subsystems that don't exist yet — see Potential Risks in
    docs/sprint_book/sprint_1_5.md regarding subsystems whose lifecycle
    (e.g. Voice Engine's dormant-until-wake-word state) may not map
    cleanly onto simple start/stop; revisit at Sprint 2.1 if so.
    """

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def health_check(self) -> bool: ...


class ServiceState(Enum):
    """Lifecycle states a LazyModule can occupy — richer than ModuleState's
    four values below, which only describe CoreManager's own start()/
    stop() bookkeeping and have no vocabulary for "constructed but never
    loaded," "loaded but currently idle," or "actively serving a request
    right now." Introduced for the Runtime Refactor Sprint's Runtime
    Phase 2 — exactly the revisit ManagedModule's own docstring above
    anticipated ("subsystems whose lifecycle...may not map cleanly onto
    simple start/stop").

    NOT_LOADED: constructed, never started.
    LOADING: start() is in flight (a real, possibly slow model load).
    READY: loaded, idle, not currently serving anything.
    ACTIVE: loaded and actively serving a request right now — never a
    valid eviction target (see RuntimeManager, Runtime Phase 9).
    IDLE: loaded, not active, has sat unused long enough to become an
    idle-unload candidate — distinct from READY so a freshly-warmed
    service isn't immediately eligible for eviction.
    SUSPENDED: unloaded by RuntimeManager's own resource-pressure
    eviction or idle-timeout sweep (Runtime Phase 9), as opposed to
    UNLOADED's stop()-was-called meaning below.
    UNLOADED: stop() has run; the module's own resources are released.
    """

    NOT_LOADED = "not_loaded"
    LOADING = "loading"
    READY = "ready"
    ACTIVE = "active"
    IDLE = "idle"
    SUSPENDED = "suspended"
    UNLOADED = "unloaded"


class LazyModule(Protocol):
    """Extended contract for a subsystem RuntimeManager (core/
    runtime_manager.py) can actually govern the timing of, beyond
    CoreManager's plain ManagedModule. A strict superset — every
    LazyModule also structurally satisfies ManagedModule (same start()/
    stop()/health_check()), so a module implementing this Protocol can
    still be registered with CoreManager exactly like any other module
    and behaves identically until RuntimeManager starts treating it as
    lazy/tiered — see that module's own docstring for the "legacy modules
    keep today's eager behavior unchanged" default this Protocol exists
    to opt out of, one subsystem at a time.

    mark_idle_timeout()'s real caller arrives with Runtime Phase 9 (idle
    unloading) — declared here now so every Runtime Phase from here on
    implements against one stable Protocol rather than widening it
    per-phase.
    """

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def health_check(self) -> bool: ...

    def state(self) -> ServiceState: ...

    def last_used_at(self) -> datetime | None: ...

    def mark_idle_timeout(self, seconds: float) -> None: ...


class ModuleState(Enum):
    REGISTERED = "registered"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class _ModuleEntry:
    module: ManagedModule
    state: ModuleState = ModuleState.REGISTERED


class ModuleRegistry:
    """Tracks registered modules, their instances, and current state.

    Preserves registration order (relies on dict ordering) since
    CoreManager starts modules in that order and stops them in reverse.
    """

    def __init__(self) -> None:
        self._entries: dict[str, _ModuleEntry] = {}
        # Runtime Phase 4 (Runtime Refactor Sprint): guards every read/
        # write below. Before this phase, this class was only ever
        # touched from one thread — main.py's own synchronous startup()
        # loop. Phase 4 makes CoreManager.startup_tier() run Tier B/C on
        # a real background thread while the main/Qt thread's own
        # ui/status_panel.py QTimer keeps polling module_states()/
        # check_resources() concurrently — the first genuine multi-thread
        # access to this class's state. An RLock (not a plain Lock) since
        # re-entrancy costs nothing here and removes a whole class of
        # future deadlock-by-refactor risk if a locked method ever calls
        # another locked method on the same instance.
        self._lock = threading.RLock()

    def register(self, name: str, module: ManagedModule) -> None:
        with self._lock:
            if name in self._entries:
                raise ValueError(f"Module already registered: {name}")
            self._entries[name] = _ModuleEntry(module=module)

    def get(self, name: str) -> ManagedModule:
        with self._lock:
            return self._entries[name].module

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._entries

    def names(self) -> list[str]:
        with self._lock:
            return list(self._entries.keys())

    def state_of(self, name: str) -> ModuleState:
        with self._lock:
            return self._entries[name].state

    def set_state(self, name: str, state: ModuleState) -> None:
        with self._lock:
            self._entries[name].state = state

    def states(self) -> dict[str, str]:
        with self._lock:
            return {name: entry.state.value for name, entry in self._entries.items()}
