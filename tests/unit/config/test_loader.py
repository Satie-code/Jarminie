"""Unit tests for config.loader."""

import pytest
import yaml

from config.errors import ConfigError
from config.loader import ConfigLoader
from config.schema import AppConfig, DeviceControlConfig


class _FakeSecretStore:
    """In-memory stand-in for security.secret_store.SecretStore —
    Sprint 6.20's own "patch the boundary" precedent (see
    tests/unit/presentation/test_vtube_studio_renderer.py's identically
    named fake), used here so these tests never touch the real OS
    credential store."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self._values = dict(values) if values else {}

    def get_secret(self, name: str, env_fallback: str | None = None) -> str | None:
        return self._values.get(name)

    def set_secret(self, name: str, value: str) -> None:
        self._values[name] = value


@pytest.fixture
def defaults_file(tmp_path):
    path = tmp_path / "defaults.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "voice": {"wake_phrases": ["hey jarminei"]},
                "resources": {"cpu_warning_percent": 70.0, "cpu_critical_percent": 90.0},
                "logging": {"level": "INFO", "max_bytes": 1000},
            }
        )
    )
    return path


def test_load_success(defaults_file, tmp_path):
    loader = ConfigLoader(
        defaults_path=defaults_file, local_path=tmp_path / "missing.yaml", env={}
    )
    config = loader.load()
    assert isinstance(config, AppConfig)
    assert config.voice.wake_phrases == ["hey jarminei"]


def test_load_missing_file_raises(tmp_path):
    loader = ConfigLoader(
        defaults_path=tmp_path / "nope.yaml", local_path=tmp_path / "nope_local.yaml", env={}
    )
    with pytest.raises(ConfigError, match="not found"):
        loader.load()


def test_load_malformed_yaml_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("voice: [unclosed")
    loader = ConfigLoader(defaults_path=bad, local_path=tmp_path / "missing.yaml", env={})
    with pytest.raises(ConfigError, match="Malformed YAML"):
        loader.load()


def test_load_non_mapping_yaml_raises_clear_error(tmp_path):
    """Regression test: valid YAML syntax but the wrong shape (a list
    instead of a mapping) previously crashed several calls downstream with
    a confusing AttributeError/ValueError instead of a clear ConfigError."""
    not_a_mapping = tmp_path / "list.yaml"
    not_a_mapping.write_text(yaml.safe_dump(["voice", "resources"]))
    loader = ConfigLoader(defaults_path=not_a_mapping, local_path=tmp_path / "missing.yaml", env={})
    with pytest.raises(ConfigError, match="mapping"):
        loader.load()


def test_load_invalid_field_raises(tmp_path):
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text(yaml.safe_dump({"resources": {"cpu_warning_percent": 500.0}}))
    loader = ConfigLoader(defaults_path=invalid, local_path=tmp_path / "missing.yaml", env={})
    with pytest.raises(ConfigError, match="cpu_warning_percent"):
        loader.load()


def test_env_override_takes_precedence(defaults_file, tmp_path):
    loader = ConfigLoader(
        defaults_path=defaults_file,
        local_path=tmp_path / "missing.yaml",
        env={"JARMINEI_LOGGING_LEVEL": "DEBUG"},
    )
    config = loader.load()
    assert config.logging.level == "DEBUG"


def test_env_override_coerces_numeric_type(defaults_file, tmp_path):
    loader = ConfigLoader(
        defaults_path=defaults_file,
        local_path=tmp_path / "missing.yaml",
        env={"JARMINEI_LOGGING_MAX_BYTES": "2000"},
    )
    config = loader.load()
    assert config.logging.max_bytes == 2000
    assert isinstance(config.logging.max_bytes, int)


def test_local_overlay_merges_over_defaults(defaults_file, tmp_path):
    local = tmp_path / "local.yaml"
    local.write_text(yaml.safe_dump({"logging": {"level": "WARNING"}}))
    loader = ConfigLoader(defaults_path=defaults_file, local_path=local, env={})
    config = loader.load()
    assert config.logging.level == "WARNING"
    assert config.voice.wake_phrases == ["hey jarminei"]


def test_env_overrides_local_overlay(defaults_file, tmp_path):
    local = tmp_path / "local.yaml"
    local.write_text(yaml.safe_dump({"logging": {"level": "WARNING"}}))
    loader = ConfigLoader(
        defaults_path=defaults_file, local_path=local, env={"JARMINEI_LOGGING_LEVEL": "ERROR"}
    )
    config = loader.load()
    assert config.logging.level == "ERROR"


def test_save_and_reload_round_trip(defaults_file, tmp_path):
    loader = ConfigLoader(
        defaults_path=defaults_file, local_path=tmp_path / "missing.yaml", env={}
    )
    config = loader.load()
    config.logging.level = "ERROR"
    save_path = tmp_path / "saved.yaml"
    loader.save(config, path=save_path)

    reload_loader = ConfigLoader(
        defaults_path=save_path, local_path=tmp_path / "missing2.yaml", env={}
    )
    reloaded = reload_loader.load()
    assert reloaded.logging.level == "ERROR"
    assert reloaded.voice.wake_phrases == ["hey jarminei"]


def test_save_uses_this_instances_local_path_not_the_module_default(tmp_path, defaults_file):
    """Regression test: save(config) with no explicit path must write to
    *this* loader's configured local_path, not the module-level
    LOCAL_CONFIG_PATH default (a real bug caught in Sprint 1.8 — see
    config/loader.py's save() docstring)."""
    local_path = tmp_path / "local.yaml"
    loader = ConfigLoader(defaults_path=defaults_file, local_path=local_path, env={})
    config = loader.load()
    config.logging.level = "ERROR"

    loader.save(config)  # no explicit path

    assert local_path.exists()
    reloaded = ConfigLoader(defaults_path=defaults_file, local_path=local_path, env={}).load()
    assert reloaded.logging.level == "ERROR"


def test_ui_section_loads_from_file_not_silently_defaulted(defaults_file, tmp_path):
    """Regression test: a ui: section in local.yaml must actually be read.
    A real bug (Sprint 1.7 added UIConfig to the schema but Sprint 1.8
    discovered _dict_to_config() never constructed it, so file values
    were silently ignored in favor of the default) — see config/loader.py's
    _SECTION_NAMES comment."""
    local = tmp_path / "local.yaml"
    local.write_text(yaml.safe_dump({"ui": {"status_refresh_interval_ms": 7500}}))
    loader = ConfigLoader(defaults_path=defaults_file, local_path=local, env={})

    config = loader.load()

    assert config.ui.status_refresh_interval_ms == 7500


def test_ui_env_override_applies(defaults_file, tmp_path):
    loader = ConfigLoader(
        defaults_path=defaults_file,
        local_path=tmp_path / "missing.yaml",
        env={"JARMINEI_UI_STATUS_REFRESH_INTERVAL_MS": "9000"},
    )

    config = loader.load()

    assert config.ui.status_refresh_interval_ms == 9000


def test_device_control_section_loads_with_no_errors(defaults_file, tmp_path):
    """Sprint 4.1 — Action Engine Foundation. device_control: is absent
    from this test's own minimal defaults_file fixture (like memory/
    models/database above), proving the section still resolves to a
    valid, empty DeviceControlConfig by default rather than raising."""
    loader = ConfigLoader(
        defaults_path=defaults_file, local_path=tmp_path / "missing.yaml", env={}
    )
    config = loader.load()
    assert config.device_control == DeviceControlConfig()


def test_real_shipped_defaults_yaml_loads_device_control_section():
    """Loads the actual, checked-in config/defaults.yaml (not a test
    fixture) — proves the real shipped file's device_control: section
    parses and validates, not just a synthetic minimal one."""
    config = ConfigLoader().load()
    assert isinstance(config.device_control, DeviceControlConfig)


# --- Sprint 6.20 (Permission & Encryption Audit): SecretStore-backed --------
# --- internet.search_api_key / tavily_api_key -------------------------------


def test_keyring_value_is_used_for_search_api_key(defaults_file, tmp_path):
    secret_store = _FakeSecretStore({"search_api_key": "from-keyring"})
    loader = ConfigLoader(
        defaults_path=defaults_file,
        local_path=tmp_path / "missing.yaml",
        env={},
        secret_store=secret_store,
    )

    config = loader.load()

    assert config.internet.search_api_key == "from-keyring"


def test_keyring_value_takes_priority_over_env_for_tavily_api_key(defaults_file, tmp_path):
    secret_store = _FakeSecretStore({"tavily_api_key": "from-keyring"})
    loader = ConfigLoader(
        defaults_path=defaults_file,
        local_path=tmp_path / "missing.yaml",
        env={"JARMINEI_INTERNET_TAVILY_API_KEY": "from-env"},
        secret_store=secret_store,
    )

    config = loader.load()

    assert config.internet.tavily_api_key == "from-keyring"


def test_env_var_is_used_when_keyring_has_nothing_for_search_api_key(defaults_file, tmp_path):
    loader = ConfigLoader(
        defaults_path=defaults_file,
        local_path=tmp_path / "missing.yaml",
        env={"JARMINEI_INTERNET_SEARCH_API_KEY": "from-env"},
        secret_store=_FakeSecretStore(),
    )

    config = loader.load()

    assert config.internet.search_api_key == "from-env"


def test_search_api_key_is_none_when_neither_keyring_nor_env_has_it(defaults_file, tmp_path):
    loader = ConfigLoader(
        defaults_path=defaults_file,
        local_path=tmp_path / "missing.yaml",
        env={},
        secret_store=_FakeSecretStore(),
    )

    config = loader.load()

    assert config.internet.search_api_key is None


def test_secret_resolution_env_fallback_uses_this_loaders_own_injected_env_not_real_os_environ(
    defaults_file, tmp_path, monkeypatch
):
    """Regression test: the env fallback for these two fields must go
    through ConfigLoader's own injected `env` dict, not the real
    process environment directly — otherwise ConfigLoader(env={}) would
    stop actually isolating tests from the real machine for exactly
    these two fields, defeating the whole reason that parameter
    exists (see every other test in this file)."""
    monkeypatch.setenv("JARMINEI_INTERNET_SEARCH_API_KEY", "leaked-from-real-os-environ")
    loader = ConfigLoader(
        defaults_path=defaults_file,
        local_path=tmp_path / "missing.yaml",
        env={},  # deliberately empty — must NOT see the real os.environ value above
        secret_store=_FakeSecretStore(),
    )

    config = loader.load()

    assert config.internet.search_api_key is None


def test_search_api_key_is_never_serialized_even_when_populated_in_memory(defaults_file, tmp_path):
    """Sprint 6.20 Acceptance Criteria: no API key is ever written to a
    plaintext file by save(), even if a caller has populated it
    on the in-memory AppConfig object directly."""
    loader = ConfigLoader(
        defaults_path=defaults_file, local_path=tmp_path / "missing.yaml", env={}
    )
    config = loader.load()
    config.internet.search_api_key = "a-real-secret-value"
    config.internet.tavily_api_key = "another-real-secret-value"

    save_path = tmp_path / "saved.yaml"
    loader.save(config, path=save_path)

    saved_text = save_path.read_text(encoding="utf-8")
    assert "a-real-secret-value" not in saved_text
    assert "another-real-secret-value" not in saved_text
    saved_raw = yaml.safe_load(saved_text)
    assert saved_raw["internet"]["search_api_key"] is None
    assert saved_raw["internet"]["tavily_api_key"] is None
