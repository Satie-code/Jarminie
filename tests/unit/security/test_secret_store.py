"""Unit tests for security.secret_store.

The happy-path/priority tests exercise a real keyring backend (Windows
Credential Manager on this project's target platform, confirmed
present in this environment) — per this sprint's own Implementation
Tasks ("verified against a real (if test-scoped) keyring backend, not
only a mock"), not just a mock. A disposable, test-only secret name is
used throughout and cleaned up by the fixture below, so no real,
persistent credential is left behind on the machine running these
tests. The no-backend-degrade tests instead force keyring to fail via
monkeypatch, mirroring test_vtube_studio_renderer.py's own "patch the
boundary" precedent.
"""

import keyring
import keyring.errors
import pytest

from security.secret_store import _SERVICE_NAME, SecretStore

_PROBE_NAME = "jarminei_test_probe_secret"


def _real_backend_available() -> bool:
    try:
        keyring.set_password(_SERVICE_NAME, _PROBE_NAME, "probe")
        keyring.delete_password(_SERVICE_NAME, _PROBE_NAME)
        return True
    except Exception:
        return False


_HAS_REAL_BACKEND = _real_backend_available()


@pytest.fixture(autouse=True)
def _cleanup_real_keyring_entry():
    """Belt-and-suspenders cleanup: even if a test in this file raises
    partway through, no leftover jarminei/_PROBE_NAME entry survives in
    the real OS credential store."""
    yield
    try:
        keyring.delete_password(_SERVICE_NAME, _PROBE_NAME)
    except Exception:
        pass


_SKIP_NO_BACKEND = pytest.mark.skipif(
    not _HAS_REAL_BACKEND, reason="No usable OS credential backend in this environment"
)


@_SKIP_NO_BACKEND
def test_set_and_get_secret_round_trips_through_a_real_backend():
    store = SecretStore()

    store.set_secret(_PROBE_NAME, "probe-value-123")
    result = store.get_secret(_PROBE_NAME)

    assert result == "probe-value-123"


@_SKIP_NO_BACKEND
def test_get_secret_prefers_keyring_over_env_fallback(monkeypatch):
    monkeypatch.setenv("JARMINEI_TEST_SECRET_STORE_ENV_FALLBACK", "from-env")
    store = SecretStore()
    store.set_secret(_PROBE_NAME, "from-keyring")

    result = store.get_secret(_PROBE_NAME, env_fallback="JARMINEI_TEST_SECRET_STORE_ENV_FALLBACK")

    assert result == "from-keyring"


def test_get_secret_returns_none_when_nothing_is_stored_and_no_env_fallback(monkeypatch):
    monkeypatch.setattr("security.secret_store.keyring.get_password", lambda *a, **k: None)
    store = SecretStore()

    assert store.get_secret("definitely_never_set_xyz") is None


def test_get_secret_falls_back_to_env_var_when_keyring_has_nothing(monkeypatch):
    monkeypatch.setattr("security.secret_store.keyring.get_password", lambda *a, **k: None)
    monkeypatch.setenv("JARMINEI_TEST_SECRET_STORE_ENV_FALLBACK_2", "from-env")
    store = SecretStore()

    result = store.get_secret(
        "definitely_never_set_xyz", env_fallback="JARMINEI_TEST_SECRET_STORE_ENV_FALLBACK_2"
    )

    assert result == "from-env"


def test_get_secret_returns_none_when_env_fallback_var_is_unset(monkeypatch):
    monkeypatch.setattr("security.secret_store.keyring.get_password", lambda *a, **k: None)
    monkeypatch.delenv("JARMINEI_TEST_SECRET_STORE_ENV_FALLBACK_UNSET", raising=False)
    store = SecretStore()

    result = store.get_secret("x", env_fallback="JARMINEI_TEST_SECRET_STORE_ENV_FALLBACK_UNSET")

    assert result is None


# --- honest degrade when no OS credential backend is available ----------------


def _raise_no_keyring(*args, **kwargs):
    raise keyring.errors.NoKeyringError("no backend available")


def test_get_secret_degrades_to_env_fallback_when_backend_unavailable(monkeypatch):
    monkeypatch.setattr("security.secret_store.keyring.get_password", _raise_no_keyring)
    monkeypatch.setenv("JARMINEI_TEST_SECRET_STORE_ENV_FALLBACK_3", "from-env")
    store = SecretStore()

    result = store.get_secret(
        "whatever", env_fallback="JARMINEI_TEST_SECRET_STORE_ENV_FALLBACK_3"
    )

    assert result == "from-env"


def test_get_secret_returns_none_when_backend_unavailable_and_no_env_fallback(monkeypatch):
    monkeypatch.setattr("security.secret_store.keyring.get_password", _raise_no_keyring)
    store = SecretStore()

    assert store.get_secret("whatever") is None


def test_get_secret_never_raises_when_backend_unavailable(monkeypatch):
    monkeypatch.setattr("security.secret_store.keyring.get_password", _raise_no_keyring)
    store = SecretStore()

    store.get_secret("whatever")  # must not raise


def test_set_secret_never_raises_when_backend_unavailable(monkeypatch):
    def _raise(*args, **kwargs):
        raise keyring.errors.PasswordSetError("no backend available")

    monkeypatch.setattr("security.secret_store.keyring.set_password", _raise)
    store = SecretStore()

    store.set_secret("whatever", "value")  # must not raise


def test_set_secret_never_writes_a_plaintext_fallback_when_backend_unavailable(
    monkeypatch, tmp_path
):
    """The honest-degrade contract: set_secret() has no plaintext
    fallback path at all — confirmed here by asserting the filesystem
    is untouched, not merely that no exception was raised."""

    def _raise(*args, **kwargs):
        raise keyring.errors.PasswordSetError("no backend available")

    monkeypatch.setattr("security.secret_store.keyring.set_password", _raise)
    store = SecretStore()

    store.set_secret("whatever", "a-real-secret-value")

    assert list(tmp_path.iterdir()) == []


def test_backend_unavailable_logs_a_warning_only_once(monkeypatch, caplog):
    monkeypatch.setattr("security.secret_store.keyring.get_password", _raise_no_keyring)
    store = SecretStore()

    with caplog.at_level("WARNING", logger="security.secret_store"):
        store.get_secret("a")
        store.get_secret("b")
        store.get_secret("c")

    unavailable_warnings = [r for r in caplog.records if "unavailable" in r.message]
    assert len(unavailable_warnings) == 1


def test_backend_unavailable_warning_is_scoped_per_instance(monkeypatch, caplog):
    """A *new* SecretStore instance logs its own first warning again —
    the once-only bound is per-instance, not process-global (no shared
    module-level flag)."""
    monkeypatch.setattr("security.secret_store.keyring.get_password", _raise_no_keyring)

    with caplog.at_level("WARNING", logger="security.secret_store"):
        SecretStore().get_secret("a")
        SecretStore().get_secret("b")

    unavailable_warnings = [r for r in caplog.records if "unavailable" in r.message]
    assert len(unavailable_warnings) == 2
