"""Action Resource Gate — a second dispatch-time guard alongside
PermissionGate: refuses (never crashes or hangs) a resource-sensitive
action while the system is at CRITICAL resource pressure. See
docs/sprint_book/sprint_4_6.md.

A sample-on-dispatch check, not a periodic monitor: ResourceMonitor is
sampled immediately before a gated action executes, not on a
background timer. This matches backlog/technical_debt.md items
11/15/17's own established "no new timer infrastructure until Level 4
Part B's Scheduler exists" discipline — a real periodic cadence remains
that Scheduler's job, not this gate's.

Deliberately a separate class from security.permission_gate.PermissionGate
(Sprint 4.1), not merged into one "gate": they answer different
questions ("is this actor allowed to do this" vs. "is the system
healthy enough to do this right now") with different owners and
different config sections, so ActionRegistry.dispatch() consults both
in sequence rather than either delegating to the other.
"""

from __future__ import annotations

from enum import Enum

from config.schema import DeviceControlConfig
from core.logging_setup import get_logger
from core.resource_monitor import ResourceAlert, ResourceMonitor
from decision.priority_queue import PriorityQueueManager
from device_control.action_engine import ActionType

logger = get_logger(__name__)


class ResourceGateDecision(Enum):
    PROCEED = "proceed"
    BLOCKED_CRITICAL_RESOURCE = "blocked_critical_resource"


class ActionResourceGate:
    """Constructor DI: (resource_monitor, priority_queue_manager,
    device_control_config). Not a ManagedModule — no lifecycle, no
    background state, cheap to construct, the same judgment call
    already made for PermissionGate (Sprint 4.1).
    """

    def __init__(
        self,
        resource_monitor: ResourceMonitor,
        priority_queue_manager: PriorityQueueManager,
        device_control_config: DeviceControlConfig,
    ) -> None:
        self._resource_monitor = resource_monitor
        self._priority_queue_manager = priority_queue_manager
        self._config = device_control_config
        self._last_blocked_alerts: list[ResourceAlert] = []

    def check(self, action_type: ActionType) -> ResourceGateDecision:
        """PROCEED immediately if action_type isn't in
        resource_gate_action_types (the cheap-action exemption).
        Otherwise samples ResourceMonitor and classifies+enqueues any
        CRITICAL alert into PriorityQueueManager for visibility, before
        returning BLOCKED_CRITICAL_RESOURCE."""
        self._last_blocked_alerts = []
        if action_type.value not in self._config.resource_gate_action_types:
            return ResourceGateDecision.PROCEED

        snapshot = self._resource_monitor.sample()
        alerts = self._resource_monitor.critical_alerts(snapshot)
        if not alerts:
            return ResourceGateDecision.PROCEED

        for alert in alerts:
            priority = self._priority_queue_manager.classify_resource_alert(alert)
            self._priority_queue_manager.enqueue(
                alert, priority, source="ActionResourceGate"
            )
        self._last_blocked_alerts = alerts
        logger.warning(
            "Action resource gate blocked %s — critical resource(s): %s",
            action_type.value,
            ", ".join(a.resource for a in alerts),
        )
        return ResourceGateDecision.BLOCKED_CRITICAL_RESOURCE

    def last_blocked_alerts(self) -> list[ResourceAlert]:
        """The ResourceAlert(s) that caused the most recent check() call
        to return BLOCKED_CRITICAL_RESOURCE — empty after a PROCEED.
        check()'s own declared return type is a bare ResourceGateDecision
        (per this sprint's spec), but ActionRegistry.dispatch() still
        needs to name the specific breached resource(s) in its
        ActionResult.error_message — this accessor is populated from
        the exact same sample check() itself just took, so the message
        can never describe a different (re-sampled, potentially stale
        or divergent) reading than what actually caused the block."""
        return list(self._last_blocked_alerts)
