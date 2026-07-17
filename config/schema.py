"""Typed configuration schema for JARMINEI.

Each subsystem's settings live in their own nested dataclass so schema
growth in later sprints/levels stays scoped to whichever subsystem owns it
(see docs/sprint_book/sprint_1_2.md, Potential Risks: "Schema growth").
"""

from dataclasses import dataclass, field

from config.errors import ConfigError

# Single source of truth for valid log level names — used for validation
# here, and imported by ui/settings_window.py and ui/debug_console.py to
# populate their level dropdowns, rather than each keeping its own copy
# (the exact "same list duplicated in several places" bug pattern already
# hit once in Sprint 1.8's config-section handling; consolidated here
# proactively rather than letting a third copy accumulate). Lives in
# config/schema.py, not core/logging_setup.py, to avoid a circular
# import — core already depends on config, not the reverse.
VALID_LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


@dataclass
class VoiceConfig:
    """Voice Engine settings (Sprint 2.1+). Wake phrases, default voice IDs,
    and microphone hardware settings (Sprint 2.1 — Microphone Manager)."""

    wake_phrases: list[str] = field(default_factory=lambda: ["hey jarminei"])
    jarvis_voice_id: str = "jarvis_default"
    minie_voice_id: str = "minie_default"
    mic_device_index: int | None = None
    mic_sample_rate_hz: int = 16000
    wake_word_sensitivity: float = 0.5


@dataclass
class ResourceThresholds:
    """Resource Protection thresholds (Sprint 1.4+). Percentages, 0-100.

    Battery is inverted relative to the others: a *lower* percentage is worse,
    so battery_critical_percent must be lower than battery_warning_percent,
    while for cpu/ram/disk the critical threshold must be higher.
    """

    cpu_warning_percent: float = 70.0
    cpu_critical_percent: float = 90.0
    ram_warning_percent: float = 75.0
    ram_critical_percent: float = 90.0
    battery_warning_percent: float = 20.0
    battery_critical_percent: float = 10.0
    disk_warning_percent: float = 85.0
    disk_critical_percent: float = 95.0


@dataclass
class DatabaseConfig:
    """Persistence paths (Sprint 3.1+)."""

    sqlite_path: str = "database/jarminei.db"
    chroma_path: str = "database/chroma"


@dataclass
class ModelConfig:
    """AI runtime model selection (Sprint 2.3+ / 3.3+)."""

    ollama_model: str = "gemma3"
    whisper_model: str = "base"


@dataclass
class LoggingConfig:
    """Logging System settings (Sprint 1.3)."""

    level: str = "INFO"
    log_dir: str = "logs"
    max_bytes: int = 5_000_000
    backup_count: int = 3


@dataclass
class UIConfig:
    """Desktop Interface settings (Sprint 1.7+).

    status_refresh_interval_ms bounds: default 3000ms (3s) sits in the
    sprint's own "2-5 seconds" guidance; the (250, 60_000) validated range
    exists so a misconfigured value can't turn Status Panel's polling into
    a resource drain of its own (see Potential Risks in sprint_1_7.md).
    """

    status_refresh_interval_ms: int = 3000


@dataclass
class AppConfig:
    """Root configuration object. Subsystems receive their own slice via DI,
    never the whole AppConfig (see Architecture Notes in sprint_1_2.md)."""

    voice: VoiceConfig = field(default_factory=VoiceConfig)
    resources: ResourceThresholds = field(default_factory=ResourceThresholds)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    models: ModelConfig = field(default_factory=ModelConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    def validate(self) -> None:
        """Raise ConfigError on the first invalid field found."""
        self._validate_resources()
        self._validate_voice()
        self._validate_logging()
        self._validate_ui()
        self._validate_paths()

    def _validate_resources(self) -> None:
        r = self.resources
        pairs = (
            ("cpu", r.cpu_warning_percent, r.cpu_critical_percent, False),
            ("ram", r.ram_warning_percent, r.ram_critical_percent, False),
            ("disk", r.disk_warning_percent, r.disk_critical_percent, False),
            ("battery", r.battery_warning_percent, r.battery_critical_percent, True),
        )
        for name, warning, critical, inverted in pairs:
            for label, value in (("warning", warning), ("critical", critical)):
                if not (0 < value <= 100):
                    raise ConfigError(
                        f"resources.{name}_{label}_percent must be in (0, 100], got {value}"
                    )
            if inverted and critical >= warning:
                raise ConfigError(
                    f"resources.{name}_critical_percent must be lower than "
                    f"{name}_warning_percent (critical = more urgent = less battery)"
                )
            if not inverted and critical <= warning:
                raise ConfigError(
                    f"resources.{name}_critical_percent must be greater than {name}_warning_percent"
                )

    def _validate_voice(self) -> None:
        if not self.voice.wake_phrases:
            raise ConfigError("voice.wake_phrases must not be empty")
        for phrase in self.voice.wake_phrases:
            if not phrase or not phrase.strip():
                raise ConfigError("voice.wake_phrases must not contain empty strings")
        if self.voice.mic_sample_rate_hz <= 0:
            raise ConfigError(
                f"voice.mic_sample_rate_hz must be positive, got {self.voice.mic_sample_rate_hz}"
            )
        if not (0 < self.voice.wake_word_sensitivity <= 1):
            raise ConfigError(
                "voice.wake_word_sensitivity must be in (0, 1], "
                f"got {self.voice.wake_word_sensitivity}"
            )

    def _validate_logging(self) -> None:
        if self.logging.level not in VALID_LOG_LEVELS:
            raise ConfigError(
                f"logging.level must be one of {sorted(VALID_LOG_LEVELS)}, "
                f"got {self.logging.level!r}"
            )
        if self.logging.max_bytes <= 0:
            raise ConfigError("logging.max_bytes must be positive")
        if self.logging.backup_count < 0:
            raise ConfigError("logging.backup_count must be non-negative")

    def _validate_ui(self) -> None:
        interval = self.ui.status_refresh_interval_ms
        if not (250 <= interval <= 60_000):
            raise ConfigError(
                f"ui.status_refresh_interval_ms must be in [250, 60000], got {interval}"
            )

    def _validate_paths(self) -> None:
        if not self.database.sqlite_path.strip():
            raise ConfigError("database.sqlite_path must not be empty")
        if not self.database.chroma_path.strip():
            raise ConfigError("database.chroma_path must not be empty")
