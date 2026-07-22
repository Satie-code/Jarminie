"""Unit tests for device_control.resource_gate.

Uses a real (non-mocked) PriorityQueueManager throughout, per this
sprint's own Acceptance Criteria — a blocked dispatch must be verified
to enqueue a correctly classified real PriorityItem, not just prove a
mock was called. Only ResourceMonitor is faked, at the one seam that
needs a real-hardware-free, deterministic CRITICAL/normal reading.
"""

from datetime import UTC, datetime

from config.schema import DeviceControlConfig, ResourceThresholds
from core.resource_monitor import ResourceAlert, ResourceMonitor, ResourceSnapshot
from decision.priority_queue import PriorityLevel, PriorityQueueManager
from device_control.action_engine import ActionType
from device_control.resource_gate import ActionResourceGate, ResourceGateDecision


class FakeResourceMonitor:
    """Duck-typed ResourceMonitor stand-in returning a fixed snapshot —
    real critical_alerts()/breached_resources() logic is reused
    unmodified by delegating to a real ResourceMonitor instance
    underneath, so only sample() itself (the real-hardware read) is
    faked."""

    def __init__(self, snapshot: ResourceSnapshot, thresholds: ResourceThresholds) -> None:
        self.snapshot = snapshot
        self._real = ResourceMonitor(thresholds)

    def sample(self) -> ResourceSnapshot:
        return self.snapshot

    def critical_alerts(self, snapshot: ResourceSnapshot) -> list[ResourceAlert]:
        return self._real.critical_alerts(snapshot)


def _snapshot(
    cpu: float = 10.0, ram: float = 10.0, disk: float = 10.0, battery: float | None = 80.0
) -> ResourceSnapshot:
    return ResourceSnapshot(
        cpu_percent=cpu,
        ram_percent=ram,
        disk_percent=disk,
        battery_percent=battery,
        timestamp=datetime.now(UTC),
    )


def _gate(
    snapshot: ResourceSnapshot,
    priority_queue_manager: PriorityQueueManager | None = None,
    resource_gate_action_types: list[str] | None = None,
) -> tuple[ActionResourceGate, PriorityQueueManager]:
    thresholds = ResourceThresholds()
    monitor = FakeResourceMonitor(snapshot, thresholds)
    if priority_queue_manager is None:
        priority_queue_manager = PriorityQueueManager(ResourceMonitor(thresholds))
    config = DeviceControlConfig(
        resource_gate_action_types=(
            resource_gate_action_types
            if resource_gate_action_types is not None
            else ["launch_application", "system_command"]
        )
    )
    gate = ActionResourceGate(monitor, priority_queue_manager, config)
    return gate, priority_queue_manager


# --- non-gated action types always proceed -----------------------------------------


def test_non_gated_action_type_proceeds_even_under_critical_sample():
    gate, _ = _gate(_snapshot(cpu=99.0))

    decision = gate.check(ActionType.FILE_DELETE)

    assert decision is ResourceGateDecision.PROCEED
    assert gate.last_blocked_alerts() == []


def test_non_gated_window_action_proceeds_under_critical_sample():
    gate, _ = _gate(_snapshot(ram=99.0))

    decision = gate.check(ActionType.WINDOW_FOCUS)

    assert decision is ResourceGateDecision.PROCEED


# --- gated action types under a normal sample ---------------------------------------


def test_gated_action_type_proceeds_under_normal_sample():
    gate, _ = _gate(_snapshot())

    decision = gate.check(ActionType.LAUNCH_APPLICATION)

    assert decision is ResourceGateDecision.PROCEED
    assert gate.last_blocked_alerts() == []


# --- gated action types blocked per resource -----------------------------------------


def test_gated_action_type_blocked_under_critical_cpu():
    gate, _ = _gate(_snapshot(cpu=99.0))

    decision = gate.check(ActionType.LAUNCH_APPLICATION)

    assert decision is ResourceGateDecision.BLOCKED_CRITICAL_RESOURCE
    assert [a.resource for a in gate.last_blocked_alerts()] == ["cpu"]


def test_gated_action_type_blocked_under_critical_ram():
    gate, _ = _gate(_snapshot(ram=99.0))

    decision = gate.check(ActionType.SYSTEM_COMMAND)

    assert decision is ResourceGateDecision.BLOCKED_CRITICAL_RESOURCE
    assert [a.resource for a in gate.last_blocked_alerts()] == ["ram"]


def test_gated_action_type_blocked_under_critical_disk():
    gate, _ = _gate(_snapshot(disk=99.0))

    decision = gate.check(ActionType.LAUNCH_APPLICATION)

    assert decision is ResourceGateDecision.BLOCKED_CRITICAL_RESOURCE
    assert [a.resource for a in gate.last_blocked_alerts()] == ["disk"]


def test_gated_action_type_blocked_under_critical_battery():
    gate, _ = _gate(_snapshot(battery=1.0))

    decision = gate.check(ActionType.LAUNCH_APPLICATION)

    assert decision is ResourceGateDecision.BLOCKED_CRITICAL_RESOURCE
    assert [a.resource for a in gate.last_blocked_alerts()] == ["battery"]


# --- real PriorityQueueManager enqueue on block --------------------------------------


def test_blocked_dispatch_enqueues_classified_alert_in_real_priority_queue():
    thresholds = ResourceThresholds()
    priority_queue_manager = PriorityQueueManager(ResourceMonitor(thresholds))
    gate, priority_queue_manager = _gate(
        _snapshot(cpu=99.0), priority_queue_manager=priority_queue_manager
    )

    decision = gate.check(ActionType.LAUNCH_APPLICATION)

    assert decision is ResourceGateDecision.BLOCKED_CRITICAL_RESOURCE
    item = priority_queue_manager.pop_next()
    assert item is not None
    assert item.priority is PriorityLevel.IMPORTANT_ALERT
    assert item.source == "ActionResourceGate"
    assert isinstance(item.payload, ResourceAlert)
    assert item.payload.resource == "cpu"
    assert priority_queue_manager.pop_next() is None


def test_proceed_does_not_enqueue_anything():
    thresholds = ResourceThresholds()
    priority_queue_manager = PriorityQueueManager(ResourceMonitor(thresholds))
    gate, priority_queue_manager = _gate(
        _snapshot(), priority_queue_manager=priority_queue_manager
    )

    gate.check(ActionType.LAUNCH_APPLICATION)

    assert priority_queue_manager.pop_next() is None


# --- last_blocked_alerts() reset between calls ----------------------------------------


def test_last_blocked_alerts_resets_after_a_subsequent_proceed():
    """Same gate instance, same underlying fake monitor -- mutating its
    snapshot between two check() calls proves last_blocked_alerts() is
    cleared at the start of every check(), not left stale from a prior
    blocked call."""
    thresholds = ResourceThresholds()
    monitor = FakeResourceMonitor(_snapshot(cpu=99.0), thresholds)
    priority_queue_manager = PriorityQueueManager(ResourceMonitor(thresholds))
    config = DeviceControlConfig(resource_gate_action_types=["launch_application"])
    gate = ActionResourceGate(monitor, priority_queue_manager, config)

    gate.check(ActionType.LAUNCH_APPLICATION)
    assert gate.last_blocked_alerts() != []

    monitor.snapshot = _snapshot()
    gate.check(ActionType.LAUNCH_APPLICATION)
    assert gate.last_blocked_alerts() == []


# --- empty resource_gate_action_types gates nothing -----------------------------------


def test_empty_resource_gate_action_types_exempts_everything():
    gate, _ = _gate(_snapshot(cpu=99.0), resource_gate_action_types=[])

    decision = gate.check(ActionType.LAUNCH_APPLICATION)

    assert decision is ResourceGateDecision.PROCEED
