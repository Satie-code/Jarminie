# Sprint 4.3 — File & Folder Operations

## Sprint ID

4.3

## Sprint Name

File & Folder Operations

## Purpose

Implement the second `ActionExecutor` (Sprint 4.1): open, create, move, copy, rename, and delete files and folders, with real safeguards — this is the Level 4 Goal's own explicit line, "with appropriate safeguards," taken literally.

## Engineering Rationale

Corresponds unchanged to `docs/sprint_book/INDEX.md`'s original `4.2 File & Folder Operations` roadmap entry — same name, same scope, no deviation.

This is the first Level 4 executor with a genuinely destructive, hard-to-reverse failure mode (data loss), so it earns more scaffolding than Sprint 4.2's `ApplicationManager`: a path-scoping boundary (never operate outside a configured set of allowed roots) and a recycle-bin-based delete (never a permanent OS-level delete) are both built into this sprint's own scope, not deferred to Sprint 4.7 — Part 2's own words are unambiguous ("Permission-sensitive operations always require user approval") but recoverability is a property of *how the operation itself is implemented*, not something a downstream permission check can retrofit after the fact. A `PermissionGate` denial prevents an operation from *starting*; it cannot make an already-executed permanent delete recoverable. This sprint's own job is to make sure a delete is never permanent in the first place, independent of whatever Sprint 4.7 later decides about who's allowed to trigger one.

## Objectives

- `FileOperationsManager` (`ActionExecutor`): create, move, copy, rename, delete for both files and folders.
- Path-scoping: every operation validates its target path(s) against a configured set of allowed root directories before touching anything.
- Delete is recycle-bin-based (recoverable), never `os.remove`/`shutil.rmtree` directly.
- Every operation reports enough detail in its `ActionResult` for Sprint 4.8 (Action Logging & Recovery) to reconstruct exactly what happened.

## Dependencies

4.1 (Action Engine Foundation)

## Files to Create

- `device_control/file_operations.py` — `FileOperationsManager`, `PathScopeError` (exception, raised internally and always caught at `execute()`'s own boundary — never propagates past this module).
- `tests/unit/device_control/test_file_operations.py`

## Files to Modify

- `config/schema.py` — `DeviceControlConfig` gains `allowed_file_roots: list[str]` (default: the user's own Documents/Desktop-equivalent paths — a real default is chosen during implementation, not left empty, since an empty allowlist would make this executor permanently non-functional) and `use_recycle_bin_for_delete: bool = True` (present as a config field for transparency; **not** intended to ever be set `False` in a shipped config — see Potential Risks).
- `config/defaults.yaml` — matching fields.
- `requirements.txt` — add `Send2Trash` (the standard, small, cross-platform-but-Windows-capable library for recycle-bin-based deletion; a genuine new dependency this sprint needs and Part 3's stack list doesn't separately name — flagged in `docs/backlog/technical_debt.md`, same treatment as the `coqui-tts` package-naming correction, item 3).

## Expected Classes

- `FileOperationsManager(ActionExecutor)` — constructor DI: `(device_control_config: DeviceControlConfig)`. Handles `FILE_CREATE`, `FILE_MOVE`, `FILE_COPY`, `FILE_RENAME`, `FILE_DELETE`, `FOLDER_CREATE`, `FOLDER_DELETE`.
- `PathScopeError(Exception)` — raised by the internal path-validation helper when a target path resolves outside every configured allowed root.

## Expected Interfaces

None new — implements `ActionExecutor` (4.1).

## Expected Functions

- `FileOperationsManager.can_handle(action_type: ActionType) -> bool`
- `FileOperationsManager.execute(request: ActionRequest) -> ActionResult` — validates every path parameter via `_validate_path_scope()` first; on `PathScopeError`, returns `ActionStatus.DENIED` with a clear message, executor logic never runs. Catches `OSError` around the actual filesystem call and returns `FAILED`, never raises.
- `FileOperationsManager._validate_path_scope(path: str) -> Path` — internal; resolves the path (`Path.resolve()`, following symlinks — a deliberate anti-bypass measure, since an unresolved relative/symlinked path could otherwise escape the allowed roots) and checks it is a descendant of at least one `allowed_file_roots` entry; raises `PathScopeError` otherwise.
- `FileOperationsManager.delete(path: str) -> bool` — internal; routes through `send2trash.send2trash()`, never `os.remove`/`shutil.rmtree`, when `use_recycle_bin_for_delete` is `True` (the only value this sprint's own default ships).

## Data Flow

```
ActionRequest(action_type=FILE_DELETE, parameters={"path": ...})
      ↓
PermissionGate.check() → ALLOW (Sprint 4.1 default; Sprint 4.7 makes this real)
      ↓
FileOperationsManager.execute()
      ↓
_validate_path_scope(path)  →  PathScopeError → ActionResult(DENIED)  [stop]
      ↓ (in scope)
send2trash.send2trash(path)  /  shutil.move/copy  /  Path.mkdir  /  Path.rename
      ↓
ActionResult(status=SUCCEEDED/FAILED, output={"path": ..., "operation": ...})
```

## Implementation Tasks

1. `config/schema.py`/`config/defaults.yaml` — `allowed_file_roots`, `use_recycle_bin_for_delete`.
2. `requirements.txt`/venv — `Send2Trash`; `docs/backlog/technical_debt.md` entry.
3. `device_control/file_operations.py` — `PathScopeError`, `FileOperationsManager` and every operation.
4. Unit tests, all against a `tmp_path`-scoped `allowed_file_roots` (never the real filesystem outside a test's own temp directory — a hard testing-discipline requirement for this sprint specifically, given the destructive potential).

## Architecture Notes

Path-scope validation happens **once**, in `execute()`, before any operation-specific branch — not duplicated per-operation — so a future sixth file operation cannot be added by a future sprint without inheriting the scoping check for free (Single Responsibility / DRY, matching `docs/CODING_STANDARDS.md`'s "avoid duplicated logic").

`FileOperationsManager` never operates on a path outside `allowed_file_roots`, full stop — there is no "admin override" parameter on `execute()` itself. If a genuine need for an out-of-scope operation ever arises, the correct fix is adding to `allowed_file_roots` via configuration (an explicit, reviewed, User-Override-Rule-shaped act), never a runtime bypass flag on the executor.

## Integration Considerations

- Registered with `ActionRegistry` by Sprint 4.11, same as `ApplicationManager`.
- Sprint 4.7's risk classification treats every `FILE_DELETE`/`FOLDER_DELETE` request as at least "needs confirmation" by default — this sprint's own `PermissionGate` interaction is still the Sprint 4.1 always-`ALLOW` stub, so Sprint 4.7 is where that classification actually takes effect.
- Sprint 4.8 (Action Logging & Recovery)'s "reversible where practical" acceptance criterion is satisfied for delete by this sprint's own recycle-bin routing — Sprint 4.8 records the audit entry and exposes a `restore` pointer, it does not implement the recoverability mechanism itself.

## Potential Risks

- **`use_recycle_bin_for_delete: bool` existing as a config field at all is itself a minor risk** — a misconfigured `False` would silently remove the one guaranteed-recoverable delete path this sprint provides. Mitigated by `AppConfig.validate()` (extended this sprint) logging a `WARNING` (not blocking startup — Human First Rule: an explicit user configuration choice is still honored) whenever it is `False`, and by this file's own Documentation Checklist making the risk explicit rather than silent.
- **Symlink/junction-based scope bypass on Windows** (NTFS symbolic links, junctions) is a real, non-hypothetical attack/bug surface for any path-scoping check — `Path.resolve()` is the standard mitigation and is used here, but must be verified against a real Windows symlink/junction during this sprint's own testing, not assumed correct from documentation alone.
- **Recycle-bin behavior for a network/removable drive path** can differ from a local NTFS drive (some drives have no recycle bin at all) — `send2trash` raises in that case, which this sprint's `execute()` catches and reports as `FAILED` rather than silently falling back to a permanent delete (a fallback to permanent delete would be a much worse failure mode than simply failing the operation).

## Acceptance Criteria

- Create/move/copy/rename/delete for both files and folders all succeed within `allowed_file_roots`.
- Every operation on a path outside `allowed_file_roots` (including via `../` traversal and a real symlink/junction escape attempt) is denied before any filesystem call happens.
- Delete never calls `os.remove`/`shutil.rmtree` — verified by a test asserting the deleted item is recoverable from the recycle bin (or, at minimum, that `send2trash` was the code path taken, not a direct OS delete call).
- A failed operation (permission error, disk full, path already exists where a create was requested) degrades to `ActionStatus.FAILED` with a clear `error_message`, never raises past `execute()`.
- Matches Part 4 Phase 4.1's "Safe desktop control. Permissions respected."

## Testing Checklist

- [ ] Unit: create/move/copy/rename/delete for files, all within a `tmp_path`-scoped allowed root.
- [ ] Unit: same six operations for folders.
- [ ] Unit: path-scope denial for an out-of-root absolute path.
- [ ] Unit: path-scope denial for a `../` traversal attempt.
- [ ] Unit: path-scope denial for a real symlink/junction pointing outside the allowed root (Windows-specific; skip with a clear reason on platforms where the test harness cannot create one).
- [ ] Unit: delete routes through `send2trash`, not a direct OS delete (mock/spy on the call, or verify recoverability directly).
- [ ] Unit: operation on a nonexistent source path degrades to `FAILED`.

## Documentation Checklist

- [ ] `device_control/file_operations.py` docstring: the path-scoping and recycle-bin-delete guarantees, stated as hard invariants, not just implementation notes.
- [ ] `docs/backlog/technical_debt.md` — `Send2Trash` dependency addition.
- [ ] `docs/STATUS.md` — Phase 4.1 row notes File & Folder Operations complete.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../CODING_STANDARDS.md).

## Estimated Complexity

Medium.

## Estimated Development Time

1.5–2 days (the path-scoping/symlink-safety verification is the slow part, not the CRUD operations themselves).

## Risks

See Potential Risks above.

## Next Sprint

4.4 — Window Management.

## Future Considerations

- A user-facing "empty the JARMINEI recycle bin" or "permanently delete after N days" retention policy — genuinely useful but not part of this sprint's own scope (Part 2 names no such retention rule); would be a Sprint 4.8 (Action Logging & Recovery) or later extension, not built speculatively now.
- Bulk/glob-pattern operations (e.g. "move all `.tmp` files") — a real future need for Workflow steps (4.9/4.10), deliberately deferred: this sprint's `execute()` takes exactly one path per request, keeping the safety/audit story simple; a bulk variant would need its own explicit confirmation-count reasoning (Part 2's "if many actions are about to execute, request confirmation").

---

## Sprint Completion Report (2026-07-20)

### Summary

Implemented `device_control/file_operations.py` (`FileOperationsManager`, `PathScopeError`) — Level 4's second real `ActionExecutor` — plus `allowed_file_roots`/`use_recycle_bin_for_delete` on `DeviceControlConfig` and a real `Send2Trash` install. 118/118 targeted tests passing; 695/695 full-suite, `ruff check .` clean.

### Files Created

- `device_control/file_operations.py` — `PathScopeError`, `_OperationOutcome` (internal dataclass), `FileOperationsManager`.
- `tests/unit/device_control/test_file_operations.py` — 26 tests.

### Files Modified

- `config/schema.py` — `DeviceControlConfig.allowed_file_roots: list[str]` (default computed per-machine via a new `_default_allowed_file_roots()` helper using `Path.home()`, never hardcoded), `use_recycle_bin_for_delete: bool = True`; `AppConfig._validate_device_control()` extended with non-empty/no-blank-entries checks for `allowed_file_roots`.
- `config/defaults.yaml` — `device_control:` section gains `use_recycle_bin_for_delete: true`; `allowed_file_roots` deliberately NOT set (would hardcode a developer-specific path into a checked-in file — see Engineering Decisions).
- `requirements.txt` — `Send2Trash>=1.8` added under a Sprint 4.3-labeled comment; installed (resolved to `2.1.0`).
- `docs/backlog/technical_debt.md` — item 19 added (Send2Trash dependency, resolved/documented).
- `tests/unit/config/test_schema.py` — 3 new tests for the new `allowed_file_roots` validation.
- `docs/STATUS.md` — Phase 4.1 row updated with this sprint's completion.

### Tests Added

29 total. In `test_file_operations.py` (26): `can_handle()` correctness; file/folder create (including missing-parent and already-exists rejection); file/folder move and copy (preserving vs. not preserving source, destination-already-exists rejection); file/folder rename; file/folder delete (recovery-verified indirectly by asserting `send2trash.send2trash()` — not a direct OS delete call — is what actually ran, via a spy); `delete()` refusing outright when `use_recycle_bin_for_delete=False` (both through `execute()` and by calling the public method directly); an out-of-root absolute path denied; a `../` traversal attempt denied; a **real** Windows symlink created inside the allowed root pointing outside it, denied (skips with a clear reason if the test environment can't create one — none needed here, see Remaining Risks); a path-scope denial proven to happen *before* any filesystem call (`send2trash` spied on, never called). In `test_schema.py` (3): the computed default `allowed_file_roots` is non-empty and itself passes validation, an empty list is rejected, a blank entry is rejected.

### Documentation Updated

This file (Sprint Completion Report). `device_control/file_operations.py`'s module/class docstrings. `config/schema.py`'s `DeviceControlConfig` docstring (the two hard invariants — path-scoping is enforced from this sprint onward, delete has no permanent-delete fallback — stated explicitly). `docs/backlog/technical_debt.md` item 19. `docs/STATUS.md` Phase 4.1 row. `docs/sprint_book/INDEX.md` (this sprint's row marked Complete).

### Acceptance Criteria Checklist

- ✔ Create/move/copy/rename/delete for both files and folders all succeed within `allowed_file_roots`.
- ✔ Every operation on a path outside `allowed_file_roots` — including a `../` traversal attempt and a **real** symlink-based escape attempt — is denied before any filesystem call happens (proven via a `send2trash` spy for the delete case; move/copy/create never got that far either, verified by the target never existing afterward).
- ✔ Delete never calls `os.remove`/`shutil.rmtree` — verified by spying on `send2trash.send2trash()` and confirming it's the actual call made.
- ✔ A failed operation (missing parameter, path already exists, source doesn't exist) degrades to `ActionStatus.FAILED` with a clear `error_message`, never raises past `execute()`.
- ✔ Matches Part 4 Phase 4.1's "Safe desktop control. Permissions respected."

### Engineering Decisions

- **`use_recycle_bin_for_delete=False` makes `delete()` refuse to run at all (raises `RuntimeError`), rather than falling back to a permanent OS-level delete.** This sprint's own original spec text was genuinely ambiguous on this point (its Expected Functions description named the `True` behavior but never stated what `False` should do; its Potential Risks called the field itself "a minor risk" without resolving what the risk actually was). Resolved in favor of the safest reading, consistent with this sprint's own stated goal ("this sprint's own job is to make sure a delete is never permanent in the first place") and the identical "hard invariant, no configurable override" pattern Sprint 4.5 (Command Execution Engine, not yet built, but already speced with `shell=False` as a non-negotiable) establishes for its own highest-risk primitive. The field remains present (per the spec's own Files to Modify), but it is now a real kill-switch for deletion entirely, never a silent safety downgrade.
- **The originally-speced `AppConfig.validate()`-time `WARNING` log for `use_recycle_bin_for_delete=False` was dropped, replaced by the `RuntimeError` above.** Discovered during implementation: `config/schema.py` cannot import `core.logging_setup` without creating a circular import (`core/logging_setup.py` itself imports `from config.schema import LoggingConfig`), and even if it could, `AppConfig.validate()` runs *before* `configure_logging()` in `main.py`'s own startup sequence — a warning logged there would never actually reach the configured log handlers. The `RuntimeError` raised at first real `delete()` call is strictly louder and better-timed than a config-load-time log line would have been anyway.
- **`allowed_file_roots`'s default is computed per-machine via a new `_default_allowed_file_roots()` factory function (`Path.home()`-based), and deliberately absent from the checked-in `config/defaults.yaml`.** Not spelled out by this sprint's own spec beyond "a real default is chosen during implementation, not left empty." Writing a literal computed path (e.g. this development machine's own `C:\Users\SATTIE\Documents`) into `defaults.yaml` would have shipped a developer-specific, meaningless-on-any-other-machine default to every installation — the dataclass `default_factory` mechanism already used throughout `config/schema.py` for mutable defaults is exactly the right tool for a value that must be computed fresh per machine, not baked in at file-write time.
- **`_dispatch()`'s per-handler methods raise `RuntimeError` for "missing required parameter" and "unhandled action type"**, rather than returning an `ActionResult(FAILED)` directly the way `ApplicationManager`'s handlers do (Sprint 4.2). A deliberate, consistent choice for this file specifically: every one of `FileOperationsManager`'s seven handlers needs the exact same three-way outcome shape (success, path-scope denial, OS/validation failure) funneled through one `try/except` in `execute()`, so routing every non-success path through an exception keeps that single funnel point real rather than leaving some handlers bypass it with an early `return`. `ApplicationManager`'s own four-operation `execute()` had less to funnel and reads more simply un-exception-ed — both are internally consistent within their own file, not a project-wide style mismatch worth reconciling.

### Remaining Risks

- **The real symlink-escape test genuinely created and resolved a Windows symlink in this environment** (confirmed via `os.symlink()` succeeding without elevation, most likely because Developer Mode or an equivalent privilege is enabled on this machine) — so the test's own `pytest.skip()` fallback path (for an environment where symlink creation requires elevation) was written defensively but never actually exercised here. Worth being aware that a future CI/build environment without that privilege would silently skip this specific check rather than fail — an accepted trade-off matching this project's own "no physical mic in CI"-style precedent (Sprint 2.1), not a new one.
- **`send2trash`'s actual recycle-bin *recoverability* was not independently verified** (e.g. by checking the Windows Recycle Bin's own contents after a delete) — this sprint's tests confirm `send2trash.send2trash()` is the code path taken (via a spy) and that the file is gone from its original location, which is what this sprint's own Acceptance Criteria actually asked for. A real, human-observed "and it's genuinely restorable from the Recycle Bin" check is more naturally Sprint 4.13's (Integration Testing & Level Freeze) real-machine verification pass than this component sprint's own unit-test scope.
- This sprint's own flagged risks (symlink/junction bypass, network-drive recycle-bin behavior, the `use_recycle_bin_for_delete` field's own risk) were all addressed as anticipated; none surfaced as worse than expected.

### Technical Debt

Item 19 (new, resolved/documented — the `Send2Trash` dependency addition) in `docs/backlog/technical_debt.md`. No new *unresolved* debt introduced by this sprint.

### Recommendations

- **For Sprint 4.4 (Window Management)**: no direct dependency on this sprint's own work, but worth noting `FileOperationsManager`'s per-handler exception-funneling pattern (see Engineering Decisions above) as a second reference point alongside `ApplicationManager`'s direct-return style — pick whichever fits `WindowManager`'s own five-operation shape better, not necessarily either one by default.
- **For Sprint 4.7 (Permission & Confirmation System)**: `allowed_file_roots` is real, enforced, and structural (no override parameter exists) — `PermissionGate`'s own risk classification sits *on top of* this sprint's scoping, never replaces it. `use_recycle_bin_for_delete`'s `RuntimeError`-on-`False` behavior means Sprint 4.7 never needs to reason about a "was this deleted permanently" ambiguity — it structurally cannot happen.
- **For Sprint 4.13 (Integration Testing & Level Freeze, Part A)**: a real, human-observed recycle-bin-recoverability check (see Remaining Risks) is a good candidate for that sprint's own real-machine verification pass, within its own disposable-scope discipline.

**Sprint 4.3 (File & Folder Operations) is complete.** **Sprint 4.4 (Window Management) is next.**
