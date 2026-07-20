# Sprint 4.8 — Action Logging & Recovery

## Sprint ID

4.8

## Sprint Name

Action Logging & Recovery

## Purpose

Give every executed Level 4 action a persistent audit trail and, where practical, a way to recover from it — this task's own Level 4 Goal lines, "Logging executed actions" and "Recovering gracefully from failed actions," and the task's own closing instruction: "Every automated action must be safe, auditable, and reversible where practical."

## Engineering Rationale

**New sprint**, with no direct predecessor in `docs/sprint_book/INDEX.md`'s original roadmap-granularity Level 4 plan — that plan named no dedicated logging/recovery sprint anywhere in Phase 4.1 or 4.2. This is a real, deliberate addition, justified the same way Sprint 4.5 (Command Execution Engine) was: this task's own Level 4 Goal list names both capabilities explicitly, and `docs/CODING_STANDARDS.md`'s existing logging rules ("use the shared logger per subsystem... never log conversation content, credentials, or other personal data") were written for conversational/voice subsystems, not for an audit trail of destructive filesystem/process/command operations — a genuinely different logging shape (structured, queryable, retained deliberately, not just `logger.info()` calls scattered through each executor) deserves its own sprint rather than being bolted onto Sprints 4.2–4.5 piecemeal after the fact.

Built **after** Sprint 4.7 (Permission & Confirmation System), not before, because a complete audit entry needs to record not just what an executor did but what was *decided* about it — the `PermissionDecision`, the `RiskLevel`, whether confirmation was requested and how it resolved. Building the audit log before Sprint 4.7 existed would mean revisiting its schema immediately afterward; sequencing it last among the "policy" sprints (4.1, 4.6, 4.7, 4.8) avoids that churn.

## Objectives

- `ActionAuditLog`: a persistent (SQLite-backed, reusing `SqliteClient` per this project's own established generic-DB-layer pattern) record of every `ActionResult` that reached `ActionRegistry.dispatch()`, including denied/failed ones, not just successes.
- `ActionRecoveryManager`: where an action is reversible (file delete via recycle bin, 4.3; a `TrackedApplication` that was launched, 4.2), exposes a `restore()`/`undo()` path; where it is not (a command execution, most window operations), records that explicitly rather than pretending recoverability exists.
- Retry/backoff for a defined set of transient failure categories (timeout, resource-gate block) — the Fail Gracefully Rule applied to Level 4 specifically: a transient failure should not require the user to re-issue the same request from scratch.

## Dependencies

4.1 (Action Engine Foundation), 4.2 (Application Manager), 4.3 (File & Folder Operations), 4.6 (System Monitoring, Action-Aware), 4.7 (Permission & Confirmation System)

## Files to Create

- `device_control/action_log.py` — `ActionAuditRecord` (dataclass), `ActionAuditLog`, `ActionRecoveryManager`, `RecoveryOutcome` (enum).
- `tests/unit/device_control/test_action_log.py`

## Files to Modify

- `device_control/action_engine.py` — `ActionRegistry.dispatch()` gains an additive `audit_log: ActionAuditLog | None = None` constructor parameter (same optional-DI pattern Sprint 4.6 used for `resource_gate`); when present, every `dispatch()` call — success, denial, or failure alike — is recorded via `audit_log.record()` before the `ActionResult` is returned.
- `config/schema.py` — `DeviceControlConfig` gains `audit_log_retention_days: int = 90` and `max_retry_attempts: int = 2` (for the transient-failure categories named above; `0` disables retry entirely — a valid, honest configuration, not a special-cased "off" flag).
- `config/defaults.yaml` — matching fields.

## Expected Classes

- `ActionAuditRecord` (dataclass) — `action_type: str`, `parameters_summary: str` (a redacted/truncated rendering of `ActionRequest.parameters` — never the raw dict verbatim, since Sprint 4.5's own Potential Risks already flagged that command output/parameters can contain sensitive data), `requested_by: str`, `risk_level: str | None`, `permission_decision: str`, `status: str`, `error_message: str | None`, `is_reversible: bool`, `recorded_at: datetime`, `record_id: int | None` (assigned by SQLite on insert).
- `ActionAuditLog(ManagedModule)` — constructor DI: `(sqlite_client: SqliteClient, device_control_config: DeviceControlConfig)`. Owns its own table DDL (`action_audit_log`), following `ConversationSessionStore`'s (2.7) and `MemoryStore`'s (3.1) own "caller owns its own DDL against the shared `SqliteClient`" precedent exactly — no second database-access layer invented.
- `ActionRecoveryManager` — constructor DI: `(audit_log: ActionAuditLog, file_operations_manager: FileOperationsManager, application_manager: ApplicationManager)`. Not a `ManagedModule` (no lifecycle of its own).
- `RecoveryOutcome(Enum)` — `RECOVERED`, `NOT_REVERSIBLE`, `RECOVERY_FAILED`.

## Expected Interfaces

None new.

## Expected Functions

- `ActionAuditLog.record(result: ActionResult, permission_decision: PermissionDecision, risk_level: RiskLevel | None) -> ActionAuditRecord` — builds the redacted `parameters_summary` (truncates long values, e.g. `CommandResult.stdout`/`stderr`, to a fixed length; never logs a value under a parameter key named `password`/`token`/`secret`/`credential`, a simple deny-by-keyword redaction matching the project's existing "never log conversation content, credentials" rule applied concretely here for the first time), persists via `sqlite_client`.
- `ActionAuditLog.query(action_type: ActionType | None = None, since: datetime | None = None, limit: int = 50) -> list[ActionAuditRecord]` — the read side, for a future "what did you do recently" query (a real, if not yet UI-surfaced, Explainability Rule capability).
- `ActionAuditLog.purge_older_than(days: int) -> int` — mirrors `ConversationSessionStore.purge_older_than()`'s (2.7) exact existing signature/pattern; **this sprint gives it a real caller from day one** (see Architecture Notes) rather than repeating `backlog/technical_debt.md` item 11's "implemented, no caller" gap a third time.
- `ActionRecoveryManager.attempt_recovery(record: ActionAuditRecord) -> RecoveryOutcome` — for a `FILE_DELETE`/`FOLDER_DELETE` record, attempts an OS-level recycle-bin restore (platform-specific; a real, tested mechanism, not aspirational — see Potential Risks for its real limits); for a `LAUNCH_APPLICATION` record whose `TrackedApplication` is still tracked, offers `close()` as the "undo" (closing what was opened) — a pragmatic, honest definition of "undo a launch," not a claim of true reversibility; for every other action type, returns `NOT_REVERSIBLE` immediately, since Part 2's own language is "reversible where practical," not "reversible always."

## Data Flow

```
ActionRegistry.dispatch(request) → ActionResult (success, denial, or failure)
      ↓
ActionAuditLog.record(result, permission_decision, risk_level)
      ↓
ActionAuditRecord persisted (SQLite, via SqliteClient)
      ↓
(on user request, e.g. "undo that") ActionRecoveryManager.attempt_recovery(record)
      ↓
RECOVERED / NOT_REVERSIBLE / RECOVERY_FAILED
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `audit_log_retention_days`, `max_retry_attempts`.
2. `device_control/action_log.py` — `ActionAuditRecord`, `ActionAuditLog` (own DDL, `record()`/`query()`/`purge_older_than()`), `ActionRecoveryManager`, `RecoveryOutcome`.
3. `device_control/action_engine.py` — additive `ActionRegistry.dispatch()` audit-log integration.
4. Retry/backoff for transient failures (`ActionStatus.FAILED` where `error_message` indicates a timeout or a Sprint 4.6 resource-gate block specifically — not a blanket retry-everything policy, since retrying a genuine `DENIED` or a bad-path `FAILED` would be pointless and noisy) inside `ActionRegistry.dispatch()`, bounded by `max_retry_attempts`.
5. Unit tests across all new functionality, including the redaction behavior and the recovery paths.

## Architecture Notes

`ActionAuditLog.purge_older_than()` is deliberately given a real caller **within this same sprint** — unlike `ConversationSessionStore.purge_older_than()` (2.7) and `MemoryLifecycleManager`'s cleanup passes (3.6), both of which shipped with no periodic caller and are still tracked as open gaps (`backlog/technical_debt.md` items 11, 15). This sprint does not repeat that pattern a third time: `ActionAuditLog.start()` (its `ManagedModule.start()`) calls `purge_older_than(audit_log_retention_days)` once at startup — the exact same "one-time-at-startup, not yet a true periodic cadence" compromise Sprint 3.12 already established for `MemoryLifecycleManager`, honestly scoped the same way, not overstated as a real recurring schedule. A true periodic cadence for all three (`ConversationSessionStore`, `MemoryLifecycleManager`, `ActionAuditLog`) remains, as items 11/15 already note, a Level 4 Part B Scheduler concern.

Retry/backoff lives inside `ActionRegistry.dispatch()`, not inside each individual executor — a retry is a cross-cutting policy identical in shape for every executor (attempt, check for a transient-shaped failure, wait, retry up to `max_retry_attempts`), so implementing it once at the dispatch layer avoids five near-identical retry loops (DRY, Single Responsibility: an executor's own `execute()` should not need to know about retry policy at all).

`ActionRecoveryManager`'s honest three-outcome model (`RECOVERED`/`NOT_REVERSIBLE`/`RECOVERY_FAILED`) deliberately has no "partially recovered" state — Part 2's Explainability Rule means a recovery attempt's outcome must be stated plainly, not hedged; if a future action type genuinely has a partial-recovery shape, that is a real design problem for whichever future sprint introduces it, not something to paper over here with a vague status.

## Integration Considerations

- Wired into the live `ActionRegistry` construction, and registered as a `ManagedModule` with `CoreManager`, by Sprint 4.11.
- Sprint 4.10 (Workflow Executor) records one `ActionAuditRecord` per workflow step (via the same `ActionRegistry.dispatch()` call path each step already uses) plus, separately, its own workflow-level run record — this sprint's schema does not need a "workflow" concept of its own; Sprint 4.10 correlates its own step results by a shared `requested_by = "workflow:<workflow_id>"` value (already part of `ActionContext`, Sprint 4.1), not a new foreign key this sprint would need to anticipate.
- No UI surface for `ActionAuditLog.query()`/`ActionRecoveryManager.attempt_recovery()` exists yet — both are real, callable, and tested, but (matching this project's now-familiar "implemented, live caller arrives later" pattern, made explicit rather than hidden) a voice command like "undo that" or "what did you just do" has no real trigger until a future sprint (not named in this Sprint Book) wires one. Flagged here, not silently left for a technical-debt log entry to rediscover later.

## Potential Risks

- **Recycle-bin restore is not perfectly reliable across all Windows configurations** (`send2trash`'s own restore is OS-Explorer-mediated on some systems, not a clean programmatic API on every version) — `attempt_recovery()` must report `RECOVERY_FAILED` honestly when the underlying restore call itself fails or is unsupported, never claim `RECOVERED` optimistically.
- **Retrying a resource-gate-blocked action automatically** could, in a pathological case, retry into a system that is *still* under load, adding load itself at the worst possible time — bounded by `max_retry_attempts` (default `2`) and a fixed backoff, not unbounded; a future sprint may find even this modest default retry undesirable under real resource pressure, flagged as a Future Consideration for that possibility rather than solved defensively now.
- **Parameter redaction by keyword-matching key names** (`password`/`token`/`secret`/`credential`) is a simple heuristic, not a guarantee — a sensitive value stored under an unexpected key name would not be caught. Documented as a known limitation, matching this project's consistent honesty about heuristic-based safety measures elsewhere (`ShortTermMemory`'s salience triggers, `PersonaManager`'s trigger phrases).

## Acceptance Criteria

- Every `ActionRegistry.dispatch()` call — success, denial, or failure — produces exactly one persisted `ActionAuditRecord`.
- `parameters_summary` never contains a raw value stored under a redacted key name.
- `purge_older_than()` is called for real at `ActionAuditLog.start()`, verified by a test asserting the call happens, not just that the method exists.
- A file delete recorded via Sprint 4.3's recycle-bin routing is genuinely recoverable via `attempt_recovery()`.
- A non-reversible action type (e.g. `SYSTEM_COMMAND`) returns `NOT_REVERSIBLE` immediately, without attempting any recovery mechanism.
- A transient (timeout- or resource-gate-shaped) failure is retried up to `max_retry_attempts` before finally reporting `FAILED`; a non-transient failure (e.g. a path-scope `DENIED`) is never retried.

## Testing Checklist

- [ ] Unit: `record()` persists success/denial/failure results correctly, including via a real (temp-file) `SqliteClient`.
- [ ] Unit: redaction — a parameter keyed `password` never appears in the persisted `parameters_summary`.
- [ ] Unit: `query()` filters correctly by `action_type` and `since`.
- [ ] Unit: `purge_older_than()` deletes only records older than the given cutoff, and is called from `start()`.
- [ ] Unit: `attempt_recovery()` for a real recycle-bin-deleted file succeeds.
- [ ] Unit: `attempt_recovery()` for a `SYSTEM_COMMAND` record returns `NOT_REVERSIBLE` immediately.
- [ ] Unit: retry logic — a simulated transient failure is retried up to the configured bound, then reports `FAILED`; a simulated non-transient `DENIED` is never retried.

## Documentation Checklist

- [ ] `device_control/action_log.py` docstring: the redaction rule, the honest three-outcome recovery model, and the "no UI caller yet" gap, all stated explicitly.
- [ ] `docs/backlog/technical_debt.md` — cross-reference this sprint's resolution style against items 11/15 (a real precedent worth citing for those items' own eventual fix).
- [ ] `docs/STATUS.md` — Phase 4.1/4.2 rows note audit logging and recovery live.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

4.9 — Workflow Builder.

## Future Considerations

- A voice-triggered "undo that" / "what did you just do" command surface — the real functionality exists from this sprint onward, but wiring a live trigger is explicitly out of this Sprint Book's own scope, flagged above.
- A true periodic purge/review cadence (rather than once-at-startup) — explicitly deferred to Level 4 Part B's Scheduler, consistent with `backlog/technical_debt.md` items 11/15/17's own established resolution path.
