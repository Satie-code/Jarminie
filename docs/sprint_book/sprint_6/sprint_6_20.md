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

- [ ] `SecretStore.get_secret()`/`set_secret()`, happy path and no-backend-degrade path.
- [ ] `InternetConfig` secrets never round-trip to plaintext `local.yaml`.
- [ ] VTube Studio token persisted via `SecretStore`, never plaintext.
- [ ] `policy_engine.py` exhaustive-coverage re-confirmation.
- [ ] Allowlist/denylist empty-by-design re-confirmation (4 fields).
- [ ] Full project suite re-run.

## Documentation Checklist

- [ ] `docs/STATUS.md` — narrative describing the `AskUserQuestion` decision, `SecretStore`, and the permission-audit re-confirmation.
- [ ] `docs/sprint_book/INDEX.md` — 6.20 row → `Complete` (once implemented).
- [ ] `docs/backlog/technical_debt.md` — new item: SQLite-database-encryption remains open, deliberately deferred by direct user decision at this sprint.
- [ ] `requirements.txt` — `keyring` addition documented.

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
