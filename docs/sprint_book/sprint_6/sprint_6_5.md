# Sprint 6.5 — Decision Engine v2

## Sprint ID

6.5

## Sprint Name

Decision Engine v2

## Purpose

Improve decision making over Level 3's original Decision Engine (`decision/authority.py`'s `AuthorityEvaluator`) without replacing it — add action ranking, risk estimation, confidence-weighted gating, required-confirmation determination, and alternative-suggestion surfacing, per the brief's own list. This is the sprint where Level 6's own design principles (Verify Before Committing, Reliability Over Cleverness) become real, checkable code rather than prose.

## Engineering Rationale

**Extends `decision/`, does not fork it** — `EngineSelection`/`AuthorityLevel`/`DecisionTrace`/`PriorityLevel` (Sprint 3.10/3.11) all stay exactly as they are; `decision_engine_v2.py` is a new module in the same package that *composes* `AuthorityEvaluator`'s existing output rather than duplicating its own already-correct authority logic. This is the same "extend or improve an existing module instead of recreating it" precedent this project's own Development Guide names as Step 1, and which `_check_and_announce_due_reminder()`'s Sprint 5.24 generalization (rather than a parallel method) already applied concretely.

**Risk estimation reuses `security/policy_engine.py`'s existing `RiskLevel`/`RiskPolicy`/`PermissionPolicyEngine` (Sprint 4.7) rather than inventing a second, parallel risk taxonomy.** `PermissionPolicyEngine` already classifies a device-control/workflow action's risk and decides whether confirmation is required — exactly the brief's own "Risk estimation... Required confirmation" language. Building a second risk-scoring system in `decision/` for Level 6's own newly-planning-originated actions (Task Graph nodes translated to `ActionRequest`s at Sprint 6.9) would be real, avoidable duplication of a policy this codebase already got right once. `DecisionEngineV2` calls into `PermissionPolicyEngine` for anything that is (or will become) an `ActionRequest`, and adds its own new logic only for what `PermissionPolicyEngine` was never scoped to cover: ranking several *candidate* actions against each other before any one of them is even dispatched, and confidence-weighting a candidate using Sprint 6.4's `ReasoningEngine.estimate_confidence()` output.

## Objectives

- `RankedAction` — one candidate action plus its computed rank, risk, confidence, and confirmation requirement.
- `DecisionEngineV2`: `rank_actions()` (orders several candidate actions by a composite score), `requires_confirmation()` (delegates to `PermissionPolicyEngine`, never reimplements its policy), `suggest_alternatives()` (delegates to `ReasoningEngine.alternatives()`).
- `DecisionEngineConfig` (new `config/schema.py` section — will grow again at Sprint 6.12).

## Dependencies

3.11 (`AuthorityEvaluator`, `DecisionTrace`, `EngineSelection`), 4.7 (`security/policy_engine.py`'s `RiskLevel`/`PermissionPolicyEngine`), 6.4 (`ReasoningEngine.estimate_confidence()`/`alternatives()`), 3.10 (`PriorityQueueManager`/`PriorityLevel`).

## Files to Create

- `decision/decision_engine_v2.py` — `RankedAction`, `DecisionEngineV2`.
- `tests/unit/decision/test_decision_engine_v2.py`

## Files to Modify

- `config/schema.py` — new `DecisionEngineConfig` dataclass: `risk_weight: float = 0.4`, `confidence_weight: float = 0.35`, `priority_weight: float = 0.25` (the three components of `rank_actions()`'s composite score — validated to sum to `1.0`, the same "weights must sum to 1" validation shape `EmotionConfig`'s own tone-blend weights already established at Sprint 5.4).
- `config/defaults.yaml` — matching `decision_engine_v2:` section.
- `config/loader.py` — `_SECTION_SCHEMAS` entry, including the weight-sum validation.

## Expected Classes

- `RankedAction` (dataclass) — `action_request: ActionRequest` (existing type, `device_control/action_engine.py`), `risk_level: RiskLevel` (existing type, `security/policy_engine.py`), `confidence: float` (0.0–1.0, from `ReasoningEngine.estimate_confidence()`), `composite_score: float`, `requires_confirmation: bool`.
- `DecisionEngineV2` — constructor DI: `(authority_evaluator: AuthorityEvaluator, permission_policy_engine: PermissionPolicyEngine, reasoning_engine: ReasoningEngine, decision_engine_config: DecisionEngineConfig)`. Not a `ManagedModule` — a pure composition/scoring layer over already-lifecycle-managed collaborators, the same shape `WorkflowExecutor` already established for its own four collaborators at Sprint 4.10.

## Expected Interfaces

None new.

## Expected Functions

- `DecisionEngineV2.rank_actions(candidates: list[ActionRequest], working_context: WorkingContext | None = None) -> list[RankedAction]` — for each candidate: classifies risk via `permission_policy_engine.classify(candidate)` (existing method — confirmed against the real `PermissionPolicyEngine` signature at implementation time, not guessed here), estimates confidence via `reasoning_engine.estimate_confidence(candidate's own description, working_context)`, reads its `PriorityLevel` if the candidate already carries one (else treats priority as neutral), computes `composite_score = risk_weight * (1 - normalized_risk) + confidence_weight * confidence + priority_weight * normalized_priority`, and sorts descending. A single candidate's classification/estimation failing degrades that candidate to the most conservative ranking (lowest score, `requires_confirmation=True`) rather than aborting the whole ranking — a partial, honestly-degraded ranking is more useful than none, and defaulting to "ask the user" on any real uncertainty is exactly Level 6's own Human Authority First principle.
- `DecisionEngineV2.requires_confirmation(action_request: ActionRequest) -> bool` — a thin, explicitly-named pass-through to `permission_policy_engine`'s own existing confirmation-requirement logic; exists as a method on this class purely so a Level 6 Part A caller has one coherent entry point rather than needing to know to reach into `security/` directly — never reimplements the underlying policy.
- `DecisionEngineV2.suggest_alternatives(action_request: ActionRequest, working_context: WorkingContext | None = None) -> list[Alternative]` — thin pass-through to `reasoning_engine.alternatives()`, given the action's own description as the reasoning subject.

## Data Flow

```
Caller (Multi-Step Workflow Engine 6.9, Proactive Assistant 6.8, Adaptive Prioritization 6.12 —
wired at 6.13) has several candidate ActionRequests, e.g. from Task Graph's ready_tasks()
      ↓
DecisionEngineV2.rank_actions(candidates, working_context)
      ↓
   for each candidate:
   ┌────────────────────────────┬─────────────────────────────────┐
   ↓                            ↓                                 ↓
permission_policy_engine    reasoning_engine.estimate_        candidate's own
.classify(candidate)        confidence(candidate description)  PriorityLevel (if any)
   └────────────────────────────┴─────────────────────────────────┘
      ↓
composite_score = weighted blend  →  RankedAction
      ↓
sorted list[RankedAction]  →  returned to caller
      ↓
requires_confirmation=True items are gated exactly as PermissionPolicyEngine
already gates any other ActionRequest — no new confirmation UX/mechanism
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml`/`config/loader.py` — `DecisionEngineConfig`, weight-sum validation.
2. `decision/decision_engine_v2.py` — `RankedAction`, `DecisionEngineV2.rank_actions()`/`requires_confirmation()`/`suggest_alternatives()`.
3. Unit tests: ranking order against a hand-built set of candidates with known risk/confidence/priority combinations; a single candidate's classification or confidence estimation raising degrades only that candidate, confirmed via the rest of the ranking being unaffected; `requires_confirmation()`/`suggest_alternatives()` confirmed as real pass-throughs via call-argument assertions against fakes (not reimplemented logic).

## Architecture Notes

`DecisionEngineV2` never calls `ActionRegistry.dispatch()` or any executor — it ranks and classifies candidates, nothing more. Dispatch stays exactly where it already lives (`device_control/action_engine.py`'s `ActionRegistry`, `workflow/workflow_executor.py`'s `WorkflowExecutor`). This is a deliberate, load-bearing boundary: Level 6's own "Human Authority First"/"Verify Before Committing" principles mean a *ranking* is not a *decision to act* — the caller (Sprint 6.9/6.13) is what actually decides whether and when to dispatch a top-ranked, non-confirmation-required action, and the existing confirmation/permission machinery is what gates anything requiring one. `DecisionEngineV2` deliberately has no power to skip that gate for any candidate, regardless of how high its own composite score is.

The `EngineSelection` enum's own docstring currently reads "Every engine Part 2's full architecture names" — Level 6 Part A is new scope beyond Part 2 entirely, so this sprint (and 6.13, which is where the enum itself actually gains a new member for live routing) will need that docstring corrected, not left stale. Recorded here since this is the sprint that first makes the claim inaccurate in spirit, even though the enum itself isn't widened until 6.13.

## Integration Considerations

- No live caller yet. Sprint 6.9 (Multi-Step Workflow Engine) is this Sprint Book's own first real consumer (ranking `ready_tasks()`-derived candidates before dispatch); Sprint 6.12 (Adaptive Prioritization) composes `rank_actions()` output with live system/context signals; Sprint 6.13 wires this into `main.py` construction.
- `DecisionEngineV2`'s constructor takes an already-constructed `AuthorityEvaluator`/`PermissionPolicyEngine`/`ReasoningEngine` — no new instances of any of the three are created by this class; whoever constructs `DecisionEngineV2` (Sprint 6.13's composition root) is responsible for wiring the same live instances already used elsewhere, never a second parallel instance.

## Potential Risks

- **The composite-score weights (`risk_weight`/`confidence_weight`/`priority_weight`) are unvalidated guesses**, the same tuned-constant caveat every comparable default in this codebase carries — a real candidate for adjustment once Sprint 6.15's real-usage verification pass observes actual ranking behavior.
- **A candidate whose risk/confidence classification both fail simultaneously still produces a `RankedAction`** (the most-conservative degraded case) rather than being dropped from the list entirely — a deliberate choice (the caller should still see every candidate it asked about) but means a caller must always check `requires_confirmation`/`composite_score` rather than assuming presence-in-the-list implies a clean classification.
- **No handling yet for a candidate that is not translatable into an `ActionRequest` at all** (e.g. a purely informational Task with nothing to dispatch) — `rank_actions()` assumes every candidate already is an `ActionRequest`; the `Task → ActionRequest` translation is Sprint 6.9's own job, so a caller must complete that translation before calling this sprint's methods. Disclosed rather than silently assumed.

## Acceptance Criteria

- `rank_actions()` returns candidates sorted descending by `composite_score`, computed from real `risk_level`/`confidence`/priority inputs.
- A candidate whose risk classification or confidence estimation raises still appears in the output, ranked most conservatively, with `requires_confirmation=True` — the call as a whole never raises because of one bad candidate.
- `requires_confirmation()` returns exactly what `permission_policy_engine`'s own existing method would return for the same `ActionRequest` — verified via a call-argument/return-value passthrough test, not a reimplemented assertion.
- `DecisionEngineConfig`'s three weights are validated to sum to `1.0` (within floating-point tolerance) at config load time.

## Testing Checklist

- [ ] Unit: `rank_actions()` ordering against hand-built candidates spanning the full risk/confidence/priority range.
- [ ] Unit: single-candidate classification failure and confidence-estimation failure, each confirmed to degrade only that candidate.
- [ ] Unit: `requires_confirmation()`/`suggest_alternatives()` pass-through behavior via fake-collaborator call-argument assertions.
- [ ] Unit: `DecisionEngineConfig` weight-sum validation (valid sum accepted; invalid sum rejected at load).

## Documentation Checklist

- [ ] `decision/decision_engine_v2.py` docstring: the explicit "ranks and classifies, never dispatches" boundary, and the reused-not-reinvented `PermissionPolicyEngine` relationship, both stated per Engineering Rationale above.
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

6.6 — Knowledge Graph.

## Future Considerations

- Learning-derived weight tuning (adjusting `risk_weight`/`confidence_weight`/`priority_weight` from Sprint 6.10's own outcome data rather than a fixed config default) — a natural future direction, explicitly not built here since Sprint 6.10 doesn't exist yet at this point in the Book.
- A richer trade-off model for `suggest_alternatives()`'s own output — deferred to whatever Sprint 6.4's own `Alternative` dataclass already bounds itself to; no basis to expand it here.

## Sprint Completion Report (2026-08-09)

Implemented as specified, authorized directly ("continue with sprint 6.5") in the same session as Sprint 6.4, right after it closed.

Delivered `decision/decision_engine_v2.py` (`RankedAction`, `DecisionEngineV2.rank_actions()`/`requires_confirmation()`/`suggest_alternatives()`) — extending `decision/`, not a new package — and `DecisionEngineConfig` (`config/schema.py`/`config/defaults.yaml`/`config/loader.py`), wired in the same declaration order every Level 6 Part A config section has used since 6.1 (planning → context_engine → reasoning → decision_engine_v2 → runtime).

**Two real, disclosed corrections from this sprint file's own text, both caught by checking the real, current source of each composed collaborator before implementing, matching this whole Sprint Book's own now-well-established discipline (6.1's Correction 1, 6.3's Correction 1, both found the identical way)**:

1. **`PermissionPolicyEngine.classify()` takes an `ActionType`, not an `ActionRequest`.** The sprint file's own Expected Functions text describes `permission_policy_engine.classify(candidate)` where `candidate` is the whole `ActionRequest` — the real method (`security/policy_engine.py`) is `classify(self, action_type: ActionType) -> RiskPolicy`. Implemented against the real signature (`candidate.action_type`) throughout.
2. **The weight-sum validation precedent this sprint file cites doesn't exist.** "The same 'weights must sum to 1' validation shape `EmotionConfig`'s own tone-blend weights already established at Sprint 5.4" — `EmotionConfig` has no weight-sum validation anywhere in `config/schema.py`. The real, existing precedent is `MemoryConfig`'s five Dynamic Memory Formula weights (Sprint 3.5) and its `retrieval_similarity_weight`/`retrieval_confidence_weight` pair (Sprint 3.9) — `_validate_decision_engine_v2()` mirrors that pattern exactly (per-field `[0, 1]` range check, then a `sum` check within `1e-6` tolerance), not a guessed-at `EmotionConfig` shape that was never real.

**One real gap in this sprint file's own text, resolved by doing exactly what it literally says and disclosing the result, not by inventing a use for it**: the constructor signature (Expected Classes) names `authority_evaluator: AuthorityEvaluator` as a required parameter, and Dependencies frames this sprint as "composes `AuthorityEvaluator`'s existing output" — but no method in Expected Functions actually calls anything on it. `DecisionEngineV2.__init__()` stores it (`self._authority_evaluator`) exactly as specified, genuinely unused by `rank_actions()`/`requires_confirmation()`/`suggest_alternatives()`, disclosed in the class's own docstring — the same "accepted but not yet consumed" shape `AdaptiveWellnessAdjuster`'s own unused `PREFERRED_TIME` read already established (Sprint 5.22, item 67), left for whichever future sprint (6.12 Adaptive Prioritization, or 6.13 Integration) actually names a use for it, rather than fabricated here.

**Reuse over reinvention, following through on this sprint's own Engineering Rationale literally**: `_composite_score()`'s risk term reuses `security/policy_engine.py`'s real `RiskLevel` (LOW/MEDIUM/HIGH, linearly normalized to `{0.0, 0.5, 1.0}` — a 3-point scale, no basis for anything richer than the enum's own real member count); the priority term reads `ActionRequest.risk_hint: PriorityLevel` directly (already present on every `ActionRequest`, defaulting to `GENERAL_SUGGESTION` — confirmed non-optional, so this sprint file's own "if the candidate already carries one (else treats priority as neutral)" hedge is never a distinct code path: `GENERAL_SUGGESTION` already normalizes to `0.0`, the "no special urgency boost" end of the range). Every description string fed to `reasoning_engine.estimate_confidence()`/`alternatives()` reuses `security/confirmation_service.py`'s own public `build_prompt_text()` — the one function that module deliberately keeps public specifically so other callers get the identical, already-reviewed action description "for free" rather than a second, independently-maintained describe-this-action implementation.

A single candidate's own risk classification or confidence estimation raising degrades only that candidate (`RiskLevel.HIGH`, `confidence=0.0`, `requires_confirmation=True`) rather than aborting the whole `rank_actions()` call — verified via three dedicated tests: a classification failure, a confidence-estimation failure, and a mixed healthy/failing two-candidate batch confirming the healthy candidate's real values are untouched. `requires_confirmation()`/`suggest_alternatives()` are both verified as real pass-throughs via call-argument assertions against a fake `PermissionPolicyEngine`/`ReasoningEngine` (never a reimplemented assertion) — plus one test comparing `requires_confirmation()`'s own output directly against a REAL `PermissionPolicyEngine(SecurityConfig())`'s own `classify().requires_confirmation` for the same `ActionRequest`, proving byte-for-byte equivalence, not just "returns a bool."

16 new tests: `tests/unit/decision/test_decision_engine_v2.py` (11 — ranking order against a hand-built LOW/MEDIUM/HIGH-risk, high/mid/low-priority candidate set; a direct composite-score arithmetic check against the configured weights; the three degrade scenarios above; `requires_confirmation()`'s two pass-through tests plus the real-`PermissionPolicyEngine`-equivalence test; `suggest_alternatives()`'s two pass-through tests), plus 5 more `DecisionEngineConfig` validation tests in `test_schema.py` (default valid, weights not summing to 1.0 rejected, weights summing to 1.0 within float tolerance accepted, and one out-of-`[0,1]`-range test per direction).

Full suite (unit + integration, opt-in real-model marker excluded): 2028 passing (2012 + 16 new), 1 skipped, zero failures, zero new flakiness. `ruff check .` clean repo-wide.

`docs/STATUS.md` (Level 6 Part A narrative extended, Part A header → "5/15 implemented," Decision & Prioritization phase → `Developing`, "6.5 Complete"), `docs/sprint_book/INDEX.md` (6.5 row → `Complete`) updated. No new `backlog/technical_debt.md` entry — this sprint extends `decision/`, no new top-level package, mirroring Sprint 6.2's own identical "extends an existing Level 6 Part A package, no new backlog item" precedent.

**No git commit made** — per this project's own "only commit when explicitly asked" rule; changes left in the working tree alongside Sprint 6.4's own still-uncommitted work, the user not yet asked whether to commit. **Sprint 6.6 (Knowledge Graph) is next.**
