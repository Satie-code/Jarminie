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

## Sprint Completion Report (2026-08-09)

Implemented as specified, authorized directly ("continue with sprint 6.12") in the same session as Sprints 6.1–6.11, right after 6.11 closed.

Delivered `decision/adaptive_prioritizer.py` (`PrioritizationDecision`, `AdaptivePrioritizer`), extending `decision/` (not a new top-level package) — the direct sibling of `decision_engine_v2.py` (6.5), the seventh sprint in a row to extend an existing package rather than fork one.

**Five real, disclosed gaps and interpretive resolutions, all found by checking what this sprint's own dependencies actually expose before implementing, matching this whole Sprint Book's own now fully-established discipline**:

1. **This sprint file's own text names two different "always surfaces regardless of context" thresholds in two adjacent sentences** — the active-conversation branch says `IMPORTANT_ALERT`; the no-conversation branch says `SCHEDULED_REMINDER` (a lower, more inclusive bar). Resolved toward one internally consistent threshold: `SCHEDULED_REMINDER`-and-above always resolves `SURFACE_NOW` regardless of conversation state, both because it is more defensible than two different thresholds for functionally the same question, and because a scheduled reminder is, by its own real-world nature, time-critical enough to still warrant interrupting a conversation — unlike `WELLNESS`/`GENERAL_SUGGESTION`'s genuinely softer content.
2. **`DecisionEngineV2`'s real, current public API has no way to produce "decision_engine_v2's own confidence signal ... on the item's own description."** `rank_actions()`/`requires_confirmation()`/`suggest_alternatives()` all require an `ActionRequest`; a queued `PriorityItem`'s own payload (an `Intent`, a `ResourceAlert`, a `ProactivePrompt`, a `Recommendation`) is never one, and this sprint's own Files to Modify does not authorize widening `decision_engine_v2.py` to expose a raw confidence-over-text method. Resolved by accepting `decision_engine_v2` exactly per the literal constructor signature (genuinely unused by `next_item()` — the fifth instance of this Book's own "accepted but not yet consumed" pattern: 6.5's `authority_evaluator`, 6.8's `decision_engine_v2`/`pattern_recognizer`, 6.10's `evaluation_timeout_seconds`, 6.11's `ranked_action` resolution gap) and adding a fourth, disclosed constructor parameter, `reasoning_engine: ReasoningEngine`, used directly for the one real confidence check the low-confidence `HOLD` branch needs — the same necessary-addition-beyond-the-literal-signature shape `TaskGraph`'s own `planning_config` (6.2) and `ExplainabilityLayer`'s own `reasoning_config` (6.11) already established.
3. **`DecisionEngineConfig` gains two further fields beyond this sprint's own two named ones.** `conversation_active_threshold_seconds` — nothing in `ConversationContext` (2.8) itself marks a session "still active," only `last_activity_at`, and this sprint's own text never assigns a threshold field for it; deliberately its own new field rather than a reuse of `voice.session_timeout_seconds`, whose own much shorter inter-turn-silence window answers a genuinely different question. `low_confidence_hold_threshold` — the numeric cutoff behind "confidence ... is low," likewise never assigned a value in this sprint's own text.
4. **`active_conversation_defer_seconds` is genuinely consumed by `next_item()`, not merely accepted-but-unused** — a disclosed quality addition beyond this sprint's own literal minimum. `PrioritizationDecision.DEFER_BRIEFLY`'s own docstring says "wait up to `active_conversation_defer_seconds`, then re-check"; since `PriorityItem.enqueued_at` (3.10) already exists, `next_item()` mechanically compares it against that bound on every call, forcing `SURFACE_NOW` once a soft item has waited past the window even if the conversation is technically still active — rather than deferring it forever across repeated polls with the field sitting unread. Changes no Acceptance Criterion (each is tested "all else equal" against a freshly-enqueued item, safely inside the window).
5. **The low-battery boost is checked unconditionally against every payload regardless of priority.** Disclosed as necessary because every real, current power-relevant producer in this codebase (`device_control/resource_gate.py`'s battery `ResourceAlert`, `proactive/proactive_assistant.py`'s `BATTERY_CRITICAL` `ProactivePrompt`) already enqueues at `IMPORTANT_ALERT` — a level that already always resolves `SURFACE_NOW` per resolution (1) above regardless of battery — making the boost a structural no-op against every payload this codebase can produce today. Verified instead via a constructed lower-priority test case (a `WELLNESS`-level item carrying a battery-relevant payload), confirming the mechanism itself is real rather than a phantom rule no real input ever exercises.

`CRITICAL_EMERGENCY`'s own always-`SURFACE_NOW` rule was verified directly against the full cross-product this sprint's own Testing Checklist names — every combination of conversation-active/inactive/absent and battery-low/normal/absent, 9 cases via `pytest.mark.parametrize`, confirming zero `ReasoningEngine` calls in every one.

31 new tests (`tests/unit/decision/test_adaptive_prioritizer.py` — the full `CRITICAL_EMERGENCY` matrix; `IMPORTANT_ALERT`/`SCHEDULED_REMINDER` never deferring; `WELLNESS`/`GENERAL_SUGGESTION` deferring during an active conversation and not when idle; the defer-window-exceeded override; the low-battery boost for both real power-relevant payload shapes, a non-battery `ResourceAlert`, a normal-battery case, and a no-`resource_status` case; the low-confidence `HOLD` path including its `LlmError` degrade and the payload-description extraction; `_is_conversation_active()` in isolation including its own threshold boundary; the empty-queue `None` case), plus 4 more `DecisionEngineConfig` validation tests in `test_schema.py`.

Full suite (unit + integration + system, opt-in real-model marker excluded): 2236 passing + 5 skipped + exactly 2 failures, both confirmed pre-existing non-regressions. `test_level4_part_a_full_acceptance_scenario` — the same well-documented host-load `wait_for_dormant`-class flake this project has hit repeatedly since Sprint 3.13 — passed cleanly on an immediate standalone re-run. `test_context_analyzer_extracts_a_nonempty_topic_for_real_input` — the identical already-long-documented real-Ollama-output-nondeterminism flake first logged at Sprint 5.2 — failed on two further standalone re-runs, so this sprint applied the more rigorous `git stash`/re-run verification Sprint 5.17's own STATUS.md entry first established: stashed, re-run against the pre-Sprint-6.12 codebase, and it failed identically there too, in `decision/context_analyzer.py`, a file this sprint never touches — conclusively ruling out this sprint's own files as the cause before restoring the stash. `ruff check .` clean repo-wide.

`docs/STATUS.md` (Level 6 Part A narrative extended, Part A header → "12/15 implemented"), `docs/sprint_book/INDEX.md` (6.12 row → `Complete`) both updated. No new `backlog/technical_debt.md` entry — this sprint extends `decision/`, no new top-level package, mirroring 6.2's/6.5's/6.7's/6.9's/6.10's/6.11's own identical precedent.

**No git commit made** — per this project's own "only commit when explicitly asked" rule; changes left in the working tree alongside Sprints 6.1–6.11's own still-uncommitted work, the user not yet asked whether to commit. **Sprint 6.13 (Autonomous Intelligence Integration) is next.**
