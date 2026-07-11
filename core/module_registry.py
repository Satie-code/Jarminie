"""Module registry — tracks the subsystems Core Manager orchestrates.

See docs/sprint_book/sprint_1_5.md for the ManagedModule contract rationale.
"""

from dataclasses import dataclass
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

    def register(self, name: str, module: ManagedModule) -> None:
        if name in self._entries:
            raise ValueError(f"Module already registered: {name}")
        self._entries[name] = _ModuleEntry(module=module)

    def get(self, name: str) -> ManagedModule:
        return self._entries[name].module

    def names(self) -> list[str]:
        return list(self._entries.keys())

    def state_of(self, name: str) -> ModuleState:
        return self._entries[name].state

    def set_state(self, name: str, state: ModuleState) -> None:
        self._entries[name].state = state

    def states(self) -> dict[str, str]:
        return {name: entry.state.value for name, entry in self._entries.items()}
