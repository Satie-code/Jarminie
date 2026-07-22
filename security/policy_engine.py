"""Permission Policy Engine — real per-ActionType risk classification,
replacing Sprint 4.1's placeholder (PermissionGate's own always-ALLOW
stub never consulted anything like this). See
docs/sprint_book/sprint_4_7.md.

RiskLevel is deliberately distinct from decision.priority_queue's
PriorityLevel (Sprint 3.10) — Sprint 4.1's own flagged Potential Risk:
"risk_hint reuses PriorityLevel rather than a new enum... conflates
'how urgent' with 'how risky'." This class is that new, dedicated
RiskLevel, resolving that flag.

Built-in RiskLevel defaults are a reasoned but unavoidably subjective
judgment call (e.g. WINDOW_CLOSE is MEDIUM, not LOW, since it's the one
genuinely destructive-shaped window operation — see Sprint 4.4's own
Architecture Notes) — config-overridable via SecurityConfig.risk_policies
specifically because of this, the same discipline as every other
tuned-weight/threshold in this codebase.

ActionType is imported only under TYPE_CHECKING, never at real runtime:
device_control.action_engine imports security.permission_gate (which
imports security.confirmation_service, which imports this module) at
its own top level, so a real runtime import of ActionType here would
create a device_control<->security circular import. _DEFAULT_RISK_LEVELS
is therefore keyed by plain ActionType.value strings, not the enum
itself — classify()/is_hard_denied() read action_type.value (duck
typing, no import needed) rather than using the enum as a dict key
directly. Matches the same function-local-import idiom
device_control/resource_gate.py and device_control/action_engine.py
already established for this exact class of problem (Sprint 4.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from config.schema import SecurityConfig
from core.logging_setup import get_logger

if TYPE_CHECKING:
    from device_control.action_engine import ActionType

logger = get_logger(__name__)


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_REQUIRES_CONFIRMATION: frozenset[RiskLevel] = frozenset({RiskLevel.MEDIUM, RiskLevel.HIGH})

_DEFAULT_RISK_LEVELS: dict[str, RiskLevel] = {
    "launch_application": RiskLevel.LOW,
    "window_focus": RiskLevel.LOW,
    "window_move": RiskLevel.LOW,
    "window_resize": RiskLevel.LOW,
    "window_minimize": RiskLevel.LOW,
    "file_create": RiskLevel.LOW,
    "folder_create": RiskLevel.LOW,
    "close_application": RiskLevel.MEDIUM,
    "window_close": RiskLevel.MEDIUM,
    "file_move": RiskLevel.MEDIUM,
    "file_copy": RiskLevel.MEDIUM,
    "file_rename": RiskLevel.MEDIUM,
    "file_delete": RiskLevel.HIGH,
    "folder_delete": RiskLevel.HIGH,
    "system_command": RiskLevel.HIGH,
    "workflow_step": RiskLevel.HIGH,
}

_FALLBACK_RISK_LEVEL = RiskLevel.MEDIUM
"""Used only for an ActionType.value with no entry in
_DEFAULT_RISK_LEVELS above (a real ActionType added later without this
table being updated) — MEDIUM, not LOW, since requiring confirmation
for an unclassified action is the safer default (fail safe-down)."""


@dataclass
class RiskPolicy:
    """requires_confirmation is derived (True for MEDIUM/HIGH, False for
    LOW) but stored explicitly rather than recomputed everywhere, so a
    future config override could in principle decouple the two without
    a structural change."""

    action_type: ActionType
    risk_level: RiskLevel
    requires_confirmation: bool


class PermissionPolicyEngine:
    """Constructor DI: (security_config). classify()/is_hard_denied()
    compute their answer on demand (not pre-built into a table at
    construction) since this module deliberately has no real ActionType
    values available to iterate over — see this module's own docstring.

    An invalid security_config.risk_policies override value (a typo
    config/schema.py's own validation didn't already reject at load
    time) logs a warning and keeps the built-in default rather than
    raising — a bad risk-policy override degrading to the safer,
    already-reviewed default is preferable to a startup crash.
    """

    def __init__(self, security_config: SecurityConfig) -> None:
        self._config = security_config

    def classify(self, action_type: ActionType) -> RiskPolicy:
        default_level = _DEFAULT_RISK_LEVELS.get(action_type.value, _FALLBACK_RISK_LEVEL)
        risk_level = default_level
        override = self._config.risk_policies.get(action_type.value)
        if override is not None:
            try:
                risk_level = RiskLevel(override)
            except ValueError:
                logger.warning(
                    "Invalid security.risk_policies override for %s: %r — keeping default %s",
                    action_type.value,
                    override,
                    default_level.value,
                )
        return RiskPolicy(
            action_type=action_type,
            risk_level=risk_level,
            requires_confirmation=risk_level in _REQUIRES_CONFIRMATION,
        )

    def is_hard_denied(self, action_type: ActionType) -> bool:
        return action_type.value in self._config.hard_denylist
