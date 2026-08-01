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

---

## Sprint Completion Report (2026-07-18)

### Summary

Implemented `decision/priority_queue.py` (`PriorityLevel`, `PriorityItem`, `PriorityQueueManager`). Also added `ResourceAlert` and `ResourceMonitor.critical_alerts()` to Sprint 1.4's already-shipped `core/resource_monitor.py` — a real, necessary gap found while implementing this sprint (see Engineering Decisions), not a deviation from it, following the same additive-fix pattern established in Sprint 3.9. 512/512 tests passing (484 prior + 28 new), `ruff check .` clean.

### Files Created

- `decision/priority_queue.py` — `PriorityLevel` (Enum), `PriorityItem` (dataclass), `PriorityQueueManager`.
- `tests/unit/decision/test_priority_queue.py` — 20 tests.

### Files Modified

- `core/resource_monitor.py` — added `ResourceAlert` (dataclass) and `ResourceMonitor.critical_alerts()`; `breached_resources()` unchanged.
- `tests/unit/core/test_resource_monitor.py` — 8 new tests for `critical_alerts()`.
- `docs/STATUS.md` — Phase 3.3 (Decision Engine) row's descriptive text updated; status itself deliberately left at `Designing`, per this sprint's own Documentation Checklist.

### Tests Added

28 total. In `test_priority_queue.py` (a real `ResourceMonitor` — cheap and side-effect-free to construct, no need for a fake): `classify()` for `EMERGENCY` vs. every other `IntentCategory` (parametrized across all six non-`EMERGENCY` categories); `classify_resource_alert()` always returning `IMPORTANT_ALERT`; strict priority ordering across all five levels enqueued out of order; FIFO-within-level ordering, including a monkeypatched-`datetime` test proving the tiebreaking counter holds even under identical timestamps (a real possibility on a fast machine, not just theoretical); a higher-priority item enqueued *after* a lower-priority one still popping first; `pop_next()`/`peek_next()` on an empty queue; `peek_next()` not removing its item; `PriorityItem`'s carried fields; and `health_check()`'s sane-depth bound (true under normal load, false past 1000 items). In `test_resource_monitor.py`: each resource's critical threshold independently, the battery inversion, `None` battery not alerting, multiple simultaneous critical alerts, and — the one genuinely new case this addition needed to prove — a warning-level-only breach does NOT produce a critical alert.

### Documentation Updated

This file (Sprint Completion Report). `decision/priority_queue.py`'s module docstring (full priority table with wired/reserved status per level, mirroring `PersonaManager`'s `SwitchReason` documentation shape). `core/resource_monitor.py`'s new docstrings. `docs/STATUS.md` as above.

### Acceptance Criteria Checklist

- ✔ Items enqueued out of priority order are always popped in strict priority order (1 before 2 before 3 before 4 before 5).
- ✔ Two items at the same priority level pop in FIFO (enqueue) order — proven both under normal timestamps and under a forced-identical-timestamp scenario.
- ✔ `intent.category == EMERGENCY` always classifies as `CRITICAL_EMERGENCY`; every other category (all six checked) classifies as `GENERAL_SUGGESTION`.
- ✔ A critical `ResourceAlert` always classifies as `IMPORTANT_ALERT`.
- ✔ `pop_next()` on an empty queue returns `None`, not an error.

### Engineering Decisions

- **Added `ResourceAlert`/`critical_alerts()` to `core/resource_monitor.py` (Sprint 1.4), purely additively.** This sprint's spec assumed "`ResourceMonitor`'s critical-threshold alerts (Sprint 1.4)" already existed and listed Files to Modify as "None" on that basis — but Sprint 1.4 only ever shipped warning-threshold checking (`breached_resources()`, returning plain resource-name strings) plus the critical-percent config fields' Settings Window display (Sprint 1.8); nothing checked a live sample against those critical fields, and no `ResourceAlert` class existed anywhere. Resolved the same way Sprint 3.9 resolved an analogous gap in `PersonaScopedMemory`/`EventMemory`: a new, additive method (`critical_alerts()`) alongside the existing one (`breached_resources()`), zero behavior change to any existing caller/test. Documented as a Post-Sprint Fix on `sprint_1_4.md`.
- **`classify_resource_alert()` is an unconditional constant return (`IMPORTANT_ALERT`), never branching on the alert's own fields.** This looked like a strange, possibly-incomplete function at first, but it's correct given the sprint's own spec wording ("a critical `ResourceAlert` always classifies as `IMPORTANT_ALERT`") combined with the fact that `critical_alerts()` (this sprint's own addition) is the *only* thing that ever constructs a `ResourceAlert` at all, and it only does so for genuinely critical-threshold breaches — there is no lower-severity `ResourceAlert` for this method to need to distinguish from.
- **The internal heap uses plain `(priority.value, enqueued_at, counter, item)` tuples, not a dedicated wrapper dataclass.** `itertools.count()`'s monotonic, guaranteed-unique counter as the third tuple element means heapq's comparison can never actually fall through to comparing the fourth element (`PriorityItem`, whose `payload: object` isn't necessarily orderable) — achieving deterministic FIFO-within-level ordering without introducing an extra class the spec's own Expected Classes didn't list.
- **`_MAX_SANE_QUEUE_DEPTH` (1000) is a plain module-level constant, not a `MemoryConfig`/new config field** — this sprint's own Files to Modify list didn't include any config file, and 1000 is intentionally far beyond any value Level 3's actual request volume (a single conversation turn plus occasional resource alerts) could plausibly reach, matching the same "large enough that a real value never plausibly reaches it" convention as `memory/event_memory.py`'s/`short_term_memory.py`'s `_LARGE_LIMIT`.

### Remaining Risks

- **Confirmed via real, non-mocked verification**: sampled actual system resources on this development machine via a real `ResourceMonitor` (no critical alerts under normal load, as expected), then ran real `Intent` objects (one `EMERGENCY`, one `CASUAL_CONVERSATION`) through `classify()`/`enqueue()`/`pop_next()` — the emergency item correctly popped first regardless of enqueue order, exactly matching the unit-test-level proof.
- This sprint's own flagged risks stand as expected: `classify()`'s binary EMERGENCY-or-GENERAL_SUGGESTION mapping is an honest limitation of what exists at this point in the roadmap (not an oversight), and no genuine concurrency exists yet to stress-test `pop_next()` (both explicitly deferred, not built speculatively).
- `backlog/technical_debt.md` item 16 (shipped `ollama_model` default) doesn't apply here — this sprint has no Ollama/LLM dependency.

### Technical Debt

None new. The `ResourceAlert`/`critical_alerts()` addition is documented as an Engineering Decision above rather than technical debt, since it's a clean, permanent, non-breaking design (not a shortcut requiring future resolution) — same framing Sprint 3.9 used for its own analogous addition.

### Recommendations

- **For Sprint 3.11 (Authority Evaluation & Engine Selection)**: consumes `pop_next()`/`peek_next()` — worth double-checking its own spec's assumptions about `PriorityItem`'s shape against what actually shipped here, per the established "check the next sprint's assumptions" pattern.
- **For Sprint 3.12 (Decision Engine Integration)**: this sprint's two wired sources (Intent-based classification, `ResourceMonitor` critical alerts) both still need a real caller — `classify()`/`enqueue()` for every turn's `Intent`, and some cadence (likely alongside `CoreManager`'s existing resource-sampling loop) calling `critical_alerts()` and enqueueing any results.

**Sprint 3.10 (Priority Queue) is complete.** **Sprint 3.11 (Authority Evaluation & Engine Selection) is next.**
