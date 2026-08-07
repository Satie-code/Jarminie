# Sprint 6.12 — Adaptive Prioritization

## Sprint ID

6.12

## Sprint Name

Adaptive Prioritization

## Purpose

Handle genuinely competing priorities in real time — the brief's own worked example: urgent deadline vs. low battery vs. incoming reminder vs. an active user conversation. Level 3's `PriorityQueueManager` already orders items by a fixed `PriorityLevel` (1–5); this sprint adds the dynamic, situational arbitration layer above that fixed ordering — deciding not just "what rank is this" but "should this actually interrupt what's happening right now."

## Engineering Rationale

Extends `decision/` (does not introduce a new top-level package) — this sprint is the direct sibling of Sprint 6.5's `decision_engine_v2.py` within the same package, and depends on it directly.

**`PriorityQueueManager`'s own fixed `PriorityLevel` ordering is never overridden or bypassed** — `AdaptivePrioritizer` does not re-sort the underlying queue or change any item's stored `PriorityLevel`. It sits as a thin decision layer *in front of* `pop_next()`, answering a narrower, situational question `PriorityQueueManager` was never designed to answer: given the single highest-ranked item the queue would hand back right now, is *this specific moment* actually a good one to surface it? A `CRITICAL_EMERGENCY` item always still preempts everything, exactly as `PriorityLevel`'s own docstring already establishes ("Part 2's five priority levels... numbers these directly") — this sprint adds judgment only within and below that already-fixed ordering, never above it.

**Reused, not reinvented**: the "is the user mid-conversation right now" signal comes from `WorkingContext.conversation` (Sprint 6.3, itself sourced from the existing `ContextManager`); the "how urgent is this concretely, right now" signal reuses `DecisionEngineV2`'s own composite-scoring machinery (Sprint 6.5) rather than a third scoring scheme.

## Objectives

- `AdaptivePrioritizer`: given the queue's current top item and a `WorkingContext`, decides whether to surface it now, defer it briefly, or let it wait for the queue's own natural next check.
- `DecisionEngineConfig` gains the fields this sprint needs (its second sprint's worth, after 6.5).

## Dependencies

3.10 (`PriorityQueueManager`, `PriorityLevel`, `PriorityItem`), 6.5 (`DecisionEngineV2`, `RankedAction`-style scoring reused for a `PriorityItem`), 6.3 (`ContextEngine`/`WorkingContext`), 6.8 (`ProactiveAssistant`, this sprint's own real new source of competing items alongside Wellness/Scheduler).

## Files to Create

- `decision/adaptive_prioritizer.py` — `PrioritizationDecision` (Enum: `SURFACE_NOW`, `DEFER_BRIEFLY`, `HOLD`), `AdaptivePrioritizer`.
- `tests/unit/decision/test_adaptive_prioritizer.py`

## Files to Modify

- `config/schema.py` — `DecisionEngineConfig` gains `active_conversation_defer_seconds: float = 120.0` (a non-`CRITICAL_EMERGENCY`/non-`IMPORTANT_ALERT` item defers by up to this long when the user is actively mid-conversation, rather than interrupting immediately), `low_battery_boost_threshold_percent: float = 10.0` (below this, a `BATTERY_CRITICAL`-sourced item's own effective urgency is boosted regardless of its nominal `PriorityLevel`, since a dead machine ends every other priority moot).
- `config/defaults.yaml` — matching additions to the `decision_engine_v2:` section (same section 6.5 created — this sprint grows it, does not create a new one).

## Expected Classes

- `PrioritizationDecision` (Enum) — `SURFACE_NOW` (announce/interrupt immediately), `DEFER_BRIEFLY` (wait up to `active_conversation_defer_seconds`, then re-check), `HOLD` (leave queued, no explicit re-check scheduled by this sprint — the queue's own next natural poll, wired at 6.13, will reconsider it).
- `AdaptivePrioritizer` — constructor DI: `(priority_queue_manager: PriorityQueueManager, decision_engine_v2: DecisionEngineV2, decision_engine_config: DecisionEngineConfig)`. Not a `ManagedModule` — a pure decision layer over already-lifecycle-managed collaborators, matching `DecisionEngineV2`'s own identical shape.

## Expected Interfaces

None new.

## Expected Functions

- `AdaptivePrioritizer.next_item(working_context: WorkingContext) -> tuple[PriorityItem, PrioritizationDecision] | None` — calls `priority_queue_manager.peek_next()` (existing, non-consuming read); returns `None` if the queue is empty. For a real item: `PriorityLevel.CRITICAL_EMERGENCY` always resolves `SURFACE_NOW` unconditionally (the one hard-coded exception to every rule below — Level 6's own "User Override Always Wins"/emergency-handling precedent from Level 3 is never subordinated to a situational judgment call). For every other level: if `working_context.resource_status`'s battery reading is below `low_battery_boost_threshold_percent` and the item's own source concerns power/urgency, boosts toward `SURFACE_NOW`. Otherwise, if `working_context.conversation` shows an active, in-progress session, resolves `DEFER_BRIEFLY` for `GENERAL_SUGGESTION`/`WELLNESS`-level items (never for `IMPORTANT_ALERT` or above) and `SURFACE_NOW` for `IMPORTANT_ALERT`. With no active conversation, resolves `SURFACE_NOW` for anything at `SCHEDULED_REMINDER` or above, and `HOLD` only for the lowest-priority `GENERAL_SUGGESTION` items when `decision_engine_v2`'s own confidence signal (via a `ReasoningEngine`-backed estimate on the item's own description) is low.
- `AdaptivePrioritizer._is_conversation_active(working_context: WorkingContext) -> bool` — isolated for direct testing, reading `working_context.conversation`'s existing session-timing fields (confirmed against the real `ConversationContext` shape at implementation time).

## Data Flow

```
Caller (wired at 6.13, replacing a direct priority_queue_manager.pop_next() call inside
voice/pipeline.py's _check_and_announce_priority_item())
      ↓
AdaptivePrioritizer.next_item(working_context)
      ↓
priority_queue_manager.peek_next()   (existing, non-consuming)
      ↓
   PriorityLevel.CRITICAL_EMERGENCY?  → SURFACE_NOW (always)
   low battery + power-relevant item?  → boosted toward SURFACE_NOW
   active conversation?  → DEFER_BRIEFLY (soft items) / SURFACE_NOW (IMPORTANT_ALERT+)
   otherwise  → SURFACE_NOW (SCHEDULED_REMINDER+) / HOLD (low-confidence GENERAL_SUGGESTION)
      ↓
(PriorityItem, PrioritizationDecision)
      ↓
caller: SURFACE_NOW → priority_queue_manager.pop_next() + announce (existing mechanism, unchanged)
        DEFER_BRIEFLY/HOLD → item stays queued, re-evaluated on the next natural tick
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — the two new `DecisionEngineConfig` fields.
2. `decision/adaptive_prioritizer.py` — `PrioritizationDecision`, `AdaptivePrioritizer.next_item()`/`_is_conversation_active()`.
3. Unit tests: `CRITICAL_EMERGENCY` always `SURFACE_NOW` regardless of every other signal; low-battery boost; active-conversation deferral for soft items and non-deferral for `IMPORTANT_ALERT`; empty-queue `None` case; low-confidence `HOLD` case for `GENERAL_SUGGESTION`.

## Architecture Notes

`AdaptivePrioritizer.next_item()` is a read-only judgment call — it never itself calls `priority_queue_manager.pop_next()`, dequeues nothing, and never speaks. The actual "pop and announce" action stays exactly where it already lives (`voice/pipeline.py`'s `_check_and_announce_priority_item()`, wired at Sprint 6.13) — this sprint answers "should I, right now?", the caller still owns "then actually do it." This mirrors Sprint 6.5's own `DecisionEngineV2` boundary exactly: rank/judge, never dispatch.

The `CRITICAL_EMERGENCY`-always-wins rule is hard-coded, not config-driven or situationally overridable by any signal this sprint introduces — a deliberate, load-bearing safety property or Level 6's own principles would be violated by any construction that let a "the user seems busy" heuristic delay a genuine emergency.

## Integration Considerations

- No live caller yet. Sprint 6.13 (Integration) is where `voice/pipeline.py`'s `_check_and_announce_priority_item()` is modified to call `AdaptivePrioritizer.next_item()` before its own existing `pop_next()`/announce logic, rather than calling `priority_queue_manager.pop_next()` directly — a small, disclosed change to an already-existing method, not a new one.
- `DEFER_BRIEFLY`/`HOLD` do not themselves schedule a re-check — Sprint 6.13's own existing `TaskScheduler`-driven poll cadence (already ticking regularly for this exact purpose since Sprint 4.18) is what naturally re-evaluates a deferred/held item; this sprint adds no new timer.

## Potential Risks

- **`active_conversation_defer_seconds`/`low_battery_boost_threshold_percent` are unvalidated guesses**, matching every comparable default in this codebase.
- **A `HOLD` decision has no explicit maximum wait** — a persistently low-confidence `GENERAL_SUGGESTION` could, in principle, be held indefinitely across many ticks if its own confidence never improves. Disclosed as a real, if low-severity (it's the lowest priority level by design), limitation rather than solved with an arbitrary forced-surface timeout this brief gives no basis for.
- **`_is_conversation_active()`'s own definition of "active" is only as good as `ConversationContext`'s existing session-timing fields** — this sprint adds no new activity signal of its own, inheriting whatever precision Sprint 2.8's `ContextManager` already has.

## Acceptance Criteria

- `next_item()` returns `SURFACE_NOW` for a `CRITICAL_EMERGENCY` item under every tested combination of battery level and conversation state.
- A `GENERAL_SUGGESTION`/`WELLNESS` item resolves `DEFER_BRIEFLY` when the conversation is active, and does not when it isn't (all else equal).
- An `IMPORTANT_ALERT` item never resolves `DEFER_BRIEFLY` regardless of conversation state.
- A power-relevant item's resolution shifts toward `SURFACE_NOW` when battery is below `low_battery_boost_threshold_percent`, compared to an otherwise-identical case above it.
- An empty queue returns `None`.

## Testing Checklist

- [ ] Unit: `CRITICAL_EMERGENCY` always `SURFACE_NOW` (conversation active/inactive × battery low/normal, full matrix).
- [ ] Unit: `IMPORTANT_ALERT` never defers regardless of conversation state.
- [ ] Unit: `GENERAL_SUGGESTION`/`WELLNESS` defer during an active conversation, surface when idle.
- [ ] Unit: low-battery boost for a power-relevant item.
- [ ] Unit: `HOLD` for a low-confidence `GENERAL_SUGGESTION`.
- [ ] Unit: empty-queue `None` case.
- [ ] Unit: `_is_conversation_active()` in isolation.
- [ ] Unit: `DecisionEngineConfig` validation for the two new fields.

## Documentation Checklist

- [ ] `decision/adaptive_prioritizer.py` docstring: the "judges, never dequeues or dispatches" boundary and the hard-coded, non-overridable `CRITICAL_EMERGENCY` rule, both stated explicitly.
- [ ] `docs/STATUS.md` — Level 6 Part A narrative extended.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium–High.

## Estimated Development Time

2 days.

## Risks

See Potential Risks above.

## Next Sprint

6.13 — Autonomous Intelligence Integration.

## Future Considerations

- A bounded maximum `HOLD` duration, if real usage shows indefinite holding is a real problem — disclosed above, not built here without evidence.
- Per-persona deferral tuning (Jarvis vs. Minie handling an active conversation differently) — no basis in this brief; not built speculatively.
