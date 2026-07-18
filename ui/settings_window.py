"""Settings Window — view and edit JARMINEI's configuration.

Validation happens in AppConfig.validate() (Sprint 1.2), reused here
rather than re-implemented in the UI layer — a single source of truth for
what makes a config valid (Architecture Notes in sprint_1_8.md). Not every
AppConfig field has a form widget (e.g. VoiceConfig's trigger phrases and
timing/threshold settings, ModelConfig's Whisper tuning fields, all of
MemoryConfig) — to_config() preserves every un-widgeted field from the
config this dialog was constructed with (dataclasses.replace(), one
section at a time) rather than reconstructing each section from scratch,
so a save can never silently reset a field this dialog has no UI for back
to its dataclass default. See backlog/technical_debt.md item 14.
"""

from dataclasses import replace

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from config.errors import ConfigError
from config.loader import ConfigLoader
from config.schema import VALID_LOG_LEVELS, AppConfig
from core.logging_setup import get_logger

logger = get_logger(__name__)

_RESOURCE_FIELDS = (
    ("cpu_warning_percent", "CPU warning"),
    ("cpu_critical_percent", "CPU critical"),
    ("ram_warning_percent", "RAM warning"),
    ("ram_critical_percent", "RAM critical"),
    ("battery_warning_percent", "Battery warning"),
    ("battery_critical_percent", "Battery critical"),
    ("disk_warning_percent", "Disk warning"),
    ("disk_critical_percent", "Disk critical"),
)


class SettingsWindow(QDialog):
    """Dialog exposing every AppConfig section as an editable form.

    Saving validates the candidate config via AppConfig.validate() before
    writing anything — an invalid value never reaches ConfigLoader.save().
    Changes take effect on next launch (no live hot-reload — out of scope
    per Sprint 1.2's Future Considerations).
    """

    def __init__(self, config: AppConfig, config_loader: ConfigLoader) -> None:
        super().__init__()
        self._config_loader = config_loader
        self._original_config = config
        self.setWindowTitle("JARMINEI Settings")
        self.resize(480, 600)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: red;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()

        layout = QVBoxLayout(self)
        layout.addWidget(self._error_label)

        self._build_voice_section(layout)
        self._build_resources_section(layout)
        self._build_database_section(layout)
        self._build_models_section(layout)
        self._build_logging_section(layout)
        self._build_ui_section(layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.load_from_config(config)

    def _build_voice_section(self, parent_layout: QVBoxLayout) -> None:
        box = QGroupBox("Voice")
        form = QFormLayout(box)
        self._wake_phrases_edit = QLineEdit()
        self._jarvis_voice_edit = QLineEdit()
        self._minie_voice_edit = QLineEdit()
        form.addRow("Wake phrases (comma-separated):", self._wake_phrases_edit)
        form.addRow("Jarvis voice ID:", self._jarvis_voice_edit)
        form.addRow("Minie voice ID:", self._minie_voice_edit)
        parent_layout.addWidget(box)

    def _build_resources_section(self, parent_layout: QVBoxLayout) -> None:
        box = QGroupBox("Resource Thresholds (%)")
        form = QFormLayout(box)
        self._resource_fields: dict[str, QDoubleSpinBox] = {}
        for field_name, label in _RESOURCE_FIELDS:
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 100.0)
            spin.setDecimals(1)
            form.addRow(f"{label}:", spin)
            self._resource_fields[field_name] = spin
        parent_layout.addWidget(box)

    def _build_database_section(self, parent_layout: QVBoxLayout) -> None:
        box = QGroupBox("Database")
        form = QFormLayout(box)
        self._sqlite_path_edit = QLineEdit()
        self._chroma_path_edit = QLineEdit()
        form.addRow("SQLite path:", self._sqlite_path_edit)
        form.addRow("ChromaDB path:", self._chroma_path_edit)
        parent_layout.addWidget(box)

    def _build_models_section(self, parent_layout: QVBoxLayout) -> None:
        box = QGroupBox("Models")
        form = QFormLayout(box)
        self._ollama_model_edit = QLineEdit()
        self._whisper_model_edit = QLineEdit()
        form.addRow("Ollama model:", self._ollama_model_edit)
        form.addRow("Whisper model:", self._whisper_model_edit)
        parent_layout.addWidget(box)

    def _build_logging_section(self, parent_layout: QVBoxLayout) -> None:
        box = QGroupBox("Logging")
        form = QFormLayout(box)
        self._log_level_combo = QComboBox()
        self._log_level_combo.addItems(VALID_LOG_LEVELS)
        self._log_dir_edit = QLineEdit()
        self._max_bytes_spin = QSpinBox()
        self._max_bytes_spin.setRange(1, 1_000_000_000)
        self._backup_count_spin = QSpinBox()
        self._backup_count_spin.setRange(0, 100)
        form.addRow("Level:", self._log_level_combo)
        form.addRow("Log directory:", self._log_dir_edit)
        form.addRow("Max file size (bytes):", self._max_bytes_spin)
        form.addRow("Backup count:", self._backup_count_spin)
        parent_layout.addWidget(box)

    def _build_ui_section(self, parent_layout: QVBoxLayout) -> None:
        box = QGroupBox("Desktop Interface")
        form = QFormLayout(box)
        self._refresh_interval_spin = QSpinBox()
        self._refresh_interval_spin.setRange(250, 60_000)
        self._refresh_interval_spin.setSuffix(" ms")
        form.addRow("Status refresh interval:", self._refresh_interval_spin)
        parent_layout.addWidget(box)

    def load_from_config(self, config: AppConfig) -> None:
        """Populate every form field from `config`."""
        self._wake_phrases_edit.setText(", ".join(config.voice.wake_phrases))
        self._jarvis_voice_edit.setText(config.voice.jarvis_voice_id)
        self._minie_voice_edit.setText(config.voice.minie_voice_id)

        for field_name, spin in self._resource_fields.items():
            spin.setValue(getattr(config.resources, field_name))

        self._sqlite_path_edit.setText(config.database.sqlite_path)
        self._chroma_path_edit.setText(config.database.chroma_path)

        self._ollama_model_edit.setText(config.models.ollama_model)
        self._whisper_model_edit.setText(config.models.whisper_model)

        self._log_level_combo.setCurrentText(config.logging.level)
        self._log_dir_edit.setText(config.logging.log_dir)
        self._max_bytes_spin.setValue(config.logging.max_bytes)
        self._backup_count_spin.setValue(config.logging.backup_count)

        self._refresh_interval_spin.setValue(config.ui.status_refresh_interval_ms)

    def to_config(self) -> AppConfig:
        """Build a candidate AppConfig from current form values (not yet
        validated). Starts from self._original_config and overrides only
        the fields this dialog actually has widgets for — every other
        field (this section's own un-widgeted fields, and entire sections
        with no form at all, e.g. MemoryConfig) passes through unchanged
        rather than reverting to a dataclass default. See this module's
        own docstring and backlog/technical_debt.md item 14."""
        wake_phrases = [
            phrase.strip() for phrase in self._wake_phrases_edit.text().split(",") if phrase.strip()
        ]
        original = self._original_config
        return replace(
            original,
            voice=replace(
                original.voice,
                wake_phrases=wake_phrases,
                jarvis_voice_id=self._jarvis_voice_edit.text(),
                minie_voice_id=self._minie_voice_edit.text(),
            ),
            resources=replace(
                original.resources,
                **{name: spin.value() for name, spin in self._resource_fields.items()},
            ),
            database=replace(
                original.database,
                sqlite_path=self._sqlite_path_edit.text(),
                chroma_path=self._chroma_path_edit.text(),
            ),
            models=replace(
                original.models,
                ollama_model=self._ollama_model_edit.text(),
                whisper_model=self._whisper_model_edit.text(),
            ),
            logging=replace(
                original.logging,
                level=self._log_level_combo.currentText(),
                log_dir=self._log_dir_edit.text(),
                max_bytes=self._max_bytes_spin.value(),
                backup_count=self._backup_count_spin.value(),
            ),
            ui=replace(
                original.ui, status_refresh_interval_ms=self._refresh_interval_spin.value()
            ),
        )

    def on_save(self) -> None:
        """Validate the candidate config; save and close on success, show
        an inline error and keep the dialog open on failure."""
        candidate = self.to_config()
        try:
            candidate.validate()
        except ConfigError as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            logger.warning("Settings validation failed: %s", exc)
            return

        try:
            self._config_loader.save(candidate)
        except OSError as exc:
            # A validated config can still fail to save (permissions, full
            # disk, missing directory) — that must show the same kind of
            # inline error as a validation failure, not crash the dialog.
            self._error_label.setText(f"Could not save settings: {exc}")
            self._error_label.show()
            logger.exception("Failed to save settings")
            return

        self._error_label.hide()
        logger.info("Settings saved.")
        self.accept()
