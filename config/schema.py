"""Typed configuration schema for JARMINEI.

Each subsystem's settings live in their own nested dataclass so schema
growth in later sprints/levels stays scoped to whichever subsystem owns it
(see docs/sprint_book/sprint_1_2.md, Potential Risks: "Schema growth").
"""

from dataclasses import dataclass, field
from pathlib import Path

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
    and microphone hardware settings (Sprint 2.1 — Microphone Manager).

    wake_phrases defaults to openWakeWord's shipped "hey_jarvis" pretrained
    model, not the product's intended "hey jarminei" phrase — the latter
    has no pretrained model and needs a custom-trained one (an offline
    ML/data-collection task, out of scope for any coding sprint). This is
    a deliberate, tracked stand-in — see backlog/technical_debt.md item 5
    and docs/sprint_book/sprint_2_2.md's Sprint Completion Report.

    jarvis_voice_id/minie_voice_id are real speaker IDs from the
    tts_models/en/vctk/vits model (ModelConfig.tts_model), user-confirmed
    by ear on 2026-07-17 (a confident-sounding voice for Jarvis, a soft/
    gentle one for Minie) — see backlog/technical_debt.md item 7 and
    docs/sprint_book/sprint_2_4.md's Sprint Completion Report. Not
    hardcoded to any other model; changing ModelConfig.tts_model would
    require picking new speaker IDs.

    session_timeout_seconds / utterance_silence_ms / utterance_silence_threshold /
    max_utterance_seconds are Sprint 2.5 (Voice Session Manager) settings —
    see docs/sprint_book/sprint_2_5.md's Engineering Decisions for how the
    utterance-boundary-detection approach (energy-based silence detection)
    was chosen; utterance_silence_threshold in particular is a starting
    point requiring real-device tuning, same caveat as wake_word_sensitivity.
    """

    wake_phrases: list[str] = field(default_factory=lambda: ["hey_jarvis"])
    jarvis_voice_id: str = "p340"
    minie_voice_id: str = "p243"
    # Sprint 2.11 — Persona Switching's Explicit Selection input (matched
    # case-insensitively as plain substrings by PersonaManager; no NLU).
    # Each list includes the bare persona name itself ("jarvis"/"minie")
    # as a short-form trigger, not just full phrases like "talk to
    # jarvis" — added 2026-07-20 at the user's explicit request.
    # minie_trigger_phrases includes "my knee"/"minnie" variants — a
    # post-release fix (backlog/technical_debt.md item 12): Whisper's
    # "base" model, even with whisper_initial_prompt's vocabulary hint,
    # isn't guaranteed to always recognize the uncommon name "Minie", and
    # real testing showed "talk to minie" transcribed as "talk to my
    # knee". This is a pragmatic safety net, not NLU — still exact
    # substring matching against known mishearings, no fuzzy logic.
    jarvis_trigger_phrases: list[str] = field(
        default_factory=lambda: ["jarvis", "talk to jarvis", "switch to jarvis"]
    )
    minie_trigger_phrases: list[str] = field(
        default_factory=lambda: [
            "minie",
            "talk to minie",
            "switch to minie",
            "talk to minnie",
            "switch to minnie",
            "talk to my knee",
            "switch to my knee",
        ]
    )
    mic_device_index: int | None = None
    mic_sample_rate_hz: int = 16000
    wake_word_sensitivity: float = 0.5
    session_timeout_seconds: float = 30.0
    utterance_silence_ms: float = 700.0
    utterance_silence_threshold: float = 0.02
    max_utterance_seconds: float = 30.0


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
    """Persistence paths (Sprint 3.1+) and policy (Sprint 2.7+).

    conversation_retention_days is Conversation Session Store's (Sprint 2.7)
    rolling-log retention window — lives here, alongside the paths, rather
    than in VoiceConfig, since persistence *policy* belongs next to
    persistence *paths* (this dataclass's existing responsibility), not
    inside the Voice Engine's own settings.
    """

    sqlite_path: str = "database/jarminei.db"
    chroma_path: str = "database/chroma"
    conversation_retention_days: int = 30


@dataclass
class MemoryConfig:
    """Memory Engine settings (Sprint 3.1+). chroma_collection_prefix
    namespaces every MemoryType's ChromaDB collection (e.g.
    "jarminei_memory_shared") so the same chroma_path (DatabaseConfig)
    could in principle host more than one prefixed set without collision.

    short_term_default_confidence (Sprint 3.4) is the starting score a
    promoted short-term memory receives — mid-range of the Dynamic Memory
    Formula's 0-29 "Temporary" band (02_System_Architecture.md), left for
    Sprint 3.5's ConfidenceScorer to recompute properly.

    short_term_salience_triggers (Sprint 3.4) is a small, deliberately
    crude keyword heuristic for "is this turn worth remembering" —
    explicitly a Sprint 3.8 (Context Analysis) replacement candidate, the
    same placeholder discipline as VoiceConfig's persona trigger phrases.

    frequency_weight/recency_weight/importance_weight/category_weight/
    emotional_weight (Sprint 3.5) are the Dynamic Memory Formula's five
    factor weights (02_System_Architecture.md) and must sum to 1.0.
    importance_weight has no term in ConfidenceScorer.score()'s normal
    formula — Importance's only real signal is the User Override Rule,
    handled as a total short-circuit (score() returns 100.0 immediately
    for user_override=True records) rather than a weighted input, exactly
    as Part 2 specifies ("immediately receives maximum confidence," not "a
    boosted score"). Kept in the weight sum anyway so the five weights
    still document what "full confidence" is built from; its practical
    effect is that a record's score can never exceed 80 (frequency_weight
    + recency_weight + category_weight + emotional_weight, all at their
    maximum) without either an explicit user override or Event Memory's
    separate is_permanent flag — see sprint_3_5.md's Engineering Decisions
    for the full reasoning.

    recency_half_life_days is the exponential decay half-life for the
    recency factor. category_importance/category_default_weight score the
    category factor; emotional_weight is applied against a fixed neutral
    placeholder value until Sprint 5.2 (Emotion Inference) exists — see
    memory/confidence_scorer.py.

    override_trigger_phrases (Sprint 3.5) triggers the User Override Rule
    — matched case-insensitively as plain substrings, no NLU, the same
    technique as VoiceConfig's persona trigger phrases.

    cleanup_grace_period_days (Sprint 3.6) protects a genuinely new
    Temporary-band record from deletion before it's had any chance to be
    reinforced — MemoryLifecycleManager.run_cleanup_pass() only deletes a
    Temporary-band record once it is both scored Temporary AND older than
    this many days (by created_at). monthly_review_min_band_days is the
    matching guard for run_monthly_review(): a record must have sat in the
    Monthly-review band (MemoryRecord.band_entered_at) this long before
    appearing in a review report.

    retrieval_similarity_weight/retrieval_confidence_weight (Sprint 3.9)
    are MemoryRetrievalEngine's blend weights for combined_rank_score —
    must sum to 1.0, same validation pattern as the five Dynamic Memory
    Formula weights above. max_retrieval_results is retrieve()'s default
    truncation bound, overridable per call.
    """

    chroma_collection_prefix: str = "jarminei_memory"
    short_term_default_confidence: float = 15.0
    short_term_salience_triggers: list[str] = field(
        default_factory=lambda: ["remind me", "don't forget", "note that", "remember that"]
    )
    frequency_weight: float = 0.25
    recency_weight: float = 0.25
    recency_half_life_days: float = 14.0
    importance_weight: float = 0.2
    category_weight: float = 0.15
    category_importance: dict[str, float] = field(
        default_factory=lambda: {"project": 0.9, "goal": 0.9, "routine": 0.6, "preference": 0.7}
    )
    category_default_weight: float = 0.5
    emotional_weight: float = 0.15
    override_trigger_phrases: list[str] = field(
        default_factory=lambda: ["remember this", "never forget this", "this is important"]
    )
    cleanup_grace_period_days: int = 7
    monthly_review_min_band_days: int = 30
    retrieval_similarity_weight: float = 0.6
    retrieval_confidence_weight: float = 0.4
    max_retrieval_results: int = 5


@dataclass
class ModelConfig:
    """AI runtime model selection (Sprint 2.3+ / 3.3+).

    whisper_no_speech_threshold (added post-Sprint-2.3, during Sprint 2.5's
    real-world verification): Whisper's own built-in no-speech skip logic
    overrides itself when a hallucinated segment's avg_logprob looks
    confident, so real ambient noise can still produce fabricated text —
    see docs/sprint_book/sprint_2_3.md's Post-Sprint Fix and
    docs/sprint_book/sprint_2_5.md's Remaining Risks. WhisperSpeechToText
    applies this threshold itself, unconditionally, rather than relying on
    Whisper's own override-prone default.

    whisper_initial_prompt (added post-release, found via real end-to-end
    testing after Level 2 shipped): Whisper's "base" model, with no
    context, misheard the uncommon proper noun "Minie" as "my knee" —
    "talk to minie" was transcribed as "talk to my knee", silently
    breaking PersonaManager.detect_explicit_selection()'s substring match.
    Passed as Whisper's own initial_prompt parameter, a standard technique
    for biasing transcription toward specific vocabulary the model
    wouldn't otherwise favor.

    ollama_model changed from "gemma3" (its original Sprint 1.2 value) to
    "llama3" during Sprint 3.14 — "gemma3" was never actually pulled on
    this project's own development machine, only "llama3:latest" was;
    every real-Ollama verification since Sprint 3.7 had to pass
    ollama_model="llama3" explicitly to work at all. Changed only after
    explicit user confirmation (the same "ask before changing a config
    default that later sprints assume" pattern as the wake-phrase and
    TTS-voice-ID defaults) once Sprint 3.14's real-model verification
    pass confirmed llama3 classifies real conversational input
    correctly. See docs/backlog/technical_debt.md item 16.
    """

    ollama_model: str = "llama3"
    ollama_host: str = "http://localhost:11434"
    ollama_timeout_seconds: float = 10.0
    whisper_model: str = "base"
    whisper_no_speech_threshold: float = 0.6
    whisper_initial_prompt: str = "Jarvis and Minie are JARMINEI's two personas."
    tts_model: str = "tts_models/en/vctk/vits"


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


def _default_allowed_file_roots() -> list[str]:
    """Computed per-machine at construction time via Path.home() —
    never hardcoded into defaults.yaml, which is checked into git and
    shared across every installation (a specific developer's
    C:\\Users\\<name>\\... path has no business being a shipped
    default). The current user's Documents/Desktop/Downloads folders —
    a real, usable default rather than an empty allowlist that would
    leave FileOperationsManager (Sprint 4.3) permanently non-functional
    out of the box."""
    home = Path.home()
    return [str(home / "Documents"), str(home / "Desktop"), str(home / "Downloads")]


@dataclass
class DeviceControlConfig:
    """Device Control Engine settings (Sprint 4.1+).

    Sprint 4.1 (Action Engine Foundation) registered this section as an
    empty placeholder. Sprint 4.2 (Application Manager) added
    application_allowlist/max_tracked_applications. Sprint 4.3 (File &
    Folder Operations) adds allowed_file_roots/use_recycle_bin_for_delete.
    Sprint 4.4 (Window Management) adds window_operation_timeout_seconds.
    Sprint 4.5 (Command Execution Engine) adds
    approved_commands/command_timeout_seconds, below. Still ahead:
    Sprint 4.6 (System Monitoring, Action-Aware)
    resource_gate_action_types — see each sprint's own Files to Modify.

    application_allowlist is present but NOT YET ENFORCED —
    security/permission_gate.py's PermissionGate.check() is still
    Sprint 4.1's own unconditional-ALLOW stub and does not consult this
    field at all. Sprint 4.7 (Permission & Confirmation System) is what
    makes it a real, enforced policy — the same "field present, policy
    arrives later" discipline this project already uses for
    AuthorityEvaluator.approved_emergency_procedures (Sprint 3.11).
    None (the default) means no allowlist restriction.

    allowed_file_roots IS enforced from Sprint 4.3 onward —
    FileOperationsManager refuses to touch any path that doesn't
    resolve inside one of these roots, structurally, with no override.
    use_recycle_bin_for_delete is present for transparency, not as a
    safe way to disable recycle-bin recovery: FileOperationsManager.delete()
    has no permanent-delete fallback — setting this False makes delete()
    refuse to run at all, loudly, rather than silently downgrading
    safety. See device_control/file_operations.py's own docstring.

    window_operation_timeout_seconds bounds every WindowManager (Sprint
    4.4) native call — a real Windows API call (SetForegroundWindow,
    MoveWindow, ShowWindow) can block on an unresponsive window's own
    message queue; this is the ceiling WindowManager waits before
    treating that call as failed rather than blocking indefinitely.

    approved_commands is a default-deny allowlist for
    CommandExecutionEngine (Sprint 4.5), matched against a command's
    executable name (basename only, case-insensitive) — never the full
    command line. Ships empty: this executor can construct and
    validate a request but can never actually run a real command until
    the list is deliberately populated, mirroring
    AuthorityEvaluator.approved_emergency_procedures's own
    "structurally unreachable by design, not an oversight" treatment
    (Sprint 3.11). Populating it for real is Sprint 4.7's job.
    command_timeout_seconds bounds every subprocess CommandExecutionEngine
    runs — a command that exceeds it is terminated and reported with
    CommandResult.timed_out=True, never left to hang the calling thread.
    """

    application_allowlist: list[str] | None = None
    max_tracked_applications: int = 50
    allowed_file_roots: list[str] = field(default_factory=_default_allowed_file_roots)
    use_recycle_bin_for_delete: bool = True
    window_operation_timeout_seconds: float = 5.0
    approved_commands: list[str] = field(default_factory=list)
    command_timeout_seconds: float = 30.0


@dataclass
class AppConfig:
    """Root configuration object. Subsystems receive their own slice via DI,
    never the whole AppConfig (see Architecture Notes in sprint_1_2.md)."""

    voice: VoiceConfig = field(default_factory=VoiceConfig)
    resources: ResourceThresholds = field(default_factory=ResourceThresholds)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    models: ModelConfig = field(default_factory=ModelConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    device_control: DeviceControlConfig = field(default_factory=DeviceControlConfig)

    def validate(self) -> None:
        """Raise ConfigError on the first invalid field found."""
        self._validate_resources()
        self._validate_voice()
        self._validate_models()
        self._validate_logging()
        self._validate_ui()
        self._validate_paths()
        self._validate_memory()
        self._validate_device_control()

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
        if self.voice.session_timeout_seconds <= 0:
            raise ConfigError(
                "voice.session_timeout_seconds must be positive, "
                f"got {self.voice.session_timeout_seconds}"
            )
        if self.voice.utterance_silence_ms <= 0:
            raise ConfigError(
                "voice.utterance_silence_ms must be positive, "
                f"got {self.voice.utterance_silence_ms}"
            )
        if not (0 < self.voice.utterance_silence_threshold <= 1):
            raise ConfigError(
                "voice.utterance_silence_threshold must be in (0, 1], "
                f"got {self.voice.utterance_silence_threshold}"
            )
        if self.voice.max_utterance_seconds <= 0:
            raise ConfigError(
                "voice.max_utterance_seconds must be positive, "
                f"got {self.voice.max_utterance_seconds}"
            )
        for field_name in ("jarvis_trigger_phrases", "minie_trigger_phrases"):
            phrases = getattr(self.voice, field_name)
            if not phrases:
                raise ConfigError(f"voice.{field_name} must not be empty")
            for phrase in phrases:
                if not phrase or not phrase.strip():
                    raise ConfigError(f"voice.{field_name} must not contain empty strings")

    def _validate_models(self) -> None:
        if not (0 < self.models.whisper_no_speech_threshold <= 1):
            raise ConfigError(
                "models.whisper_no_speech_threshold must be in (0, 1], "
                f"got {self.models.whisper_no_speech_threshold}"
            )
        if not self.models.ollama_host.strip():
            raise ConfigError("models.ollama_host must not be empty")
        if self.models.ollama_timeout_seconds <= 0:
            raise ConfigError(
                "models.ollama_timeout_seconds must be positive, "
                f"got {self.models.ollama_timeout_seconds}"
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
        if self.database.conversation_retention_days <= 0:
            raise ConfigError(
                "database.conversation_retention_days must be positive, "
                f"got {self.database.conversation_retention_days}"
            )

    def _validate_memory(self) -> None:
        if not self.memory.chroma_collection_prefix.strip():
            raise ConfigError("memory.chroma_collection_prefix must not be empty")
        if not (0 <= self.memory.short_term_default_confidence <= 100):
            raise ConfigError(
                "memory.short_term_default_confidence must be in [0, 100], "
                f"got {self.memory.short_term_default_confidence}"
            )
        if not self.memory.short_term_salience_triggers:
            raise ConfigError("memory.short_term_salience_triggers must not be empty")
        for phrase in self.memory.short_term_salience_triggers:
            if not phrase or not phrase.strip():
                raise ConfigError(
                    "memory.short_term_salience_triggers must not contain empty strings"
                )
        weights = {
            "frequency_weight": self.memory.frequency_weight,
            "recency_weight": self.memory.recency_weight,
            "importance_weight": self.memory.importance_weight,
            "category_weight": self.memory.category_weight,
            "emotional_weight": self.memory.emotional_weight,
        }
        for name, value in weights.items():
            if not (0 <= value <= 1):
                raise ConfigError(f"memory.{name} must be in [0, 1], got {value}")
        weight_sum = sum(weights.values())
        if abs(weight_sum - 1.0) > 1e-6:
            raise ConfigError(
                "memory's five Dynamic Memory Formula weights "
                "(frequency_weight, recency_weight, importance_weight, category_weight, "
                f"emotional_weight) must sum to 1.0, got {weight_sum}"
            )
        if self.memory.recency_half_life_days <= 0:
            raise ConfigError(
                "memory.recency_half_life_days must be positive, "
                f"got {self.memory.recency_half_life_days}"
            )
        if not (0 <= self.memory.category_default_weight <= 1):
            raise ConfigError(
                "memory.category_default_weight must be in [0, 1], "
                f"got {self.memory.category_default_weight}"
            )
        for category, weight in self.memory.category_importance.items():
            if not (0 <= weight <= 1):
                raise ConfigError(
                    f"memory.category_importance[{category!r}] must be in [0, 1], got {weight}"
                )
        if not self.memory.override_trigger_phrases:
            raise ConfigError("memory.override_trigger_phrases must not be empty")
        for phrase in self.memory.override_trigger_phrases:
            if not phrase or not phrase.strip():
                raise ConfigError("memory.override_trigger_phrases must not contain empty strings")
        if self.memory.cleanup_grace_period_days <= 0:
            raise ConfigError(
                "memory.cleanup_grace_period_days must be positive, "
                f"got {self.memory.cleanup_grace_period_days}"
            )
        if self.memory.monthly_review_min_band_days <= 0:
            raise ConfigError(
                "memory.monthly_review_min_band_days must be positive, "
                f"got {self.memory.monthly_review_min_band_days}"
            )
        retrieval_weights = {
            "retrieval_similarity_weight": self.memory.retrieval_similarity_weight,
            "retrieval_confidence_weight": self.memory.retrieval_confidence_weight,
        }
        for name, value in retrieval_weights.items():
            if not (0 <= value <= 1):
                raise ConfigError(f"memory.{name} must be in [0, 1], got {value}")
        retrieval_weight_sum = sum(retrieval_weights.values())
        if abs(retrieval_weight_sum - 1.0) > 1e-6:
            raise ConfigError(
                "memory's retrieval blend weights (retrieval_similarity_weight, "
                f"retrieval_confidence_weight) must sum to 1.0, got {retrieval_weight_sum}"
            )
        if self.memory.max_retrieval_results <= 0:
            raise ConfigError(
                "memory.max_retrieval_results must be positive, "
                f"got {self.memory.max_retrieval_results}"
            )

    def _validate_device_control(self) -> None:
        if self.device_control.max_tracked_applications <= 0:
            raise ConfigError(
                "device_control.max_tracked_applications must be positive, "
                f"got {self.device_control.max_tracked_applications}"
            )
        if self.device_control.application_allowlist is not None:
            for name in self.device_control.application_allowlist:
                if not name or not name.strip():
                    raise ConfigError(
                        "device_control.application_allowlist must not contain empty strings"
                    )
        if not self.device_control.allowed_file_roots:
            raise ConfigError("device_control.allowed_file_roots must not be empty")
        for root in self.device_control.allowed_file_roots:
            if not root or not root.strip():
                raise ConfigError(
                    "device_control.allowed_file_roots must not contain empty strings"
                )
        if self.device_control.window_operation_timeout_seconds <= 0:
            raise ConfigError(
                "device_control.window_operation_timeout_seconds must be positive, "
                f"got {self.device_control.window_operation_timeout_seconds}"
            )
        for name in self.device_control.approved_commands:
            if not name or not name.strip():
                raise ConfigError("device_control.approved_commands must not contain empty strings")
        if self.device_control.command_timeout_seconds <= 0:
            raise ConfigError(
                "device_control.command_timeout_seconds must be positive, "
                f"got {self.device_control.command_timeout_seconds}"
            )
