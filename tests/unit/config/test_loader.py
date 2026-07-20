"""Unit tests for config.loader."""

import pytest
import yaml

from config.errors import ConfigError
from config.loader import ConfigLoader
from config.schema import AppConfig, DeviceControlConfig


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
