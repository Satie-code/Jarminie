# Sprint 4.1 — Action Engine Foundation

## Sprint ID

4.1

## Sprint Name

Action Engine Foundation

## Purpose

Establish the shared contract every Level 4 action — application launch, file operation, window operation, system command, workflow step — is built against: a typed request/result shape, an executor interface, a registry, and a real (if minimal) hook into the Authority System (Sprint 3.11) and a new thin Security Layer stub. This is the foundation Sprints 4.2–4.10 build on, the same role Sprint 1.5 (Core Manager) played for Level 1 and Sprint 3.9 (Memory Retrieval Engine) played as a late-inserted composition layer for Level 3.

## Engineering Rationale

Part 2's Device Control Engine section lists five distinct control surfaces (Applications, Windows, Files, Folders, System settings) plus Automation and System monitoring; Part 4's Phase 4.1 and this task's own Level 4 Goal both require every one of them to be "safe, auditable, and reversible where practical" and to enforce "permission-based action execution." Building five-plus independent executors without a shared contract first would mean re-solving the same problem five times — how a caller requests an action, how risk is classified, how a result is reported, how a failure is logged — a direct violation of Single Responsibility and Documentation First applied at the architecture level, not just the code level. This sprint is that shared contract, and nothing else: no application/file/window/command logic lives here, matching the discipline Sprint 3.9 itself named ("introduces no new storage, no new confidence logic, only retrieval composition").

This sprint is a **deliberate addition** to `docs/sprint_book/INDEX.md`'s original roadmap-granularity Level 4 plan, which listed `4.1 Application Control` as the first sprint with no separate foundation step. See `INDEX.md`'s "Level 4 breakdown changes" note for the full before/after — the same category of deviation as Level 3's Sprint 3.9 insertion, explained in full here rather than assumed.

Two structural decisions worth recording explicitly, since neither is spelled out by any prior spec:

- **Home for the shared contract.** Part 3's repository structure is fixed and has no neutral "actions" folder. `device_control/` is the more architecturally foundational of the two consumers — Part 2's own Workflow Engine example ("Continue Project JARMINEI → Open IDE → Open project folder → ...") is a sequence of what are, individually, Device Control actions — so `workflow/` depends on `device_control/`'s action contract, never the reverse. The contract therefore lives in `device_control/action_engine.py`, not a new top-level package.
- **Security Layer stub timing.** `INDEX.md`'s own Recommendations section (recorded 2026-07-20, before this sprint existed) flagged: *"Consider a thin `security/` stub (permission-check pass-through, no real enforcement) as early as Sprint 4.1... Device Control's 'permission-sensitive operations always require user approval' needs something to call even before Phase 6.3 builds it out fully."* This sprint acts on that recommendation directly: `security/permission_gate.py` ships now as a real, callable, honestly-thin pass-through (delegates to `AuthorityEvaluator`, adds no new policy of its own) — not a placeholder that returns `True` unconditionally. Sprint 4.7 (Permission & Confirmation System) is what turns this into a real risk-classification and confirmation-flow engine.

## Objectives

- A typed `ActionRequest` / `ActionResult` / `ActionStatus` shape every Level 4 executor uses, uniformly.
- An `ActionExecutor` protocol (interface-first design, per `docs/CODING_STANDARDS.md`) that every concrete executor (Application Manager, File Operations, Window Management, Command Execution) implements.
- An `ActionRegistry` that looks up the correct executor for a given `ActionRequest.action_type`.
- A real, callable `PermissionGate` (in `security/`) that every executor consults before acting — thin now, deliberately built to be extended by Sprint 4.7 rather than replaced.
- Zero application/file/window/command-specific logic in this sprint.

## Dependencies

1.2 (Configuration Manager), 1.5 (Core Manager), 3.10 (Priority Queue — `PriorityLevel` reused for `ActionRequest.risk_hint`), 3.11 (Authority Evaluation & Engine Selection)

## Files to Create

- `device_control/action_engine.py` — `ActionType` (enum), `ActionStatus` (enum), `ActionRequest`, `ActionResult`, `ActionContext`, `ActionExecutor` (Protocol), `ActionRegistry`.
- `security/permission_gate.py` — `PermissionDecision` (enum), `PermissionGate`.
- `tests/unit/device_control/test_action_engine.py`
- `tests/unit/security/test_permission_gate.py`

## Files to Modify

- `config/schema.py` — new `DeviceControlConfig` dataclass (empty-but-present placeholder fields only: this sprint adds no real policy yet, Sprint 4.7 grows it) registered on `AppConfig`.
- `config/defaults.yaml` — matching `device_control:` section.
- `docs/backlog/technical_debt.md` — record the `device_control/`-hosts-the-shared-contract decision above as a documented architecture note (not debt, but the project's established pattern of recording non-obvious structural calls in one place — see item 2's precedent for `emotion/`).

## Expected Classes

- `ActionType(Enum)` — `LAUNCH_APPLICATION`, `CLOSE_APPLICATION`, `FILE_CREATE`, `FILE_MOVE`, `FILE_COPY`, `FILE_RENAME`, `FILE_DELETE`, `FOLDER_CREATE`, `FOLDER_DELETE`, `WINDOW_FOCUS`, `WINDOW_MOVE`, `WINDOW_RESIZE`, `WINDOW_MINIMIZE`, `WINDOW_CLOSE`, `SYSTEM_COMMAND`, `WORKFLOW_STEP` — every concrete action Sprints 4.2–4.10 will implement, declared once here so no executor invents its own ad hoc type strings.
- `ActionStatus(Enum)` — `PENDING`, `AWAITING_CONFIRMATION`, `APPROVED`, `DENIED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `RECOVERED` (Sprint 4.8 is the real producer of `RECOVERED`; the value exists here so `ActionResult` never needs a breaking change later).
- `ActionContext` (dataclass) — `requested_by: str` (e.g. `"user_voice"`, `"workflow:<workflow_id>"`), `persona_name: str | None`, `session_id: str | None`, `decision_trace: DecisionTrace | None` (Sprint 3.11's own explainability object, threaded through so a denied/failed action can still answer "why").
- `ActionRequest` (dataclass) — `action_type: ActionType`, `parameters: dict[str, object]`, `context: ActionContext`, `risk_hint: PriorityLevel` (Sprint 3.10's enum, reused rather than a new one — a `CRITICAL_EMERGENCY`-hinted request gets the same urgency vocabulary the rest of the Decision Engine already uses), `requested_at: datetime`.
- `ActionResult` (dataclass) — `request: ActionRequest`, `status: ActionStatus`, `output: object | None`, `error_message: str | None`, `completed_at: datetime`.
- `ActionExecutor` (Protocol) — `can_handle(action_type: ActionType) -> bool`; `execute(request: ActionRequest) -> ActionResult`. Deliberately two methods only, mirroring `ManagedModule`'s own "kept deliberately minimal" precedent (Sprint 1.5).
- `ActionRegistry` — `register(executor: ActionExecutor) -> None`; `dispatch(request: ActionRequest) -> ActionResult` (finds the first registered executor whose `can_handle()` is `True`, consults `PermissionGate` first, then calls `execute()`; raises no exception — an unhandled `action_type` or a denied permission both resolve to a normal `ActionResult` with `status=FAILED`/`DENIED`, per Fail Gracefully).
- `PermissionDecision(Enum)` — `ALLOW`, `DENY`, `REQUIRE_CONFIRMATION` (the last is defined now but never returned by this sprint's own logic — Sprint 4.7 is the first real producer; see Integration Considerations).
- `PermissionGate` — constructor DI: `(authority_evaluator: AuthorityEvaluator)`. Not a `ManagedModule` (no lifecycle of its own, same reasoning `ContextManager`/`MemoryRetrievalEngine` used) — a plain, stateless delegator.

## Expected Interfaces

- `ActionExecutor` (Protocol, above) — the interface every Sprint 4.2–4.5 concrete class implements; `workflow/` (Sprints 4.9–4.10) depends on this protocol, never on a concrete executor class directly.

## Expected Functions

- `ActionRegistry.register(executor: ActionExecutor) -> None`
- `ActionRegistry.dispatch(request: ActionRequest) -> ActionResult` — calls `PermissionGate.check(request)` first; on `DENY`, returns immediately with `ActionStatus.DENIED` and never calls the executor; on `ALLOW`, proceeds to `execute()`; on `REQUIRE_CONFIRMATION` (unreachable this sprint), would return `ActionStatus.AWAITING_CONFIRMATION` — the branch is written now so Sprint 4.7 changes zero call sites, only `PermissionGate`'s internals.
- `PermissionGate.check(request: ActionRequest) -> PermissionDecision` — this sprint's real logic: delegates the request's `risk_hint`/context to `AuthorityEvaluator`-shaped reasoning; concretely, denies nothing this sprint (`ActionType` alone carries no real risk signal yet — no application/file/window logic exists to be risky about), always returns `ALLOW`, but is a real, tested, callable method, not a `TODO`. Sprint 4.7 is what makes this method's answer actually vary by risk.

## Data Flow

```
Decision Engine (3.11) DecisionTrace, once EngineSelection.DEVICE_CONTROL/WORKFLOW is real (Sprint 4.11)
      ↓
caller builds ActionRequest(action_type, parameters, context, risk_hint)
      ↓
ActionRegistry.dispatch(request)
      ↓
PermissionGate.check(request) → ALLOW / DENY / REQUIRE_CONFIRMATION
      ↓ (ALLOW)
matching ActionExecutor.execute(request)
      ↓
ActionResult(status, output, error_message)
      ↓
(Sprint 4.8) ActionAuditLog.record(result)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `DeviceControlConfig` (minimal placeholder).
2. `device_control/action_engine.py` — every dataclass/enum/Protocol/class above.
3. `security/permission_gate.py` — `PermissionDecision`, `PermissionGate`.
4. Unit tests for `ActionRegistry` dispatch (including the "no executor can handle this type" and "permission denies" degrade paths) and `PermissionGate.check()`.
5. `docs/backlog/technical_debt.md` entry recording the `device_control/`-hosts-the-shared-contract decision.

## Architecture Notes

`ActionRegistry`/`ActionExecutor` is deliberately the same shape as `ModuleRegistry`/`ManagedModule` (Sprint 1.5) — a name/type-keyed lookup over a small protocol — reusing an already-proven pattern rather than inventing a new one, per the project's own "prefer editing/extending over recreating" discipline (`05_Claude_Development_Guide.md`, Step 1). It is a distinct class, not a reuse of `ModuleRegistry` itself: `ManagedModule` answers "is this subsystem alive," `ActionExecutor` answers "can you perform this specific, parameterized action" — different questions, same shape, Single Responsibility preserved by keeping them separate.

`PermissionGate` is intentionally NOT a `ManagedModule` — it has no lifecycle, no background state, and is cheap to construct; wrapping it in the `ManagedModule` machinery would add ceremony with no benefit, the same judgment call already made for `ContextManager` (2.8) and `MemoryRetrievalEngine` (3.9).

`ActionContext.decision_trace` is `DecisionTrace | None`, not a hard `DecisionTrace`, because not every action originates from a live conversation turn — a workflow step triggered by another workflow step, or (later, Level 4 Part B) a scheduled reminder, has no single originating `DecisionTrace` to attach. `None` is the honest value in that case, not a synthetic one.

## Integration Considerations

- No live caller exists yet. `ActionRegistry`/`PermissionGate` are exercised only by this sprint's own unit tests until Sprint 4.2 registers the first real `ActionExecutor`, and until Sprint 4.11 wires `EngineSelection.DEVICE_CONTROL`/`WORKFLOW` in `decision/authority.py` to actually build and dispatch an `ActionRequest` — the same "implemented and tested in isolation, live caller arrives later" shape already established by `backlog/technical_debt.md` items 11, 15, and 17. Not repeating that gap silently: Sprint 4.11 is named explicitly as the live-caller sprint in this file's own Next Sprint chain, not left to be rediscovered later.
- `PermissionGate.check()` always returning `ALLOW` this sprint is a known, temporary, and explicitly documented state — Sprint 4.7 is the committed resolution, not an open-ended placeholder.
- `AuthorityEvaluator.approved_emergency_procedures` (3.11) remains empty through this sprint — `PermissionGate` does not populate it; Sprint 4.7 owns that as "a deliberate, reviewed act," per `INDEX.md`'s own flagged Recommendation.

## Potential Risks

- **`ActionType` is a closed enum.** Adding a genuinely new action type later (e.g. a Level 5 capability) means editing this file — an accepted trade-off for the type safety and single-source-of-truth benefit over a stringly-typed alternative, consistent with `IntentCategory`'s own closed-enum precedent (`decision/models.py`).
- **Reusing `PriorityLevel` for `ActionRequest.risk_hint`** conflates "how urgent" (Priority Queue's original purpose) with "how risky" (this sprint's need) — acceptable now since no richer risk vocabulary exists yet; Sprint 4.7 may find it needs its own `RiskLevel` enum instead, flagged as a Future Consideration rather than built speculatively here.
- **A stub `PermissionGate` that always allows** is safe only because nothing yet calls `ActionRegistry.dispatch()` with a live, consequential action (Integration Consideration above) — this sprint's own Acceptance Criteria include a regression test guaranteeing Sprint 4.7 cannot ship without changing this default-allow behavior for at least one real risk case.

## Acceptance Criteria

- `ActionRegistry.dispatch()` correctly routes to the one registered executor whose `can_handle()` returns `True` for a given `action_type`.
- `ActionRegistry.dispatch()` for an unregistered `action_type` returns `ActionStatus.FAILED` with a clear `error_message`, never raises.
- `PermissionGate.check()` is a real, callable method backed by a real `AuthorityEvaluator` instance (not mocked in at least one test) and returns `PermissionDecision.ALLOW` for every case in this sprint's own scope.
- `ActionRegistry.dispatch()` calls `PermissionGate.check()` before calling `execute()` on every request, provably (a test double `PermissionGate` returning `DENY` proves the executor is never reached).
- `DeviceControlConfig` loads and validates with zero fields required for this sprint's own scope (placeholder only).

## Testing Checklist

- [ ] Unit: `ActionRegistry.register()`/`dispatch()` correct-executor routing.
- [ ] Unit: `dispatch()` with no matching executor degrades to `FAILED`, not an exception.
- [ ] Unit: `dispatch()` short-circuits to `DENIED` when `PermissionGate` denies, executor never called.
- [ ] Unit: `PermissionGate.check()` against a real `AuthorityEvaluator()` (default, empty whitelist) returns `ALLOW`.
- [ ] Unit: `ActionResult`/`ActionRequest`/`ActionContext` field defaults and `datetime` stamping.
- [ ] Unit: `DeviceControlConfig` loads via `ConfigLoader` with no validation errors.

## Documentation Checklist

- [ ] `device_control/action_engine.py` module docstring: this sprint's role as the shared contract, explicit statement that no application/file/window/command logic lives here.
- [ ] `security/permission_gate.py` module docstring: explicit "always ALLOW this sprint, Sprint 4.7 replaces this" statement, so no future reader mistakes the stub for a finished policy engine.
- [ ] `docs/backlog/technical_debt.md` — the `device_control/`-hosts-the-shared-contract architecture note.
- [ ] `docs/STATUS.md` — Phase 4.1 (Device Control) row moves to `Designing`.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium — no algorithmic complexity, but this sprint's shapes are load-bearing for the rest of Level 4, so correctness and API stability matter more than usual.

## Estimated Development Time

1–1.5 days.

## Risks

See Potential Risks above (kept together per this Sprint Book's own template; duplicated here only as a pointer, not repeated verbatim, to avoid drift between two copies of the same list).

## Next Sprint

4.2 — Application Manager.

## Future Considerations

- If `ActionType`'s closed enum proves too rigid once Level 5 (Wellness/Emotion) or Level 4 Part B (Scheduler/Internet Agent) need their own action-shaped operations, consider a registration-based open type instead — not built speculatively now (YAGNI, matches this project's consistent stance elsewhere).
- A dedicated `RiskLevel` enum, separate from `PriorityLevel`, if Sprint 4.7's real risk classification needs finer granularity than urgency alone provides.

---

## Sprint Completion Report (2026-07-20)

### Summary

Implemented `device_control/action_engine.py` (`ActionType`, `ActionStatus`, `ActionContext`, `ActionRequest`, `ActionResult`, `ActionExecutor`, `ActionRegistry`) and `security/permission_gate.py` (`PermissionDecision`, `PermissionGate`) exactly per this file's own spec, plus the `DeviceControlConfig` placeholder section wired through `config/schema.py`/`config/loader.py`/`config/defaults.yaml`. 641/641 tests passing (623 prior + 18 new), `ruff check .` clean.

### Files Created

- `device_control/action_engine.py` — `ActionType`, `ActionStatus`, `ActionContext`, `ActionRequest`, `ActionResult`, `ActionExecutor` (Protocol), `ActionRegistry`.
- `security/permission_gate.py` — `PermissionDecision`, `PermissionGate`.
- `tests/unit/device_control/test_action_engine.py` — 12 tests.
- `tests/unit/security/test_permission_gate.py` — 4 tests.

### Files Modified

- `config/schema.py` — `DeviceControlConfig` (empty placeholder dataclass, per spec), registered on `AppConfig`; `AppConfig.validate()` docstring notes there is nothing to validate yet.
- `config/defaults.yaml` — `device_control: {}` section added, with a comment pointing to the schema docstring.
- `config/loader.py` — **not named in this sprint's own Files to Modify list, but a real, necessary addition found during implementation**: `_SECTION_SCHEMAS` (the file's own documented "single source of truth for every `AppConfig` section... adding a future section here is now the only place needed for both load paths to pick it up") had to gain `"device_control": DeviceControlConfig`, or the new section would silently never load from file/env at all — the exact class of bug that comment's own history (Sprint 1.7/1.8's `UIConfig` gap) already warns about by name. Caught by writing `test_real_shipped_defaults_yaml_loads_device_control_section` first and watching it fail before this fix.
- `tests/unit/config/test_loader.py` — 2 new tests (`test_device_control_section_loads_with_no_errors`, `test_real_shipped_defaults_yaml_loads_device_control_section`) — not named in this sprint's own Files to Create/Modify list either, added for the same reason as the `config/loader.py` fix above: the sprint's own Acceptance Criteria ("`DeviceControlConfig` loads and validates with zero fields required") and Testing Checklist ("Unit: `DeviceControlConfig` loads via `ConfigLoader` with no validation errors") explicitly require this coverage, and it belongs in the existing config test suite (matching that suite's own established per-section-addition pattern), not a new dedicated file.
- `docs/backlog/technical_debt.md` — item 18 added (the `device_control/`-hosts-the-shared-contract decision, resolved/documented, no action needed); item 17 updated to reflect Sprint 4.6's future partial resolution note and to fix a stale "Sprint 4.8+" reference (Scheduler moved to Level 4 Part B / renumbered 4.14+ when this Sprint Book was written — the technical debt entry hadn't been updated to match).
- `docs/STATUS.md` — Phase 4.1 row: status moved `Designing` → `Developing`, with this sprint's own completion noted.

### Tests Added

18 total. In `test_action_engine.py`: correct-executor routing across multiple registered executors; no-matching-executor and zero-executors degrade to `FAILED`; `PermissionGate` `DENY`/`REQUIRE_CONFIRMATION`/`ALLOW` branches (via a duck-typed `StubPermissionGate`), each proving the executor is or isn't called as expected; `PermissionGate.check()` raising and an executor's own `execute()` raising both degrade to `FAILED` rather than propagating (Fail Gracefully); `ActionContext`/`ActionRequest`/`ActionResult` field defaults; one full end-to-end test against a *real* `PermissionGate` backed by a *real* `AuthorityEvaluator`, not just stubs. In `test_permission_gate.py`: `check()` returns `ALLOW` for every `ActionType`; `ALLOW` is genuinely unconditional even against a non-empty (Sprint-4.7-shaped) `approved_emergency_procedures` whitelist; constructed with a real, non-mocked `AuthorityEvaluator`; a full real `ActionRequest` round trip. In `test_loader.py`: the new `device_control` section resolves to a valid empty `DeviceControlConfig` both from a minimal test fixture and from the real, checked-in `config/defaults.yaml`.

### Documentation Updated

This file (Sprint Completion Report). `device_control/action_engine.py` and `security/permission_gate.py` module/class docstrings (written as part of initial implementation, matching this sprint's own Documentation Checklist). `config/schema.py`'s `DeviceControlConfig` docstring. `docs/backlog/technical_debt.md` (items 17, 18). `docs/STATUS.md` (Phase 4.1 row). `docs/sprint_book/INDEX.md` (this sprint's row marked Complete).

### Acceptance Criteria Checklist

- ✔ `ActionRegistry.dispatch()` correctly routes to the one registered executor whose `can_handle()` returns `True` for a given `action_type`.
- ✔ `ActionRegistry.dispatch()` for an unregistered `action_type` returns `ActionStatus.FAILED` with a clear `error_message`, never raises.
- ✔ `PermissionGate.check()` is a real, callable method backed by a real `AuthorityEvaluator` instance (not mocked in at least one test) and returns `PermissionDecision.ALLOW` for every case in this sprint's own scope.
- ✔ `ActionRegistry.dispatch()` calls `PermissionGate.check()` before calling `execute()` on every request — proven via `StubPermissionGate` returning `DENY`, executor never called.
- ✔ `DeviceControlConfig` loads and validates with zero fields required for this sprint's own scope — proven against both a minimal test fixture and the real shipped `config/defaults.yaml`.

### Engineering Decisions

- **Circular import between `device_control/` and `security/`, resolved via `TYPE_CHECKING`.** `ActionRegistry` needs a real runtime import of `PermissionDecision`/`PermissionGate` from `security.permission_gate`; `PermissionGate.check()`'s own signature names `ActionRequest` (defined in `device_control/action_engine.py`) — a naive two-way import would cycle. Resolved by having `security/permission_gate.py` import `ActionRequest` only under `if TYPE_CHECKING:`, combined with `from __future__ import annotations` (PEP 563) so the annotation is never evaluated at runtime. This also settles, in code, the dependency direction this sprint's own spec argued for in prose: `device_control` depends on `security` (a lower-level, reusable safety primitive per Part 2's "gatekeeper" framing), never the reverse. Not called out anywhere in this sprint's own original Architecture Notes — a real implementation-time discovery, not a deviation from the plan.
- **`ActionRequest.risk_hint` given a default (`PriorityLevel.GENERAL_SUGGESTION`), `ActionRequest.requested_at` left required with no default.** This sprint's own Expected Classes section listed both fields without specifying defaults. Matched against this codebase's own established convention: timestamp fields (`Intent.detected_at`, `PriorityItem.enqueued_at`, `ResourceSnapshot.timestamp`) are always required and constructed explicitly by the caller, never `default_factory`-hidden — so `requested_at` follows that precedent. `risk_hint` isn't a timestamp and a sensible default measurably reduces every call site's boilerplate without hiding anything meaningful, so it got one.
- **`ActionRegistry.dispatch()` wraps both `PermissionGate.check()` and the executor's own `execute()` in `try/except`, converting any raised exception into `ActionResult(status=FAILED)`.** Not explicitly spelled out in this sprint's own Expected Functions description (which only names the missing-executor `FAILED` degrade path), but required by the broader Fail Gracefully Rule and by this sprint's own Architecture Notes precedent (`AuthorityEvaluator.evaluate()`'s "fail safe-down, never safe-up"). Sprints 4.2–4.5's own individual executors are separately specified to never let an exception escape their own `execute()` — this is deliberate defense-in-depth at the dispatch layer, not a substitute for that discipline.
- **`DeviceControlConfig` shipped as a genuinely zero-field dataclass**, per this sprint's own "empty-but-present placeholder" instruction, rather than inventing a placeholder field. Valid Python, and keeps `AppConfig.validate()` honest — there is truly nothing to validate yet, so no `_validate_device_control()` method was added (a no-op validator would have been dead code).

### Remaining Risks

- This sprint's own flagged risks stand as expected and are unchanged by implementation: `ActionType`'s closed enum, `PriorityLevel` reuse for `risk_hint`, and the always-`ALLOW` `PermissionGate` stub are all real, deliberate, and explicitly tracked for Sprint 4.7's resolution — none surfaced as worse than anticipated during implementation.
- No live caller exists anywhere yet (`main.py` does not construct or register `ActionRegistry`/`PermissionGate`) — exactly as this sprint's own Integration Considerations predicted; Sprint 4.11 is the committed resolution.

### Technical Debt

Item 18 (new, resolved/documented — the `device_control/`-hosts-the-shared-contract decision) and item 17 (updated, partially resolved by a future sprint's own design, stale cross-reference fixed) in `docs/backlog/technical_debt.md`. No new *unresolved* debt introduced by this sprint.

### Recommendations

- **For Sprint 4.2 (Application Manager)**: the first real `ActionExecutor` — double-check its own spec's assumptions about `ActionRequest.parameters`'s shape against what actually shipped here (a plain `dict[str, object]`, no further structure enforced), per this project's established "check the next sprint's assumptions against what actually shipped" pattern.
- **For Sprint 4.7 (Permission & Confirmation System)**: `PermissionGate.__init__` already stores `authority_evaluator` as `self._authority_evaluator` — ready for that sprint to start consulting it for real without a constructor signature change.
- Any future sprint adding a new `AppConfig` section **must** remember `config/loader.py`'s `_SECTION_SCHEMAS` dict, not just `config/schema.py`/`config/defaults.yaml` — this sprint is the second time this exact class of gap has been found (see the `config/loader.py` comment's own reference to the original Sprint 1.7/1.8 incident), suggesting it's worth a standing checklist item rather than relying on each sprint's implementer to remember it fresh.

**Sprint 4.1 (Action Engine Foundation) is complete.** **Sprint 4.2 (Application Manager) is next.**
