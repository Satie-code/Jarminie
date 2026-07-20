# Sprint 4.6 — System Monitoring & Resource Protection (Action-Aware)

## Sprint ID

4.6

## Sprint Name

System Monitoring & Resource Protection (Action-Aware)

## Purpose

Close the loop between the Resource Monitor Sprint 1.4 already built and the Level 4 executors Sprints 4.2–4.5 just built: before any Device Control action runs, consult live resource state, and refuse or defer the action if the system is already under critical pressure. This is Part 2's Resource Protection Rule ("if thresholds are exceeded, background work is reduced before the system becomes unresponsive... the user should never experience degraded usability because of JARMINEI") applied specifically to automation, for the first time.

## Engineering Rationale

Corresponds to `docs/sprint_book/INDEX.md`'s original `4.4 System Monitoring & Resource Protection (full)` roadmap entry, scoped narrower here on purpose: the original entry's parenthetical "(full)" implied building out `ResourceMonitor`'s remaining unfulfilled promise from Sprint 1.4's own docstring — *"It does not itself decide what to throttle — that belongs to whichever subsystem consumes it (Core Manager, and the full System Monitoring work in Phase 4.1)"* — but that promise has two genuinely separable halves: (1) a real consumer that throttles *action execution* specifically (this sprint's scope), and (2) a general system-wide background-work throttling policy applying to every subsystem, including ones outside Level 4 entirely (voice pipeline, memory lifecycle passes, etc.) — a materially larger, cross-cutting concern that this task's own Level 4 Goal list does not ask for and that would reach into Level 2/3 modules this Sprint Book has no mandate to modify. This sprint deliberately builds only the first half — renamed "(Action-Aware)" rather than "(full)" to make that narrowing explicit rather than silently under-delivering against the original entry's own name.

Also directly resolves `docs/backlog/technical_debt.md` item 17's own stated resolution path: *"Wire a real caller once Level 4's Scheduler (Sprint 4.8+) exists... worth resolving together with items 11 and 15."* This sprint is a **partial** resolution — it gives `ResourceMonitor.critical_alerts()`/`PriorityQueueManager.classify_resource_alert()` their first real caller (via the new `ActionResourceGate`, sampled immediately before dispatch, not on a periodic timer), but a true periodic/scheduled cadence for items 11, 15, and 17 still requires the Scheduler (Level 4 Part B) — this sprint's own Integration Considerations say so explicitly, so the technical debt log is updated accurately, not overstated the way `docs/STATUS.md`'s Phase 3.3 description once was (see item 17's own history).

## Objectives

- `ActionResourceGate`: samples `ResourceMonitor` immediately before a resource-sensitive action executes; blocks (returns a clear denial, not a crash or hang) when any resource is at CRITICAL per Sprint 1.4's own thresholds.
- `ActionRegistry.dispatch()` (4.1) consults this gate as a second guard, alongside `PermissionGate` — a resource denial and a permission denial are different reasons, both must be distinguishable in the resulting `ActionResult`.
- A first real, non-periodic caller for `ResourceMonitor.critical_alerts()`/`PriorityQueueManager.classify_resource_alert()`, closing part of `backlog/technical_debt.md` item 17 (the sample-on-dispatch path; the periodic path remains open, owned by Level 4 Part B's Scheduler).

## Dependencies

4.1 (Action Engine Foundation), 1.4 (Health Monitor / `ResourceMonitor`), 3.10 (Priority Queue — `PriorityQueueManager.classify_resource_alert()`)

## Files to Create

- `device_control/resource_gate.py` — `ResourceGateDecision` (enum), `ActionResourceGate`.
- `tests/unit/device_control/test_resource_gate.py`

## Files to Modify

- `device_control/action_engine.py` — `ActionRegistry.dispatch()` gains the `ActionResourceGate` check (constructor DI: `ActionRegistry.__init__` takes an optional `resource_gate: ActionResourceGate | None = None`, `None` preserving Sprint 4.1's exact existing behavior/tests for callers that don't need it — an additive, non-breaking change, the same pattern Sprint 3.9's Completion Report used for `recall_for_persona_scored()`).
- `config/schema.py` — `DeviceControlConfig` gains `resource_gate_action_types: list[str]` (default: `["launch_application", "system_command"]` — the two executors with genuine resource-consumption risk; file and window operations are cheap enough to exempt by default, consistent with Sprint 4.4's own Integration Considerations already noting window operations don't need this gate).
- `config/defaults.yaml` — matching field.

## Expected Classes

- `ResourceGateDecision(Enum)` — `PROCEED`, `BLOCKED_CRITICAL_RESOURCE`.
- `ActionResourceGate` — constructor DI: `(resource_monitor: ResourceMonitor, priority_queue_manager: PriorityQueueManager, device_control_config: DeviceControlConfig)`. Not a `ManagedModule` (no lifecycle, cheap to construct — same reasoning as `PermissionGate`, 4.1).

## Expected Interfaces

None new.

## Expected Functions

- `ActionResourceGate.check(action_type: ActionType) -> ResourceGateDecision` — returns `PROCEED` immediately if `action_type.value` is not in `resource_gate_action_types` (the cheap-action exemption); otherwise samples `resource_monitor.sample()`, checks `resource_monitor.critical_alerts(snapshot)`; if any alert exists, classifies each via `priority_queue_manager.classify_resource_alert()` and enqueues it (`priority_queue_manager.enqueue()`) for visibility/explainability, then returns `BLOCKED_CRITICAL_RESOURCE`. If no critical alert, returns `PROCEED`.
- `ActionRegistry.dispatch()` (modified) — when a `resource_gate` is present, calls `resource_gate.check(request.action_type)` after `PermissionGate.check()` returns `ALLOW` and before calling the executor; a `BLOCKED_CRITICAL_RESOURCE` result produces an `ActionResult` with `status=ActionStatus.FAILED` and an `error_message` naming the specific breached resource(s), the executor is never called.

## Data Flow

```
ActionRegistry.dispatch(request)
      ↓
PermissionGate.check(request) → ALLOW
      ↓
ActionResourceGate.check(request.action_type)
      ↓
resource_type in resource_gate_action_types?  → no → PROCEED  [skip to executor]
      ↓ yes
ResourceMonitor.sample() → ResourceSnapshot
      ↓
ResourceMonitor.critical_alerts(snapshot) → list[ResourceAlert]
      ↓ (non-empty)
PriorityQueueManager.classify_resource_alert(alert) → IMPORTANT_ALERT → enqueue()
      ↓
ResourceGateDecision.BLOCKED_CRITICAL_RESOURCE → ActionResult(FAILED, "cpu at 94% (critical)")
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `resource_gate_action_types`.
2. `device_control/resource_gate.py` — `ResourceGateDecision`, `ActionResourceGate`.
3. `device_control/action_engine.py` — additive `ActionRegistry.dispatch()` change (optional `resource_gate` parameter, existing tests/callers unaffected).
4. Unit tests: gate blocks under a simulated CRITICAL sample, passes under a normal sample, exempts non-gated action types, and correctly enqueues a classified alert via a real (not mocked) `PriorityQueueManager` for at least one test.

## Architecture Notes

`ActionResourceGate` is deliberately a **separate class from `PermissionGate`** (4.1), not a merged "one big gate" — they answer different questions ("is this actor allowed to do this" vs. "is the system healthy enough to do this right now") with different owners (Authority System vs. Resource Monitor) and different config sections, so merging them would violate Single Responsibility for a superficial convenience. `ActionRegistry.dispatch()` calling both in sequence, rather than either gate calling the other, keeps that separation visible in the code path, not just in prose.

The resource sample happens **at dispatch time, immediately before execution** — not on a background periodic timer — which is exactly the same "sample-on-demand, no new timer infrastructure" discipline `backlog/technical_debt.md` items 11/15/17 already flag as the correct interim answer until a real Scheduler exists. This sprint does not add a `threading.Timer` or any polling loop; it adds a synchronous check at an existing call site.

## Integration Considerations

- Wired into the live `ActionRegistry` construction by Sprint 4.11, alongside `PermissionGate`.
- This sprint's own resolution of `backlog/technical_debt.md` item 17 is **partial** — the sample-on-dispatch path is real and live from this sprint onward, but `ResourceMonitor.critical_alerts()`/`PriorityQueueManager.classify_resource_alert()` still have no *periodic* caller; that remains open, owned by Level 4 Part B's Scheduler (Sprint 4.14+), and this sprint's Documentation Checklist updates item 17's own text to say so precisely, not overstate it as fully resolved.
- Sprint 4.7's Permission & Confirmation System and this sprint's `ActionResourceGate` are both consulted by `ActionRegistry.dispatch()`, in a fixed order (permission, then resource) — Sprint 4.7 must not reorder this without updating this file's own Data Flow, since a resource-blocked action should never even reach the point of asking the user to confirm it.

## Potential Risks

- **A CRITICAL resource reading is often transient** (a brief CPU spike) — this sprint's gate has no retry/backoff, it simply fails the action for that one dispatch attempt; a caller (a Workflow step, Sprint 4.10) that wants to retry after resources recover must do so itself. Not built as automatic retry here — premature complexity for a condition this sprint has no evidence is common enough to warrant it (no premature optimization, matching this project's consistent stance).
- **The `resource_gate_action_types` exemption list is a guess** (file/window operations exempted by default) — reasonable given `ResourceSnapshot`'s own fields (CPU/RAM/disk/battery) have little to do with a single file move's actual cost, but config-driven specifically so it can be corrected without a code change if real use proves otherwise.
- **Battery-critical blocking a legitimate low-power action** (e.g. closing an application, which *reduces* resource usage) is a real edge case this sprint's simple "gated action types" list does not distinguish by directionality — flagged as a Future Consideration rather than solved here, since `ActionType` alone doesn't currently carry a "this action reduces load" signal.

## Acceptance Criteria

- A gated action type (`launch_application`, `system_command`) is blocked when `ResourceMonitor.critical_alerts()` reports any CRITICAL resource, with a clear `error_message` naming the resource.
- The same action types proceed normally under a non-critical sample.
- Non-gated action types (file/window operations) always proceed regardless of resource state.
- A blocked dispatch results in a real, classified `PriorityQueueManager` enqueue (`IMPORTANT_ALERT`), verified against a real (non-mocked) `PriorityQueueManager` in at least one test.
- `ActionRegistry`'s existing (Sprint 4.1) tests continue passing unmodified with no `resource_gate` supplied — confirms this sprint's change is genuinely additive.

## Testing Checklist

- [ ] Unit: gated action type blocked under a simulated CRITICAL CPU/RAM/disk/battery sample (one test per resource).
- [ ] Unit: gated action type proceeds under a normal sample.
- [ ] Unit: non-gated action type always proceeds, even under a CRITICAL sample.
- [ ] Unit: a blocked dispatch enqueues a correctly classified `PriorityItem` in a real `PriorityQueueManager`.
- [ ] Regression: Sprint 4.1's own `ActionRegistry` test suite passes unmodified with no `resource_gate` argument supplied.

## Documentation Checklist

- [ ] `device_control/resource_gate.py` docstring: explicit statement that this is a sample-on-dispatch check, not a periodic monitor, and the reasoning for that scope.
- [ ] `docs/backlog/technical_debt.md` — item 17 updated to reflect this sprint's partial resolution (sample-on-dispatch real; periodic cadence still owned by Level 4 Part B).
- [ ] `docs/STATUS.md` — Phase 4.1 row notes System Monitoring (Action-Aware) complete, with the same partial-resolution caveat.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1–1.5 days.

## Risks

See Potential Risks above.

## Next Sprint

4.7 — Permission & Confirmation System.

## Future Considerations

- Directionality-aware gating (load-reducing actions like `CLOSE_APPLICATION` exempted even under critical pressure, since they help rather than hurt) — flagged above, not built now.
- A real periodic resource-check cadence feeding the Priority Queue continuously, not just at action-dispatch time — explicitly deferred to Level 4 Part B's Scheduler, per this sprint's own Integration Considerations.
