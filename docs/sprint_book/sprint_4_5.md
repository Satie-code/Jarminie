# Sprint 4.5 — Command Execution Engine

## Sprint ID

4.5

## Sprint Name

Command Execution Engine

## Purpose

Implement the fourth `ActionExecutor` (Sprint 4.1): controlled execution of approved system commands — this task's own Level 4 Goal line, "Executing approved system commands," taken as this sprint's literal scope.

## Engineering Rationale

This sprint has **no direct predecessor** in `docs/sprint_book/INDEX.md`'s original roadmap-granularity Level 4 plan — that plan's `4.1 Application Control`/`4.4 System Monitoring` entries cover launching applications and read-only resource sampling, but neither covers arbitrary(-within-policy) shell/subprocess command execution with captured output, which this task's Level 4 Goal names as its own explicit capability. This is a genuine, real gap between the previously-approved roadmap and this task's own instructions, resolved by adding a dedicated sprint rather than silently folding command execution into `ApplicationManager` (which would violate Single Responsibility — "launch a tracked GUI application" and "run a command and capture its output/exit code" are different enough operations, with different risk shapes, to deserve separate executors, the same reasoning that already separates `ApplicationManager` from `FileOperationsManager`).

This is, by a clear margin, the **highest-risk executor in Level 4 Part A** — an arbitrary shell command is a strictly more powerful (and more dangerous) primitive than any single file operation or window operation, since a command can *itself* perform file operations, launch processes, or worse, entirely outside this Sprint Book's other executors' own safeguards. Accordingly, this sprint ships with a **default-deny command allowlist**, not a blocklist — the same structural pattern `AuthorityEvaluator.approved_emergency_procedures` (3.11) already established for emergency procedures, applied here to shell commands. An empty allowlist (this sprint's own shipped default) means this executor can construct and validate a request but never actually run a real command until the allowlist is deliberately populated — mirroring 3.11's own "structurally unreachable... by design, not an oversight" language exactly.

## Objectives

- `CommandExecutionEngine` (`ActionExecutor`): run a system command as a subprocess, with a bounded timeout, captured stdout/stderr/exit code.
- A default-deny allowlist: only commands whose executable name (not full arbitrary command line) appears in `DeviceControlConfig.approved_commands` may run at all.
- No shell string interpolation — commands run via `subprocess.run(args_list, shell=False, ...)` exclusively, closing the standard shell-injection vector by construction, not by sanitization.

## Dependencies

4.1 (Action Engine Foundation)

## Files to Create

- `device_control/command_executor.py` — `CommandExecutionEngine`, `CommandResult` (dataclass).
- `tests/unit/device_control/test_command_executor.py`

## Files to Modify

- `config/schema.py` — `DeviceControlConfig` gains `approved_commands: list[str]` (default: empty list — structurally unreachable until deliberately populated, same discipline as `AuthorityEvaluator`) and `command_timeout_seconds: float = 30.0`.
- `config/defaults.yaml` — matching fields (empty `approved_commands` list, present and documented, not omitted).

## Expected Classes

- `CommandResult` (dataclass) — `command: list[str]`, `exit_code: int | None` (`None` on timeout — the process never reached a real exit code), `stdout: str`, `stderr: str`, `timed_out: bool`, `duration_seconds: float`.
- `CommandExecutionEngine(ActionExecutor)` — constructor DI: `(device_control_config: DeviceControlConfig)`. Handles `SYSTEM_COMMAND`.

## Expected Interfaces

None new — implements `ActionExecutor` (4.1).

## Expected Functions

- `CommandExecutionEngine.can_handle(action_type: ActionType) -> bool`
- `CommandExecutionEngine.execute(request: ActionRequest) -> ActionResult` — extracts `parameters["command"]: list[str]` (never a raw shell string — a caller must already have split the command into an argv-shaped list, pushing shell-syntax handling out of this trust boundary entirely); validates `command[0]` (the executable name, basename-only, case-insensitive) against `approved_commands`; on a non-match, returns `ActionStatus.DENIED` immediately, subprocess never spawned; on a match, runs via `_run_subprocess()`.
- `CommandExecutionEngine._run_subprocess(command: list[str]) -> CommandResult` — internal; `subprocess.run(command, shell=False, capture_output=True, timeout=command_timeout_seconds, text=True)`; catches `subprocess.TimeoutExpired` and returns a `CommandResult` with `timed_out=True`, `exit_code=None`; catches `OSError`/`FileNotFoundError` (executable not actually present despite passing the allowlist check) and returns `ActionStatus.FAILED` at the `execute()` level, not a raised exception.
- `CommandExecutionEngine.is_approved(executable_name: str) -> bool` — public, so Sprint 4.7's Permission & Confirmation System can pre-check approval status without triggering an actual run (useful for a confirmation prompt that wants to say "this command is not on the approved list" before even asking the user to confirm).

## Data Flow

```
ActionRequest(action_type=SYSTEM_COMMAND, parameters={"command": ["ping", "-n", "1", "localhost"]})
      ↓
PermissionGate.check() → ALLOW (Sprint 4.1 default; Sprint 4.7 makes this real)
      ↓
CommandExecutionEngine.execute()
      ↓
is_approved(command[0])  →  False → ActionResult(DENIED)  [stop, subprocess never spawned]
      ↓ (approved)
subprocess.run(command, shell=False, timeout=..., capture_output=True)
      ↓
CommandResult(exit_code, stdout, stderr, timed_out, duration_seconds)
      ↓
ActionResult(status=SUCCEEDED/FAILED, output=CommandResult)
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `approved_commands` (empty default), `command_timeout_seconds`.
2. `device_control/command_executor.py` — `CommandResult`, `CommandExecutionEngine`.
3. Unit tests: approved-command success, denied-command rejection (subprocess never spawned — verify via a spy, not just the returned status), timeout handling, nonexistent-executable handling, and — critically — a shell-injection-shaped input (e.g. `["echo", "hello; rm -rf /"]` as a single literal argv element) proving it is passed as one literal argument, never shell-interpreted.

## Architecture Notes

The **default-deny allowlist checked against `command[0]` alone, not the full command line**, is a deliberate scope boundary: this sprint approves *which executables* may run, not *which arguments* are safe for an approved executable — argument-level policy (e.g. "`git` is approved, but not `git push --force`") is explicitly out of this sprint's scope and, if ever needed, belongs to Sprint 4.7's richer risk-classification policy, not a speculative addition here.

`shell=False` is a hard invariant, not a configuration option — there is no config field to enable shell interpolation, because doing so would reopen the exact injection vector `command[0]` allowlisting and argv-list-only input are both designed to close. This is the one place in Level 4 Part A where a capability is withheld structurally (no override exists at all), matching Part 2's own "Emergency actions never include... those always require approval" absolute-boundary language, applied here to shell interpolation instead of a specific action category.

## Integration Considerations

- Registered with `ActionRegistry` by Sprint 4.11.
- Sprint 4.6 (System Monitoring, Action-Aware)'s resource-pressure gate applies to command execution — a long-running or resource-heavy command is exactly the shape of automation the Resource Protection Rule exists to bound; wired in Sprint 4.6, not this sprint.
- Sprint 4.7 owns the actual *populating* of `approved_commands` as a deliberate, reviewed act (mirroring `AuthorityEvaluator.approved_emergency_procedures`'s own treatment) — this sprint ships the mechanism with an intentionally empty, non-functional-by-default list.
- Sprint 4.8 (Action Logging & Recovery) logs every `CommandResult` in full (including `stdout`/`stderr`) for audit — subject to `docs/CODING_STANDARDS.md`'s "never log conversation content, credentials, or other personal data" rule, which becomes directly relevant here for the first time in Level 4: a command's captured output could easily contain sensitive data, so Sprint 4.8's logging must account for this explicitly, not by default assume command output is safe to log verbatim.

## Potential Risks

- **An empty `approved_commands` list makes this executor fully inert until deliberately configured** — an accepted, deliberate trade-off (same as 3.11's empty emergency-procedure whitelist), not an oversight; this sprint's own Acceptance Criteria include a test proving the default ships empty, so a future change to that default is a visible, reviewable diff, not a silent drift.
- **`command_timeout_seconds` as a single global value** may be wrong for some legitimately long-running approved commands and too generous for others — config-driven per this sprint, but not yet per-command; flagged as a Future Consideration rather than over-built now (no real approved command exists yet to calibrate against).
- **Capturing full `stdout`/`stderr` risks logging sensitive data** if a future approved command happens to echo secrets — this sprint's own `CommandResult` captures it in full (needed for the caller/workflow to actually use the output), but Sprint 4.8's logging layer, not this sprint, is where a redaction/truncation policy must be decided before anything is persisted to disk.

## Acceptance Criteria

- A command whose executable is in `approved_commands` runs and returns accurate `stdout`/`stderr`/`exit_code`.
- A command whose executable is NOT in `approved_commands` is denied before any subprocess is spawned — provably, via a spy on the subprocess call.
- The shipped default `approved_commands` is empty — this executor is non-functional until deliberately configured, verified by a test.
- A command that exceeds `command_timeout_seconds` is terminated and reported with `timed_out=True`, `exit_code=None`, never hangs the calling thread indefinitely.
- No code path in this module ever calls `subprocess.run(..., shell=True)` or otherwise interpolates a raw string into a shell — verified by a test asserting `shell=False` is always passed, and by a literal-argument injection-shaped test case.

## Testing Checklist

- [ ] Unit: approved command executes and returns correct `CommandResult`.
- [ ] Unit: unapproved command is denied, subprocess never spawned (spy-verified).
- [ ] Unit: default `approved_commands` ships empty.
- [ ] Unit: timeout handling — a command exceeding `command_timeout_seconds` returns `timed_out=True`.
- [ ] Unit: nonexistent executable (passes allowlist check by name but doesn't actually exist on `PATH`) degrades to `FAILED`, not an unhandled exception.
- [ ] Unit: shell-injection-shaped argv element (e.g. a string containing `;`/`&&`/`|`) is passed through as one literal argument, never shell-interpreted — verified against a real subprocess, not mocked, for at least one case.
- [ ] Unit: `is_approved()` public lookup matches `execute()`'s own internal check exactly (no drift between the two).

## Documentation Checklist

- [ ] `device_control/command_executor.py` docstring: the default-deny allowlist model, the `shell=False`/argv-list-only hard invariant, and the "captured output may contain sensitive data" logging caveat for Sprint 4.8 — all stated explicitly.
- [ ] `docs/backlog/technical_debt.md` — note (informational, not debt) that `approved_commands` ships empty by design, cross-referencing Sprint 4.7 as the resolution, same treatment as 3.11's whitelist got at the time.
- [ ] `docs/STATUS.md` — Phase 4.1 row notes Command Execution Engine complete (mechanism only; policy population is Sprint 4.7's).

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium — the mechanism itself is simple; the security-boundary verification (injection resistance, allowlist correctness) is what makes this sprint deserve care.

## Estimated Development Time

1.5–2 days.

## Risks

See Potential Risks above.

## Next Sprint

4.6 — System Monitoring & Resource Protection (Action-Aware).

## Future Considerations

- Argument-level policy (approved executable + approved argument patterns) if a real need for finer-grained command approval emerges — deliberately out of this sprint's scope, noted above.
- Streaming output (for a long-running approved command a caller wants to observe incrementally) rather than this sprint's own capture-then-return model — no real approved command exists yet to justify the added complexity; not built speculatively.

## Sprint Completion Report (2026-07-20)

Implemented as specified, authorized directly ("proceed to sprint 4.5") — same no-separate-Pass-1 pattern as 4.2-4.4 since this sprint's spec was already complete. Delivered `device_control/command_executor.py` (`CommandResult`, `CommandExecutionEngine`), `tests/unit/device_control/test_command_executor.py` (14 tests), `DeviceControlConfig.approved_commands` (default empty list, validated no empty-string entries) and `command_timeout_seconds` (default 30.0, validated `> 0`). 729/729 full-suite tests passing (one pre-existing, timing-sensitive `test_full_level3_acceptance_scripted_conversation` flake under full-suite system load — confirmed passing standalone immediately after, same known flake class already documented for the Level 2 acceptance test; unrelated to this sprint, which touches no voice/decision code), `ruff check .` clean.

No spec gaps or design ambiguities this time — unlike 4.2/4.3/4.4, this sprint's `ActionType.SYSTEM_COMMAND`, `CommandResult`, and `CommandExecutionEngine` shapes were all fully and unambiguously specified, so implementation followed the spec directly with no deviation to record.

**Verified for real, not just via fakes**: every test runs a real `subprocess.run()` against a real `sys.executable` child process (matching `ApplicationManager`'s own "genuinely harmless, universally present" testing precedent) — including the sprint's own explicitly-required real-subprocess injection test (`["echo", "hello; rm -rf /"]`-shaped input passed as one literal argv element to a real process, whose own output proves it was never shell-interpreted) and a real timeout (a real child process outliving `command_timeout_seconds`, really killed by `subprocess.run`'s own timeout handling, not simulated). Only the "subprocess never spawned when denied" and "`shell=False` is always passed" tests mock `subprocess.run` directly, since those are assertions about a call that must *not* happen (or must happen with an exact keyword argument), which a real run can't itself prove.

`approved_commands` ships empty exactly as specified — logged as an informational (not defect) entry in `backlog/technical_debt.md` item 20, cross-referencing Sprint 4.7 as the sprint that actually populates it, matching this sprint's own Documentation Checklist and the precedent `AuthorityEvaluator.approved_emergency_procedures` (Sprint 3.11) already set.

Not yet wired into `main.py`/`ActionRegistry` — per this sprint's own Integration Considerations, that's Sprint 4.11's job; the resource-pressure gate over command execution is Sprint 4.6's. **Sprint 4.6 (System Monitoring & Resource Protection, Action-Aware) is next.**
