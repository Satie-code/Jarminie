"""Unit tests for config.schema."""

import pytest

from config.errors import ConfigError
from config.schema import AppConfig, LoggingConfig, ResourceThresholds, UIConfig, VoiceConfig


def test_default_config_is_valid():
    AppConfig().validate()


def test_resource_threshold_out_of_range_raises():
    config = AppConfig(resources=ResourceThresholds(cpu_warning_percent=150.0))
    with pytest.raises(ConfigError, match="cpu_warning_percent"):
        config.validate()


def test_resource_critical_not_worse_than_warning_raises():
    config = AppConfig(
        resources=ResourceThresholds(cpu_warning_percent=90.0, cpu_critical_percent=70.0)
    )
    with pytest.raises(ConfigError, match="cpu_critical_percent"):
        config.validate()


def test_battery_critical_must_be_lower_than_warning():
    config = AppConfig(
        resources=ResourceThresholds(battery_warning_percent=10.0, battery_critical_percent=20.0)
    )
    with pytest.raises(ConfigError, match="battery_critical_percent"):
        config.validate()


def test_empty_wake_phrases_raises():
    config = AppConfig(voice=VoiceConfig(wake_phrases=[]))
    with pytest.raises(ConfigError, match="wake_phrases"):
        config.validate()


def test_blank_wake_phrase_raises():
    config = AppConfig(voice=VoiceConfig(wake_phrases=["  "]))
    with pytest.raises(ConfigError, match="wake_phrases"):
        config.validate()


def test_invalid_log_level_raises():
    config = AppConfig(logging=LoggingConfig(level="VERBOSE"))
    with pytest.raises(ConfigError, match="logging.level"):
        config.validate()


def test_non_positive_max_bytes_raises():
    config = AppConfig(logging=LoggingConfig(max_bytes=0))
    with pytest.raises(ConfigError, match="max_bytes"):
        config.validate()


def test_negative_backup_count_raises():
    config = AppConfig(logging=LoggingConfig(backup_count=-1))
    with pytest.raises(ConfigError, match="backup_count"):
        config.validate()


def test_empty_database_path_raises():
    config = AppConfig()
    config.database.sqlite_path = ""
    with pytest.raises(ConfigError, match="sqlite_path"):
        config.validate()


def test_status_refresh_interval_too_low_raises():
    config = AppConfig(ui=UIConfig(status_refresh_interval_ms=100))
    with pytest.raises(ConfigError, match="status_refresh_interval_ms"):
        config.validate()


def test_status_refresh_interval_too_high_raises():
    config = AppConfig(ui=UIConfig(status_refresh_interval_ms=120_000))
    with pytest.raises(ConfigError, match="status_refresh_interval_ms"):
        config.validate()


def test_status_refresh_interval_within_range_is_valid():
    AppConfig(ui=UIConfig(status_refresh_interval_ms=3000)).validate()
