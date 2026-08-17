# Sprint 6.20 — Permission & Encryption Audit

## Sprint ID

6.20

## Sprint Name

Permission & Encryption Audit

## Purpose

Deliver Phase 6.3's own first task pair, "Permission audit. Encryption audit." Permission audit: re-confirm the existing `security/` policy machinery is still correct against the Level-6-widened `ActionType` surface. Encryption audit: a real, concrete gap — zero encryption exists anywhere in this codebase today, directly contradicting [03_Engineering_Standards.md](../../03_Engineering_Standards.md)'s own Security Guidelines ("Encrypt sensitive data"). Confirmed by research, not assumed: API keys, the persisted VTube Studio auth token, and every SQLite database are all plaintext at rest.

## Engineering Rationale

**A real, disclosed stop-and-ask gate, resolved via `AskUserQuestion` before any code was scoped** — the same category of decision as Sprint 4.16's search-provider choice and Sprint 5.8's VTube Studio WebSocket-client choice: given zero encryption exists and a genuine multi-way scope choice (audit-only and defer; encrypt secrets only; encrypt secrets and every database), the user was asked directly. **The user chose "encrypt secrets only"**: real encryption for the two highest-risk plaintext items (API keys, the VTube Studio auth token) via OS-level credential storage (the `keyring` library, backed by Windows Credential Manager on this project's target platform — no manual key-management/recovery burden this project would otherwise have to design), leaving the SQLite databases plaintext with that gap explicitly documented as a separate, larger future decision, not silently implied resolved by this sprint.

Permission audit: `security/permission_gate.py`'s `PermissionGate.check()`, `security/policy_engine.py`'s `PermissionPolicyEngine`/`RiskLevel`, and `security/confirmation_service.py`'s `VoiceConfirmationService` are all real, already well-tested (41 existing tests across `tests/unit/security/`), and — confirmed by research — every allowlist/denylist (`DeviceControlConfig.approved_commands`/`application_allowlist`, `SecurityConfig.hard_denylist`, `AuthorityEvaluator.approved_emergency_procedures`) remains deliberately empty by design, exactly as `backlog/technical_debt.md` item 22 already established. This sprint's own job is narrowly to *re-confirm* this machinery still holds against the current, Level-6-widened system, not to populate any of those deliberately-empty lists (a separate, larger content decision item 22 already named, out of this sprint's own scope) and not to re-litigate `PermissionGate.check()`'s own already-disclosed, deliberate choice not to consult `authority_evaluator` (its own docstring already documents this).

## Objectives

- New `security/secret_store.py`'s `SecretStore` — wraps `keyring.set_password()`/`get_password()` under one service name (`"jarminei"`), with a real, honest degrade when no OS credential backend is available (e.g. a headless/CI-less environment): falls back to reading the same environment variable this codebase already, by convention, reads secrets from (`InternetConfig`'s own existing "deliberately read from the environment... never committed to yaml" discipline), logging once that OS-level storage is unavailable — never crashes, never silently writes plaintext as a fallback.
- `InternetConfig.search_api_key`/`tavily_api_key` are read via `SecretStore` (keyring-first, environment-variable fallback) rather than only ever from the environment; `config/loader.py`'s `ConfigLoader.save()` gains an explicit, enforced exclusion for both fields (never serialized to `local.yaml` even if a caller populates them on the in-memory `AppConfig` object) — closing the "the env-only discipline is convention, not enforced by code" gap research confirmed.
- `presentation/vtube_studio_renderer.py`'s `_persist_token()`/`_load_token()` store the VTube Studio auth token via `SecretStore` instead of `path.write_text(json.dumps(...))`/plaintext JSON read — a pre-existing plaintext token file (if one exists on a machine that already ran VTube Studio integration) is not auto-migrated by code; the one-time re-authentication a user in that position needs is documented, not built as migration machinery, matching this project's own "don't build speculative migration tooling" discipline (the same treatment the `espeak-ng` system-binary install already received).
- Permission audit: re-run `security/policy_engine.py`'s own exhaustive per-`ActionType` coverage test against the current enum (already includes `OPEN_URL`, added at Sprint 6.9, per `docs/STATUS.md`'s own Sprint 6.9 narrative) — confirm it is still exhaustive, not stale; re-confirm every allowlist/denylist is still empty exactly as designed.

## Dependencies

3.11 (`AuthorityEvaluator`), 4.7 (Permission & Confirmation System), 6.9 (widened `ActionType`), Level 6 Part A.

## Files to Create

- `security/secret_store.py`

## Files to Modify

- `config/schema.py` / `config/loader.py` (`SecretStore`-backed read path for `search_api_key`/`tavily_api_key`; explicit non-serialization)
- `presentation/vtube_studio_renderer.py` (`SecretStore`-backed token persistence)
- `requirements.txt` (`keyring`)
- `security/__init__.py` (docstring update — "Encryption" responsibility now has a real, if narrowly-scoped, implementation)

## Expected Classes

- `security/secret_store.py`'s `SecretStore` — `get_secret(name: str, env_fallback: str | None = None) -> str | None`, `set_secret(name: str, value: str) -> None`, both degrading honestly (never raising) when the OS credential backend is unavailable.

## Expected Functions

None beyond `SecretStore`'s own two public methods.

## Data Flow

`InternetConfig`/`PresentationConfig` construction → `SecretStore.get_secret()` (keyring lookup → environment-variable fallback → `None`) → unchanged downstream use (`BraveSearchProvider`/`TavilySearchProvider`/`VTubeStudioAvatarRenderer` construction). Write path: a user-provided secret → `SecretStore.set_secret()` → OS credential store only, never `config/local.yaml`.

## Implementation Tasks

1. `security/secret_store.py`'s `SecretStore`, with real, honest degrade-on-unavailable-backend behavior, verified against a real (if test-scoped) keyring backend, not only a mock.
2. Wire `InternetConfig.search_api_key`/`tavily_api_key` through `SecretStore`; add the explicit non-serialization guard in `config/loader.py`'s `save()`.
3. `presentation/vtube_studio_renderer.py`'s `_persist_token()`/`_load_token()` migrated to `SecretStore`; a regression test confirms no plaintext token file is ever written by fresh code.
4. Permission audit: re-run and, if needed, extend `test_policy_engine.py`'s own exhaustive-coverage test; add a explicit re-confirmation test for each of the four deliberately-empty allowlist/denylist fields, mirroring the existing `test_approved_commands_ships_empty_so_every_command_is_denied_by_default` precedent.
5. `requirements.txt` — add `keyring`, following this project's own established "resolved dependency, documented not hidden" convention (`backlog/technical_debt.md` items 3/19's own precedent).

## Architecture Notes

`SecretStore` is a narrow, single-purpose wrapper — it does not become a general encryption utility for other subsystems to reach for speculatively; the SQLite databases stay explicitly out of this sprint's own scope, per the user's own direct decision, not an oversight. `ConfigLoader`'s existing plaintext `yaml.safe_dump()` path is otherwise unchanged — every non-secret config field continues to round-trip through `local.yaml` exactly as before.

## Integration Considerations

- Sprint 6.21 (Privacy Verification) is the natural sibling sprint for the SQLite-database-encryption question this sprint deliberately defers — not this sprint's own job to revisit, since the user's own scope decision already drew that line; Sprint 6.21's own privacy audit covers *what* data is stored and *how long*, not *whether it's encrypted*.
- Sprint 6.22 (Full Documentation Pass) is where the deferred database-encryption gap gets formally logged to `backlog/technical_debt.md` as a real, disclosed, future-facing item if not already logged by this sprint directly.

## Potential Risks

- **`keyring`'s own backend availability varies by environment** (a real Windows Credential Manager backend on the target machine, but potentially no usable backend in a minimal/headless test environment) — `SecretStore`'s own honest degrade-to-environment-variable path is exactly the mitigation, verified by a test that forces the no-backend case explicitly, not just the happy path.
- **A pre-existing plaintext VTube Studio token file left on disk from before this sprint is not cleaned up automatically** — disclosed explicitly (Objectives) as a deliberate choice, not a gap this sprint silently leaves undocumented.

## Acceptance Criteria

- No API key or the VTube Studio auth token is ever written to a plaintext file by this sprint's own code, verified by a real regression test.
- `SecretStore` degrades honestly (never raises, never silently writes plaintext) when no OS credential backend is available.
- `security/policy_engine.py`'s exhaustive `ActionType` coverage test is confirmed current (including `OPEN_URL`); every allowlist/denylist is confirmed still empty by design.
- Full test suite (unit + integration + system, opt-in real-model marker excluded) passes with zero regressions.
- `ruff check .` clean.

## Testing Checklist

- [x] `SecretStore.get_secret()`/`set_secret()`, happy path and no-backend-degrade path.
- [x] `InternetConfig` secrets never round-trip to plaintext `local.yaml`.
- [x] VTube Studio token persisted via `SecretStore`, never plaintext.
- [x] `policy_engine.py` exhaustive-coverage re-confirmation.
- [x] Allowlist/denylist empty-by-design re-confirmation (4 fields).
- [x] Full project suite re-run.

## Documentation Checklist

- [x] `docs/STATUS.md` — narrative describing the `AskUserQuestion` decision, `SecretStore`, and the permission-audit re-confirmation.
- [x] `docs/sprint_book/INDEX.md` — 6.20 row → `Complete` (once implemented).
- [x] `docs/backlog/technical_debt.md` — new item: SQLite-database-encryption remains open, deliberately deferred by direct user decision at this sprint.
- [x] `requirements.txt` — `keyring` addition documented.

## Definition of Done

Per [docs/CODING_STANDARDS.md](../../CODING_STANDARDS.md).

## Estimated Complexity

Medium–High.

## Estimated Development Time

2.5–3 days.

## Risks

See Potential Risks above.

## Next Sprint

6.21 — Privacy Verification.

## Future Considerations

- Encryption-at-rest for the SQLite databases (memory, conversation, knowledge graph, calendar, action audit log) — a real, larger future decision (SQLCipher vs. app-level field encryption, key management/recovery UX, migration of existing plaintext files), deliberately out of this sprint's own scope per the user's own direct choice, logged to `backlog/technical_debt.md` rather than assumed resolved.

## Sprint Completion Report (2026-08-16)

Implemented as specified, continued from a prior session's own "continue with the implementation of sprint 6.20." The encryption-scope `AskUserQuestion` gate this sprint's own Engineering Rationale describes had already been resolved in an earlier session ("encrypt secrets only," via `keyring`) — this session began directly from research and implementation, not from re-asking that question.

**`SecretStore` (Objective 1/Implementation Task 1) — implemented and verified against a real backend.** New `security/secret_store.py`'s `SecretStore` wraps `keyring.get_password()`/`set_password()` under service name `"jarminei"`; `get_secret(name, env_fallback=None)` tries keyring first, then the named environment variable, then `None`; `set_secret()` degrades to a once-per-instance logged warning on any backend exception, never raising and never writing a plaintext fallback. Verified against the real, live Windows Credential Manager backend on this machine (`keyring.backends.Windows.WinVaultKeyring`, confirmed via a real `set_password`/`get_password`/`delete_password` round trip both manually and in `tests/unit/security/test_secret_store.py`), not only a mock — the no-backend-degrade path is separately forced via `monkeypatch` raising `keyring.errors.NoKeyringError`/`PasswordSetError`.

**A real circular-import bug, found and fixed before it could reach any caller.** The first version wired `SecretStore` into `config/loader.py` via a normal module-level import. `config/__init__.py` eagerly imports `config.loader`; `security/secret_store.py` imports `core.logging_setup`, which imports `config.schema` — and the first time anything imports `security.secret_store` directly (as `tests/unit/security/test_secret_store.py` does), that chain loops back through `config/__init__.py` to `config/loader.py`'s own `from security.secret_store import SecretStore` line before `security/secret_store.py`'s own module body has finished defining the class, raising `ImportError: cannot import name 'SecretStore' from partially initialized module`. Fixed using this codebase's own already-established pattern for exactly this class of problem (`security/policy_engine.py`'s own `TYPE_CHECKING`-gated `ActionType` import, documented in that module's own docstring): `config/loader.py` gained `from __future__ import annotations`, moved the `SecretStore` import under `TYPE_CHECKING` for the type hint, and imports it for real only inside `ConfigLoader.__init__`, function-locally.

**Objective 2 (Implementation Task 2) — implemented, plus one real design correction for test isolation.** `ConfigLoader` gained an optional `secret_store` constructor collaborator (defaults to a real `SecretStore()`); `_resolve_secrets()` runs after `_dict_to_config()`, keyring-first for both `internet.search_api_key`/`tavily_api_key`. One deliberate departure from `SecretStore.get_secret()`'s own literal `env_fallback` parameter: `ConfigLoader._resolve_secrets()` does *not* pass `env_fallback` to `SecretStore` (which would read the real process environment directly) — it instead falls back to `self._env`, `ConfigLoader`'s own already-injected env source. Every existing `test_loader.py` test relies on `ConfigLoader(env={})` to fully isolate itself from the real machine's environment; letting `SecretStore`'s own env fallback bypass that dict and read real `os.environ` directly would have quietly broken that isolation guarantee for exactly these two fields. `ConfigLoader.save()` now forces `internet.search_api_key`/`tavily_api_key` to `None` in the serialized dict unconditionally, regardless of what the in-memory `AppConfig` holds.

**Objective 3 (Implementation Task 3) — implemented.** `VTubeStudioAvatarRenderer` gained an optional `secret_store` collaborator (defaults to a real `SecretStore()`, the same "optional collaborator" pattern `memory/lifecycle_manager.py`'s `runtime_manager` established at Sprint 6.19); `_load_persisted_token()`/`_persist_token()` now read/write through it under key `"vtube_studio_auth_token"` instead of `Path.write_text(json.dumps(...))`/plaintext JSON. The `Path` import is no longer needed in that file and was removed. `tests/unit/presentation/test_vtube_studio_renderer.py` gained an autouse fixture patching the module's `SecretStore` reference to an in-memory `_FakeSecretStore` (mirroring the file's own established "patch the boundary" precedent for `connect`) — without it, every test in the file would have round-tripped through this machine's real Windows Credential Manager entry, leaking a persisted token across test runs (caught by 12 real test failures on the first run, all order-dependent — direct confirmation the plaintext-file removal actually changed behavior, not a no-op). A new regression test, `test_mount_never_writes_a_plaintext_token_file`, directly confirms nothing is written under `tmp_path` at all.

**Objective 4 / Permission audit (Implementation Task 4) — re-confirmed current, no drift found.** `test_policy_engine.py`'s exhaustive `test_every_action_type_has_a_default_risk_level_covered_by_this_test` already covers `OPEN_URL` (added at Sprint 6.9) and passes unchanged — `ActionType` has not grown since. All four deliberately-empty allowlist/denylist fields (`DeviceControlConfig.approved_commands`, `DeviceControlConfig.application_allowlist`, `SecurityConfig.hard_denylist`, `AuthorityEvaluator.approved_emergency_procedures`) already had behavioral "ships empty so X happens by default" coverage; two (`approved_commands` via `test_approved_commands_ships_empty_so_every_command_is_denied_by_default`, `hard_denylist` via `test_hard_denylist_ships_empty_by_default`) already had a direct field-value assertion too. Added the two that didn't: `test_application_allowlist_ships_none_by_default` (`tests/unit/security/test_permission_gate.py`) and `test_approved_emergency_procedures_ships_empty_by_default` (`tests/unit/decision/test_authority.py`).

**A small, disclosed scope boundary.** `PresentationConfig.vtube_studio_auth_token_path` was not in this sprint's own Files to Modify list (only `presentation/vtube_studio_renderer.py` was named for the token-persistence change) and was left untouched — it still exists, still validates, but is no longer read or written by fresh code. Logged as `backlog/technical_debt.md` item 58 rather than silently left inconsistent or edited beyond this sprint's own named scope.

**Full regression suite.** `tests/unit/`: 2281 passed, 1 skipped (12 new `test_secret_store.py` tests, 6 new `test_loader.py` tests, 2 new re-confirmation tests, 1 new `test_vtube_studio_renderer.py` regression test — zero regressions from the 2260+1 baseline). `tests/integration/`: 75 passed, fully clean. `tests/system/`: run together, 31 passed, 4 skipped, 3 failed; all three failures independently re-run in isolation — `test_full_level3_acceptance_scripted_conversation` and `test_level4_part_a_full_acceptance_scenario` both passed standalone (resource-contention timing flakes from the combined heavy run, not real failures), and `test_context_analyzer_extracts_a_nonempty_topic_for_real_input` failed the same way standalone too — but this is the pre-existing, already-documented real-Ollama-nondeterminism flake named in Sprint 6.19's own completion report, unrelated to any change this sprint made. Zero real regressions. `ruff check .` clean repo-wide. No git commit made — sits uncommitted alongside all of 6.1–6.19's own backlog.
