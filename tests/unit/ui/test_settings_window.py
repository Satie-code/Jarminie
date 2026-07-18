"""Unit tests for ui.settings_window."""

from unittest.mock import MagicMock

import yaml

from config.loader import ConfigLoader
from config.schema import AppConfig
from ui.settings_window import SettingsWindow


def test_load_from_config_populates_fields(qtbot):
    config = AppConfig()
    config.voice.wake_phrases = ["hey jarminei", "ok minie"]
    dialog = SettingsWindow(config, MagicMock())
    qtbot.addWidget(dialog)

    assert dialog._wake_phrases_edit.text() == "hey jarminei, ok minie"
    assert dialog._jarvis_voice_edit.text() == config.voice.jarvis_voice_id
    assert dialog._log_level_combo.currentText() == config.logging.level
    assert dialog._refresh_interval_spin.value() == config.ui.status_refresh_interval_ms


def test_to_config_round_trips_edited_values(qtbot):
    config = AppConfig()
    dialog = SettingsWindow(config, MagicMock())
    qtbot.addWidget(dialog)

    dialog._log_level_combo.setCurrentText("DEBUG")
    dialog._jarvis_voice_edit.setText("custom_jarvis")
    dialog._wake_phrases_edit.setText("hello there, hey jarminei")

    candidate = dialog.to_config()

    assert candidate.logging.level == "DEBUG"
    assert candidate.voice.jarvis_voice_id == "custom_jarvis"
    assert candidate.voice.wake_phrases == ["hello there", "hey jarminei"]


def test_to_config_preserves_fields_with_no_form_widget(qtbot):
    """Regression test for backlog/technical_debt.md item 14:
    to_config() must not silently reset a field this dialog has no widget
    for back to its dataclass default — database.conversation_retention_days,
    models.whisper_no_speech_threshold/whisper_initial_prompt/tts_model,
    voice's trigger phrases/mic/timing settings, and the entire memory
    section all have no form widgets and must survive a save unchanged."""
    config = AppConfig()
    config.database.conversation_retention_days = 90
    config.models.whisper_no_speech_threshold = 0.9
    config.models.tts_model = "some/other/model"
    config.voice.jarvis_trigger_phrases = ["yo jarvis"]
    config.voice.wake_word_sensitivity = 0.8
    config.memory.chroma_collection_prefix = "custom_prefix"
    dialog = SettingsWindow(config, MagicMock())
    qtbot.addWidget(dialog)

    candidate = dialog.to_config()

    assert candidate.database.conversation_retention_days == 90
    assert candidate.models.whisper_no_speech_threshold == 0.9
    assert candidate.models.tts_model == "some/other/model"
    assert candidate.voice.jarvis_trigger_phrases == ["yo jarvis"]
    assert candidate.voice.wake_word_sensitivity == 0.8
    assert candidate.memory.chroma_collection_prefix == "custom_prefix"


def test_ui_section_round_trips_refresh_interval(qtbot):
    config = AppConfig()
    dialog = SettingsWindow(config, MagicMock())
    qtbot.addWidget(dialog)

    dialog._refresh_interval_spin.setValue(5000)
    candidate = dialog.to_config()

    assert candidate.ui.status_refresh_interval_ms == 5000


def test_on_save_with_valid_data_calls_loader_save(qtbot):
    config = AppConfig()
    loader = MagicMock()
    dialog = SettingsWindow(config, loader)
    qtbot.addWidget(dialog)
    dialog.show()  # isVisible() reflects real state only once the dialog itself is shown

    dialog.on_save()

    loader.save.assert_called_once()
    assert not dialog._error_label.isVisible()


def test_on_save_with_invalid_data_does_not_call_save(qtbot):
    config = AppConfig()
    loader = MagicMock()
    dialog = SettingsWindow(config, loader)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._resource_fields["cpu_warning_percent"].setValue(0.0)  # invalid: must be > 0
    dialog.on_save()

    loader.save.assert_not_called()
    assert dialog._error_label.isVisible()
    assert "cpu_warning_percent" in dialog._error_label.text()


def test_on_save_shows_error_and_does_not_crash_when_save_raises_oserror(qtbot):
    """Regression test: a validated config can still fail to persist
    (permissions, full disk, missing directory) — on_save() must show an
    inline error like a validation failure, not let the OSError propagate
    and crash the dialog."""
    config = AppConfig()
    loader = MagicMock()
    loader.save.side_effect = PermissionError("Access is denied")
    dialog = SettingsWindow(config, loader)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.on_save()  # must not raise

    assert dialog._error_label.isVisible()
    assert "Access is denied" in dialog._error_label.text()


def test_valid_edit_persists_through_real_config_loader(qtbot, tmp_path):
    defaults_path = tmp_path / "defaults.yaml"
    defaults_path.write_text(yaml.safe_dump({"voice": {"wake_phrases": ["hey jarminei"]}}))
    local_path = tmp_path / "local.yaml"

    real_loader = ConfigLoader(defaults_path=defaults_path, local_path=local_path, env={})
    config = real_loader.load()

    dialog = SettingsWindow(config, real_loader)
    qtbot.addWidget(dialog)
    dialog._log_level_combo.setCurrentText("DEBUG")

    dialog.on_save()

    reloaded = ConfigLoader(defaults_path=defaults_path, local_path=local_path, env={}).load()
    assert reloaded.logging.level == "DEBUG"
