"""Typed configuration schema for JARMINEI.

Each subsystem's settings live in their own nested dataclass so schema
growth in later sprints/levels stays scoped to whichever subsystem owns it
(see docs/sprint_book/sprint_1_2.md, Potential Risks: "Schema growth").
"""

import re
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
    category factor; emotional_weight is applied against a real, derived
    signal (MemoryRecord.emotional_significance) as of Sprint 5.3
    (Emotional Memory) — see memory/confidence_scorer.py.

    emotional_moment_recall_threshold (Sprint 5.3) is memory/
    emotional_memory.py's EmotionalMemory.recall_recent_moments()'s own
    minimum emotional_significance a record must meet to be surfaced —
    deliberately a higher bar than "any nonzero significance," so only
    genuinely notable moments (not every ordinary emotionally-neutral
    exchange) come back.

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
    emotional_moment_recall_threshold: float = 0.6


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
    approved_commands/command_timeout_seconds. Sprint 4.6 (System
    Monitoring, Action-Aware) adds resource_gate_action_types, below.

    application_allowlist IS enforced from Sprint 4.7 onward —
    security/permission_gate.py's PermissionGate.check() denies any
    LAUNCH_APPLICATION request whose executable isn't listed, before
    confirmation is even offered. None (the default) means no allowlist
    restriction.

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
    CommandExecutionEngine (Sprint 4.5) AND, from Sprint 4.7 onward,
    for PermissionGate itself (a second, earlier enforcement point —
    deliberate defense-in-depth, not redundant dead code): matched
    against a command's executable name (basename only,
    case-insensitive) — never the full command line. Ships empty: this
    executor can construct and validate a request but can never
    actually run a real command until the list is deliberately
    populated, mirroring AuthorityEvaluator.approved_emergency_procedures's
    own "structurally unreachable by design, not an oversight" treatment
    (Sprint 3.11) — still deliberately empty as of Sprint 4.7 too (see
    decision/authority.py's own docstring for why).
    command_timeout_seconds bounds every subprocess CommandExecutionEngine
    runs — a command that exceeds it is terminated and reported with
    CommandResult.timed_out=True, never left to hang the calling thread.

    resource_gate_action_types names which ActionType.value strings
    ActionResourceGate (Sprint 4.6) actually samples ResourceMonitor
    for — file and window operations are cheap enough to exempt by
    default (consistent with Sprint 4.4's own Integration Considerations
    already noting window operations don't need this gate); only
    launching an application or running a command carries genuine
    resource-consumption risk. Config-driven specifically so this list
    can be corrected without a code change if real use proves the
    default wrong.

    audit_log_retention_days bounds ActionAuditLog's (Sprint 4.8) rolling
    retention window — purge_older_than() is called for real once, at
    ActionAuditLog.start(), the same one-time-at-startup compromise
    Sprint 3.12 already established for MemoryLifecycleManager. max_retry_attempts
    bounds ActionRegistry.dispatch()'s own retry of a transient-shaped
    failure (a timeout, or a Sprint 4.6 resource-gate block) — 0 disables
    retry entirely, a valid, honest configuration, not a special-cased
    "off" flag.

    application_launch_readiness_check_seconds (Sprint 4.12 — Error
    Handling & Recovery Hardening) bounds ApplicationManager.launch()'s
    own post-spawn liveness check: a short, non-blocking-on-exit poll
    confirming the process is still running (not a real "is this app
    responsive" guarantee — no universal OS-level signal for that exists
    without a window handle, which many valid launches never create).
    A process that has already exited within this window is reported via
    TrackedApplication.readiness_confirmed=False, still ActionStatus.
    SUCCEEDED (the process DID spawn) — see device_control/
    application_manager.py's own docstring.

    allowed_url_schemes (Sprint 6.9 — Multi-Step Workflow Engine) is
    ApplicationManager.open_url()'s own explicit scheme allowlist —
    webbrowser.open() itself performs no scheme validation, so this is
    the only real safety boundary between a malformed/malicious URL and
    the OS's default handler. This sprint's own Files to Modify text
    named `WorkflowConfig` as this field's home, but ApplicationManager
    is constructed with only DeviceControlConfig (never WorkflowConfig)
    — placing it there instead is a disclosed correction, not a literal
    reading, since the alternative would require widening
    ApplicationManager's own constructor signature and rippling into
    main.py's existing, unauthorized-by-this-sprint construction call.
    Typed list[str], not tuple[str, ...] as that same sprint text
    literally wrote — every other list-shaped field in this codebase
    (approved_commands, allowed_file_roots, resource_gate_action_types,
    hard_denylist) is list[str], because YAML deserializes to a real
    list and config/loader.py performs no tuple coercion; a tuple-typed
    field would silently hold a list once loaded from defaults.yaml
    anyway, a real, disclosed inconsistency this correction avoids.
    """

    application_allowlist: list[str] | None = None
    max_tracked_applications: int = 50
    allowed_file_roots: list[str] = field(default_factory=_default_allowed_file_roots)
    use_recycle_bin_for_delete: bool = True
    window_operation_timeout_seconds: float = 5.0
    approved_commands: list[str] = field(default_factory=list)
    command_timeout_seconds: float = 30.0
    resource_gate_action_types: list[str] = field(
        default_factory=lambda: ["launch_application", "system_command"]
    )
    audit_log_retention_days: int = 90
    max_retry_attempts: int = 2
    application_launch_readiness_check_seconds: float = 0.5
    allowed_url_schemes: list[str] = field(default_factory=lambda: ["https", "http"])


_VALID_RISK_LEVEL_VALUES: frozenset[str] = frozenset({"low", "medium", "high"})


@dataclass
class SecurityConfig:
    """Security Layer settings (Sprint 4.7 — Permission & Confirmation
    System). Deliberately has no knowledge of ActionType/RiskLevel as
    real types (this module is a dependency-direction leaf — nothing in
    config/ imports device_control/ or security/) — action types and
    risk levels are both referenced here only as plain strings, matched
    against the real enums by security/policy_engine.py itself.

    risk_policies overrides security.policy_engine.PermissionPolicyEngine's
    built-in per-ActionType RiskLevel defaults, keyed by ActionType.value
    (e.g. "file_delete") -> RiskLevel.value ("low"/"medium"/"high"). An
    unrecognized ActionType key is silently ignored (never matched
    against anything); an invalid RiskLevel value is validated here at
    config-load time so a typo surfaces as a clear ConfigError rather
    than a confusing runtime KeyError deep inside PermissionPolicyEngine.

    confirmation_timeout_seconds bounds how long ConfirmationService
    waits for a reply — it controls only the wait duration; what happens
    on timeout (always DENY, never ALLOW) is a hard, non-configurable
    rule enforced in code, not something this field can weaken.

    hard_denylist names ActionType.value strings that are always DENY,
    with no confirmation ever offered — empty by default, present for
    future use (no real entry exists yet; a real one would be as
    consequential a content decision as approved_emergency_procedures
    itself and deserves the same explicit review before shipping).
    """

    risk_policies: dict[str, str] = field(default_factory=dict)
    confirmation_timeout_seconds: float = 20.0
    hard_denylist: list[str] = field(default_factory=list)


@dataclass
class WorkflowConfig:
    """Workflow Engine settings (Sprint 4.9 — Workflow Builder).

    max_steps_per_workflow is a defensive bound, not a validated
    real-world figure — Part 2's own "if many actions are about to
    execute, request confirmation" language implies workflows are meant
    to be a bounded, human-reviewable sequence, not an unbounded script.
    Config-driven so it can be corrected without a code change if real
    use proves the default wrong.

    large_workflow_step_threshold/large_workflow_confirmation_prompt_template
    (Sprint 4.10 — Workflow Executor) implement Part 2's own "large
    workflow rule": a workflow at or above this many steps, or containing
    any HIGH-risk step regardless of count, triggers one whole-workflow
    confirmation prompt before any step runs — see
    workflow/workflow_executor.py's own docstring for why this is a
    distinct question from Sprint 4.7's per-step confirmation, not a
    duplicate of it.

    max_steps_from_task_graph (Sprint 6.9 — Multi-Step Workflow Engine) is
    a defensive bound on TaskGraphWorkflowAdapter.build_workflow()'s own
    translation of TaskGraph.ready_tasks() into WorkflowSteps — mirrors
    PlanningConfig's own "bounding, not requiring" shape: a pathologically
    large TaskGraph should never silently produce an unreviewable giant
    workflow.
    """

    max_steps_per_workflow: int = 20
    large_workflow_step_threshold: int = 5
    large_workflow_confirmation_prompt_template: str = (
        "This workflow '{name}' will run {step_count} actions, including "
        "{high_risk_count} higher-risk steps. Should I proceed?"
    )
    max_steps_from_task_graph: int = 15


@dataclass
class SchedulerConfig:
    """Scheduler Engine settings (Sprint 4.14 — Calendar & Deadlines Store;
    Sprint 4.15 — Reminder Engine).

    max_lookahead_days is a defensive bound against an unbounded
    future-dated query — the same category of guard
    WorkflowConfig.max_steps_per_workflow already established, config-
    driven for the identical reason.

    poll_interval_seconds (Sprint 4.15) is how often ReminderEngine's
    background TaskScheduler job checks CalendarStore for newly-due
    items. reminder_lookahead_seconds widens that check's own query
    window into the future by this many seconds, so a reminder can be
    enqueued slightly ahead of its exact due time rather than strictly
    only once poll_interval_seconds has already elapsed past it — 0.0
    (the default) means "due now or overdue only." CommunicationPipeline
    (Sprint 4.18) also reuses poll_interval_seconds for its own
    proactive-announcement idle-check job — the two concerns (checking
    for newly-due items, checking whether it's safe to announce one)
    are close enough in spirit that a second, separate interval knob
    would be unwarranted config-surface growth for this project's own
    scale; see voice/pipeline.py's own docstring.

    maintenance_interval_seconds (Sprint 4.18) is the recurring cadence
    CommunicationPipeline registers for MemoryLifecycleManager's/
    ConversationSessionStore's/ActionAuditLog's periodic passes —
    deliberately a much longer default than poll_interval_seconds
    (background maintenance work has no reason to run as often as a
    reminder check), closing backlog/technical_debt.md items 11/15's
    still-open recurring-cadence half for real.
    """

    max_lookahead_days: int = 365
    poll_interval_seconds: float = 30.0
    reminder_lookahead_seconds: float = 0.0
    maintenance_interval_seconds: float = 3600.0


@dataclass
class InternetConfig:
    """Internet Agent settings (Sprint 4.16 — Search & Research; Sprint
    4.17 — Summarization & Source Validation; 2026-08-01 Post-Sprint
    Revision — provider-agnostic refactor).

    **The Internet Agent is provider-agnostic by design — Brave is the
    default, not a required dependency.** search_provider selects which
    SearchProvider implementation internet/search_provider_registry.py's
    create_search_provider() actually constructs; "brave" is the only
    one implemented as of this revision, but ResearchEngine/Summarizer
    both depend only on the SearchProvider Protocol
    (internet/search_provider.py), never on any concrete provider class
    — a new provider (Tavily, SerpAPI, SearXNG, or any future one)
    needs one new class plus one registry entry, nothing else in this
    codebase changes. See internet/search_provider_registry.py's own
    docstring for exactly how, and docs/sprint_book/sprint_4_16.md's
    Post-Sprint Revision section for the full reasoning behind this
    change (a direct, explicit user request).

    Deliberately NOT validated against the real provider registry here
    — config/ is a dependency-direction leaf (nothing in config/
    imports internet/ or any other subsystem package, the same
    discipline SecurityConfig.risk_policies already follows for
    ActionType/RiskLevel) — an unrecognized search_provider value
    surfaces a clear, loud UnknownSearchProviderError at construction
    time instead (search_provider_registry.py), not a silent config-
    load-time guess.

    search_api_key / search_base_url are deliberately GENERIC, not
    Brave-specific — most keyed providers (Brave, Tavily, SerpAPI) need
    only a single API key; a self-hosted provider (SearXNG) instead
    needs a base URL and typically no key at all. Both are optional,
    and it's each concrete SearchProvider implementation's own job to
    read whichever of the two (or neither) it actually needs — this
    dataclass makes no assumption about which fields a given provider
    requires. search_api_key is deliberately read from the environment
    (JARMINEI_INTERNET_SEARCH_API_KEY, matching this project's existing
    JARMINEI_<SECTION>_<FIELD> env-override convention — see
    config/loader.py's _apply_env_overrides()) rather than ever being
    committed to defaults.yaml/local.yaml — a real secret, never
    written to disk anywhere in this repo. This is the first sprint in
    this project whose whole purpose is making outbound requests to the
    public internet — see internet/search_provider.py's own docstring
    for why that's flagged as a real, deliberate boundary crossing.

    max_results_per_query/request_timeout_seconds are defensive bounds,
    the same category of guard WorkflowConfig.max_steps_per_workflow
    already established.

    summarization_model (Sprint 4.17) names which Ollama model
    Summarization should use; None (the default) means "reuse
    ModelConfig.ollama_model," the same shared-unless-overridden
    convention every other ModelConfig-adjacent field already follows.
    Purely informational to this dataclass itself — internet/
    summarizer.py's Summarizer has no way to act on it directly (its
    LanguageModelClient is already bound to a model when constructed);
    it exists to guide Sprint 4.18's own main.py wiring, which concrete
    OllamaClient to build for the Summarizer it constructs. See
    internet/summarizer.py's own docstring.

    min_sources_for_corroboration (Sprint 4.17) is an unvalidated,
    config-driven guess, same caveat class as every other tuned bound
    in this codebase — see internet/source_validator.py's own
    docstring for what corroboration actually measures.

    search_providers (Runtime Stability & Internet Layer Refactor,
    2026-08-01) is the new multi-provider fallback chain — an ORDERED
    list of provider names internet/search_provider_registry.py's
    create_search_provider_with_fallback() tries in sequence, moving to
    the next on any failure, never depending on any one provider being
    available. Additive, not a breaking change: search_provider (the
    original single-provider field) still works exactly as before for
    any caller using create_search_provider() directly; search_providers
    is a genuinely separate, higher-level field only
    create_search_provider_with_fallback() reads. An EMPTY list (not
    None — deliberately, so this project's existing generic env-override
    coercion, config/loader.py's _apply_env_overrides(), correctly
    recognizes it as list-typed; a `list[str] | None` union type does
    not) means "no fallback chain configured, use search_provider
    (single) instead" — the same fallback-to-old-behavior semantics
    `None` would have expressed, chosen instead for this one, purely
    mechanical env-override reason. Shipped default ["tavily", "searxng",
    "brave"] tries the two free/self-hostable options first, Brave last
    and optional, per this project's own explicit "no application logic
    should depend on Brave specifically" design goal.

    tavily_api_key is Tavily's own dedicated credential (env:
    JARMINEI_INTERNET_TAVILY_API_KEY, matching search_api_key's own
    established env-only-never-committed-to-disk convention exactly).
    Brave continues reading from the existing, generic search_api_key
    field (unchanged, preserving every existing Brave-only config's own
    behavior verbatim); SearXNG continues reading from the existing,
    generic search_base_url field (that field's own docstring already
    anticipated exactly this use before any SearXNG code existed). Each
    concrete SearchProvider implementation still owns the decision of
    which field(s) it actually needs — this dataclass makes no
    assumption about which provider needs what, unchanged from this
    class's own original design principle.
    """

    search_provider: str = "brave"
    search_api_key: str | None = None
    search_base_url: str | None = None
    search_providers: list[str] = field(default_factory=lambda: ["tavily", "searxng", "brave"])
    tavily_api_key: str | None = None
    max_results_per_query: int = 5
    request_timeout_seconds: float = 10.0
    summarization_model: str | None = None
    min_sources_for_corroboration: int = 2


# Valid EmotionalState (emotion/state_manager.py) dimension names and
# their ranges — duplicated here rather than imported, since config/ is a
# dependency-direction leaf (nothing in config/ imports emotion/ or any
# other subsystem package, the same discipline SecurityConfig.risk_policies
# already follows for ActionType/RiskLevel). Used only to validate
# EmotionConfig.label_state_targets below.
_EMOTIONAL_STATE_DIMENSION_RANGES: dict[str, tuple[float, float]] = {
    "mood": (-100.0, 100.0),
    "energy": (0.0, 100.0),
    "stress": (0.0, 100.0),
    "focus": (0.0, 100.0),
    "comfort": (0.0, 100.0),
    "social_energy": (0.0, 100.0),
    "conversation_momentum": (0.0, 100.0),
}


def _default_label_state_targets() -> dict[str, dict[str, float]]:
    """Per-EmotionLabel.value target VALUES (not deltas) for a subset of
    EmotionalState's six label-driven dimensions (emotion/state_manager.py
    — conversation_momentum is deliberately never driven from here, see
    that module's own docstring). A label's own dict names only the
    dimensions it meaningfully moves; every other dimension is left
    untouched for that label (mathematically equivalent to a target equal
    to whatever the dimension's current value already is). UNKNOWN has no
    entry — EmotionalStateManager.apply_estimate() treats it as a
    deliberate no-op, never reaching this table. Real, disclosed,
    unvalidated first-pass defaults — same category as
    MemoryConfig's five Dynamic Memory Formula weights."""
    return {
        "happy": {"mood": 60.0, "comfort": 70.0},
        "calm": {"stress": 20.0, "comfort": 65.0, "energy": 40.0},
        "stressed": {"stress": 85.0, "comfort": 25.0, "mood": -30.0},
        "tired": {"energy": 15.0, "focus": 30.0, "mood": -10.0},
        "excited": {"energy": 85.0, "mood": 55.0, "social_energy": 75.0},
        "frustrated": {"stress": 75.0, "mood": -45.0, "comfort": 30.0},
        "confused": {"focus": 25.0, "stress": 60.0},
        "curious": {"focus": 70.0, "energy": 60.0, "social_energy": 60.0},
        "focused": {"focus": 90.0, "energy": 55.0},
    }


def _default_lexical_markers() -> dict[str, list[str]]:
    """A deliberately crude, English-only starting vocabulary — the same
    "documented starting point, correctable via config" category as
    VoiceConfig's trigger phrases / MemoryConfig's salience triggers.
    Keyed by EmotionLabel.value (emotion/models.py); UNKNOWN has no entry
    by design (it is the fallback, never something to match toward)."""
    return {
        "happy": ["happy", "glad", "great news", "wonderful", "so good"],
        "calm": ["calm", "relaxed", "at ease", "peaceful"],
        "stressed": ["stressed", "overwhelmed", "so much pressure", "can't keep up", "anxious"],
        "tired": ["tired", "exhausted", "sleepy", "worn out", "drained"],
        "excited": ["excited", "can't wait", "thrilled", "pumped"],
        "frustrated": ["frustrated", "annoyed", "this is ridiculous", "fed up", "irritated"],
        "confused": ["confused", "not sure", "don't understand", "i'm lost", "unclear"],
        "curious": ["curious", "i wonder", "wonder if", "interested to know"],
        "focused": ["focused", "in the zone", "concentrating", "deep work"],
    }


@dataclass
class EmotionConfig:
    """Emotion Detection Engine settings (Sprint 5.1 — Level 5 Part A).

    A **behavioral-estimate engine, never a diagnostic one** — see
    emotion/models.py's own docstring for the "no medical/psychological
    diagnosis" rule this Level is built under.

    lexical_markers is a deliberately crude, config-driven keyword
    heuristic (case-insensitive substring matching, no NLU) keyed by
    EmotionLabel.value — the same honestly-acknowledged limitation
    PersonaManager.detect_context_heuristic()/MemoryConfig.
    short_term_salience_triggers already carry.

    speaking_rate_baseline_wpm/long_pause_threshold_seconds are unvalidated,
    reasonable-guess numeric baselines (same disclosed-default category as
    VoiceConfig.wake_word_sensitivity) used only as tie-breakers among
    matched lexical markers, never as an independent detector on their own
    — see emotion/detection_engine.py's _resolve_lexical_tie().

    sentiment_hint_base_confidence/lexical_marker_agreement_bonus/
    lexical_only_base_confidence/numeric_tie_break_bonus are
    EmotionDetectionEngine.estimate()'s own confidence-weighting knobs:
    SentimentHint (decision/context_analyzer.py, itself LLM-derived) is
    treated as the richer, higher-confidence primary signal;
    lexical-marker agreement with it is a bonus, never a replacement.
    When SentimentHint is NEUTRAL, matched lexical markers alone drive a
    lower base confidence, itself nudged by numeric-signal corroboration.

    min_estimate_confidence is the floor below which estimate() discounts
    a low-evidence read to EmotionLabel.UNKNOWN/0.0 rather than assert a
    guess it isn't confident in — an honest "no read" is always preferred
    over a forced one (emotion/detection_engine.py's own docstring).

    state_smoothing_alpha (Sprint 5.2) is EmotionalStateManager.
    apply_estimate()'s bounded exponential-moving-average weight
    (new = old * (1 - alpha) + target * alpha) — small by default so
    EmotionalState evolves gradually across several consistent turns,
    never snapping to one turn's own read (the brief's own explicit
    "not sentence-by-sentence" requirement).

    baseline_decay_half_life_seconds (Sprint 5.2) is
    decay_toward_baseline()'s half-life: the real elapsed time (seconds)
    after which a displaced dimension has decayed halfway back to its
    neutral midpoint. Applied once per turn using the real gap since the
    previous turn, so a long idle gap (a new session) naturally returns
    the state close to neutral without a special-cased reset.

    label_state_targets (Sprint 5.2, see _default_label_state_targets())
    are the per-EmotionLabel.value target VALUES apply_estimate() pulls
    each dimension toward — real, disclosed, unvalidated first-pass
    defaults, correctable via config without a code change.

    tone_high_stress_threshold/{jarvis,minie}_tone_low_mood_threshold/
    {jarvis,minie}_tone_low_comfort_threshold (Sprint 5.4) are
    personas/jarvis.py's/personas/minie.py's own _select_tone_variant()
    thresholds — real, disclosed, unvalidated first-pass defaults, same
    category as speaking_rate_baseline_wpm above, correctable via config
    without a code change per 03_Engineering_Standards.md's "no
    hardcoded... thresholds" rule. The stress threshold is shared (both
    personas read the same value); mood/comfort are per-persona since
    Minie's own "casual, comfort, wellness" identity leans into
    ToneVariant.ENCOURAGING more readily than Jarvis's (looser, i.e.
    less-negative/less-extreme, thresholds) — see sprint_5_4.md's own
    Engineering Rationale.
    """

    lexical_markers: dict[str, list[str]] = field(default_factory=_default_lexical_markers)
    speaking_rate_baseline_wpm: float = 150.0
    long_pause_threshold_seconds: float = 4.0
    sentiment_hint_base_confidence: float = 0.65
    lexical_marker_agreement_bonus: float = 0.2
    lexical_only_base_confidence: float = 0.45
    numeric_tie_break_bonus: float = 0.1
    min_estimate_confidence: float = 0.35
    state_smoothing_alpha: float = 0.15
    baseline_decay_half_life_seconds: float = 1800.0
    label_state_targets: dict[str, dict[str, float]] = field(
        default_factory=_default_label_state_targets
    )
    tone_high_stress_threshold: float = 70.0
    jarvis_tone_low_mood_threshold: float = -25.0
    jarvis_tone_low_comfort_threshold: float = 35.0
    minie_tone_low_mood_threshold: float = -15.0
    minie_tone_low_comfort_threshold: float = 40.0


_HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _validate_presentation_range(
    name: str, low: float, high: float, domain_low: float, domain_high: float
) -> None:
    """Shared helper for `AppConfig._validate_presentation()`'s two range
    families (0.0-1.0 for most `PresentationState` fields, 0.5-2.0 for
    animation_speed) — same "loop over named pairs" technique
    `_validate_resources()` already established for warning/critical
    pairs, factored into a real function here since it's applied to ten
    (then two) pairs rather than four."""
    if not (domain_low <= low <= domain_high):
        raise ConfigError(
            f"presentation.{name}_min must be in [{domain_low}, {domain_high}], got {low}"
        )
    if not (domain_low <= high <= domain_high):
        raise ConfigError(
            f"presentation.{name}_max must be in [{domain_low}, {domain_high}], got {high}"
        )
    if low > high:
        raise ConfigError(
            f"presentation.{name}_min ({low}) must be <= presentation.{name}_max ({high})"
        )


def _default_vtube_studio_parameter_mapping() -> dict[str, str]:
    """Sprint 5.8 — real, disclosed, unvalidated first-pass defaults; see
    PresentationConfig's own docstring for why voice_warmth's default is
    a placeholder custom-parameter name rather than a real Live2D
    standard one."""
    return {
        "smile_intensity": "ParamMouthForm",
        "eye_openness": "ParamEyeLOpen",
        "voice_warmth": "ParamGlow",
    }


def _default_minie_expression_thresholds() -> dict[str, float]:
    """Sprint 5.8 — real, disclosed, unvalidated first-pass expression
    vocabulary/thresholds; see PresentationConfig's own docstring."""
    return {
        "neutral": 0.0,
        "smile": 0.45,
        "big_smile": 0.75,
    }


def _default_workspace_profile_keywords() -> dict[str, list[str]]:
    """Sprint 5.12 — real, disclosed, unvalidated first-pass keyword
    vocabulary; keyed by `WorkspaceProfile.value`. Deliberately no
    "general" entry — GENERAL is `AdaptiveWorkspaceController.
    select_profile()`'s own safe-failure default, never something a
    keyword match resolves *into* (see that module's own docstring)."""
    return {
        "coding": ["code", "coding", "bug", "debug", "function", "repository", "compile", "script"],
        "research": ["research", "article", "source", "citation", "paper", "investigate"],
        "study": ["study", "exam", "homework", "lecture", "course", "assignment"],
        "projects": ["project", "deadline", "milestone", "roadmap", "meeting", "plan"],
    }


def _default_gesture_vocabulary() -> dict[str, list[str]]:
    """Sprint 5.9 — real, disclosed, unvalidated first-pass gesture
    vocabulary, keyed by `GestureTrigger.value` (presentation/
    gesture_engine.py). Deliberately shared across both personas —
    `GestureEngine` itself holds no persona-specific logic (that
    sprint's own Architecture Notes); each renderer's own
    trigger_gesture() decides how, or whether, a given gesture_id
    renders differently (JarvisRenderer applies one uniform accent
    pulse regardless of which id was chosen; MinieRenderer forwards
    the id verbatim to AvatarRenderer.trigger_gesture(), where it is
    matched against the user's own loaded Live2D model's real hotkeys)."""
    return {
        "notification": ["notification_glance", "notification_pulse"],
        "turn_start": ["attentive_lean", "focus_pulse"],
        "turn_end": ["settle", "soft_nod"],
        "mode_transition_to_active": ["wake_pulse", "brighten"],
        "mode_transition_to_dormant": ["dim_fade", "settle"],
        "listening_posture": ["listening_tilt", "listen_pulse"],
        "speaking_posture": ["speaking_bob", "speak_pulse"],
        "ambient_idle": ["idle_glance", "idle_blink", "head_tilt"],
    }


@dataclass
class PresentationConfig:
    """Presentation State Engine settings (Sprint 5.5 — Level 5 Part A).

    Per-persona baseline/range values `presentation/jarvis_state_computer.py`'s/
    `presentation/minie_state_computer.py`'s own `compute()` methods map an
    `EmotionalState` (5.2) reading into — real, disclosed, unvalidated
    first-pass numbers, same category as `EmotionConfig`'s own thresholds,
    correctable via config without a code change.

    Each numeric `PresentationState` field (`presentation/presentation_state.py`)
    has a `{persona}_{field}_min`/`{persona}_{field}_max` pair here, defining
    the *actual output range* that persona's computer scales into — not the
    field's own structural valid range (0.0-1.0 for smile_intensity/
    eye_openness/voice_warmth/particle_density/gesture_probability, 0.5-2.0
    for animation_speed; every min/max pair here must itself fall inside that
    structural range, enforced by `AppConfig._validate_presentation()`).

    Jarvis's own ranges are deliberately narrow and low (the brief's locked
    "Minimal. Confident... No flashy cyberpunk effects" identity) — his
    smile_intensity/particle_density ranges sit entirely below Minie's own
    minimums by construction, so "Jarvis stays observably lower than Minie"
    (this sprint's own Acceptance Criteria) holds structurally, not just
    typically. Minie's own ranges are wide (the brief's locked "Warm.
    Comforting. Expressive" identity).

    `{jarvis,minie}_lighting_color`/`{jarvis,minie}_ui_accent` are the
    brief's own locked per-persona palettes (Jarvis: electric blue/cyan;
    Minie: lavender/rose gold) as fixed `#RRGGBB` hex strings — identity,
    not mood-driven (see `presentation/presentation_state.py`'s own
    Architecture Notes reference). Exact hex values are a real, reviewable
    content choice made at this sprint's own implementation time, not
    fabricated by the spec — any reasonable value within the named color
    family is acceptable and correctable via config without a code change.

    jarvis_ring_segment_count (Sprint 5.7) is `presentation/widgets/
    segmented_ring_widget.py`'s own fixed arc-segment count for Jarvis's
    holographic ring. jarvis_animation_tick_ms is `presentation/
    jarvis_renderer.py`'s own `QTimer` interval driving both the sphere's
    breathing pulse and the ring's rotation — deliberately modest
    (~30fps) per this sprint's own Potential Risks ("smooth enough for a
    'deliberate, purposeful' animation without chasing a high frame rate
    this class of visual doesn't need"), a real, disclosed, unvalidated
    first-pass number like every other Level 5 config default so far.

    avatar_backend (Sprint 5.8) names which `AvatarRenderer`
    `presentation/avatar_renderer_registry.py`'s `create_avatar_renderer()`
    constructs — `"vtube_studio"` is the only real, registered value this
    sprint; an unrecognized value raises `UnknownAvatarBackendError` at
    construction time, never validated here (the same "known-value check
    lives at the registry, not at config validation" split
    `internet.search_provider`/`InternetConfig._validate_internet()`
    already established).

    `vtube_studio_host`/`vtube_studio_port` name the local VTube Studio
    instance's own WebSocket Plugin API endpoint (`ws://{host}:{port}`,
    VTube Studio's own documented default port `8001`) —
    `presentation/vtube_studio_renderer.py`'s `VTubeStudioAvatarRenderer`
    only ever talks to an already-running, separately-installed VTube
    Studio process the user owns and configures independently; JARMINEI
    neither embeds nor redistributes Live2D's own SDK, and does not
    itself render Minie's avatar (see that module's own docstring).
    `vtube_studio_plugin_name`/`vtube_studio_plugin_developer` identify
    this project to VTube Studio's own permission-prompt UI during the
    one-time authentication handshake. `vtube_studio_connection_timeout_seconds`
    bounds how long `mount()` waits for that handshake before degrading
    to a disconnected, no-op state rather than blocking indefinitely.

    `vtube_studio_reconnect_max_attempts` (Sprint 5.15, scenario a) bounds
    how many bounded, background reconnect attempts `VTubeStudioAvatarRenderer`
    makes across a single disconnected session before giving up and
    degrading permanently to the existing silent no-op — triggered the
    next time any of its methods is called while disconnected, rather
    than requiring a full `unmount()`/`mount()` cycle. A real
    `unmount()`/`mount()` cycle still resets the budget. A small,
    disclosed first-pass default, the same category as every other
    Level 5 tuned default.

    `vtube_studio_auth_token_path` is where the VTube-Studio-issued
    plugin authentication token (requested once, on first successful
    connect, then reused on every later run) is persisted on disk —
    deliberately a config-driven local file path, not an environment
    variable like `InternetConfig.search_api_key`, since VTube Studio's
    own protocol issues this token interactively at connect time rather
    than something a user pre-generates and supplies up front. Still a
    real secret: the default path (`config/vtube_studio_token.json`) is
    listed in `.gitignore`, never committed, matching
    `search_api_key`'s own "a real secret, never written to a shared
    file" discipline even though the storage mechanism differs.

    `vtube_studio_parameter_mapping` maps a `PresentationState` field
    name (`smile_intensity`/`eye_openness`/`voice_warmth`) to the Live2D
    model parameter name `VTubeStudioAvatarRenderer.render_state()`
    injects it into via VTube Studio's own `InjectParameterDataRequest`
    — a Live2D model's own parameter names are author-defined, never
    something JARMINEI can assume, so this is deliberately config-driven
    rather than hardcoded. The shipped defaults name VTube Studio's own
    commonly-used built-in parameters (`ParamMouthForm`, `ParamEyeLOpen`)
    for the two fields with an obvious standard-parameter equivalent;
    `voice_warmth` has no standard Live2D built-in counterpart (it is a
    JARMINEI-specific concept, not a real face shape) and defaults to a
    placeholder custom-parameter name (`ParamGlow`) that only has a
    visible effect if the user's own loaded model happens to define a
    matching custom parameter — an honest, disclosed limitation, not a
    guaranteed-to-work mapping.

    `minie_expression_thresholds` (Sprint 5.8) is `presentation/
    minie_renderer.py`'s own `_derive_expression_id()` threshold table:
    keys are `expression_id` values passed to `AvatarRenderer.
    set_expression()` (matched against whatever expressions/hotkeys the
    user's own loaded Live2D model actually defines inside VTube
    Studio), values are the minimum `(smile_intensity + voice_warmth) /
    2` "expressiveness" reading (0.0-1.0) that expression requires —
    the highest-threshold entry whose value is met wins. Must include a
    `0.0`-threshold entry as an always-reachable floor; real, disclosed,
    unvalidated first-pass defaults/vocabulary, not fabricated to match
    any specific real Live2D model (the user's own model may define a
    different expression vocabulary entirely — reconfigurable without a
    code change).

    `gesture_vocabulary`/`ambient_gesture_roll_interval_seconds`
    (Sprint 5.9) drive `presentation/gesture_engine.py`'s `GestureEngine`:
    `gesture_vocabulary` maps each `GestureTrigger.value` to a list of
    candidate `gesture_id` strings `trigger_event()` round-robins
    through (an empty or absent list is a valid, honest no-op — not a
    config error); `ambient_gesture_roll_interval_seconds` bounds how
    often `maybe_roll_ambient_gesture()` can fire, independent of
    `PresentationState.gesture_probability` itself.
    `gesture_trigger_min_interval_seconds` (Sprint 5.15, scenario f)
    applies the same interval-gate discipline to `trigger_event()`
    itself, per `GestureTrigger` value — so a bug elsewhere calling
    `trigger_event()` far more often than intended (e.g. a retry loop)
    cannot flood a renderer with gesture calls either.
    `jarvis_gesture_pulse_ticks`
    is `JarvisRenderer.trigger_gesture()`'s own accent-pulse duration on
    `SegmentedRingWidget` — added beyond this sprint's own originally-named
    config fields so that pulse's duration is config-driven rather than a
    hardcoded constant, the same `03_Engineering_Standards.md` "no
    hardcoded... thresholds" discipline `EmotionConfig`'s/Sprint 5.4's
    own tone thresholds already established. All three are real,
    disclosed, unvalidated first-pass defaults/vocabulary, the same
    category as every other Level 5 tuned default so far.

    `transition_max_duration_seconds`/`transition_particle_phase_seconds`
    (Sprint 5.10) drive `presentation/transition_engine.py`'s
    `TransitionEngine.transition()`: `transition_particle_phase_seconds`
    is how long the `PARTICLE_TRANSITION` phase is held before moving on;
    `transition_max_duration_seconds` is the whole seven-phase sequence's
    own budget, checked between phases (never preempting a phase
    mid-flight) — a budget overrun skips straight to `LOADING_TARGET`/
    `COMPLETE`, guaranteeing the renderer swap itself always eventually
    happens. Both real, disclosed, unvalidated first-pass timing guesses,
    the same category as every other Level 5 tuned default.

    `pacing_pause_marker`/`pacing_low_warmth_pause_weight`/
    `pacing_high_warmth_pause_weight` (Sprint 5.11) drive
    `presentation/voice_personality.py`'s `VoicePersonalityModulator.
    shape_pacing()`. `pacing_pause_marker` defaults to an ellipsis
    (`"..."`) — verified against the real installed `coqui-tts` (0.27.5)
    text pipeline (`TTS.tts.utils.text.cleaners`'s own default
    `_punctuations = "!'(),-.:;? "`): there is no dedicated SSML-style
    pause/silence token, only ordinary punctuation characters the model's
    own tokenizer already treats as pause-inducing (comma/period/etc. are
    literally in its supported character vocabulary, not stripped before
    synthesis) — an ellipsis is simply three such characters in a row,
    a real, working pacing technique, not a "special recognized token."
    `pacing_low_warmth_pause_weight`/`pacing_high_warmth_pause_weight`
    bound the fraction of sentence/clause boundaries `shape_pacing()`
    inserts a marker at, interpolated by `voice_warmth`.

    `lip_sync_sample_window_ms` (Sprint 5.11) is `presentation/lip_sync.py`'s
    `LipSyncDriver`'s own RMS-amplitude sampling window size. All four
    real, disclosed, unvalidated first-pass defaults, the same category
    as every other Level 5 tuned default.

    `workspace_profile_keywords`/`workspace_switch_debounce_turns`
    (Sprint 5.12) drive `presentation/adaptive_workspace.py`'s
    `AdaptiveWorkspaceController`: `workspace_profile_keywords` maps each
    `WorkspaceProfile.value` (deliberately excluding `"general"`, its own
    safe-failure default — see that module's own docstring) to a list of
    keywords `select_profile()` substring-matches against a turn's
    `primary_topic`/`mentioned_entities`; `workspace_switch_debounce_turns`
    is `should_switch()`'s own minimum consecutive-matching-turn count
    before recommending an actual dashboard rearrangement. Both real,
    disclosed, unvalidated first-pass defaults, the same category as
    every other Level 5 tuned default.

    `greeting_idle_threshold_seconds`/`celebration_significance_threshold`
    (Sprint 5.13) drive `presentation/companion_experience.py`'s
    `CompanionExperienceEngine`: below `greeting_idle_threshold_seconds`
    of session idle time, `check_for_greeting()` returns `None` (no
    special "welcome back" moment warranted); `celebration_significance_threshold`
    is a deliberately higher bar than `MemoryConfig.
    emotional_moment_recall_threshold`'s own general-recall threshold —
    `check_for_celebration()` reserves itself for genuinely standout
    moments, not merely ones significant enough to recall at all. Both
    real, disclosed, unvalidated first-pass defaults, the same category
    as every other Level 5 tuned default.
    """

    jarvis_smile_intensity_min: float = 0.0
    jarvis_smile_intensity_max: float = 0.05
    jarvis_eye_openness_min: float = 0.5
    jarvis_eye_openness_max: float = 0.7
    jarvis_voice_warmth_min: float = 0.2
    jarvis_voice_warmth_max: float = 0.4
    jarvis_animation_speed_min: float = 0.9
    jarvis_animation_speed_max: float = 1.2
    jarvis_particle_density_min: float = 0.0
    jarvis_particle_density_max: float = 0.05
    jarvis_gesture_probability_min: float = 0.05
    jarvis_gesture_probability_max: float = 0.2
    jarvis_lighting_color: str = "#0A84FF"
    jarvis_ui_accent: str = "#22D3EE"
    jarvis_ring_segment_count: int = 12
    jarvis_animation_tick_ms: int = 33

    minie_smile_intensity_min: float = 0.15
    minie_smile_intensity_max: float = 0.95
    minie_eye_openness_min: float = 0.35
    minie_eye_openness_max: float = 1.0
    minie_voice_warmth_min: float = 0.4
    minie_voice_warmth_max: float = 1.0
    minie_animation_speed_min: float = 0.6
    minie_animation_speed_max: float = 1.6
    minie_particle_density_min: float = 0.1
    minie_particle_density_max: float = 0.75
    minie_gesture_probability_min: float = 0.15
    minie_gesture_probability_max: float = 0.65
    minie_lighting_color: str = "#C8A8E9"
    minie_ui_accent: str = "#B76E79"

    avatar_backend: str = "vtube_studio"
    vtube_studio_host: str = "localhost"
    vtube_studio_port: int = 8001
    vtube_studio_plugin_name: str = "JARMINEI"
    vtube_studio_plugin_developer: str = "JARMINEI Project"
    vtube_studio_auth_token_path: str = "config/vtube_studio_token.json"
    vtube_studio_connection_timeout_seconds: float = 5.0
    vtube_studio_reconnect_max_attempts: int = 3
    vtube_studio_parameter_mapping: dict[str, str] = field(
        default_factory=_default_vtube_studio_parameter_mapping
    )
    minie_expression_thresholds: dict[str, float] = field(
        default_factory=_default_minie_expression_thresholds
    )

    gesture_vocabulary: dict[str, list[str]] = field(default_factory=_default_gesture_vocabulary)
    ambient_gesture_roll_interval_seconds: float = 15.0
    gesture_trigger_min_interval_seconds: float = 0.5
    jarvis_gesture_pulse_ticks: int = 10

    transition_max_duration_seconds: float = 2.5
    transition_particle_phase_seconds: float = 0.8

    pacing_pause_marker: str = "..."
    pacing_low_warmth_pause_weight: float = 0.3
    pacing_high_warmth_pause_weight: float = 0.7
    lip_sync_sample_window_ms: float = 50.0

    workspace_profile_keywords: dict[str, list[str]] = field(
        default_factory=_default_workspace_profile_keywords
    )
    workspace_switch_debounce_turns: int = 2

    greeting_idle_threshold_seconds: float = 3600.0
    celebration_significance_threshold: float = 0.75


@dataclass
class AnalyticsConfig:
    """Analytics Engine settings (Sprint 5.17 — Usage & Habit Tracking).

    sample_interval_seconds is how often UsageTracker's background
    TaskScheduler job samples the real foreground window/process.

    session_gap_seconds is UsageStore.list_sessions_since()'s own
    grouping bound: a gap between two same-process samples wider than
    this splits them into two sessions rather than one continuous one —
    accounts for a missed poll without falsely joining two real,
    separate sessions.

    category_map is a small, literal, config-driven process_name ->
    category lookup (e.g. {"devenv.exe": "coding"}), the same
    classification discipline PresentationConfig.workspace_profile_
    keywords/decision/authority.py's keyword tuples already established
    — empty by default, since no category has any basis without the
    user's own machine-specific application list.

    top_applications_limit (Sprint 5.20 — Analytics Dashboard Data) caps
    DailySummary.top_applications' own descending-by-time list — a real
    gap found and closed beyond this sprint's own stated Files to Modify
    field list, the same "found a necessary config gap, resolved it
    directly, disclosed it" precedent WellnessConfig.high_stress_threshold
    (Sprint 5.18)/max_postponements_before_hard_limit (Sprint 5.19)
    already established.

    habit_category_names/project_category_names (Sprint 5.20) name which
    category_map values count as a "habit" vs. a "project progress" proxy
    respectively — deliberately separate fields, since a category can be
    one without being the other. Both empty by default, the same "no
    built-in guess" discipline category_map itself already follows. Typed
    list[str], not the sprint file's own tuple[str, ...] — the identical
    mechanical reason WellnessConfig.trigger_priority_order (Sprint 5.18)
    is list[str]: config/loader.py's real YAML load path always produces
    lists, never tuples.

    habit_consistency_window_days (Sprint 5.20) is Part 2's own implicit
    weekly framing for "consistency" — also the shared default window for
    AnalyticsDashboardService.project_progress().
    """

    sample_interval_seconds: float = 60.0
    session_gap_seconds: float = 180.0
    category_map: dict[str, str] = field(default_factory=dict)
    top_applications_limit: int = 5
    habit_category_names: list[str] = field(default_factory=list)
    project_category_names: list[str] = field(default_factory=list)
    habit_consistency_window_days: int = 7


# PatternType's four values (learning/pattern_model.py), duplicated here
# as strings rather than imported — config/ is a dependency-direction
# leaf, the same discipline _WELLNESS_TRIGGER_TYPES below already
# established. Used only to validate LearningConfig.recommendation_
# templates' own keys.
_LEARNING_PATTERN_TYPES: tuple[str, ...] = (
    "preferred_time",
    "frequent_application",
    "work_habit",
    "conversation_style",
    "preferred_workflow",
    "preferred_tool",
    "daily_routine",
    "study_schedule",
)


def _default_recommendation_templates() -> dict[str, str]:
    """One {subject}-formatted template per recommendable PatternType.value
    — real, disclosed, unvalidated first-pass wording, the same content-
    quality caveat every templated-phrase config in this codebase already
    carries. A pattern type absent from this map produces no
    recommendation at all (learning/recommendation.py's own
    RecommendationEngine.generate_recommendations() never falls back to a
    raw/untemplated string — that would itself be the kind of
    unpredictable, unreviewed wording Phase 5.4's own Acceptance Criteria
    rules out)."""
    return {
        "frequent_application": (
            "You often use {subject} around this time — want me to open it for you next time?"
        ),
        "preferred_time": (
            "You're often active around {subject} — want me to keep that time free for "
            "focused work?"
        ),
        "work_habit": (
            "You're regularly active in the '{subject}' category — want tips to stay consistent?"
        ),
        "conversation_style": (
            "You seem to engage more with {subject}'s conversational style — want me to "
            "default to {subject} more often?"
        ),
        "preferred_workflow": (
            "You often run the '{subject}' workflow — want me to suggest it more proactively?"
        ),
        "preferred_tool": (
            "You often use {subject} for focused work — want me to treat it as a preferred tool?"
        ),
        "daily_routine": (
            "You seem to have a daily routine around {subject} — want me to build around it?"
        ),
        "study_schedule": (
            "You typically study or work around {subject} — want me to protect that time?"
        ),
    }


@dataclass
class LearningConfig:
    """Learning Engine settings (Sprint 5.21 — Pattern Recognition;
    extended Sprint 5.23 — Preference Learning & Recommendations).

    pattern_min_occurrences/pattern_min_days are the two-gate "gradually,
    not from one data point" thresholds every learning/pattern_recognizer.py
    detect_*() method requires before producing a LearnedPattern — the
    same category of "don't act on one data point" guard emotion/
    detection_engine.py's own confidence-bonus-only-on-agreement
    discipline already established.

    preferred_time_bucket_hours groups usage into evenly-sized hour-of-day
    windows (e.g. 2 -> 14:00-16:00) — must evenly divide 24 so every
    bucket label is clean and non-overlapping.

    lookback_days bounds how far back into UsageStore each detect_*()
    method scans — a defensive bound against an unbounded historical
    scan, the same category of guard SchedulerConfig.max_lookahead_days
    already established.

    conversation_style_min_records (Sprint 5.23) is the identical "don't
    act on one data point" gate applied to
    learning/preference_learner.py's PreferenceLearner.
    detect_conversation_style() — the combined JARVIS+MINIE memory-record
    count must clear this before a CONVERSATION_STYLE pattern is produced
    at all.

    recommendation_templates (Sprint 5.23) maps each recommendable
    PatternType.value to its own single {subject}-formatted template
    string — learning/recommendation.py's RecommendationEngine composes
    these, never an LLM call, so a recommendation's exact wording for a
    given pattern is always the same, predictable string (Phase 5.4's own
    "No unpredictable behavior" Acceptance Criterion, applied literally).

    pattern_detection_interval_seconds/recommendation_generation_interval_
    seconds (Sprint 5.24 — Companion Intelligence Integration) are the
    real, periodic TaskScheduler cadences voice/pipeline.py's
    CommunicationPipeline.start() registers for
    PatternRecognizer.run_detection_pass()/RecommendationEngine.
    generate_recommendations() — the sprint file's own Files to Modify
    left which config section owns these two fields as "a genuine, small
    implementation-time judgment call, resolved directly during
    implementation." Landed here, in LearningConfig, rather than
    SchedulerConfig or WellnessConfig — both PatternRecognizer and
    RecommendationEngine already live in learning/, mirroring
    AnalyticsConfig.sample_interval_seconds/WellnessConfig.idle_check_
    interval_seconds's own identical "each engine's own config section
    owns its own cadence" precedent, rather than growing SchedulerConfig
    into a dumping ground for every engine's own polling interval.
    Both default to a daily-scale cadence, far longer than
    SchedulerConfig.poll_interval_seconds — neither needs to run often,
    the same reasoning SchedulerConfig.maintenance_interval_seconds's own
    docstring already gives for its own much-longer-than-poll_interval_
    seconds default.

    preferred_workflow_min_runs/preferred_tool_min_sessions/
    daily_routine_min_days/study_schedule_min_sessions (Sprint 6.7 —
    Learning Engine v2, Level 6 Part A) are the four new detectors' own
    evidence thresholds, each dedicated rather than reusing
    pattern_min_occurrences directly — mirroring conversation_style_min_
    records's own precedent of a detector-specific evidence gate. All
    four detectors still additionally require pattern_min_days worth of
    distinct-day evidence (PatternRecognizer._clears_both_gates()),
    except daily_routine_min_days itself, which REPLACES pattern_min_days
    as detect_daily_routine()'s own day-count gate — deliberately a
    stricter bar (5 vs. 3 by default) than "preferred time" needs, since
    a genuine daily routine is a stronger claim than a merely-preferred
    time-of-day.
    """

    pattern_min_occurrences: int = 5
    pattern_min_days: int = 3
    preferred_time_bucket_hours: int = 2
    lookback_days: int = 30
    conversation_style_min_records: int = 10
    recommendation_templates: dict[str, str] = field(
        default_factory=_default_recommendation_templates
    )
    pattern_detection_interval_seconds: float = 86400.0
    recommendation_generation_interval_seconds: float = 86400.0
    preferred_workflow_min_runs: int = 3
    preferred_tool_min_sessions: int = 5
    daily_routine_min_days: int = 5
    study_schedule_min_sessions: int = 4


# WellnessTriggerType's five values (wellness/wellness_model.py), duplicated
# here as strings rather than imported — config/ is a dependency-direction
# leaf, the same discipline _EMOTIONAL_STATE_DIMENSION_RANGES above already
# established for emotion/state_manager.py's own dimension names. Used only
# to validate WellnessConfig.trigger_priority_order below.
_WELLNESS_TRIGGER_TYPES: tuple[str, ...] = (
    "break",
    "hydration",
    "eye_protection",
    "late_night",
    "overwork",
)


def _default_escalation_message_templates() -> dict[str, list[str]]:
    """Level-1 (gentle) / level-2 (slightly stronger) / level-3 (strong
    recommendation) phrasing per Part 2's own named escalation ladder —
    real, disclosed, unvalidated first-pass wording, the same content-
    quality caveat every templated-phrase config in this codebase already
    carries (PresentationConfig.gesture_vocabulary,
    decision/authority.py's reasoning templates)."""
    return {
        "break": [
            "You've been active for a while — consider taking a short break.",
            "It's been a while since your last break — a short one would really help.",
            "You've been going a long time without a break — please take one soon.",
        ],
        "hydration": [
            "It might be a good time to drink some water.",
            "Still worth pausing for some water when you get a moment.",
            "Please take a moment to hydrate — it's been quite a while.",
        ],
        "eye_protection": [
            "Consider looking at something 20 feet away for 20 seconds to rest your eyes.",
            "Your eyes could use a real rest — try looking away for 20 seconds.",
            "Please give your eyes a proper rest soon — this has gone on a while.",
        ],
        "overwork": [
            "You've been active for a long stretch — consider taking a longer break.",
            "This has been a long, continuous stretch of activity — a real break would help.",
            "You've been working a very long time without a real break — please stop soon.",
        ],
        "late_night": [
            "It's getting late — you might want to consider wrapping up soon.",
            "It's quite late now — winding down soon would be a good idea.",
            "It's very late — please consider stopping for the night.",
        ],
    }


@dataclass
class WellnessConfig:
    """Wellness Engine settings (Sprint 5.18 — Wellness Triggers).

    idle_check_interval_seconds is how often WellnessTracker's background
    TaskScheduler job samples real OS-level idle time
    (win32api.GetLastInputInfo()).

    inactivity_reset_seconds is the "significant inactivity" resume
    condition Part 2's Hard Limit Rule names (15 minutes by default) — an
    idle reading at or beyond this resets both _continuous_active_seconds
    and _daily_active_seconds to zero, correctly suppressing any trigger
    that would otherwise have fired (a real, disclosed simplification: this
    sprint tracks no calendar-day boundary at all, so "daily" means
    "cumulative since the last significant break," not "since local
    midnight" — no Part 2 text names calendar-day-boundary handling, and
    counters are in-memory-only regardless, see wellness_tracker.py's own
    docstring).

    break_interval_seconds/hydration_interval_seconds/
    eye_protection_interval_seconds/overwork_daily_seconds are each
    trigger's own configured threshold — real, disclosed, unvalidated
    first-pass guesses (see wellness_tracker.py's own docstring); no
    clinical or ergonomic authority backs these numbers, and none is
    claimed.

    late_night_start_hour/late_night_end_hour define a wrapping window
    (start_hour > end_hour means "wraps past midnight," e.g. 23 -> 5).

    trigger_priority_order resolves which single trigger fires when more
    than one threshold is crossed in the same tick — config-driven, not
    hardcoded, per 03_Engineering_Standards.md's own rule. Must be a
    permutation of exactly WellnessTriggerType's five values. Typed
    list[str], not the sprint file's own tuple[str, ...] — every other
    YAML-sourced ordered/collection field in this schema (search_providers,
    workspace_profile_keywords, gesture_vocabulary) is a list for the same
    mechanical reason: config/loader.py's YAML/env-override path produces
    lists, never tuples, so a tuple type hint here would silently mismatch
    the real runtime value post-load. A disclosed deviation, not an
    oversight.

    stress_sensitivity_factor is a narrow, opt-in-by-default-zero
    adjustment: when a live EmotionalState is supplied and its stress
    reads at or above high_stress_threshold, evaluate_triggers() shortens
    the effective overwork_daily_seconds/break_interval_seconds threshold
    by this bounded fraction. Default 0.0 means inert unless explicitly
    configured — a conservative, disclosed default per this sprint's own
    Architecture Notes. high_stress_threshold mirrors
    EmotionConfig.tone_high_stress_threshold's identical default (70.0) —
    the same "user is under real strain" bar, reused rather than
    reinvented, though kept as its own field since WellnessConfig has no
    access to EmotionConfig.

    max_postponements_before_hard_limit (Sprint 5.19 — Wellness
    Escalation & Hard Limit) is Part 2's own "Stop repeated reminders
    after three postponements" Hard Limit Rule, config-driven rather than
    a bare literal 3, per 03_Engineering_Standards.md's own rule.

    escalation_message_templates (Sprint 5.19) maps each
    WellnessTriggerType.value to its own 3-level (gentle/stronger/strong)
    phrasing ladder — typed dict[str, list[str]], not the sprint file's
    own dict[str, tuple[str, str, str]], for the identical mechanical
    reason trigger_priority_order above is list[str]: config/loader.py's
    real YAML load path always produces lists, never tuples. A trigger
    type absent from this map falls back to
    wellness/escalation.py's own hardcoded generic template rather than
    raising KeyError — that fallback is intentionally NOT itself a config
    field, since the sprint's own Files to Modify names only these two
    new fields.

    adaptive_min_multiplier/adaptive_max_multiplier (Sprint 5.22 —
    Adaptive Wellness) are the structural bound wellness/adaptive_wellness.
    py's AdaptiveWellnessAdjuster.compute_overrides() clamps every
    interval multiplier into before it ever reaches evaluate_triggers() —
    Part 2's own "Adjust reminders accordingly" is a bounded adjustment on
    top of the existing static threshold, never an unbounded override.
    """

    idle_check_interval_seconds: float = 60.0
    inactivity_reset_seconds: float = 900.0
    break_interval_seconds: float = 3600.0
    hydration_interval_seconds: float = 2700.0
    eye_protection_interval_seconds: float = 1200.0
    overwork_daily_seconds: float = 21600.0
    late_night_start_hour: int = 23
    late_night_end_hour: int = 5
    trigger_priority_order: list[str] = field(
        default_factory=lambda: ["break", "eye_protection", "hydration", "overwork", "late_night"]
    )
    stress_sensitivity_factor: float = 0.0
    high_stress_threshold: float = 70.0
    max_postponements_before_hard_limit: int = 3
    escalation_message_templates: dict[str, list[str]] = field(
        default_factory=_default_escalation_message_templates
    )
    adaptive_min_multiplier: float = 0.75
    adaptive_max_multiplier: float = 1.5


@dataclass
class PlanningConfig:
    """Planning Engine settings (Sprint 6.1 — Planning Engine, Level 6
    Part A: Autonomous Intelligence & Cognitive Architecture).

    max_milestones_per_goal/max_tasks_per_milestone are defensive upper
    bounds on PlanningEngine.decompose_goal()'s own LLM output, not
    product requirements — a decomposition that returns more is
    truncated (logged once, not per-item) rather than silently accepted
    or treated as an error, the same "defensive bound enforced at the
    parse boundary" discipline WellnessConfig.max_postponements_before_
    hard_limit/AnalyticsConfig.top_applications_limit already establish
    for their own respective LLM/data-driven surfaces.

    decomposition_timeout_seconds is this class's own dedicated per-call
    timeout, deliberately longer than ModelConfig.ollama_timeout_seconds'
    own 10.0s default — goal decomposition is a larger, more open-ended
    generation (potentially several milestones, each with several tasks)
    than Intent Detection/Context Analysis's short, fixed-line-count
    answers, the same "a longer generation needs a longer timeout"
    reasoning internet/summarizer.py's own Summarizer already applied
    for research summarization.

    max_task_dependencies (Sprint 6.2 — Task Graph) is a defensive upper
    bound on incoming TaskEdges per task — how many prerequisites a
    single Task may have — preventing a pathological or LLM-hallucinated
    dependency explosion from ever being accepted by
    TaskGraph.add_dependency(), the same "defensive bound enforced at
    the write boundary" discipline max_milestones_per_goal/
    max_tasks_per_milestone above already establish.
    """

    max_milestones_per_goal: int = 5
    max_tasks_per_milestone: int = 8
    decomposition_timeout_seconds: float = 45.0
    max_task_dependencies: int = 20


@dataclass
class ContextEngineConfig:
    """Context Engine settings (Sprint 6.3 — Context Engine, Level 6
    Part A).

    memory_lookback_count mirrors ContextManager's own recent_turn_window
    shape (Sprint 2.8) — how many recent MemoryRecords ContextEngine.
    build() includes, passed straight through to MemoryStore.recent()'s
    own existing limit parameter.

    usage_lookback_hours/calendar_lookahead_hours bound how far back
    "current apps" and how far ahead "upcoming" respectively reach —
    real, disclosed, unvalidated first-pass windows, the same tuned-
    constant caveat every comparable default in this codebase carries.
    """

    memory_lookback_count: int = 10
    usage_lookback_hours: float = 4.0
    calendar_lookahead_hours: float = 24.0


@dataclass
class ReasoningConfig:
    """Reasoning Engine settings (Sprint 6.4 — Reasoning Engine, Level 6
    Part A).

    max_alternatives is a defensive upper bound on ReasoningEngine.
    alternatives()'s own LLM output, not a product requirement — the
    same "defensive bound enforced at the parse boundary" discipline
    PlanningConfig.max_milestones_per_goal/ContextEngineConfig's own
    lookback fields already establish for their respective LLM/data-
    driven surfaces.

    reasoning_timeout_seconds is this class's own dedicated per-call
    timeout, deliberately longer than ModelConfig.ollama_timeout_seconds'
    own 10.0s default, mirroring PlanningConfig.decomposition_timeout_
    seconds' identical "a longer, more open-ended generation needs a
    longer timeout" reasoning.
    """

    max_alternatives: int = 3
    reasoning_timeout_seconds: float = 30.0


@dataclass
class DecisionEngineConfig:
    """Decision Engine v2 settings (Sprint 6.5 — Decision Engine v2,
    Level 6 Part A).

    risk_weight/confidence_weight/priority_weight are DecisionEngineV2.
    rank_actions()'s own composite-score blend weights and must sum to
    1.0 — the same validation pattern MemoryConfig's five Dynamic Memory
    Formula weights (Sprint 3.5) and its retrieval_similarity_weight/
    retrieval_confidence_weight pair (Sprint 3.9) already establish. This
    sprint's own text cited EmotionConfig as the precedent instead, but
    EmotionConfig has no weight-sum validation anywhere in this
    codebase — a disclosed correction, following the real, existing
    pattern rather than the sprint file's own inaccurate citation.

    Real, disclosed, unvalidated first-pass defaults — a candidate for
    adjustment once Sprint 6.15's real-usage verification pass observes
    actual ranking behavior, per this sprint's own Potential Risks.
    """

    risk_weight: float = 0.4
    confidence_weight: float = 0.35
    priority_weight: float = 0.25


@dataclass
class KnowledgeGraphConfig:
    """Knowledge Graph settings (Sprint 6.6 — Knowledge Graph, Level 6
    Part A).

    max_traversal_depth is a defensive upper bound on KnowledgeGraphStore.
    related_entities()'s own breadth-first traversal, not a product
    requirement — a caller requesting a deeper walk is silently clamped,
    never rejected, the same "defensive bound enforced at the read
    boundary" discipline PlanningConfig.max_task_dependencies established
    at the write boundary. An unbounded graph walk over user-authored
    data is a real, if unlikely, performance/DoS-shaped risk even purely
    locally.

    max_relationships_per_entity bounds how many relationship rows may
    touch a single entity (as either endpoint) before
    KnowledgeGraphStore.add_relationship() raises TooManyRelationshipsError
    — see that method's own docstring for why both endpoints are checked.
    """

    max_traversal_depth: int = 3
    max_relationships_per_entity: int = 50


@dataclass
class ProactiveConfig:
    """Proactive Assistant settings (Sprint 6.8 — Proactive Assistant,
    Level 6 Part A).

    evaluation_interval_seconds is deliberately coarser than Wellness's
    own idle_check_interval_seconds — proactive triggers are, by design,
    lower-frequency/higher-deliberation than wellness prompts.

    missed_meal_window_start_hour/missed_meal_window_end_hour bound a
    single, configurable lunch window — a dinner-window pair is a
    plausible future addition, not built without a named second window
    in this brief.

    trigger_cooldown_seconds is the shared per-ProactiveTriggerType
    dedup window — a fired trigger will not re-fire for this long,
    regardless of whether its own condition is still true.

    All defaults are real, disclosed, unvalidated first-pass guesses —
    the same tuned-constant caveat every comparable default in this
    codebase carries.
    """

    evaluation_interval_seconds: float = 300.0
    deadline_warning_hours: float = 24.0
    battery_critical_percent: float = 15.0
    long_session_hours: float = 3.0
    missed_meal_window_start_hour: int = 12
    missed_meal_window_end_hour: int = 14
    project_inactivity_days: int = 7
    trigger_cooldown_seconds: float = 3600.0


@dataclass
class RuntimeConfig:
    """Runtime Manager settings (Runtime Phase 9 — Runtime Refactor
    Sprint). Governs idle-timeout eviction for the currently-lazy
    subsystems (speech_to_text/text_to_speech/memory_store — see
    core/runtime_manager.py's own RuntimeManager.register() docstring)
    and how often CommunicationPipeline's own new housekeeping
    TaskScheduler job sweeps for both idle-timeout and resource-pressure
    eviction.

    default_idle_timeout_seconds is applied uniformly to every lazy=True
    registration in main.py — a single shared value, not per-service,
    since nothing in this first pass distinguishes "Whisper should stay
    warm longer than MemoryStore" from a real, measured need; revisit
    only if a real per-service tuning requirement is ever observed (the
    same "don't design for a hypothetical" discipline this whole
    refactor's own governing principles already establish).
    """

    default_idle_timeout_seconds: float = 300.0
    housekeeping_interval_seconds: float = 60.0


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
    security: SecurityConfig = field(default_factory=SecurityConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    internet: InternetConfig = field(default_factory=InternetConfig)
    emotion: EmotionConfig = field(default_factory=EmotionConfig)
    presentation: PresentationConfig = field(default_factory=PresentationConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    wellness: WellnessConfig = field(default_factory=WellnessConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)
    planning: PlanningConfig = field(default_factory=PlanningConfig)
    context_engine: ContextEngineConfig = field(default_factory=ContextEngineConfig)
    reasoning: ReasoningConfig = field(default_factory=ReasoningConfig)
    decision_engine_v2: DecisionEngineConfig = field(default_factory=DecisionEngineConfig)
    knowledge_graph: KnowledgeGraphConfig = field(default_factory=KnowledgeGraphConfig)
    proactive: ProactiveConfig = field(default_factory=ProactiveConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)

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
        self._validate_security()
        self._validate_workflow()
        self._validate_scheduler()
        self._validate_internet()
        self._validate_emotion()
        self._validate_presentation()
        self._validate_analytics()
        self._validate_wellness()
        self._validate_learning()
        self._validate_planning()
        self._validate_context_engine()
        self._validate_reasoning()
        self._validate_decision_engine_v2()
        self._validate_knowledge_graph()
        self._validate_proactive()
        self._validate_runtime()

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
        if not (0 <= self.memory.emotional_moment_recall_threshold <= 1):
            raise ConfigError(
                "memory.emotional_moment_recall_threshold must be in [0, 1], "
                f"got {self.memory.emotional_moment_recall_threshold}"
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
        for action_type_value in self.device_control.resource_gate_action_types:
            if not action_type_value or not action_type_value.strip():
                raise ConfigError(
                    "device_control.resource_gate_action_types must not contain empty strings"
                )
        if self.device_control.audit_log_retention_days <= 0:
            raise ConfigError(
                "device_control.audit_log_retention_days must be positive, "
                f"got {self.device_control.audit_log_retention_days}"
            )
        if self.device_control.max_retry_attempts < 0:
            raise ConfigError(
                "device_control.max_retry_attempts must not be negative, "
                f"got {self.device_control.max_retry_attempts}"
            )
        if self.device_control.application_launch_readiness_check_seconds <= 0:
            raise ConfigError(
                "device_control.application_launch_readiness_check_seconds must be positive, "
                f"got {self.device_control.application_launch_readiness_check_seconds}"
            )
        if not self.device_control.allowed_url_schemes:
            raise ConfigError("device_control.allowed_url_schemes must not be empty")
        for scheme in self.device_control.allowed_url_schemes:
            if not scheme or not scheme.strip():
                raise ConfigError(
                    "device_control.allowed_url_schemes must not contain empty strings"
                )

    def _validate_security(self) -> None:
        for action_type_key, risk_level_value in self.security.risk_policies.items():
            if not action_type_key or not action_type_key.strip():
                raise ConfigError("security.risk_policies must not contain empty-string keys")
            if risk_level_value not in _VALID_RISK_LEVEL_VALUES:
                raise ConfigError(
                    f"security.risk_policies[{action_type_key!r}] must be one of "
                    f"{sorted(_VALID_RISK_LEVEL_VALUES)}, got {risk_level_value!r}"
                )
        if self.security.confirmation_timeout_seconds <= 0:
            raise ConfigError(
                "security.confirmation_timeout_seconds must be positive, "
                f"got {self.security.confirmation_timeout_seconds}"
            )
        for action_type_value in self.security.hard_denylist:
            if not action_type_value or not action_type_value.strip():
                raise ConfigError("security.hard_denylist must not contain empty strings")

    def _validate_workflow(self) -> None:
        if self.workflow.max_steps_per_workflow <= 0:
            raise ConfigError(
                "workflow.max_steps_per_workflow must be positive, "
                f"got {self.workflow.max_steps_per_workflow}"
            )
        if self.workflow.large_workflow_step_threshold <= 0:
            raise ConfigError(
                "workflow.large_workflow_step_threshold must be positive, "
                f"got {self.workflow.large_workflow_step_threshold}"
            )
        if not self.workflow.large_workflow_confirmation_prompt_template.strip():
            raise ConfigError(
                "workflow.large_workflow_confirmation_prompt_template must not be blank"
            )
        if self.workflow.max_steps_from_task_graph <= 0:
            raise ConfigError(
                "workflow.max_steps_from_task_graph must be positive, "
                f"got {self.workflow.max_steps_from_task_graph}"
            )

    def _validate_scheduler(self) -> None:
        if self.scheduler.max_lookahead_days <= 0:
            raise ConfigError(
                "scheduler.max_lookahead_days must be positive, "
                f"got {self.scheduler.max_lookahead_days}"
            )
        if self.scheduler.poll_interval_seconds <= 0:
            raise ConfigError(
                "scheduler.poll_interval_seconds must be positive, "
                f"got {self.scheduler.poll_interval_seconds}"
            )
        if self.scheduler.reminder_lookahead_seconds < 0:
            raise ConfigError(
                "scheduler.reminder_lookahead_seconds must not be negative, "
                f"got {self.scheduler.reminder_lookahead_seconds}"
            )
        if self.scheduler.maintenance_interval_seconds <= 0:
            raise ConfigError(
                "scheduler.maintenance_interval_seconds must be positive, "
                f"got {self.scheduler.maintenance_interval_seconds}"
            )

    def _validate_internet(self) -> None:
        if not self.internet.search_provider.strip():
            raise ConfigError("internet.search_provider must not be blank")
        if self.internet.max_results_per_query <= 0:
            raise ConfigError(
                "internet.max_results_per_query must be positive, "
                f"got {self.internet.max_results_per_query}"
            )
        if self.internet.request_timeout_seconds <= 0:
            raise ConfigError(
                "internet.request_timeout_seconds must be positive, "
                f"got {self.internet.request_timeout_seconds}"
            )
        if self.internet.min_sources_for_corroboration <= 0:
            raise ConfigError(
                "internet.min_sources_for_corroboration must be positive, "
                f"got {self.internet.min_sources_for_corroboration}"
            )

    def _validate_emotion(self) -> None:
        for label, keywords in self.emotion.lexical_markers.items():
            if not label or not label.strip():
                raise ConfigError("emotion.lexical_markers must not contain empty-string keys")
            for keyword in keywords:
                if not keyword or not keyword.strip():
                    raise ConfigError(
                        f"emotion.lexical_markers[{label!r}] must not contain empty strings"
                    )
        if self.emotion.speaking_rate_baseline_wpm <= 0:
            raise ConfigError(
                "emotion.speaking_rate_baseline_wpm must be positive, "
                f"got {self.emotion.speaking_rate_baseline_wpm}"
            )
        if self.emotion.long_pause_threshold_seconds <= 0:
            raise ConfigError(
                "emotion.long_pause_threshold_seconds must be positive, "
                f"got {self.emotion.long_pause_threshold_seconds}"
            )
        confidence_fields = {
            "sentiment_hint_base_confidence": self.emotion.sentiment_hint_base_confidence,
            "lexical_marker_agreement_bonus": self.emotion.lexical_marker_agreement_bonus,
            "lexical_only_base_confidence": self.emotion.lexical_only_base_confidence,
            "numeric_tie_break_bonus": self.emotion.numeric_tie_break_bonus,
            "min_estimate_confidence": self.emotion.min_estimate_confidence,
        }
        for name, value in confidence_fields.items():
            if not (0 <= value <= 1):
                raise ConfigError(f"emotion.{name} must be in [0, 1], got {value}")
        if not (0 < self.emotion.state_smoothing_alpha <= 1):
            raise ConfigError(
                "emotion.state_smoothing_alpha must be in (0, 1], "
                f"got {self.emotion.state_smoothing_alpha}"
            )
        if self.emotion.baseline_decay_half_life_seconds <= 0:
            raise ConfigError(
                "emotion.baseline_decay_half_life_seconds must be positive, "
                f"got {self.emotion.baseline_decay_half_life_seconds}"
            )
        for label, targets in self.emotion.label_state_targets.items():
            if not label or not label.strip():
                raise ConfigError("emotion.label_state_targets must not contain empty-string keys")
            for dimension, target in targets.items():
                if dimension not in _EMOTIONAL_STATE_DIMENSION_RANGES:
                    raise ConfigError(
                        f"emotion.label_state_targets[{label!r}] names unknown dimension "
                        f"{dimension!r}, must be one of {sorted(_EMOTIONAL_STATE_DIMENSION_RANGES)}"
                    )
                low, high = _EMOTIONAL_STATE_DIMENSION_RANGES[dimension]
                if not (low <= target <= high):
                    raise ConfigError(
                        f"emotion.label_state_targets[{label!r}][{dimension!r}] must be in "
                        f"[{low}, {high}], got {target}"
                    )
        stress_low, stress_high = _EMOTIONAL_STATE_DIMENSION_RANGES["stress"]
        if not (stress_low <= self.emotion.tone_high_stress_threshold <= stress_high):
            raise ConfigError(
                "emotion.tone_high_stress_threshold must be in "
                f"[{stress_low}, {stress_high}], got {self.emotion.tone_high_stress_threshold}"
            )
        mood_low, mood_high = _EMOTIONAL_STATE_DIMENSION_RANGES["mood"]
        for name, value in (
            ("jarvis_tone_low_mood_threshold", self.emotion.jarvis_tone_low_mood_threshold),
            ("minie_tone_low_mood_threshold", self.emotion.minie_tone_low_mood_threshold),
        ):
            if not (mood_low <= value <= mood_high):
                raise ConfigError(
                    f"emotion.{name} must be in [{mood_low}, {mood_high}], got {value}"
                )
        comfort_low, comfort_high = _EMOTIONAL_STATE_DIMENSION_RANGES["comfort"]
        for name, value in (
            ("jarvis_tone_low_comfort_threshold", self.emotion.jarvis_tone_low_comfort_threshold),
            ("minie_tone_low_comfort_threshold", self.emotion.minie_tone_low_comfort_threshold),
        ):
            if not (comfort_low <= value <= comfort_high):
                raise ConfigError(
                    f"emotion.{name} must be in [{comfort_low}, {comfort_high}], got {value}"
                )

    def _validate_presentation(self) -> None:
        p = self.presentation
        unit_range_fields = (
            ("jarvis_smile_intensity", p.jarvis_smile_intensity_min, p.jarvis_smile_intensity_max),
            ("jarvis_eye_openness", p.jarvis_eye_openness_min, p.jarvis_eye_openness_max),
            ("jarvis_voice_warmth", p.jarvis_voice_warmth_min, p.jarvis_voice_warmth_max),
            (
                "jarvis_particle_density",
                p.jarvis_particle_density_min,
                p.jarvis_particle_density_max,
            ),
            (
                "jarvis_gesture_probability",
                p.jarvis_gesture_probability_min,
                p.jarvis_gesture_probability_max,
            ),
            ("minie_smile_intensity", p.minie_smile_intensity_min, p.minie_smile_intensity_max),
            ("minie_eye_openness", p.minie_eye_openness_min, p.minie_eye_openness_max),
            ("minie_voice_warmth", p.minie_voice_warmth_min, p.minie_voice_warmth_max),
            (
                "minie_particle_density",
                p.minie_particle_density_min,
                p.minie_particle_density_max,
            ),
            (
                "minie_gesture_probability",
                p.minie_gesture_probability_min,
                p.minie_gesture_probability_max,
            ),
        )
        for name, low, high in unit_range_fields:
            _validate_presentation_range(name, low, high, 0.0, 1.0)

        speed_range_fields = (
            ("jarvis_animation_speed", p.jarvis_animation_speed_min, p.jarvis_animation_speed_max),
            ("minie_animation_speed", p.minie_animation_speed_min, p.minie_animation_speed_max),
        )
        for name, low, high in speed_range_fields:
            _validate_presentation_range(name, low, high, 0.5, 2.0)

        for name, value in (
            ("jarvis_lighting_color", p.jarvis_lighting_color),
            ("jarvis_ui_accent", p.jarvis_ui_accent),
            ("minie_lighting_color", p.minie_lighting_color),
            ("minie_ui_accent", p.minie_ui_accent),
        ):
            if not _HEX_COLOR_PATTERN.match(value):
                raise ConfigError(
                    f"presentation.{name} must be a #RRGGBB hex color string, got {value!r}"
                )

        if p.jarvis_ring_segment_count < 3:
            raise ConfigError(
                "presentation.jarvis_ring_segment_count must be at least 3, got "
                f"{p.jarvis_ring_segment_count}"
            )
        if p.jarvis_animation_tick_ms <= 0:
            raise ConfigError(
                "presentation.jarvis_animation_tick_ms must be positive, got "
                f"{p.jarvis_animation_tick_ms}"
            )

        if not p.avatar_backend.strip():
            raise ConfigError("presentation.avatar_backend must not be blank")
        if not p.vtube_studio_host.strip():
            raise ConfigError("presentation.vtube_studio_host must not be blank")
        if not (0 < p.vtube_studio_port <= 65535):
            raise ConfigError(
                f"presentation.vtube_studio_port must be in (0, 65535], got {p.vtube_studio_port}"
            )
        if not p.vtube_studio_plugin_name.strip():
            raise ConfigError("presentation.vtube_studio_plugin_name must not be blank")
        if not p.vtube_studio_plugin_developer.strip():
            raise ConfigError("presentation.vtube_studio_plugin_developer must not be blank")
        if not p.vtube_studio_auth_token_path.strip():
            raise ConfigError("presentation.vtube_studio_auth_token_path must not be blank")
        if p.vtube_studio_connection_timeout_seconds <= 0:
            raise ConfigError(
                "presentation.vtube_studio_connection_timeout_seconds must be positive, got "
                f"{p.vtube_studio_connection_timeout_seconds}"
            )
        if p.vtube_studio_reconnect_max_attempts <= 0:
            raise ConfigError(
                "presentation.vtube_studio_reconnect_max_attempts must be positive, got "
                f"{p.vtube_studio_reconnect_max_attempts}"
            )
        for state_field, parameter_name in p.vtube_studio_parameter_mapping.items():
            if not state_field.strip():
                raise ConfigError(
                    "presentation.vtube_studio_parameter_mapping must not contain "
                    "empty-string keys"
                )
            if not parameter_name.strip():
                raise ConfigError(
                    f"presentation.vtube_studio_parameter_mapping[{state_field!r}] must not "
                    "be blank"
                )

        if not p.minie_expression_thresholds:
            raise ConfigError("presentation.minie_expression_thresholds must not be empty")
        if 0.0 not in p.minie_expression_thresholds.values():
            raise ConfigError(
                "presentation.minie_expression_thresholds must include a 0.0-threshold entry "
                "as an always-reachable floor"
            )

        for trigger_name, candidates in p.gesture_vocabulary.items():
            if not trigger_name.strip():
                raise ConfigError(
                    "presentation.gesture_vocabulary must not contain empty-string keys"
                )
            for gesture_id in candidates:
                if not gesture_id or not gesture_id.strip():
                    raise ConfigError(
                        f"presentation.gesture_vocabulary[{trigger_name!r}] must not contain "
                        "empty-string gesture ids"
                    )
        if p.ambient_gesture_roll_interval_seconds <= 0:
            raise ConfigError(
                "presentation.ambient_gesture_roll_interval_seconds must be positive, got "
                f"{p.ambient_gesture_roll_interval_seconds}"
            )
        if p.gesture_trigger_min_interval_seconds <= 0:
            raise ConfigError(
                "presentation.gesture_trigger_min_interval_seconds must be positive, got "
                f"{p.gesture_trigger_min_interval_seconds}"
            )
        if p.jarvis_gesture_pulse_ticks <= 0:
            raise ConfigError(
                "presentation.jarvis_gesture_pulse_ticks must be positive, got "
                f"{p.jarvis_gesture_pulse_ticks}"
            )
        if p.transition_max_duration_seconds <= 0:
            raise ConfigError(
                "presentation.transition_max_duration_seconds must be positive, got "
                f"{p.transition_max_duration_seconds}"
            )
        if p.transition_particle_phase_seconds <= 0:
            raise ConfigError(
                "presentation.transition_particle_phase_seconds must be positive, got "
                f"{p.transition_particle_phase_seconds}"
            )
        if p.transition_particle_phase_seconds > p.transition_max_duration_seconds:
            raise ConfigError(
                "presentation.transition_particle_phase_seconds "
                f"({p.transition_particle_phase_seconds}) must be <= "
                f"transition_max_duration_seconds ({p.transition_max_duration_seconds})"
            )

        if not p.pacing_pause_marker:
            raise ConfigError("presentation.pacing_pause_marker must not be blank")
        for name, value in (
            ("pacing_low_warmth_pause_weight", p.pacing_low_warmth_pause_weight),
            ("pacing_high_warmth_pause_weight", p.pacing_high_warmth_pause_weight),
        ):
            if not (0.0 <= value <= 1.0):
                raise ConfigError(f"presentation.{name} must be in [0.0, 1.0], got {value}")
        if p.pacing_low_warmth_pause_weight > p.pacing_high_warmth_pause_weight:
            raise ConfigError(
                "presentation.pacing_low_warmth_pause_weight "
                f"({p.pacing_low_warmth_pause_weight}) must be <= "
                f"pacing_high_warmth_pause_weight ({p.pacing_high_warmth_pause_weight})"
            )
        if p.lip_sync_sample_window_ms <= 0:
            raise ConfigError(
                "presentation.lip_sync_sample_window_ms must be positive, got "
                f"{p.lip_sync_sample_window_ms}"
            )

        for profile_name, keywords in p.workspace_profile_keywords.items():
            if not profile_name.strip():
                raise ConfigError(
                    "presentation.workspace_profile_keywords must not contain "
                    "empty-string keys"
                )
            for keyword in keywords:
                if not keyword or not keyword.strip():
                    raise ConfigError(
                        f"presentation.workspace_profile_keywords[{profile_name!r}] must not "
                        "contain empty-string keywords"
                    )
        if p.workspace_switch_debounce_turns <= 0:
            raise ConfigError(
                "presentation.workspace_switch_debounce_turns must be positive, got "
                f"{p.workspace_switch_debounce_turns}"
            )

        if p.greeting_idle_threshold_seconds <= 0:
            raise ConfigError(
                "presentation.greeting_idle_threshold_seconds must be positive, got "
                f"{p.greeting_idle_threshold_seconds}"
            )
        if not (0.0 <= p.celebration_significance_threshold <= 1.0):
            raise ConfigError(
                "presentation.celebration_significance_threshold must be in [0.0, 1.0], got "
                f"{p.celebration_significance_threshold}"
            )
        for expression_id, threshold in p.minie_expression_thresholds.items():
            if not expression_id.strip():
                raise ConfigError(
                    "presentation.minie_expression_thresholds must not contain "
                    "empty-string keys"
                )
            if not (0.0 <= threshold <= 1.0):
                raise ConfigError(
                    f"presentation.minie_expression_thresholds[{expression_id!r}] must be in "
                    f"[0.0, 1.0], got {threshold}"
                )

    def _validate_analytics(self) -> None:
        if self.analytics.sample_interval_seconds <= 0:
            raise ConfigError(
                "analytics.sample_interval_seconds must be positive, "
                f"got {self.analytics.sample_interval_seconds}"
            )
        if self.analytics.session_gap_seconds <= 0:
            raise ConfigError(
                "analytics.session_gap_seconds must be positive, "
                f"got {self.analytics.session_gap_seconds}"
            )
        for process_name, category in self.analytics.category_map.items():
            if not process_name.strip():
                raise ConfigError("analytics.category_map must not contain empty-string keys")
            if not category or not category.strip():
                raise ConfigError(
                    f"analytics.category_map[{process_name!r}] must not be blank"
                )
        if self.analytics.top_applications_limit <= 0:
            raise ConfigError(
                "analytics.top_applications_limit must be positive, "
                f"got {self.analytics.top_applications_limit}"
            )
        if self.analytics.habit_consistency_window_days <= 0:
            raise ConfigError(
                "analytics.habit_consistency_window_days must be positive, "
                f"got {self.analytics.habit_consistency_window_days}"
            )
        for field_name in ("habit_category_names", "project_category_names"):
            for name in getattr(self.analytics, field_name):
                if not name or not name.strip():
                    raise ConfigError(f"analytics.{field_name} must not contain blank entries")

    def _validate_wellness(self) -> None:
        w = self.wellness
        for field_name in (
            "idle_check_interval_seconds",
            "inactivity_reset_seconds",
            "break_interval_seconds",
            "hydration_interval_seconds",
            "eye_protection_interval_seconds",
            "overwork_daily_seconds",
        ):
            value = getattr(w, field_name)
            if value <= 0:
                raise ConfigError(f"wellness.{field_name} must be positive, got {value}")
        if not (0 <= w.late_night_start_hour <= 23):
            raise ConfigError(
                f"wellness.late_night_start_hour must be in [0, 23], got {w.late_night_start_hour}"
            )
        if not (0 <= w.late_night_end_hour <= 23):
            raise ConfigError(
                f"wellness.late_night_end_hour must be in [0, 23], got {w.late_night_end_hour}"
            )
        if sorted(w.trigger_priority_order) != sorted(_WELLNESS_TRIGGER_TYPES):
            raise ConfigError(
                "wellness.trigger_priority_order must be a permutation of "
                f"{_WELLNESS_TRIGGER_TYPES}, got {w.trigger_priority_order}"
            )
        if not (0.0 <= w.stress_sensitivity_factor <= 1.0):
            raise ConfigError(
                "wellness.stress_sensitivity_factor must be in [0.0, 1.0], got "
                f"{w.stress_sensitivity_factor}"
            )
        if not (0.0 <= w.high_stress_threshold <= 100.0):
            raise ConfigError(
                "wellness.high_stress_threshold must be in [0.0, 100.0], got "
                f"{w.high_stress_threshold}"
            )
        if w.max_postponements_before_hard_limit <= 0:
            raise ConfigError(
                "wellness.max_postponements_before_hard_limit must be positive, got "
                f"{w.max_postponements_before_hard_limit}"
            )
        for trigger_value, templates in w.escalation_message_templates.items():
            if trigger_value not in _WELLNESS_TRIGGER_TYPES:
                raise ConfigError(
                    "wellness.escalation_message_templates has an unknown trigger type key "
                    f"{trigger_value!r}, must be one of {_WELLNESS_TRIGGER_TYPES}"
                )
            if len(templates) != 3:
                raise ConfigError(
                    f"wellness.escalation_message_templates[{trigger_value!r}] must have "
                    f"exactly 3 entries (level 1/2/3), got {len(templates)}"
                )
            for level, message in enumerate(templates, start=1):
                if not message or not message.strip():
                    raise ConfigError(
                        f"wellness.escalation_message_templates[{trigger_value!r}] level "
                        f"{level} must not be blank"
                    )
        if w.adaptive_min_multiplier <= 0:
            raise ConfigError(
                "wellness.adaptive_min_multiplier must be positive, "
                f"got {w.adaptive_min_multiplier}"
            )
        if w.adaptive_max_multiplier <= 0:
            raise ConfigError(
                "wellness.adaptive_max_multiplier must be positive, "
                f"got {w.adaptive_max_multiplier}"
            )
        if w.adaptive_min_multiplier > w.adaptive_max_multiplier:
            raise ConfigError(
                "wellness.adaptive_min_multiplier must not exceed adaptive_max_multiplier, "
                f"got {w.adaptive_min_multiplier} > {w.adaptive_max_multiplier}"
            )

    def _validate_learning(self) -> None:
        learning_config = self.learning
        if learning_config.pattern_min_occurrences <= 0:
            raise ConfigError(
                "learning.pattern_min_occurrences must be positive, "
                f"got {learning_config.pattern_min_occurrences}"
            )
        if learning_config.pattern_min_days <= 0:
            raise ConfigError(
                "learning.pattern_min_days must be positive, "
                f"got {learning_config.pattern_min_days}"
            )
        if not (1 <= learning_config.preferred_time_bucket_hours <= 24):
            raise ConfigError(
                "learning.preferred_time_bucket_hours must be in [1, 24], got "
                f"{learning_config.preferred_time_bucket_hours}"
            )
        if 24 % learning_config.preferred_time_bucket_hours != 0:
            raise ConfigError(
                "learning.preferred_time_bucket_hours must evenly divide 24 (so every bucket "
                "label is clean and non-overlapping), got "
                f"{learning_config.preferred_time_bucket_hours}"
            )
        if learning_config.lookback_days <= 0:
            raise ConfigError(
                f"learning.lookback_days must be positive, got {learning_config.lookback_days}"
            )
        if learning_config.conversation_style_min_records <= 0:
            raise ConfigError(
                "learning.conversation_style_min_records must be positive, got "
                f"{learning_config.conversation_style_min_records}"
            )
        for pattern_type_value, template in learning_config.recommendation_templates.items():
            if pattern_type_value not in _LEARNING_PATTERN_TYPES:
                raise ConfigError(
                    "learning.recommendation_templates has an unknown pattern type key "
                    f"{pattern_type_value!r}, must be one of {_LEARNING_PATTERN_TYPES}"
                )
            if not template or not template.strip():
                raise ConfigError(
                    f"learning.recommendation_templates[{pattern_type_value!r}] must not be blank"
                )
            if "{subject}" not in template:
                raise ConfigError(
                    f"learning.recommendation_templates[{pattern_type_value!r}] must contain a "
                    "{subject} placeholder"
                )
        if learning_config.pattern_detection_interval_seconds <= 0:
            raise ConfigError(
                "learning.pattern_detection_interval_seconds must be positive, got "
                f"{learning_config.pattern_detection_interval_seconds}"
            )
        if learning_config.recommendation_generation_interval_seconds <= 0:
            raise ConfigError(
                "learning.recommendation_generation_interval_seconds must be positive, got "
                f"{learning_config.recommendation_generation_interval_seconds}"
            )
        if learning_config.preferred_workflow_min_runs <= 0:
            raise ConfigError(
                "learning.preferred_workflow_min_runs must be positive, got "
                f"{learning_config.preferred_workflow_min_runs}"
            )
        if learning_config.preferred_tool_min_sessions <= 0:
            raise ConfigError(
                "learning.preferred_tool_min_sessions must be positive, got "
                f"{learning_config.preferred_tool_min_sessions}"
            )
        if learning_config.daily_routine_min_days <= 0:
            raise ConfigError(
                "learning.daily_routine_min_days must be positive, got "
                f"{learning_config.daily_routine_min_days}"
            )
        if learning_config.study_schedule_min_sessions <= 0:
            raise ConfigError(
                "learning.study_schedule_min_sessions must be positive, got "
                f"{learning_config.study_schedule_min_sessions}"
            )

    def _validate_planning(self) -> None:
        p = self.planning
        if p.max_milestones_per_goal <= 0:
            raise ConfigError(
                "planning.max_milestones_per_goal must be positive, got "
                f"{p.max_milestones_per_goal}"
            )
        if p.max_tasks_per_milestone <= 0:
            raise ConfigError(
                "planning.max_tasks_per_milestone must be positive, got "
                f"{p.max_tasks_per_milestone}"
            )
        if p.decomposition_timeout_seconds <= 0:
            raise ConfigError(
                "planning.decomposition_timeout_seconds must be positive, got "
                f"{p.decomposition_timeout_seconds}"
            )
        if p.max_task_dependencies <= 0:
            raise ConfigError(
                f"planning.max_task_dependencies must be positive, got {p.max_task_dependencies}"
            )

    def _validate_context_engine(self) -> None:
        c = self.context_engine
        if c.memory_lookback_count <= 0:
            raise ConfigError(
                f"context_engine.memory_lookback_count must be positive, got "
                f"{c.memory_lookback_count}"
            )
        if c.usage_lookback_hours <= 0:
            raise ConfigError(
                f"context_engine.usage_lookback_hours must be positive, got "
                f"{c.usage_lookback_hours}"
            )
        if c.calendar_lookahead_hours <= 0:
            raise ConfigError(
                "context_engine.calendar_lookahead_hours must be positive, got "
                f"{c.calendar_lookahead_hours}"
            )

    def _validate_reasoning(self) -> None:
        r = self.reasoning
        if r.max_alternatives <= 0:
            raise ConfigError(
                f"reasoning.max_alternatives must be positive, got {r.max_alternatives}"
            )
        if r.reasoning_timeout_seconds <= 0:
            raise ConfigError(
                "reasoning.reasoning_timeout_seconds must be positive, got "
                f"{r.reasoning_timeout_seconds}"
            )

    def _validate_decision_engine_v2(self) -> None:
        weights = {
            "risk_weight": self.decision_engine_v2.risk_weight,
            "confidence_weight": self.decision_engine_v2.confidence_weight,
            "priority_weight": self.decision_engine_v2.priority_weight,
        }
        for name, value in weights.items():
            if not (0 <= value <= 1):
                raise ConfigError(f"decision_engine_v2.{name} must be in [0, 1], got {value}")
        weight_sum = sum(weights.values())
        if abs(weight_sum - 1.0) > 1e-6:
            raise ConfigError(
                "decision_engine_v2's three composite-score weights (risk_weight, "
                f"confidence_weight, priority_weight) must sum to 1.0, got {weight_sum}"
            )

    def _validate_knowledge_graph(self) -> None:
        k = self.knowledge_graph
        if k.max_traversal_depth <= 0:
            raise ConfigError(
                f"knowledge_graph.max_traversal_depth must be positive, got "
                f"{k.max_traversal_depth}"
            )
        if k.max_relationships_per_entity <= 0:
            raise ConfigError(
                "knowledge_graph.max_relationships_per_entity must be positive, got "
                f"{k.max_relationships_per_entity}"
            )

    def _validate_proactive(self) -> None:
        p = self.proactive
        if p.evaluation_interval_seconds <= 0:
            raise ConfigError(
                "proactive.evaluation_interval_seconds must be positive, got "
                f"{p.evaluation_interval_seconds}"
            )
        if p.deadline_warning_hours <= 0:
            raise ConfigError(
                f"proactive.deadline_warning_hours must be positive, got "
                f"{p.deadline_warning_hours}"
            )
        if not (0 < p.battery_critical_percent <= 100):
            raise ConfigError(
                "proactive.battery_critical_percent must be in (0, 100], got "
                f"{p.battery_critical_percent}"
            )
        if p.long_session_hours <= 0:
            raise ConfigError(
                f"proactive.long_session_hours must be positive, got {p.long_session_hours}"
            )
        if not (0 <= p.missed_meal_window_start_hour <= 23):
            raise ConfigError(
                "proactive.missed_meal_window_start_hour must be in [0, 23], got "
                f"{p.missed_meal_window_start_hour}"
            )
        if not (0 <= p.missed_meal_window_end_hour <= 23):
            raise ConfigError(
                "proactive.missed_meal_window_end_hour must be in [0, 23], got "
                f"{p.missed_meal_window_end_hour}"
            )
        if p.missed_meal_window_end_hour <= p.missed_meal_window_start_hour:
            raise ConfigError(
                "proactive.missed_meal_window_end_hour must be after "
                "missed_meal_window_start_hour, got "
                f"{p.missed_meal_window_end_hour} <= {p.missed_meal_window_start_hour}"
            )
        if p.project_inactivity_days <= 0:
            raise ConfigError(
                "proactive.project_inactivity_days must be positive, got "
                f"{p.project_inactivity_days}"
            )
        if p.trigger_cooldown_seconds <= 0:
            raise ConfigError(
                "proactive.trigger_cooldown_seconds must be positive, got "
                f"{p.trigger_cooldown_seconds}"
            )

    def _validate_runtime(self) -> None:
        r = self.runtime
        if r.default_idle_timeout_seconds <= 0:
            raise ConfigError(
                "runtime.default_idle_timeout_seconds must be positive, got "
                f"{r.default_idle_timeout_seconds}"
            )
        if r.housekeeping_interval_seconds <= 0:
            raise ConfigError(
                "runtime.housekeeping_interval_seconds must be positive, got "
                f"{r.housekeeping_interval_seconds}"
            )
