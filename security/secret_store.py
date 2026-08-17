"""SecretStore — OS-level credential storage (Sprint 6.20 — Permission &
Encryption Audit).

Resolves Phase 6.3's encryption-audit finding: zero encryption existed
anywhere in this codebase, directly contradicting
03_Engineering_Standards.md's own Security Guidelines ("Encrypt
sensitive data"). The scope was a real, disclosed stop-and-ask gate
resolved with the user via AskUserQuestion before any code was
written: "encrypt secrets only" — API keys and the VTube Studio auth
token, via the `keyring` library (backed by Windows Credential Manager
on this project's target platform). The SQLite databases stay
plaintext, a separate, larger, deliberately deferred decision — see
docs/backlog/technical_debt.md.

Wraps `keyring.get_password()`/`set_password()` under one fixed
service name so callers never configure a backend themselves. Both
methods degrade honestly when no usable OS credential backend exists
(e.g. a headless/CI-less environment not this project's own target
platform): `get_secret()` falls back to reading a caller-named
environment variable — this codebase's own pre-existing "read secrets
from the environment, never commit them to yaml" convention (see
config/schema.py's InternetConfig docstring) — and `set_secret()`
simply logs once and returns. Neither ever raises, and neither ever
writes plaintext anywhere as a substitute for the real OS-level
storage that wasn't available.

Deliberately narrow: not a general encryption utility for other
subsystems to reach for speculatively — see this module's own Sprint
6.20 Architecture Notes.
"""

from __future__ import annotations

import os

import keyring

from core.logging_setup import get_logger

logger = get_logger(__name__)

_SERVICE_NAME = "jarminei"


class SecretStore:
    """No constructor dependencies — keyring's own backend is process-
    global, not something this class configures. The only state kept
    (_warned_unavailable) bounds the "backend unavailable" log line to
    once per instance rather than once per call."""

    def __init__(self) -> None:
        self._warned_unavailable = False

    def get_secret(self, name: str, env_fallback: str | None = None) -> str | None:
        try:
            value = keyring.get_password(_SERVICE_NAME, name)
        except Exception:
            self._warn_unavailable()
            value = None
        if value is not None:
            return value
        if env_fallback is not None:
            return os.environ.get(env_fallback) or None
        return None

    def set_secret(self, name: str, value: str) -> None:
        try:
            keyring.set_password(_SERVICE_NAME, name, value)
        except Exception:
            self._warn_unavailable()

    def _warn_unavailable(self) -> None:
        if self._warned_unavailable:
            return
        self._warned_unavailable = True
        logger.warning(
            "OS-level credential storage (keyring) is unavailable on this "
            "machine — degrading to environment variables for secrets. "
            "No secret is ever written to a plaintext file as a substitute."
        )
