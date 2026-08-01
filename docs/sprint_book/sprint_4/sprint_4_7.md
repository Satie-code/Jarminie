# Sprint 4.7 — Permission & Confirmation System

## Sprint ID

4.7

## Sprint Name

Permission & Confirmation System

## Purpose

Replace Sprint 4.1's deliberately-thin, always-`ALLOW` `PermissionGate` stub with a real risk-classification and user-confirmation engine covering every Level 4 executor built so far (4.2–4.5), and formally populate `AuthorityEvaluator.approved_emergency_procedures` (3.11) as the "deliberate, reviewed act" `docs/sprint_book/INDEX.md`'s own Recommendations section named. This is Part 2's "Permission-sensitive operations always require user approval" and this task's own "Requesting user confirmation for sensitive actions... Enforcing permission and safety policies," made real.

## Engineering Rationale

Generalizes and **absorbs** `docs/sprint_book/INDEX.md`'s original `4.7 Large-Workflow Confirmation Gate` roadmap entry, rather than keeping it as a separate later sprint. That original entry scoped confirmation to workflows specifically ("if many actions are about to execute, request confirmation" — Part 2's own Workflow Engine section), but by the time this Sprint Book reached this point, four other executors (4.2–4.5) already exist with their own individual confirmation needs (closing an application, deleting a file, running a command) that have nothing to do with workflows at all. Building a workflow-only confirmation gate first, then a second, broader one later for individual actions, would mean solving the same "classify risk, ask the user, honor the answer" problem twice. This sprint solves it once, generally, and Sprint 4.10 (Workflow Executor) simply becomes one more caller of it — the same "solve it once at the right layer" reasoning Sprint 3.9 (Memory Retrieval Engine) used to justify composing across memory types instead of duplicating retrieval logic per type.

Deliberately built **after** Sprints 4.2–4.6, not first, even though "gate everything before it can act" sounds safer in the abstract — because a real risk classification needs real action types and real parameters to classify against. Sprint 4.1's stub existed specifically to unblock 4.2–4.6's own development without a chicken-and-egg dependency on a not-yet-designed policy engine; this sprint is where that debt is deliberately, visibly repaid — every one of Sprints 4.1–4.6's files states this explicitly in their own Integration Considerations, so this is not a silent retrofit.

## Objectives

- A real `RiskLevel` classification (per Sprint 4.1's own flagged Potential Risk, distinct from `PriorityLevel`) for every `ActionType`, config-driven and overridable.
- `PermissionGate.check()` (4.1) now genuinely varies its answer: `ALLOW` for low-risk actions, `REQUIRE_CONFIRMATION` for medium/high-risk actions, `DENY` for anything matching a configured hard denylist.
- A real `ConfirmationService` that can request and await user confirmation (voice or UI-surfaced — the actual surfacing mechanism is a UI-layer concern outside this sprint's own files, but the service's contract is defined here) before an `ActionRegistry.dispatch()` proceeds past `REQUIRE_CONFIRMATION`.
- `AuthorityEvaluator.approved_emergency_procedures` (3.11) populated with a real, reviewed, initial set — the first non-empty value that whitelist has ever had.
- `DeviceControlConfig.application_allowlist`/`approved_commands` (4.2, 4.5) become genuinely enforced policy, not just present-but-unenforced fields.

## Dependencies

4.1 (Action Engine Foundation), 4.2 (Application Manager), 4.3 (File & Folder Operations), 4.4 (Window Management), 4.5 (Command Execution Engine), 4.6 (System Monitoring, Action-Aware), 3.11 (Authority Evaluation & Engine Selection)

## Files to Create

- `security/policy_engine.py` — `RiskLevel` (enum), `RiskPolicy` (dataclass), `PermissionPolicyEngine`.
- `security/confirmation_service.py` — `ConfirmationRequest` (dataclass), `ConfirmationOutcome` (enum), `ConfirmationService` (Protocol), `VoiceConfirmationService` (concrete — asks via the active persona's own voice, reuses `Persona.compose_reply`-shaped output rather than a new speech path).
- `tests/unit/security/test_policy_engine.py`
- `tests/unit/security/test_confirmation_service.py`

## Files to Modify

- `security/permission_gate.py` — `PermissionGate.check()` now delegates risk classification to `PermissionPolicyEngine` and, for `REQUIRE_CONFIRMATION` outcomes, calls `ConfirmationService.request_confirmation()` synchronously before returning a final `PermissionDecision` (an `ALLOW` if the user confirms, `DENY` if they decline or the request times out — a confirmation timeout defaults to denial, Human First applied conservatively: silence is never treated as consent).
- `decision/authority.py` — `AuthorityEvaluator` constructed (in Sprint 4.11's `main.py` wiring, not this file itself) with a real, non-empty `approved_emergency_procedures` frozenset; this sprint's own change here is limited to the module docstring, updated to remove the now-outdated "zero procedures are approved anywhere in the codebase yet" language and point to this sprint as the resolution.
- `config/schema.py` — `DeviceControlConfig.application_allowlist`/`approved_commands` gain real validation (a non-empty list is checked for well-formed entries); new `SecurityConfig` dataclass: `risk_policies: dict[str, str]` (action_type name → `RiskLevel` name, overriding the built-in defaults), `confirmation_timeout_seconds: float = 20.0`, `hard_denylist: list[str]` (action_type names that are always `DENY`, never even offered for confirmation — empty by default, present for future use).
- `config/defaults.yaml` — matching `security:` section.

## Expected Classes

- `RiskLevel(Enum)` — `LOW`, `MEDIUM`, `HIGH`. Built-in defaults: `LAUNCH_APPLICATION`/`WINDOW_FOCUS`/`WINDOW_MOVE`/`WINDOW_RESIZE`/`WINDOW_MINIMIZE`/`FILE_CREATE`/`FOLDER_CREATE` → `LOW`; `CLOSE_APPLICATION`/`WINDOW_CLOSE`/`FILE_MOVE`/`FILE_COPY`/`FILE_RENAME` → `MEDIUM`; `FILE_DELETE`/`FOLDER_DELETE`/`SYSTEM_COMMAND`/`WORKFLOW_STEP` → `HIGH`.
- `RiskPolicy` (dataclass) — `action_type: ActionType`, `risk_level: RiskLevel`, `requires_confirmation: bool` (derived: `True` for `MEDIUM`/`HIGH`, `False` for `LOW`, but stored explicitly rather than recomputed everywhere, so a future config override could in principle decouple the two without a structural change).
- `PermissionPolicyEngine` — constructor DI: `(security_config: SecurityConfig)`. Builds its working `RiskPolicy` table from the built-in defaults above, overridden per-entry by `security_config.risk_policies`.
- `ConfirmationRequest` (dataclass) — `action_request: ActionRequest`, `risk_level: RiskLevel`, `prompt_text: str` (a human-readable description of exactly what will happen, built from `ActionRequest.parameters` — the Explainability Rule applied to a confirmation prompt, not just a decision trace).
- `ConfirmationOutcome(Enum)` — `CONFIRMED`, `DECLINED`, `TIMED_OUT`.
- `ConfirmationService` (Protocol) — `request_confirmation(request: ConfirmationRequest) -> ConfirmationOutcome`.
- `VoiceConfirmationService(ConfirmationService)` — constructor DI: `(session_manager: VoiceSessionManager, confirmation_timeout_seconds: float)`. Speaks `prompt_text` via the active session, listens for a yes/no-shaped reply within the timeout (reusing `VoiceSessionManager`'s existing utterance-capture machinery from Sprint 2.5, not a new audio path), degrades to `TIMED_OUT` on silence/no session.

## Expected Interfaces

- `ConfirmationService` (Protocol, above) — Sprint 4.10 (Workflow Executor) and any future UI-surfaced confirmation both depend on this interface, never on `VoiceConfirmationService` directly (Interface First Design).

## Expected Functions

- `PermissionPolicyEngine.classify(action_type: ActionType) -> RiskPolicy`
- `PermissionPolicyEngine.is_hard_denied(action_type: ActionType) -> bool`
- `PermissionGate.check(request: ActionRequest) -> PermissionDecision` (rewritten) — `is_hard_denied()` first (immediate `DENY`, no confirmation offered at all); then application/command allowlist checks for `LAUNCH_APPLICATION`/`SYSTEM_COMMAND` specifically (delegating to `ApplicationManager`'s config or `CommandExecutionEngine.is_approved()`, 4.5); then `classify()` — `LOW` risk returns `ALLOW` directly; `MEDIUM`/`HIGH` calls `confirmation_service.request_confirmation()` and maps `CONFIRMED → ALLOW`, `DECLINED`/`TIMED_OUT → DENY`.
- `VoiceConfirmationService.request_confirmation(request: ConfirmationRequest) -> ConfirmationOutcome`
- `VoiceConfirmationService._build_prompt_text(action_request: ActionRequest, risk_level: RiskLevel) -> str` — internal; e.g. `"This will permanently delete the file example.txt. Should I proceed?"` for a `HIGH`-risk `FILE_DELETE`.

## Data Flow

```
ActionRegistry.dispatch(request)
      ↓
PermissionGate.check(request)
      ↓
is_hard_denied(action_type)?  → yes → DENY  [stop]
      ↓ no
allowlist check (application_allowlist / approved_commands, for LAUNCH_APPLICATION / SYSTEM_COMMAND only)  → not listed → DENY  [stop]
      ↓ listed / not applicable
PermissionPolicyEngine.classify(action_type) → RiskPolicy(risk_level)
      ↓
LOW → ALLOW  [stop]
      ↓ MEDIUM / HIGH
ConfirmationService.request_confirmation(ConfirmationRequest(prompt_text=...))
      ↓
CONFIRMED → ALLOW      DECLINED / TIMED_OUT → DENY
      ↓
ActionResourceGate.check() (4.6)  →  executor.execute()
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `SecurityConfig`, `application_allowlist`/`approved_commands` real validation.
2. `security/policy_engine.py` — `RiskLevel`, `RiskPolicy`, `PermissionPolicyEngine`.
3. `security/confirmation_service.py` — `ConfirmationRequest`, `ConfirmationOutcome`, `ConfirmationService`, `VoiceConfirmationService`.
4. `security/permission_gate.py` — rewrite `check()` per Data Flow above; existing Sprint 4.1 tests updated (not silently broken — every prior always-`ALLOW` assertion is revisited against the new real classification, matching Sprint 4.1's own Acceptance Criteria promise that Sprint 4.7 "cannot ship without changing this default-allow behavior for at least one real risk case").
5. `decision/authority.py` docstring update; the real `approved_emergency_procedures` value itself is decided and reviewed as part of this sprint's own implementation (a real content decision, not a placeholder — see Architecture Notes), then passed to `AuthorityEvaluator`'s constructor by Sprint 4.11.
6. Unit tests across all new/modified files.

## Architecture Notes

`AuthorityEvaluator.approved_emergency_procedures` population is treated here as a genuine, narrow, reviewed policy decision, not a byproduct of shipping Device Control generally — per `INDEX.md`'s own Recommendation. This sprint's own implementation must propose a small, conservative initial set (e.g. a battery-critical-triggered safe-shutdown-prompt procedure, using capabilities Sprints 4.2–4.6 already built) and treat it the same way `VoiceConfig.jarvis_voice_id`/`minie_voice_id` (Sprint 2.4) were decided — a real content choice requiring explicit confirmation before shipping as a default, not an implementation detail to guess silently. Flag for discussion before this sprint's real implementation begins, per this Sprint Book's own template for such decisions.

`ConfirmationService` is defined as a Protocol specifically so `VoiceConfirmationService` is not the only possible implementation — a headless/CI test double, and a future UI-surfaced confirmation (a dialog, once Level 4 gets its own UI panel — not in this Sprint Book's scope), both depend on the same interface, matching `SpeechToText`'s own interface-first precedent (Sprint 2.3).

A confirmation timeout defaulting to `DENY` (never `ALLOW`) is a hard, non-configurable direction — `confirmation_timeout_seconds` controls *how long* to wait, never *what happens* on timeout. This mirrors `AuthorityEvaluator.evaluate()`'s own "fail safe-down, never safe-up" rule (3.13) applied to the confirmation flow specifically.

## Integration Considerations

- `PermissionGate`'s constructor grows a new required dependency (`PermissionPolicyEngine`, `ConfirmationService`) — Sprint 4.11's `main.py` wiring must construct and inject both; every executor sprint (4.2–4.6) already calls `ActionRegistry.dispatch()` exclusively through the registry, never `PermissionGate` directly, so this is a construction-site-only change, not a call-site change anywhere else.
- `VoiceConfirmationService` depends on `VoiceSessionManager` (Sprint 2.5) — the first Level 4 dependency on a Level 2 module. A confirmation request arriving while no voice session is active (e.g. a Workflow step triggered by a future Scheduler, Level 4 Part B, with no live conversation) has no session to speak/listen through; `request_confirmation()` degrades to `TIMED_OUT` immediately in that case (consistent with "timeout defaults to denial"), not a crash or an indefinite wait — this sprint's own Testing Checklist covers it explicitly.
- Sprint 4.10 (Workflow Executor) calls `ConfirmationService` directly for its own large-workflow-specific prompt wording (distinct from a single action's prompt), reusing the same interface and timeout-defaults-to-denial contract, not a second confirmation mechanism.

## Potential Risks

- **The built-in `RiskLevel` defaults are a reasoned but unavoidably subjective judgment call** (why is `WINDOW_CLOSE` `MEDIUM` and not `LOW`? — see Sprint 4.4's own note that it's the one genuinely destructive-shaped window operation) — config-overridable specifically because of this, same discipline as every other tuned-weight/threshold in this codebase (Dynamic Memory Formula weights, retrieval blend weights).
- **A no-active-session confirmation degrading to `TIMED_OUT`/`DENY`** means any Level 4 Part B automation triggered outside a live conversation (a future Scheduler-fired workflow) will always be denied under this sprint's own logic until a non-voice `ConfirmationService` implementation exists — an explicitly acknowledged limitation, not silently swept aside; Level 4 Part B's own future Sprint Book must address it, flagged here as a Future Consideration.
- **Populating `approved_emergency_procedures` for real is the single highest-consequence content decision in this entire Sprint Book** — a wrong or overly permissive entry could let a future Level 3-classified `CRITICAL_EMERGENCY` bypass confirmation entirely (3.11's own `EMERGENCY_ASSIST` path is deliberately confirmation-free, matching Part 2's real-emergency urgency). This sprint's own Architecture Notes above call for explicit review before shipping any non-empty value, precisely because of this risk.

## Acceptance Criteria

- `PermissionGate.check()` returns `ALLOW` for a `LOW`-risk action without ever calling `ConfirmationService`.
- `PermissionGate.check()` for a `MEDIUM`/`HIGH`-risk action calls `ConfirmationService.request_confirmation()`, and correctly maps `CONFIRMED → ALLOW`, `DECLINED → DENY`, `TIMED_OUT → DENY`.
- `application_allowlist`/`approved_commands` are now genuinely enforced: an unlisted application/command is denied even at `LOW`/`MEDIUM` risk classification, before confirmation is even offered.
- `hard_denylist` entries are denied unconditionally, with no confirmation prompt offered.
- `AuthorityEvaluator.approved_emergency_procedures` is populated with a real, reviewed, non-empty value (or explicitly, documentedly, deliberately left empty pending further review — either outcome is acceptable, but silence/omission is not).
- `VoiceConfirmationService` degrades to `TIMED_OUT` (never hangs, never crashes) when no voice session is active.

## Testing Checklist

- [ ] Unit: `PermissionPolicyEngine.classify()` matches the documented built-in `RiskLevel` table for every `ActionType`.
- [ ] Unit: config override of a built-in risk level takes effect.
- [ ] Unit: `PermissionGate.check()` LOW-risk path never calls `ConfirmationService` (spy-verified).
- [ ] Unit: `PermissionGate.check()` MEDIUM/HIGH-risk path calls `ConfirmationService` and correctly maps all three outcomes.
- [ ] Unit: application/command allowlist enforcement (listed passes to risk classification; unlisted denies immediately).
- [ ] Unit: `hard_denylist` entries denied unconditionally, no confirmation offered.
- [ ] Unit: `VoiceConfirmationService` with no active session degrades to `TIMED_OUT`.
- [ ] Unit: `VoiceConfirmationService` correctly interprets an affirmative/negative spoken reply within the timeout (using a fake `VoiceSessionManager`, matching the project's established fakes-at-the-hardware-boundary discipline).
- [ ] Regression: every Sprint 4.1–4.6 test that exercised `PermissionGate`'s old always-`ALLOW` stub is revisited and still passes under the new real classification.

## Documentation Checklist

- [ ] `security/policy_engine.py`/`security/confirmation_service.py`/`security/permission_gate.py` docstrings: the full decision flow (Data Flow above), stated explicitly.
- [ ] `decision/authority.py` docstring updated to remove the now-outdated "zero procedures approved" language.
- [ ] `docs/backlog/technical_debt.md` — cross-reference update on any item this sprint touches (e.g. the 3.11 whitelist note).
- [ ] `docs/STATUS.md` — Phase 4.1/4.2 rows note real permission enforcement is live.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

High — the highest-stakes sprint in Level 4 Part A: it changes the actual behavior (not just the mechanism) of every previously-built executor, and includes the project's first genuinely consequential emergency-procedure content decision.

## Estimated Development Time

2–2.5 days.

## Risks

See Potential Risks above.

## Next Sprint

4.8 — Action Logging & Recovery.

## Future Considerations

- A non-voice (UI dialog, push notification) `ConfirmationService` implementation, needed once Level 4 Part B introduces automation that can trigger outside a live voice session — explicitly named as an open gap above, not solved in this sprint.
- Per-action-instance risk override (e.g. a `FILE_DELETE` inside a user's own scratch/temp folder classified lower risk than one inside Documents) — a real refinement, deliberately deferred: this sprint's classification is by `ActionType` alone, not by parameters, keeping the policy engine's first version simple and auditable.

## Sprint Completion Report (2026-07-20)

Implemented largely as specified — the highest-stakes, highest-ambiguity sprint in Level 4 Part A so far, matching its own "High" complexity estimate. Two genuine stop-and-ask gates were hit and resolved with the user's explicit input *before* any code was written, per this sprint's own Architecture Notes and the project's standing "ask, don't assume" rule — both are detailed below rather than only summarized. Delivered `security/policy_engine.py` (`RiskLevel`, `RiskPolicy`, `PermissionPolicyEngine`), `security/confirmation_service.py` (`ConfirmationRequest`, `ConfirmationOutcome`, `ConfirmationService`, `VoiceConfirmationService`, `build_prompt_text()`), a full rewrite of `security/permission_gate.py`'s `check()`, `SecurityConfig` in `config/schema.py`/`config/defaults.yaml`, a docstring-only update to `decision/authority.py`, and one small additive method on `voice/session_manager.py` (`capture_and_transcribe_reply()`). 60 new/rewritten tests across `tests/unit/security/` (`test_policy_engine.py` 28, `test_confirmation_service.py` 15, `test_permission_gate.py` fully rewritten to 18 — the old always-ALLOW-era suite is gone, per this sprint's own explicit Testing Checklist item). 802/802 full-suite tests passing, `ruff check .` clean.

**Gate 1 — `approved_emergency_procedures`, resolved before any implementation.** This sprint's own Architecture Notes call populating this whitelist "the single highest-consequence content decision in this entire Sprint Book" and explicitly instruct flagging it for discussion first. Before proposing anything, investigated `decision/authority.py` directly rather than guessing: confirmed `_determine_engine()` always returns `CONVERSATIONAL_RESPONSE`/`INFORM_ONLY` regardless of `authority_level` — meaning nothing in the codebase currently converts an `EMERGENCY_ASSIST` grant into any real automated action — and that no `ActionType` exists for anything resembling a real emergency-response procedure (the spec's own suggested example, "a battery-critical-triggered safe-shutdown-prompt procedure," has no executor behind it either). Presented this finding to the user with two real options (leave empty and documented, vs. approve a small initial set anyway despite it having no real teeth yet); the user chose to leave it empty. `decision/authority.py`'s docstring now records this explicitly as reviewed-and-deferred, not an oversight, cross-referencing this report. `backlog/technical_debt.md` item 22 logs the same decision for `approved_commands`/`application_allowlist` jointly, since both remain empty/unrestricted by the same underlying reasoning (an empty allowlist is exactly as inert as an empty procedure whitelist).

**Gate 2 — `VoiceConfirmationService`'s reply-listening mechanism, resolved before writing that class.** The spec asks `VoiceConfirmationService` to reuse `VoiceSessionManager`'s existing utterance-capture machinery, "not a new audio path." Checked `voice/session_manager.py` directly: the real capture-and-transcribe logic (`_capture_one_utterance()` + STT) was private, driven entirely by the session's own autonomous background loop, with no public synchronous "capture and transcribe one reply right now" entry point — and `voice/session_manager.py` isn't in this sprint's own Files to Modify. Every alternative considered either recreated a second, concurrent mic-reading path (risking the exact class of frame-stealing bug Sprint 2.12's own wake-word/session fix already resolved once — see `backlog/technical_debt.md` item 10) or required touching files even further out of scope (`voice/pipeline.py`). Presented to the user as an explicit choice (add one small public method to `VoiceSessionManager` vs. ship `VoiceConfirmationService` with real listening deliberately deferred); the user approved adding the method. Delivered as `VoiceSessionManager.capture_and_transcribe_reply(timeout_seconds) -> str | None`: a new `_awaiting_external_reply` flag lets `_on_utterance_ready()` route the *next* captured utterance to a waiting caller (via a new `threading.Event`) instead of the normal `on_turn_complete` callback, without ever running a second mic reader. `end_session()` also now sets that same event, so a caller waiting inside `capture_and_transcribe_reply()` is woken immediately if the session ends mid-wait, rather than only discovering it once its own timeout separately expires. Purely additive — every existing `VoiceSessionManager` caller and all 12 of `tests/unit/voice/test_session_manager.py`'s existing tests pass completely unmodified. Logged as `backlog/technical_debt.md` item 23 (a Level 2 file touched by a Level 4 sprint, deliberately, not accidentally).

**A real circular import, found and fixed the same way as Sprint 4.6's own precedent.** `device_control/action_engine.py` imports `security/permission_gate.py` (unchanged since Sprint 4.1) at module level; `permission_gate.py` now imports `security/confirmation_service.py`, which imports `security/policy_engine.py` — and `policy_engine.py`'s first draft imported `ActionType` from `action_engine.py` at module level to build its `_DEFAULT_RISK_LEVELS` table, completing a four-file cycle. Resolved more thoroughly than a simple deferred import this time: `policy_engine.py` never imports `ActionType` at real runtime at all (`TYPE_CHECKING`-only, for annotations) — `_DEFAULT_RISK_LEVELS` is keyed by plain `ActionType.value` strings instead of the enum itself, and `classify()`/`is_hard_denied()` read `action_type.value` (duck typing) rather than using the enum as a dict key. This has a genuine secondary benefit beyond breaking the cycle: `classify()` now computes its answer on demand instead of pre-building a table at construction time, which meant it could gain a safe `MEDIUM` fallback for a hypothetical future `ActionType` this table doesn't yet know about, rather than raising `KeyError` — a strictly more robust design, not just a workaround.

**`PermissionGate`'s allowlist matching deliberately duplicates a few lines of `CommandExecutionEngine.is_approved()`'s own basename-comparison logic** rather than importing and calling it — `security/` must never import `device_control/` at runtime (Sprint 4.1's own established dependency direction: `device_control` depends on `security`, never the reverse), so calling into a live `CommandExecutionEngine`/`ApplicationManager` instance from `permission_gate.py` was never an option. This is intentional defense-in-depth with `CommandExecutionEngine`'s own independent `is_approved()` check at actual execution time, not redundant dead code — each layer defends itself without trusting an upstream layer already did, matching `FileOperationsManager`'s own path-scope-check precedent.

**`ConfirmationRequest.prompt_text` construction, resolved without needing to ask.** The spec lists `VoiceConfirmationService._build_prompt_text()` as that class's own internal method, but `ConfirmationRequest` (built by `PermissionGate`, before any `ConfirmationService` implementation ever sees it) already carries a `prompt_text: str` field. Resolved by making `build_prompt_text()` a shared, public module-level function in `confirmation_service.py` — `PermissionGate` calls it to populate `ConfirmationRequest.prompt_text` (so even a future non-voice implementation gets a sensible description for free), and `VoiceConfirmationService._build_prompt_text()` (kept as an instance method, matching the spec's own naming) simply calls the same shared function for what it actually speaks. One implementation, not two independently-maintained copies of the same describe-this-action logic.

**`_interpret_reply()`'s word-set matching (not raw substring containment)** was a deliberate choice, not an oversight: a naive `"no" in text.lower()` check would false-positive on any reply containing "know" (e.g. "you know, let's do it"). Word-tokenized set intersection avoids this; an unrecognized reply defaults to `DECLINED`, matching this sprint's own "fail safe-down" confirmation-timeout discipline rather than risking a false `CONFIRMED`.

Not yet wired into `main.py`/`ActionRegistry`/`CoreManager` — per this sprint's own Integration Considerations, `PermissionGate`'s constructor growing new required dependencies is a construction-site-only change, and that construction site is Sprint 4.11's. **Sprint 4.8 (Action Logging & Recovery) is next.**
