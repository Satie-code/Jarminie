"""Unit tests for config.schema."""

import pytest

from config.errors import ConfigError
from config.schema import (
    AppConfig,
    DatabaseConfig,
    DeviceControlConfig,
    LoggingConfig,
    MemoryConfig,
    ModelConfig,
    ResourceThresholds,
    UIConfig,
    VoiceConfig,
)


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


def test_empty_jarvis_trigger_phrases_raises():
    config = AppConfig(voice=VoiceConfig(jarvis_trigger_phrases=[]))
    with pytest.raises(ConfigError, match="jarvis_trigger_phrases"):
        config.validate()


def test_blank_jarvis_trigger_phrase_raises():
    config = AppConfig(voice=VoiceConfig(jarvis_trigger_phrases=["  "]))
    with pytest.raises(ConfigError, match="jarvis_trigger_phrases"):
        config.validate()


def test_empty_minie_trigger_phrases_raises():
    config = AppConfig(voice=VoiceConfig(minie_trigger_phrases=[]))
    with pytest.raises(ConfigError, match="minie_trigger_phrases"):
        config.validate()


def test_blank_minie_trigger_phrase_raises():
    config = AppConfig(voice=VoiceConfig(minie_trigger_phrases=["  "]))
    with pytest.raises(ConfigError, match="minie_trigger_phrases"):
        config.validate()


def test_non_positive_mic_sample_rate_hz_raises():
    config = AppConfig(voice=VoiceConfig(mic_sample_rate_hz=0))
    with pytest.raises(ConfigError, match="mic_sample_rate_hz"):
        config.validate()


def test_wake_word_sensitivity_zero_raises():
    config = AppConfig(voice=VoiceConfig(wake_word_sensitivity=0.0))
    with pytest.raises(ConfigError, match="wake_word_sensitivity"):
        config.validate()


def test_wake_word_sensitivity_above_one_raises():
    config = AppConfig(voice=VoiceConfig(wake_word_sensitivity=1.5))
    with pytest.raises(ConfigError, match="wake_word_sensitivity"):
        config.validate()


def test_wake_word_sensitivity_at_upper_bound_is_valid():
    AppConfig(voice=VoiceConfig(wake_word_sensitivity=1.0)).validate()


def test_non_positive_session_timeout_seconds_raises():
    config = AppConfig(voice=VoiceConfig(session_timeout_seconds=0))
    with pytest.raises(ConfigError, match="session_timeout_seconds"):
        config.validate()


def test_non_positive_utterance_silence_ms_raises():
    config = AppConfig(voice=VoiceConfig(utterance_silence_ms=0))
    with pytest.raises(ConfigError, match="utterance_silence_ms"):
        config.validate()


def test_utterance_silence_threshold_out_of_range_raises():
    config = AppConfig(voice=VoiceConfig(utterance_silence_threshold=1.5))
    with pytest.raises(ConfigError, match="utterance_silence_threshold"):
        config.validate()


def test_non_positive_max_utterance_seconds_raises():
    config = AppConfig(voice=VoiceConfig(max_utterance_seconds=0))
    with pytest.raises(ConfigError, match="max_utterance_seconds"):
        config.validate()


def test_whisper_no_speech_threshold_zero_raises():
    config = AppConfig(models=ModelConfig(whisper_no_speech_threshold=0.0))
    with pytest.raises(ConfigError, match="whisper_no_speech_threshold"):
        config.validate()


def test_whisper_no_speech_threshold_above_one_raises():
    config = AppConfig(models=ModelConfig(whisper_no_speech_threshold=1.5))
    with pytest.raises(ConfigError, match="whisper_no_speech_threshold"):
        config.validate()


def test_default_ollama_host_and_timeout():
    config = ModelConfig()
    assert config.ollama_host == "http://localhost:11434"
    assert config.ollama_timeout_seconds == 10.0


def test_empty_ollama_host_raises():
    config = AppConfig(models=ModelConfig(ollama_host="  "))
    with pytest.raises(ConfigError, match="ollama_host"):
        config.validate()


def test_non_positive_ollama_timeout_seconds_raises():
    config = AppConfig(models=ModelConfig(ollama_timeout_seconds=0))
    with pytest.raises(ConfigError, match="ollama_timeout_seconds"):
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


def test_non_positive_conversation_retention_days_raises():
    config = AppConfig(database=DatabaseConfig(conversation_retention_days=0))
    with pytest.raises(ConfigError, match="conversation_retention_days"):
        config.validate()


def test_status_refresh_interval_too_low_raises():
    config = AppConfig(ui=UIConfig(status_refresh_interval_ms=100))
    with pytest.raises(ConfigError, match="status_refresh_interval_ms"):
        config.validate()


def test_status_refresh_interval_too_high_raises():
    config = AppConfig(ui=UIConfig(status_refresh_interval_ms=120_000))
    with pytest.raises(ConfigError, match="status_refresh_interval_ms"):
        config.validate()


def test_default_memory_config_has_expected_prefix():
    assert AppConfig().memory.chroma_collection_prefix == "jarminei_memory"


def test_empty_chroma_collection_prefix_raises():
    config = AppConfig(memory=MemoryConfig(chroma_collection_prefix=""))
    with pytest.raises(ConfigError, match="chroma_collection_prefix"):
        config.validate()


def test_default_short_term_memory_settings():
    config = MemoryConfig()
    assert config.short_term_default_confidence == 15.0
    assert config.short_term_salience_triggers == [
        "remind me",
        "don't forget",
        "note that",
        "remember that",
    ]


def test_short_term_default_confidence_out_of_range_raises():
    config = AppConfig(memory=MemoryConfig(short_term_default_confidence=150.0))
    with pytest.raises(ConfigError, match="short_term_default_confidence"):
        config.validate()


def test_empty_short_term_salience_triggers_raises():
    config = AppConfig(memory=MemoryConfig(short_term_salience_triggers=[]))
    with pytest.raises(ConfigError, match="short_term_salience_triggers"):
        config.validate()


def test_blank_short_term_salience_trigger_raises():
    config = AppConfig(memory=MemoryConfig(short_term_salience_triggers=["remind me", "  "]))
    with pytest.raises(ConfigError, match="short_term_salience_triggers"):
        config.validate()


def test_status_refresh_interval_within_range_is_valid():
    AppConfig(ui=UIConfig(status_refresh_interval_ms=3000)).validate()


def test_non_positive_max_tracked_applications_raises():
    config = AppConfig(device_control=DeviceControlConfig(max_tracked_applications=0))
    with pytest.raises(ConfigError, match="max_tracked_applications"):
        config.validate()


def test_none_application_allowlist_is_valid():
    AppConfig(device_control=DeviceControlConfig(application_allowlist=None)).validate()


def test_blank_application_allowlist_entry_raises():
    config = AppConfig(
        device_control=DeviceControlConfig(application_allowlist=["notepad.exe", "  "])
    )
    with pytest.raises(ConfigError, match="application_allowlist"):
        config.validate()


def test_default_allowed_file_roots_is_non_empty_and_valid():
    """The computed default (Path.home()-based) must itself pass
    validation -- not just a hand-constructed override."""
    AppConfig().validate()
    assert AppConfig().device_control.allowed_file_roots


def test_empty_allowed_file_roots_raises():
    config = AppConfig(device_control=DeviceControlConfig(allowed_file_roots=[]))
    with pytest.raises(ConfigError, match="allowed_file_roots"):
        config.validate()


def test_blank_allowed_file_roots_entry_raises():
    config = AppConfig(
        device_control=DeviceControlConfig(allowed_file_roots=["C:/Users/test/Documents", "  "])
    )
    with pytest.raises(ConfigError, match="allowed_file_roots"):
        config.validate()
