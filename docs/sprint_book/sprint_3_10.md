# Sprint 3.10 — Priority Queue

## Sprint ID

3.10

## Sprint Name

Priority Queue

## Purpose

Implement the Decision Engine pipeline's fourth stage, per [02_System_Architecture.md](../02_System_Architecture.md): *"... → Memory Retrieval → **Priority Evaluation** → Authority Evaluation → ..."* Also implements Part 2's Priority Queue System in full: *"Priority 1: Critical emergency (immediate interruption). Priority 2: Important alerts (wait for natural pause). Priority 3: Scheduled reminders (queued). Priority 4: Wellness (context-aware reminders). Priority 5: General suggestions (lowest priority)."*

## Engineering Rationale

Following the exact discipline already established for `SwitchReason` (Sprint 2.11): build the full five-level mechanism now, since Part 2 defines it completely and reshaping it later would be more disruptive than under-wiring it today, but only connect the priority sources that have a real producer at this point in the roadmap:

- **Priority 1 (Critical emergency)** — has a real, if partial, source: Sprint 3.7's `Intent.category == EMERGENCY`. Note the pipeline ordering carefully: Priority Evaluation runs *before* Authority Evaluation (Sprint 3.11) — so this sprint can only *tentatively* flag something priority-1 based on Intent Detection's classification; Sprint 3.11 is what actually confirms whether, and how, JARMINEI is authorized to act on it (bounded to the Authority System's "Emergency Assist" level, which Part 2 defines narrowly).
- **Priority 2 (Important alerts)** — has a real source already built in Level 1: `ResourceMonitor`'s critical-threshold alerts (Sprint 1.4). This is a genuine, non-speculative integration point wired in this sprint.
- **Priority 3 (Scheduled reminders)** — requires the Scheduler (Level 4, Sprint 4.8+). Reserved, unwired.
- **Priority 4 (Wellness)** — requires the Wellness Engine (Level 5, Phase 5.2). Reserved, unwired.
- **Priority 5 (General suggestions)** — the default fallback for anything not matched above (e.g. `INFORMATIONAL`, `CASUAL_CONVERSATION` intents).

Level 3 has no genuinely concurrent request sources yet in the way Level 4/5 will (a single active conversation turn, plus the occasional resource-protection alert) — so this sprint is honestly scoped to building a real, correctly-ordered priority queue data structure and classification function, without pretending Level 3 has a rich multi-source scheduling problem to solve yet. The mechanism is real and complete; most of its five inputs are not yet live, exactly like `SwitchReason`'s `CRITICAL_EMERGENCY`/`DAILY_ROUTINE` slots.

## Objectives

- A `PriorityLevel` enum matching Part 2's five levels exactly, declaration order encoding priority (same convention as `SwitchReason`).
- A `PriorityQueueManager` that classifies a request into a `PriorityLevel` and maintains a real priority-ordered queue (heap by level, FIFO within a level).
- Two real, wired sources (Intent-based tentative emergency flagging, `ResourceMonitor` critical alerts); two reserved, documented sources (Scheduler, Wellness).

## Dependencies

1.5 (Core Manager — for `ResourceMonitor` integration), 3.9 (Memory Retrieval Engine — receives its output as queue item context)

## Files to Create

- `decision/priority_queue.py` — `PriorityLevel` (Enum), `PriorityItem` (dataclass), `PriorityQueueManager(ManagedModule)`.
- `tests/unit/decision/test_priority_queue.py`

## Files to Modify

None — `ResourceMonitor`'s existing critical-alert reporting (Sprint 1.4) is read, not modified.

## Expected Classes

- `PriorityLevel` (Enum) — `CRITICAL_EMERGENCY = 1`, `IMPORTANT_ALERT = 2`, `SCHEDULED_REMINDER = 3` (reserved), `WELLNESS = 4` (reserved), `GENERAL_SUGGESTION = 5`. Explicit integer values, matching Part 2's own numbered list exactly (unlike `SwitchReason`'s implicit declaration-order convention, Part 2 numbers these directly, so the enum mirrors that literally).
- `PriorityItem` (dataclass) — `payload: Intent | ResourceAlert | object`, `priority: PriorityLevel`, `enqueued_at: datetime`, `source: str` (e.g. `"intent_detection"`, `"resource_monitor"`).
- `PriorityQueueManager(ManagedModule)` — constructor DI: `(resource_monitor: ResourceMonitor)`. Owns an internal `heapq`-based queue keyed by `(priority.value, enqueued_at)` — priority first, then insertion order, giving deterministic FIFO-within-level ordering.

## Expected Interfaces

- `ManagedModule` (reused) — `start()`/`stop()` log only (no external resource beyond the injected `resource_monitor`, already managed by `CoreManager`); `health_check()` reports queue depth is within a sane bound (a defensive check against an unbounded backlog, not an expected real condition at Level 3's request volume).

## Expected Functions

- `PriorityQueueManager.classify(intent: Intent) -> PriorityLevel` — returns `CRITICAL_EMERGENCY` if `intent.category == IntentCategory.EMERGENCY`; otherwise `GENERAL_SUGGESTION` (the honest default — `SCHEDULED_REMINDER`/`WELLNESS` have no classification path yet since nothing produces an `Intent` or signal shaped like those categories at Level 3).
- `PriorityQueueManager.classify_resource_alert(alert: ResourceAlert) -> PriorityLevel` — a critical-threshold `ResourceAlert` (Sprint 1.4) always classifies as `IMPORTANT_ALERT`.
- `PriorityQueueManager.enqueue(payload: object, priority: PriorityLevel, source: str) -> None`
- `PriorityQueueManager.pop_next() -> PriorityItem | None` — returns the highest-priority, oldest-enqueued item; `None` if the queue is empty (an expected, common state — most of the time nothing is queued).
- `PriorityQueueManager.peek_next() -> PriorityItem | None` — non-destructive read, used by Sprint 3.11 to inspect priority without consuming the item.

## Data Flow

```
Intent (3.7)                              ResourceAlert (ResourceMonitor, 1.4)
      ↓                                          ↓
PriorityQueueManager.classify(intent)      PriorityQueueManager.classify_resource_alert(alert)
      ↓                                          ↓
PriorityQueueManager.enqueue(payload, priority, source)
      ↓
internal heapq, ordered by (priority.value, enqueued_at)
      ↓
PriorityQueueManager.pop_next() / peek_next()
      ↓
Sprint 3.11 (Authority Evaluation & Engine Selection)
```

## Implementation Tasks

1. `decision/priority_queue.py` — `PriorityLevel`, `PriorityItem`, `PriorityQueueManager(ManagedModule)`, heap-based `enqueue()`/`pop_next()`/`peek_next()`.
2. `classify()`/`classify_resource_alert()` — the two wired sources; explicit code comments marking `SCHEDULED_REMINDER`/`WELLNESS` as reserved, unwired, per the same pattern `SwitchReason` used.
3. Unit tests covering ordering correctness (priority first, FIFO within a level), the two wired classification paths, and the empty-queue case.

## Architecture Notes

`PriorityQueueManager` is the first Level 3 module to depend directly on a Level 1 module (`ResourceMonitor`) rather than another Level 3 module — a deliberate, real integration (Priority 2's genuine source), not a layering violation, since `ResourceMonitor` was always meant to be consumed by higher-level decision logic once one existed (Sprint 1.4's own Future Considerations anticipated this). It does not depend on `MemoryRetrievalEngine` (3.9) directly for classification — `RetrievedMemory` results travel alongside a request as context for Sprint 3.11's decision, not as an input to priority classification itself.

## Integration Considerations

- No live caller enqueues real items yet — wired into the real turn-processing path (Intent-sourced items) and a `ResourceMonitor` alert callback (alert-sourced items) by Sprint 3.12.
- `SCHEDULED_REMINDER`'s real source arrives at Sprint 4.8+ (Scheduler); `WELLNESS`'s real source arrives at Phase 5.2 — both sprints should call `enqueue()` directly with the appropriate `PriorityLevel`, requiring no change to `PriorityQueueManager` itself, the same "mechanism built once, sources wired incrementally" outcome `SwitchReason` achieved for Persona Switching.
- Sprint 3.11 is the sole consumer of `pop_next()`/`peek_next()` at Level 3.

## Potential Risks

- **`classify()`'s binary EMERGENCY-or-GENERAL_SUGGESTION mapping is coarse** — Level 3 genuinely has no signal shaped like "important alert from conversation" (as opposed to from `ResourceMonitor`) or "scheduled"/"wellness" — this is an honest limitation of what exists at this point in the roadmap, not an oversight; documented explicitly so it isn't mistaken for a more complete classifier than it is.
- **No true concurrency exists yet to stress the queue** — a single active conversation turn plus occasional resource alerts means `pop_next()` racing conditions are largely theoretical at Level 3; revisit if Level 4/5's real concurrent sources (Scheduler, Wellness) expose a genuine ordering bug not caught by this sprint's own tests.

## Acceptance Criteria

- Items enqueued out of priority order are always popped in strict priority order (1 before 2 before 3, etc.).
- Two items at the same priority level are popped in FIFO (enqueue) order.
- `intent.category == EMERGENCY` always classifies as `CRITICAL_EMERGENCY`; every other category classifies as `GENERAL_SUGGESTION`.
- A critical `ResourceAlert` always classifies as `IMPORTANT_ALERT`.
- `pop_next()` on an empty queue returns `None`, not an error.

## Testing Checklist

- [ ] Unit: priority ordering across all five levels (mixed-order enqueue, ordered pop).
- [ ] Unit: FIFO-within-level ordering.
- [ ] Unit: `classify()` for `EMERGENCY` vs. every other `IntentCategory`.
- [ ] Unit: `classify_resource_alert()` for a critical alert.
- [ ] Unit: `pop_next()`/`peek_next()` on an empty queue.
- [ ] Unit: `peek_next()` does not remove the item (a subsequent `pop_next()` still returns it).

## Documentation Checklist

- [ ] `decision/priority_queue.py` docstring: full priority table with wired/reserved status per level, cross-referencing Sprint 4.8+ (Scheduler) and Phase 5.2 (Wellness) as where reserved levels get real sources — the same documentation shape `PersonaManager` used for `SwitchReason`.
- [ ] `docs/STATUS.md` — Phase 3.3 (Decision Engine) row remains `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1–1.5 days.

## Next Sprint

3.11 — Authority Evaluation & Engine Selection.

## Future Considerations

- Sprint 4.9 (Reminder Engine) and Phase 5.2 (Wellness) should call `PriorityQueueManager.enqueue()` directly with `SCHEDULED_REMINDER`/`WELLNESS` once those sources exist — no anticipated change to this sprint's public API.
- If real concurrent load ever makes `pop_next()` a contention point, revisit its internal locking — not a concern at Level 3's actual usage pattern.
