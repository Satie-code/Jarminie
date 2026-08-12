"""Unit tests for config.schema."""

import pytest

from config.errors import ConfigError
from config.schema import (
    AppConfig,
    ContextEngineConfig,
    DatabaseConfig,
    DecisionEngineConfig,
    DeviceControlConfig,
    EmotionConfig,
    KnowledgeGraphConfig,
    LearningConfig,
    LoggingConfig,
    MemoryConfig,
    ModelConfig,
    PlanningConfig,
    PresentationConfig,
    ProactiveConfig,
    ReasoningConfig,
    ResourceThresholds,
    RuntimeConfig,
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


def test_default_allowed_url_schemes_is_valid():
    AppConfig().validate()
    assert AppConfig().device_control.allowed_url_schemes == ["https", "http"]


def test_empty_allowed_url_schemes_raises():
    config = AppConfig(device_control=DeviceControlConfig(allowed_url_schemes=[]))
    with pytest.raises(ConfigError, match="allowed_url_schemes"):
        config.validate()


def test_blank_allowed_url_schemes_entry_raises():
    config = AppConfig(device_control=DeviceControlConfig(allowed_url_schemes=["https", "  "]))
    with pytest.raises(ConfigError, match="allowed_url_schemes"):
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


def test_non_positive_max_steps_from_task_graph_raises():
    config = AppConfig(workflow=WorkflowConfig(max_steps_from_task_graph=0))
    with pytest.raises(ConfigError, match="max_steps_from_task_graph"):
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


# --- planning (Sprint 6.1 — Planning Engine, Level 6 Part A) ---------------------------
# Note: AnalyticsConfig/WellnessConfig/LearningConfig (Sprints 5.17-5.23) have no
# validation test coverage anywhere in this suite — a real, pre-existing gap found while
# adding this section, out of this sprint's own scope to backfill.


def test_default_planning_config_is_valid():
    AppConfig(planning=PlanningConfig()).validate()


def test_non_positive_max_milestones_per_goal_raises():
    config = AppConfig(planning=PlanningConfig(max_milestones_per_goal=0))
    with pytest.raises(ConfigError, match="max_milestones_per_goal"):
        config.validate()


def test_non_positive_max_tasks_per_milestone_raises():
    config = AppConfig(planning=PlanningConfig(max_tasks_per_milestone=0))
    with pytest.raises(ConfigError, match="max_tasks_per_milestone"):
        config.validate()


def test_non_positive_decomposition_timeout_seconds_raises():
    config = AppConfig(planning=PlanningConfig(decomposition_timeout_seconds=0.0))
    with pytest.raises(ConfigError, match="decomposition_timeout_seconds"):
        config.validate()


def test_non_positive_max_task_dependencies_raises():
    config = AppConfig(planning=PlanningConfig(max_task_dependencies=0))
    with pytest.raises(ConfigError, match="max_task_dependencies"):
        config.validate()


def test_non_positive_evaluation_timeout_seconds_raises():
    config = AppConfig(planning=PlanningConfig(evaluation_timeout_seconds=0.0))
    with pytest.raises(ConfigError, match="evaluation_timeout_seconds"):
        config.validate()


# --- context_engine (Sprint 6.3 — Context Engine, Level 6 Part A) -----------------------


def test_default_context_engine_config_is_valid():
    AppConfig(context_engine=ContextEngineConfig()).validate()


def test_non_positive_memory_lookback_count_raises():
    config = AppConfig(context_engine=ContextEngineConfig(memory_lookback_count=0))
    with pytest.raises(ConfigError, match="memory_lookback_count"):
        config.validate()


def test_non_positive_usage_lookback_hours_raises():
    config = AppConfig(context_engine=ContextEngineConfig(usage_lookback_hours=0.0))
    with pytest.raises(ConfigError, match="usage_lookback_hours"):
        config.validate()


def test_non_positive_calendar_lookahead_hours_raises():
    config = AppConfig(context_engine=ContextEngineConfig(calendar_lookahead_hours=0.0))
    with pytest.raises(ConfigError, match="calendar_lookahead_hours"):
        config.validate()


# --- reasoning (Sprint 6.4 — Reasoning Engine, Level 6 Part A) ---------------------------


def test_default_reasoning_config_is_valid():
    AppConfig(reasoning=ReasoningConfig()).validate()


def test_non_positive_max_alternatives_raises():
    config = AppConfig(reasoning=ReasoningConfig(max_alternatives=0))
    with pytest.raises(ConfigError, match="max_alternatives"):
        config.validate()


def test_non_positive_reasoning_timeout_seconds_raises():
    config = AppConfig(reasoning=ReasoningConfig(reasoning_timeout_seconds=0.0))
    with pytest.raises(ConfigError, match="reasoning_timeout_seconds"):
        config.validate()


def test_non_positive_max_explanation_sentences_raises():
    config = AppConfig(reasoning=ReasoningConfig(max_explanation_sentences=0))
    with pytest.raises(ConfigError, match="max_explanation_sentences"):
        config.validate()


# --- decision_engine_v2 (Sprint 6.5 — Decision Engine v2, Level 6 Part A) ----------------


def test_default_decision_engine_config_is_valid():
    AppConfig(decision_engine_v2=DecisionEngineConfig()).validate()


def test_decision_engine_weights_not_summing_to_one_raises():
    config = AppConfig(
        decision_engine_v2=DecisionEngineConfig(
            risk_weight=0.5, confidence_weight=0.5, priority_weight=0.5
        )
    )
    with pytest.raises(ConfigError, match="must sum to 1.0"):
        config.validate()


def test_decision_engine_weights_summing_to_one_within_tolerance_is_valid():
    config = AppConfig(
        decision_engine_v2=DecisionEngineConfig(
            risk_weight=0.4, confidence_weight=0.35, priority_weight=0.25000001
        )
    )
    config.validate()


def test_decision_engine_weight_below_zero_raises():
    config = AppConfig(decision_engine_v2=DecisionEngineConfig(risk_weight=-0.1))
    with pytest.raises(ConfigError, match="risk_weight"):
        config.validate()


def test_decision_engine_weight_above_one_raises():
    config = AppConfig(decision_engine_v2=DecisionEngineConfig(confidence_weight=1.5))
    with pytest.raises(ConfigError, match="confidence_weight"):
        config.validate()


def test_non_positive_active_conversation_defer_seconds_raises():
    config = AppConfig(
        decision_engine_v2=DecisionEngineConfig(active_conversation_defer_seconds=0.0)
    )
    with pytest.raises(ConfigError, match="active_conversation_defer_seconds"):
        config.validate()


def test_low_battery_boost_threshold_percent_out_of_range_raises():
    config = AppConfig(
        decision_engine_v2=DecisionEngineConfig(low_battery_boost_threshold_percent=150.0)
    )
    with pytest.raises(ConfigError, match="low_battery_boost_threshold_percent"):
        config.validate()


def test_non_positive_conversation_active_threshold_seconds_raises():
    config = AppConfig(
        decision_engine_v2=DecisionEngineConfig(conversation_active_threshold_seconds=0.0)
    )
    with pytest.raises(ConfigError, match="conversation_active_threshold_seconds"):
        config.validate()


def test_low_confidence_hold_threshold_out_of_range_raises():
    config = AppConfig(
        decision_engine_v2=DecisionEngineConfig(low_confidence_hold_threshold=1.5)
    )
    with pytest.raises(ConfigError, match="low_confidence_hold_threshold"):
        config.validate()


# --- knowledge_graph (Sprint 6.6 — Knowledge Graph, Level 6 Part A) ----------------------


def test_default_knowledge_graph_config_is_valid():
    AppConfig(knowledge_graph=KnowledgeGraphConfig()).validate()


def test_non_positive_max_traversal_depth_raises():
    config = AppConfig(knowledge_graph=KnowledgeGraphConfig(max_traversal_depth=0))
    with pytest.raises(ConfigError, match="max_traversal_depth"):
        config.validate()


def test_non_positive_max_relationships_per_entity_raises():
    config = AppConfig(knowledge_graph=KnowledgeGraphConfig(max_relationships_per_entity=0))
    with pytest.raises(ConfigError, match="max_relationships_per_entity"):
        config.validate()


# --- learning, Sprint 6.7 additions only (Learning Engine v2, Level 6 Part A) ------------
# Note: LearningConfig's pre-existing (Sprint 5.21/5.23) fields have no validation test
# coverage anywhere in this suite — a real, pre-existing gap (see item 73's own disclosure
# of this same gap for AnalyticsConfig/WellnessConfig/LearningConfig), out of this sprint's
# own scope to backfill; only the four fields this sprint actually added are covered here.


def test_default_learning_config_is_valid():
    AppConfig(learning=LearningConfig()).validate()


def test_non_positive_preferred_workflow_min_runs_raises():
    config = AppConfig(learning=LearningConfig(preferred_workflow_min_runs=0))
    with pytest.raises(ConfigError, match="preferred_workflow_min_runs"):
        config.validate()


def test_non_positive_preferred_tool_min_sessions_raises():
    config = AppConfig(learning=LearningConfig(preferred_tool_min_sessions=0))
    with pytest.raises(ConfigError, match="preferred_tool_min_sessions"):
        config.validate()


def test_non_positive_daily_routine_min_days_raises():
    config = AppConfig(learning=LearningConfig(daily_routine_min_days=0))
    with pytest.raises(ConfigError, match="daily_routine_min_days"):
        config.validate()


def test_non_positive_study_schedule_min_sessions_raises():
    config = AppConfig(learning=LearningConfig(study_schedule_min_sessions=0))
    with pytest.raises(ConfigError, match="study_schedule_min_sessions"):
        config.validate()


# --- proactive (Sprint 6.8 — Proactive Assistant, Level 6 Part A) -----------------------


def test_default_proactive_config_is_valid():
    AppConfig(proactive=ProactiveConfig()).validate()


def test_non_positive_evaluation_interval_seconds_raises():
    config = AppConfig(proactive=ProactiveConfig(evaluation_interval_seconds=0.0))
    with pytest.raises(ConfigError, match="evaluation_interval_seconds"):
        config.validate()


def test_non_positive_deadline_warning_hours_raises():
    config = AppConfig(proactive=ProactiveConfig(deadline_warning_hours=0.0))
    with pytest.raises(ConfigError, match="deadline_warning_hours"):
        config.validate()


def test_battery_critical_percent_out_of_range_raises():
    config = AppConfig(proactive=ProactiveConfig(battery_critical_percent=0.0))
    with pytest.raises(ConfigError, match="battery_critical_percent"):
        config.validate()


def test_non_positive_long_session_hours_raises():
    config = AppConfig(proactive=ProactiveConfig(long_session_hours=0.0))
    with pytest.raises(ConfigError, match="long_session_hours"):
        config.validate()


def test_missed_meal_window_start_hour_out_of_range_raises():
    config = AppConfig(proactive=ProactiveConfig(missed_meal_window_start_hour=24))
    with pytest.raises(ConfigError, match="missed_meal_window_start_hour"):
        config.validate()


def test_missed_meal_window_end_hour_out_of_range_raises():
    config = AppConfig(proactive=ProactiveConfig(missed_meal_window_end_hour=-1))
    with pytest.raises(ConfigError, match="missed_meal_window_end_hour"):
        config.validate()


def test_missed_meal_window_end_hour_before_start_hour_raises():
    config = AppConfig(
        proactive=ProactiveConfig(missed_meal_window_start_hour=14, missed_meal_window_end_hour=12)
    )
    with pytest.raises(ConfigError, match="missed_meal_window_end_hour"):
        config.validate()


def test_non_positive_project_inactivity_days_raises():
    config = AppConfig(proactive=ProactiveConfig(project_inactivity_days=0))
    with pytest.raises(ConfigError, match="project_inactivity_days"):
        config.validate()


def test_non_positive_trigger_cooldown_seconds_raises():
    config = AppConfig(proactive=ProactiveConfig(trigger_cooldown_seconds=0.0))
    with pytest.raises(ConfigError, match="trigger_cooldown_seconds"):
        config.validate()


# --- runtime (Runtime Phase 9 — Runtime Refactor Sprint) --------------------------------


def test_default_runtime_config_is_valid():
    AppConfig(runtime=RuntimeConfig()).validate()


def test_non_positive_default_idle_timeout_seconds_raises():
    config = AppConfig(runtime=RuntimeConfig(default_idle_timeout_seconds=0.0))
    with pytest.raises(ConfigError, match="default_idle_timeout_seconds"):
        config.validate()


def test_non_positive_housekeeping_interval_seconds_raises():
    config = AppConfig(runtime=RuntimeConfig(housekeeping_interval_seconds=0.0))
    with pytest.raises(ConfigError, match="housekeeping_interval_seconds"):
        config.validate()
