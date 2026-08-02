"""Unit tests for config.schema."""

import pytest

from config.errors import ConfigError
from config.schema import (
    AppConfig,
    DatabaseConfig,
    DeviceControlConfig,
    EmotionConfig,
    LoggingConfig,
    MemoryConfig,
    ModelConfig,
    PresentationConfig,
    ResourceThresholds,
    UIConfig,
    VoiceConfig,
    WorkflowConfig,
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


def test_non_positive_application_launch_readiness_check_seconds_raises():
    config = AppConfig(
        device_control=DeviceControlConfig(application_launch_readiness_check_seconds=0)
    )
    with pytest.raises(ConfigError, match="application_launch_readiness_check_seconds"):
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


# --- WorkflowConfig (Sprint 4.10 additions) ----------------------------------------


def test_non_positive_large_workflow_step_threshold_raises():
    config = AppConfig(workflow=WorkflowConfig(large_workflow_step_threshold=0))
    with pytest.raises(ConfigError, match="large_workflow_step_threshold"):
        config.validate()


def test_blank_large_workflow_confirmation_prompt_template_raises():
    config = AppConfig(
        workflow=WorkflowConfig(large_workflow_confirmation_prompt_template="   ")
    )
    with pytest.raises(ConfigError, match="large_workflow_confirmation_prompt_template"):
        config.validate()


# --- EmotionConfig (Sprint 5.1) ----------------------------------------------------


def test_blank_lexical_marker_keyword_raises():
    config = AppConfig(emotion=EmotionConfig(lexical_markers={"happy": ["  "]}))
    with pytest.raises(ConfigError, match="lexical_markers"):
        config.validate()


def test_non_positive_speaking_rate_baseline_raises():
    config = AppConfig(emotion=EmotionConfig(speaking_rate_baseline_wpm=0.0))
    with pytest.raises(ConfigError, match="speaking_rate_baseline_wpm"):
        config.validate()


def test_non_positive_long_pause_threshold_raises():
    config = AppConfig(emotion=EmotionConfig(long_pause_threshold_seconds=-1.0))
    with pytest.raises(ConfigError, match="long_pause_threshold_seconds"):
        config.validate()


def test_confidence_field_out_of_range_raises():
    config = AppConfig(emotion=EmotionConfig(min_estimate_confidence=1.5))
    with pytest.raises(ConfigError, match="min_estimate_confidence"):
        config.validate()


def test_state_smoothing_alpha_out_of_range_raises():
    config = AppConfig(emotion=EmotionConfig(state_smoothing_alpha=0.0))
    with pytest.raises(ConfigError, match="state_smoothing_alpha"):
        config.validate()


def test_non_positive_baseline_decay_half_life_raises():
    config = AppConfig(emotion=EmotionConfig(baseline_decay_half_life_seconds=0.0))
    with pytest.raises(ConfigError, match="baseline_decay_half_life_seconds"):
        config.validate()


def test_label_state_targets_unknown_dimension_raises():
    config = AppConfig(emotion=EmotionConfig(label_state_targets={"happy": {"bogus": 1.0}}))
    with pytest.raises(ConfigError, match="label_state_targets"):
        config.validate()


def test_label_state_targets_out_of_range_value_raises():
    config = AppConfig(emotion=EmotionConfig(label_state_targets={"happy": {"mood": 999.0}}))
    with pytest.raises(ConfigError, match="label_state_targets"):
        config.validate()


# --- EmotionConfig tone-adaptation thresholds (Sprint 5.4) --------------------


def test_tone_high_stress_threshold_out_of_range_raises():
    config = AppConfig(emotion=EmotionConfig(tone_high_stress_threshold=150.0))
    with pytest.raises(ConfigError, match="tone_high_stress_threshold"):
        config.validate()


@pytest.mark.parametrize(
    "field_name", ["jarvis_tone_low_mood_threshold", "minie_tone_low_mood_threshold"]
)
def test_tone_low_mood_threshold_out_of_range_raises(field_name):
    config = AppConfig(emotion=EmotionConfig(**{field_name: -200.0}))
    with pytest.raises(ConfigError, match=field_name):
        config.validate()


@pytest.mark.parametrize(
    "field_name", ["jarvis_tone_low_comfort_threshold", "minie_tone_low_comfort_threshold"]
)
def test_tone_low_comfort_threshold_out_of_range_raises(field_name):
    config = AppConfig(emotion=EmotionConfig(**{field_name: -5.0}))
    with pytest.raises(ConfigError, match=field_name):
        config.validate()


def test_default_tone_adaptation_thresholds_are_valid():
    """The shipped defaults themselves must pass validation — the same
    sanity check every other EmotionConfig default already gets
    implicitly via test_config_loads_with_no_overrides()-shaped tests
    elsewhere in this file."""
    AppConfig(emotion=EmotionConfig()).validate()


# --- PresentationConfig (Sprint 5.5) -------------------------------------------


def test_default_presentation_config_is_valid():
    AppConfig(presentation=PresentationConfig()).validate()


@pytest.mark.parametrize(
    "field_name",
    [
        "jarvis_smile_intensity_min",
        "jarvis_eye_openness_min",
        "jarvis_voice_warmth_min",
        "jarvis_particle_density_min",
        "jarvis_gesture_probability_min",
        "minie_smile_intensity_min",
        "minie_eye_openness_min",
        "minie_voice_warmth_min",
        "minie_particle_density_min",
        "minie_gesture_probability_min",
    ],
)
def test_unit_range_field_below_zero_raises(field_name):
    config = AppConfig(presentation=PresentationConfig(**{field_name: -0.1}))
    with pytest.raises(ConfigError, match=field_name):
        config.validate()


@pytest.mark.parametrize(
    "field_name",
    [
        "jarvis_smile_intensity_max",
        "minie_smile_intensity_max",
    ],
)
def test_unit_range_field_above_one_raises(field_name):
    config = AppConfig(presentation=PresentationConfig(**{field_name: 1.1}))
    with pytest.raises(ConfigError, match=field_name):
        config.validate()


def test_min_greater_than_max_raises():
    config = AppConfig(
        presentation=PresentationConfig(
            jarvis_smile_intensity_min=0.5, jarvis_smile_intensity_max=0.1
        )
    )
    with pytest.raises(ConfigError, match="jarvis_smile_intensity_min"):
        config.validate()


@pytest.mark.parametrize("field_name", ["jarvis_animation_speed_min", "minie_animation_speed_min"])
def test_animation_speed_below_structural_floor_raises(field_name):
    config = AppConfig(presentation=PresentationConfig(**{field_name: 0.1}))
    with pytest.raises(ConfigError, match=field_name):
        config.validate()


@pytest.mark.parametrize("field_name", ["jarvis_animation_speed_max", "minie_animation_speed_max"])
def test_animation_speed_above_structural_ceiling_raises(field_name):
    config = AppConfig(presentation=PresentationConfig(**{field_name: 3.0}))
    with pytest.raises(ConfigError, match=field_name):
        config.validate()


@pytest.mark.parametrize(
    "field_name",
    ["jarvis_lighting_color", "jarvis_ui_accent", "minie_lighting_color", "minie_ui_accent"],
)
def test_invalid_hex_color_raises(field_name):
    config = AppConfig(presentation=PresentationConfig(**{field_name: "not-a-color"}))
    with pytest.raises(ConfigError, match=field_name):
        config.validate()


def test_hex_color_without_leading_hash_raises():
    config = AppConfig(presentation=PresentationConfig(jarvis_lighting_color="0A84FF"))
    with pytest.raises(ConfigError, match="jarvis_lighting_color"):
        config.validate()


def test_jarvis_and_minie_particle_density_ranges_do_not_overlap():
    """The structural guarantee presentation/jarvis_state_computer.py's/
    presentation/minie_state_computer.py's own tests rely on for "Jarvis
    always observably lower than Minie" — verified here at the config
    level directly, for the shipped defaults."""
    config = PresentationConfig()
    assert config.jarvis_particle_density_max < config.minie_particle_density_min
    assert config.jarvis_smile_intensity_max < config.minie_smile_intensity_min


# --- VTube Studio / avatar backend (Sprint 5.8) --------------------------------


def test_blank_avatar_backend_raises():
    config = AppConfig(presentation=PresentationConfig(avatar_backend="  "))
    with pytest.raises(ConfigError, match="avatar_backend"):
        config.validate()


def test_blank_vtube_studio_host_raises():
    config = AppConfig(presentation=PresentationConfig(vtube_studio_host=""))
    with pytest.raises(ConfigError, match="vtube_studio_host"):
        config.validate()


@pytest.mark.parametrize("port", [0, -1, 70000])
def test_vtube_studio_port_out_of_range_raises(port):
    config = AppConfig(presentation=PresentationConfig(vtube_studio_port=port))
    with pytest.raises(ConfigError, match="vtube_studio_port"):
        config.validate()


def test_blank_vtube_studio_plugin_name_raises():
    config = AppConfig(presentation=PresentationConfig(vtube_studio_plugin_name=" "))
    with pytest.raises(ConfigError, match="vtube_studio_plugin_name"):
        config.validate()


def test_blank_vtube_studio_plugin_developer_raises():
    config = AppConfig(presentation=PresentationConfig(vtube_studio_plugin_developer=" "))
    with pytest.raises(ConfigError, match="vtube_studio_plugin_developer"):
        config.validate()


def test_blank_vtube_studio_auth_token_path_raises():
    config = AppConfig(presentation=PresentationConfig(vtube_studio_auth_token_path=" "))
    with pytest.raises(ConfigError, match="vtube_studio_auth_token_path"):
        config.validate()


def test_non_positive_vtube_studio_connection_timeout_raises():
    config = AppConfig(
        presentation=PresentationConfig(vtube_studio_connection_timeout_seconds=0.0)
    )
    with pytest.raises(ConfigError, match="vtube_studio_connection_timeout_seconds"):
        config.validate()


def test_vtube_studio_parameter_mapping_blank_key_raises():
    config = AppConfig(
        presentation=PresentationConfig(vtube_studio_parameter_mapping={" ": "ParamX"})
    )
    with pytest.raises(ConfigError, match="vtube_studio_parameter_mapping"):
        config.validate()


def test_vtube_studio_parameter_mapping_blank_value_raises():
    config = AppConfig(
        presentation=PresentationConfig(vtube_studio_parameter_mapping={"smile_intensity": " "})
    )
    with pytest.raises(ConfigError, match="vtube_studio_parameter_mapping"):
        config.validate()


def test_minie_expression_thresholds_empty_raises():
    config = AppConfig(presentation=PresentationConfig(minie_expression_thresholds={}))
    with pytest.raises(ConfigError, match="minie_expression_thresholds"):
        config.validate()


def test_minie_expression_thresholds_missing_zero_floor_raises():
    config = AppConfig(
        presentation=PresentationConfig(minie_expression_thresholds={"smile": 0.5})
    )
    with pytest.raises(ConfigError, match="minie_expression_thresholds"):
        config.validate()


def test_minie_expression_thresholds_out_of_range_value_raises():
    config = AppConfig(
        presentation=PresentationConfig(
            minie_expression_thresholds={"neutral": 0.0, "bogus": 1.5}
        )
    )
    with pytest.raises(ConfigError, match="minie_expression_thresholds"):
        config.validate()


def test_default_vtube_studio_config_is_valid():
    AppConfig(presentation=PresentationConfig()).validate()
