"""Shared fixtures and fakes for tests/integration/ — the real,
non-mocked exercise of Level 2's Communication Pipeline (Sprint 2.12),
its hardened failure paths (Sprint 2.13), and Level 3's Decision Engine
Integration (Sprint 3.12), reused by test_communication_pipeline.py
(2.12/2.13's own file), test_voice_pipeline_integration.py (Sprint
2.14's expansion), and test_decision_engine_integration.py (3.12's own
file).

Fakes stand in only at the audio-hardware/ML boundary (AudioBackend,
WakeWordEngine, SpeechToText, TextToSpeech, and now LanguageModelClient
for the Ollama-backed IntentDetector/ContextAnalyzer) — the same "fake
only at the seams that need real hardware/models" precedent every Level
2 unit-test file already established since Sprint 2.1. Chroma/SQLite are
NOT faked here, consistent with every Level 3 unit test's own
established convention (tests/unit/memory/*) of using a real MemoryStore
throughout — Chroma has no external-service dependency the way Ollama
does. Everything else is real: MicrophoneManager, WakeWordDetector,
VoiceSessionManager, QuietModeController, a real SQLite file under
tmp_path via SqliteClient/ConversationSessionStore, ContextManager,
JarvisPersona/MiniePersona, PersonaManager, MemoryStore and every Level 3
memory/decision module, and CommunicationPipeline itself. No physical
hardware, no ML model downloads, and no running Ollama service are
required to run this suite — real Whisper/Coqui/openWakeWord/Ollama
verification is done separately via one-off, non-committed scratchpad
smoke scripts (Sprint 2.12, 2.14, 3.7-3.12).

Plain helper functions/classes can't be imported across files here
(tests/ has no __init__.py, by convention since Sprint 1.1), so shared
helpers are exposed as fixtures instead, same pattern as
tests/unit/voice/conftest.py.
"""

import threading
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from analytics.dashboard_data import AnalyticsDashboardService
from analytics.usage_store import UsageStore
from analytics.usage_tracker import UsageTracker
from config.schema import (
    AnalyticsConfig,
    DatabaseConfig,
    DeviceControlConfig,
    EmotionConfig,
    InternetConfig,
    LearningConfig,
    MemoryConfig,
    ModelConfig,
    PresentationConfig,
    ResourceThresholds,
    SchedulerConfig,
    SecurityConfig,
    UIConfig,
    VoiceConfig,
    WellnessConfig,
    WorkflowConfig,
)
from core.resource_monitor import ResourceMonitor, ResourceSnapshot
from database.sqlite_client import SqliteClient
from decision.authority import AuthorityEvaluator
from decision.context_analyzer import ContextAnalyzer
from decision.intent_detector import IntentDetector
from decision.priority_queue import PriorityQueueManager
from decision.response_generator import ResponseGenerator
from device_control.action_engine import ActionRegistry
from device_control.action_log import ActionAuditLog
from device_control.application_manager import ApplicationManager
from device_control.command_executor import CommandExecutionEngine
from device_control.file_operations import FileOperationsManager
from device_control.resource_gate import ActionResourceGate
from device_control.window_manager import WindowManager
from emotion.detection_engine import EmotionDetectionEngine
from emotion.state_manager import EmotionalStateManager
from internet.research_engine import ResearchEngine
from internet.search_provider import SearchResult
from internet.source_validator import SourceValidator
from internet.summarizer import Summarizer
from learning.pattern_recognizer import PatternRecognizer
from learning.pattern_store import PatternStore
from learning.preference_learner import PreferenceLearner
from learning.recommendation import RecommendationEngine
from memory.chroma_client import ChromaMemoryClient
from memory.confidence_scorer import ConfidenceScorer
from memory.emotional_memory import EmotionalMemory
from memory.event_memory import EventMemory
from memory.lifecycle_manager import MemoryLifecycleManager
from memory.memory_store import MemoryStore
from memory.persona_scoped_memory import PersonaScopedMemory
from memory.retrieval_engine import MemoryRetrievalEngine
from memory.short_term_memory import ShortTermMemory
from personas.jarvis import JarvisPersona
from personas.minie import MiniePersona
from personas.persona_manager import PersonaManager
from presentation.adaptive_workspace import AdaptiveWorkspaceController
from presentation.avatar_renderer_registry import create_avatar_renderer
from presentation.companion_experience import CompanionExperienceEngine
from presentation.gesture_engine import GestureEngine
from presentation.jarvis_renderer import JarvisRenderer
from presentation.jarvis_state_computer import JarvisPresentationStateComputer
from presentation.lip_sync import LipSyncDriver
from presentation.minie_renderer import MinieRenderer
from presentation.minie_state_computer import MiniePresentationStateComputer
from presentation.presentation_controller import PresentationController
from presentation.transition_engine import TransitionEngine
from presentation.voice_personality import VoicePersonalityModulator
from scheduler.calendar_store import CalendarStore
from scheduler.reminder_engine import ReminderEngine
from scheduler.task_scheduler import TaskScheduler
from security.confirmation_service import VoiceConfirmationService
from security.permission_gate import PermissionGate
from security.policy_engine import PermissionPolicyEngine
from voice.context_manager import ContextManager
from voice.conversation_store import ConversationSessionStore
from voice.microphone import MicrophoneManager, MicrophoneMode
from voice.pipeline import CallbackRelay, CommunicationPipeline
from voice.quiet_mode import OperatingMode, QuietModeController
from voice.session_manager import VoiceSessionManager
from voice.speech_to_text import TranscriptionResult
from voice.wake_word import WakeWordDetector
from wellness.adaptive_wellness import AdaptiveWellnessAdjuster
from wellness.escalation import WellnessEscalationManager
from wellness.wellness_tracker import WellnessTracker
from workflow.workflow_executor import WorkflowExecutor
from workflow.workflow_store import WorkflowStore

WAIT_TIMEOUT = 5.0

LOUD_FRAME = b"\xff\x7f" * 480
QUIET_FRAME = b"\x00\x00" * 480


class FakeAudioBackend:
    """Real hardware would block on read(); this returns instantly, which
    is exactly why WakeWordDetector's Sprint 2.12 pause-while-active fix
    (see voice/wake_word.py) matters here — without it, this backend's
    unthrottled reads would let the still-running wake-word thread starve
    the session's own utterance capture of every frame."""

    def __init__(self) -> None:
        self.is_open = False
        self.frame_queue: list[bytes] = []
        self.raise_on_read = False

    def open(self, device_index: int | None, sample_rate_hz: int) -> None:
        self.is_open = True

    def read(self, num_frames: int) -> bytes:
        if self.raise_on_read:
            raise RuntimeError("simulated device disconnect")
        if self.frame_queue:
            return self.frame_queue.pop(0)
        return b"\x00\x00" * num_frames

    def flush(self) -> None:
        """VoiceSessionManager.begin_session() calls this immediately
        after switching to ACTIVE_CAPTURE (post-release fix) — safe to
        genuinely clear frame_queue here since every test in this
        directory only calls push_utterance() after the session has
        already begun, never before."""
        self.frame_queue.clear()

    def close(self) -> None:
        self.is_open = False


class FakeWakeWordEngine:
    def __init__(self, match_on_call: int, match_phrase: str = "hey_jarvis") -> None:
        self.calls = 0
        self.match_on_call = match_on_call
        self.match_phrase = match_phrase

    def process(self, frame: bytes) -> str | None:
        call_index = self.calls
        self.calls += 1
        if call_index == self.match_on_call:
            return self.match_phrase
        return None


class FakeSpeechToText:
    """Returns queued transcripts in order, one per transcribe() call —
    lets a test script a multi-turn conversation. should_raise (Sprint
    2.14, scenario b at integration level) simulates a Whisper failure."""

    def __init__(self) -> None:
        self.pending_transcripts: list[str] = []
        self.calls: list[bytes] = []
        self.should_raise = False

    def transcribe(self, audio: bytes) -> TranscriptionResult:
        self.calls.append(audio)
        if self.should_raise:
            from voice.errors import SpeechToTextError

            raise SpeechToTextError("simulated Whisper transcription failure")
        text = self.pending_transcripts.pop(0) if self.pending_transcripts else ""
        return TranscriptionResult(text=text, average_confidence=0.9, duration_ms=1)


class FakeTextToSpeech:
    """should_raise (Sprint 2.14, scenario c at integration level)
    simulates a Coqui synthesis/playback failure. on_audio_ready (Sprint
    5.14) is accepted (matching the real TextToSpeech.speak() Protocol,
    voice/text_to_speech.py) and invoked with a tiny synthetic float32
    silence buffer — real enough for LipSyncDriver.drive_from_audio()'s
    own np.frombuffer() decode to succeed without raising, never
    asserted on by any test in this directory that doesn't explicitly
    care."""

    def __init__(self) -> None:
        self.speak_calls: list[tuple[str, str]] = []
        self.spoken_event = threading.Event()
        self.should_raise = False

    def speak(self, text: str, voice_id: str, on_audio_ready=None) -> None:
        if self.should_raise:
            from voice.errors import TextToSpeechError

            raise TextToSpeechError("simulated Coqui synthesis failure")
        if on_audio_ready is not None:
            import numpy as np

            silence = np.zeros(160, dtype=np.float32).tobytes()
            on_audio_ready(silence, 16000)
        self.speak_calls.append((text, voice_id))
        self.spoken_event.set()


class FakeLanguageModelClient:
    """Fakes only the Ollama boundary IntentDetector/ContextAnalyzer
    depend on (Sprint 3.7/3.8) — see this module's own docstring for why
    Chroma/SQLite are real throughout instead. Dispatches on prompt
    content: IntentDetector's own prompt always instructs a "CATEGORY:"
    line; ContextAnalyzer's never does (it uses "TOPIC:"/"PERSONA:"
    instead), so checking for that exact literal substring reliably
    tells the two callers apart without either constructor needing to
    know which stage is asking.

    should_raise (Sprint 3.13 hardening, scenario a) simulates Ollama
    being entirely unreachable — same should_raise convention already
    established on FakeSpeechToText/FakeTextToSpeech above.

    summary_response (Sprint 4.18) is returned for internet/
    summarizer.py's own prompt — detected via the literal "Search
    results:" substring that ONLY that prompt template ever contains
    (IntentDetector's own always has "CATEGORY:", ContextAnalyzer's
    never has either), the same "dispatch on a template-unique literal
    substring" discipline this fake already used for the first two.

    should_raise_for_summary (Sprint 4.19 hardening, scenario b) fails
    ONLY the Summarizer's own call, distinct from should_raise (which
    fails every call, including the earlier IntentDetector/
    ContextAnalyzer stages of the same turn and so can never reach
    Summarizer at all) — this is what actually lets a test exercise "the
    search succeeded, only summarization failed" instead of the whole
    turn degrading before routing ever happens.

    conversational_response (0.4.2 — Response Generation) is returned
    for decision/response_generator.py's own prompt — detected via the
    literal "Reply to the user directly" substring that ONLY that
    prompt template contains, same "dispatch on a template-unique
    literal substring" discipline as summary_response above.
    should_raise_for_conversation mirrors should_raise_for_summary: it
    fails ONLY the ResponseGenerator's own call, so a test can exercise
    "everything upstream succeeded, only response generation failed,
    degrade to the templated reply for this one turn" without every
    earlier stage failing too."""

    def __init__(self) -> None:
        self.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
        self.context_response = (
            "TOPIC: general\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
            "PERSONA: NONE\nSENTIMENT: NEUTRAL"
        )
        self.summary_response = "Here is a summary based on the provided sources."
        self.conversational_response = "Here's a real, generated answer to your question."
        self.calls: list[str] = []
        self.should_raise = False
        self.should_raise_for_summary = False
        self.should_raise_for_conversation = False

    def generate(
        self, prompt: str, timeout_seconds: float, stop: list[str] | None = None
    ) -> str:
        self.calls.append(prompt)
        if self.should_raise:
            from decision.llm_client import LlmError

            raise LlmError("simulated Ollama connection failure")
        if "Search results:" in prompt:
            if self.should_raise_for_summary:
                from decision.llm_client import LlmError

                raise LlmError("simulated Ollama connection failure during summarization")
            return self.summary_response
        if "Reply to the user directly" in prompt:
            if self.should_raise_for_conversation:
                from decision.llm_client import LlmError

                raise LlmError("simulated Ollama connection failure during response generation")
            return self.conversational_response
        if "CATEGORY:" in prompt:
            return self.intent_response
        return self.context_response


class FakeSearchProvider:
    """Local double implementing the SearchProvider Protocol (Sprint
    4.18) — the one place tests/integration/ fakes the Internet Agent's
    own true external boundary, matching every other module's "fake
    only at the seams needing real hardware/models/external services"
    precedent."""

    def __init__(self) -> None:
        self.queued_results: list[SearchResult] = []
        self.calls: list[tuple[str, int]] = []
        self.should_raise = False

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        self.calls.append((query, max_results))
        if self.should_raise:
            from internet.search_provider import SearchError

            raise SearchError("simulated search provider failure")
        return self.queued_results


@pytest.fixture
def voice_config() -> VoiceConfig:
    """session_timeout_seconds=3.0/max_utterance_seconds=10.0 (Sprint
    3.12, was 0.8/2.0): pipeline_harness starts wake_word_detector last,
    so the background wake thread is already running the instant the
    fixture yields — any real work a test does before its own first
    wait_for_active_capture()/push_utterance() call (a real, first-use
    Chroma embedding call is genuinely slow) narrows the effective
    window before the session's own timeout/safety-cap clocks (which
    started ticking as soon as the wake match fired) expire. Concretely
    reproduced as a real, reliably-failing test once a Level 3 test
    added a real MemoryStore write between activation and pushing an
    utterance. Same margin reasoning as tests/system/conftest.py's own
    voice_config fixture."""
    return VoiceConfig(
        mic_sample_rate_hz=16000,
        utterance_silence_ms=30,
        utterance_silence_threshold=0.02,
        max_utterance_seconds=10.0,
        session_timeout_seconds=3.0,
    )


def _wait_for_no_scheduler_worker_threads(timeout: float = 3.0) -> None:
    """Polls (never blindly sleeps) until no APScheduler ThreadPoolExecutor
    worker thread remains alive, or timeout elapses — best-effort, not a
    guarantee, so a stuck job body can't turn teardown itself into a new
    hang. Confirmed directly (a throwaway BackgroundScheduler probe, not
    just APScheduler's own docs) that shutdown(wait=False) still leaves
    an in-flight job's own "ThreadPoolExecutor-N_M"-named worker thread
    alive until that invocation actually finishes — the scheduler's own
    dispatcher thread (named "APScheduler") disappears immediately, but
    the worker executing real store code does not. Calling this between
    TaskScheduler.stop() and closing any SqliteClient connection a job
    might still be mid-execute()/commit() against is the real fix for a
    concretely reproduced hang (a full thread-stack dump showed threads
    stuck in sqlite_client.close()/query() — sqlite3_close() racing a
    concurrent execute() on the same connection object from another
    thread is undefined behavior at the SQLite C level, not a clean,
    fast-failing exception)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(
            t.name.startswith("ThreadPoolExecutor") and t.is_alive()
            for t in threading.enumerate()
        ):
            return
        time.sleep(0.02)


def _fake_core_manager(interval_ms: int = 3000) -> MagicMock:
    """Sprint 5.14: JarvisRenderer/MinieRenderer's own required
    core_manager constructor parameter — this harness starts modules by
    hand rather than through a real CoreManager (see this function's own
    docstring), so a MagicMock stands in, mirroring tests/unit/presentation/
    test_jarvis_renderer.py's own _fake_core_manager() helper exactly.
    Only ui_config()/module_states()/check_resources() are ever actually
    called (by _SystemStatusPanel, only if a test calls
    apply_workspace_profile()) — real values are supplied for those three
    so such a call would not crash outright, even though no test in this
    directory currently exercises that path."""
    manager = MagicMock()
    manager.ui_config.return_value = UIConfig(status_refresh_interval_ms=interval_ms)
    manager.module_states.return_value = {}
    manager.check_resources.return_value = ResourceSnapshot(
        cpu_percent=10.0,
        ram_percent=20.0,
        disk_percent=30.0,
        battery_percent=80.0,
        timestamp=datetime.now(UTC),
    )
    return manager


def _pipeline_harness_impl(
    tmp_path,
    voice_config,
    scheduler_config: SchedulerConfig,
    wellness_config: WellnessConfig | None = None,
    learning_config: LearningConfig | None = None,
    analytics_config: AnalyticsConfig | None = None,
    level5_part_b_available: bool = True,
):
    """The real Communication Pipeline object graph, matching
    main.py's own composition order exactly (_register_level2_modules,
    _register_level3_modules, _register_level4_modules, and — Sprint
    5.14 — _register_level5_modules) — fakes only at the mic/wake-engine/
    STT/TTS/Ollama boundary. Level 5's own real avatar_renderer
    (VTubeStudioAvatarRenderer, via create_avatar_renderer()) is used
    unfaked too — mount()'s own "disconnected, never crash" contract
    (Sprint 5.8) already degrades a real connection attempt against a
    VTube Studio instance that isn't running to a safe, fast no-op, the
    same "real external dependency stays opt-in" precedent this
    module's own docstring already applies to Ollama/search providers.

    Level 4's device_control_config is deliberately scoped for safety,
    per sprint_4_11.md's own Potential Risks ("every destructive-shaped
    integration test must operate exclusively within a tmp_path-scoped
    allowed_file_roots and against test-only, disposable applications"):
    allowed_file_roots is tmp_path itself, and application_allowlist
    names only hostname.exe — a real Windows binary present on every
    Windows machine that takes no arguments, prints one line, and exits
    in well under a second, with no window and no side effects. Chosen
    specifically because a real device-control-shaped voice turn (see
    voice/pipeline.py's own _handle_device_control_turn()) has no way to
    pass extra argv beyond a bare executable name — sys.executable with
    zero arguments would instead drop into a real, indefinitely-blocking
    Python REPL, the wrong kind of "disposable" for an automated test.
    confirmation_timeout_seconds is shortened from SecurityConfig's own
    20s default so a deliberately undriven confirmation prompt times out
    within a normal test's own patience, matching voice_config's own
    already-established "tuned short for tests" precedent above."""
    audio_backend = FakeAudioBackend()
    mic = MicrophoneManager(voice_config, audio_backend)

    stt = FakeSpeechToText()
    tts = FakeTextToSpeech()

    database_config = DatabaseConfig(
        sqlite_path=str(tmp_path / "conversations.db"), chroma_path=str(tmp_path / "chroma")
    )
    sqlite_client = SqliteClient(database_config.sqlite_path)
    conversation_store = ConversationSessionStore(sqlite_client, database_config)
    context_manager = ContextManager(conversation_store)

    # Sprint 5.14: stands in for on_switch until transition_engine (Level
    # 5, built much later in this same function) exists — the identical
    # circular-construction problem/CallbackRelay resolution main.py's
    # own persona_switch_relay applies, reproduced here by hand since
    # this harness constructs its object graph directly rather than
    # through main.py's own composition-root functions.
    persona_switch_relay = CallbackRelay()
    jarvis = JarvisPersona(voice_config)
    minie = MiniePersona(voice_config)
    persona_manager = PersonaManager(jarvis, minie, voice_config, on_switch=persona_switch_relay)

    turn_complete_relay = CallbackRelay()
    session_ended_relay = CallbackRelay()
    session_manager = VoiceSessionManager(
        mic, stt, tts, voice_config, turn_complete_relay, session_ended_relay
    )
    quiet_mode_controller = QuietModeController(session_manager)

    wake_engine = FakeWakeWordEngine(match_on_call=2)
    wake_word_detector = WakeWordDetector(
        mic, wake_engine, quiet_mode_controller._on_wake_word_detected
    )

    memory_config = MemoryConfig(chroma_collection_prefix="pipeline_harness")
    model_config = ModelConfig()
    memory_sqlite_client = SqliteClient(database_config.sqlite_path)
    chroma_client = ChromaMemoryClient(memory_config, database_config)
    memory_store = MemoryStore(memory_sqlite_client, chroma_client)

    persona_scoped_memory = PersonaScopedMemory(memory_store)
    event_memory = EventMemory(memory_store)
    short_term_memory = ShortTermMemory(memory_store, memory_config)
    confidence_scorer = ConfidenceScorer(memory_config)
    memory_lifecycle_manager = MemoryLifecycleManager(
        memory_store, confidence_scorer, memory_config
    )
    memory_retrieval_engine = MemoryRetrievalEngine(
        persona_scoped_memory, event_memory, short_term_memory, confidence_scorer, memory_config
    )

    llm_client = FakeLanguageModelClient()
    intent_detector = IntentDetector(llm_client, model_config)
    context_analyzer = ContextAnalyzer(llm_client, model_config)
    response_generator = ResponseGenerator(llm_client, model_config)
    resource_monitor = ResourceMonitor(ResourceThresholds())
    priority_queue_manager = PriorityQueueManager(resource_monitor)
    authority_evaluator = AuthorityEvaluator()

    device_control_config = DeviceControlConfig(
        allowed_file_roots=[str(tmp_path)],
        application_allowlist=["hostname.exe"],
        # Post-Sprint Fix (found during Sprint 4.12's own full-suite run):
        # resource_gate_action_types defaults to ["launch_application",
        # "system_command"], which makes ActionResourceGate sample the
        # REAL host machine's own current CPU/RAM via ResourceMonitor —
        # a genuine, non-deterministic environmental dependency this
        # harness otherwise deliberately avoids (fakes stand in for
        # every other hardware/model boundary). Confirmed concretely: a
        # real launch_application dispatch was blocked here because
        # this development machine's own real RAM usage was genuinely
        # at 90-96% at the time, unrelated to anything this test
        # exercises. Empty here disables real resource sampling for
        # this harness entirely — resource-gate blocking behavior
        # itself is already covered by tests/unit/device_control/
        # test_resource_gate.py's own dedicated, deterministic suite.
        resource_gate_action_types=[],
    )
    security_config = SecurityConfig(confirmation_timeout_seconds=2.0)
    workflow_config = WorkflowConfig()

    policy_engine = PermissionPolicyEngine(security_config)
    confirmation_service = VoiceConfirmationService(
        session_manager, persona_manager, security_config.confirmation_timeout_seconds
    )
    permission_gate = PermissionGate(
        authority_evaluator, policy_engine, confirmation_service, device_control_config
    )
    resource_gate = ActionResourceGate(
        resource_monitor, priority_queue_manager, device_control_config
    )
    audit_sqlite_client = SqliteClient(database_config.sqlite_path)
    audit_log = ActionAuditLog(audit_sqlite_client, device_control_config)
    action_registry = ActionRegistry(
        permission_gate,
        resource_gate,
        audit_log,
        max_retry_attempts=device_control_config.max_retry_attempts,
    )
    application_manager = ApplicationManager(device_control_config)
    file_operations_manager = FileOperationsManager(device_control_config)
    window_manager = WindowManager(device_control_config)
    command_executor = CommandExecutionEngine(device_control_config)
    for executor in (
        application_manager,
        file_operations_manager,
        window_manager,
        command_executor,
    ):
        action_registry.register(executor)

    workflow_sqlite_client = SqliteClient(database_config.sqlite_path)
    workflow_store = WorkflowStore(workflow_sqlite_client, workflow_config)
    workflow_executor = WorkflowExecutor(
        workflow_store, action_registry, policy_engine, confirmation_service, workflow_config
    )

    # Sprint 4.18 (Scheduler & Internet Agent Integration) — Level 4
    # Part B, same fake-boundary discipline as Level 4 Part A above
    # (fakes only at the real network/LLM boundary — FakeSearchProvider/
    # FakeLanguageModelClient). scheduler_config is caller-supplied (not
    # hardcoded here) precisely so pipeline_harness (below) can keep its
    # own REALISTIC (slow, near-production-default) intervals — a real,
    # concretely reproduced hang was found when these fired every
    # 0.05-0.1s: a background TaskScheduler job (e.g.
    # conversation_store_purge) mid-SQLite-operation on APScheduler's own
    # thread pool raced against teardown closing that same SqliteClient
    # connection from the main thread — while fast_scheduler_harness
    # (below) opts into short intervals for tests that need to observe
    # real recurrence, paired with _wait_for_no_scheduler_worker_threads()
    # in this same function's own teardown to close that exact race
    # instead of merely avoiding it by staying slow.
    internet_config = InternetConfig()

    task_scheduler = TaskScheduler()
    calendar_sqlite_client = SqliteClient(database_config.sqlite_path)
    calendar_store = CalendarStore(calendar_sqlite_client, scheduler_config)
    reminder_engine = ReminderEngine(
        calendar_store, priority_queue_manager, task_scheduler, scheduler_config
    )

    fake_search_provider = FakeSearchProvider()
    research_engine = ResearchEngine(fake_search_provider, internet_config)
    source_validator = SourceValidator(internet_config)
    summarizer = Summarizer(llm_client, internet_config, model_config)

    # Sprint 5.14 — Level 5 Part A, same construction shape as main.py's
    # own _construct_level5_modules() (real classes throughout; the one
    # real external boundary, VTube Studio, is unfaked but self-degrading
    # — see this function's own docstring).
    emotion_config = EmotionConfig()
    presentation_config = PresentationConfig()
    fake_core_manager = _fake_core_manager()

    emotion_detection_engine = EmotionDetectionEngine(emotion_config)
    emotional_state_manager = EmotionalStateManager(emotion_config)
    emotional_memory = EmotionalMemory(memory_store, memory_config)

    gesture_engine = GestureEngine(presentation_config)
    jarvis_state_computer = JarvisPresentationStateComputer(presentation_config)
    minie_state_computer = MiniePresentationStateComputer(presentation_config)
    jarvis_renderer = JarvisRenderer(presentation_config, fake_core_manager)
    avatar_renderer = create_avatar_renderer(presentation_config)
    minie_renderer = MinieRenderer(avatar_renderer, presentation_config, fake_core_manager)

    presentation_controller = PresentationController(
        persona_manager=persona_manager,
        emotional_state_manager=emotional_state_manager,
        quiet_mode_controller=quiet_mode_controller,
        state_computers={"jarvis": jarvis_state_computer, "minie": minie_state_computer},
        renderers={"jarvis": jarvis_renderer, "minie": minie_renderer},
        gesture_engine=gesture_engine,
    )
    transition_engine = TransitionEngine(presentation_controller, presentation_config)
    persona_switch_relay.target = transition_engine.transition

    adaptive_workspace_controller = AdaptiveWorkspaceController(presentation_config)
    companion_experience_engine = CompanionExperienceEngine(
        emotional_memory, event_memory, presentation_config
    )
    voice_personality_modulator = VoicePersonalityModulator(presentation_config)
    lip_sync_driver = LipSyncDriver(presentation_config)

    # Sprint 5.24 — Level 5 Part B (Companion Intelligence), matching
    # main.py's own _construct_level5_part_b_modules() exactly (real
    # classes throughout, each store getting its own fresh SqliteClient
    # against the identical database file — the same established
    # per-store-not-shared precedent every other store construction in
    # this fixture already follows).
    analytics_config = analytics_config if analytics_config is not None else AnalyticsConfig()
    wellness_config = wellness_config if wellness_config is not None else WellnessConfig()
    learning_config = learning_config if learning_config is not None else LearningConfig()

    usage_sqlite_client = SqliteClient(database_config.sqlite_path)
    usage_store = UsageStore(usage_sqlite_client, analytics_config)
    usage_tracker = UsageTracker(task_scheduler, usage_store, analytics_config)

    wellness_escalation_manager = WellnessEscalationManager(wellness_config)

    pattern_sqlite_client = SqliteClient(database_config.sqlite_path)
    pattern_store = PatternStore(pattern_sqlite_client)
    adaptive_wellness_adjuster = AdaptiveWellnessAdjuster(pattern_store, wellness_config)

    wellness_tracker = WellnessTracker(
        task_scheduler, wellness_config, emotional_state_manager, wellness_escalation_manager
    )

    dashboard_service = AnalyticsDashboardService(usage_store, analytics_config)
    pattern_recognizer = PatternRecognizer(
        usage_store, dashboard_service, pattern_store, learning_config
    )
    preference_learner = PreferenceLearner(memory_store, pattern_store, learning_config)
    recommendation_engine = RecommendationEngine(pattern_store, learning_config)

    pipeline = CommunicationPipeline(
        mic=mic,
        wake_word_detector=wake_word_detector,
        session_manager=session_manager,
        quiet_mode_controller=quiet_mode_controller,
        conversation_store=conversation_store,
        context_manager=context_manager,
        persona_manager=persona_manager,
        turn_complete_relay=turn_complete_relay,
        session_ended_relay=session_ended_relay,
        intent_detector=intent_detector,
        context_analyzer=context_analyzer,
        response_generator=response_generator,
        memory_retrieval_engine=memory_retrieval_engine,
        priority_queue_manager=priority_queue_manager,
        authority_evaluator=authority_evaluator,
        short_term_memory=short_term_memory,
        confidence_scorer=confidence_scorer,
        memory_lifecycle_manager=memory_lifecycle_manager,
        action_registry=action_registry,
        workflow_store=workflow_store,
        workflow_executor=workflow_executor,
        task_scheduler=task_scheduler,
        calendar_store=calendar_store,
        reminder_engine=reminder_engine,
        research_engine=research_engine,
        source_validator=source_validator,
        summarizer=summarizer,
        action_audit_log=audit_log,
        scheduler_config=scheduler_config,
        memory_config=memory_config,
        emotion_detection_engine=emotion_detection_engine,
        emotional_state_manager=emotional_state_manager,
        emotional_memory=emotional_memory,
        presentation_controller=presentation_controller,
        adaptive_workspace_controller=adaptive_workspace_controller,
        gesture_engine=gesture_engine,
        voice_personality_modulator=voice_personality_modulator,
        lip_sync_driver=lip_sync_driver,
        companion_experience_engine=companion_experience_engine,
        jarvis_renderer=jarvis_renderer,
        avatar_renderer=avatar_renderer,
        # Sprint 5.24's own null-fallback path: level5_part_b_available=
        # False wires literal None through every one of these six
        # optional constructor parameters — matching main.py's own
        # _null_level5_part_b_modules() shape — while the real objects
        # above are still constructed/started/registered regardless, a
        # pragmatic harness simplification (simpler than skipping their
        # construction entirely) that still validates the one thing the
        # sprint's own Acceptance Criteria actually cares about:
        # CommunicationPipeline tolerating None for all six.
        wellness_tracker=wellness_tracker if level5_part_b_available else None,
        wellness_escalation_manager=(
            wellness_escalation_manager if level5_part_b_available else None
        ),
        adaptive_wellness_adjuster=(
            adaptive_wellness_adjuster if level5_part_b_available else None
        ),
        dashboard_service=dashboard_service if level5_part_b_available else None,
        usage_tracker=usage_tracker if level5_part_b_available else None,
        pattern_recognizer=pattern_recognizer if level5_part_b_available else None,
        recommendation_engine=recommendation_engine if level5_part_b_available else None,
        learning_config=learning_config,
        wellness_config=wellness_config,
    )

    # task_scheduler/calendar_store start FIRST, before pipeline.start()
    # — CommunicationPipeline.start() (Sprint 4.18) calls
    # task_scheduler.add_job() directly, which requires TaskScheduler.
    # start() to have already run (matching main.py's own real
    # registration-order requirement, reproduced here by hand since this
    # harness starts modules individually rather than through
    # CoreManager). emotion_detection_engine/emotional_state_manager/
    # presentation_controller (Sprint 5.14's own three ManagedModules)
    # start last, mirroring main.py's own _register_level5_modules()
    # ordering — presentation_controller.start() calls persona_manager.
    # active_persona(), which requires persona_manager already started.
    task_scheduler.start()
    calendar_store.start()
    mic.start()
    conversation_store.start()
    persona_manager.start()
    session_manager.start()
    quiet_mode_controller.start()
    memory_store.start()
    memory_lifecycle_manager.start()
    intent_detector.start()
    context_analyzer.start()
    priority_queue_manager.start()
    authority_evaluator.start()
    audit_log.start()
    workflow_store.start()
    emotion_detection_engine.start()
    emotional_state_manager.start()
    presentation_controller.start()
    # Sprint 5.24 — Level 5 Part B, started after Level 5 Part A (stores
    # before their own dependents: usage_store before usage_tracker,
    # pattern_store before pattern_recognizer), before pipeline.start()
    # registers its own TaskScheduler jobs against them.
    usage_store.start()
    usage_tracker.start()
    pattern_store.start()
    pattern_recognizer.start()
    wellness_tracker.start()
    pipeline.start()
    wake_word_detector.start()

    harness = SimpleNamespace(
        mic=mic,
        audio_backend=audio_backend,
        stt=stt,
        tts=tts,
        wake_engine=wake_engine,
        wake_word_detector=wake_word_detector,
        conversation_store=conversation_store,
        persona_manager=persona_manager,
        session_manager=session_manager,
        quiet_mode_controller=quiet_mode_controller,
        pipeline=pipeline,
        memory_store=memory_store,
        persona_scoped_memory=persona_scoped_memory,
        event_memory=event_memory,
        short_term_memory=short_term_memory,
        confidence_scorer=confidence_scorer,
        memory_lifecycle_manager=memory_lifecycle_manager,
        memory_retrieval_engine=memory_retrieval_engine,
        llm_client=llm_client,
        intent_detector=intent_detector,
        context_analyzer=context_analyzer,
        response_generator=response_generator,
        priority_queue_manager=priority_queue_manager,
        authority_evaluator=authority_evaluator,
        action_registry=action_registry,
        application_manager=application_manager,
        audit_log=audit_log,
        workflow_store=workflow_store,
        workflow_executor=workflow_executor,
        device_control_config=device_control_config,
        task_scheduler=task_scheduler,
        calendar_store=calendar_store,
        reminder_engine=reminder_engine,
        fake_search_provider=fake_search_provider,
        research_engine=research_engine,
        source_validator=source_validator,
        summarizer=summarizer,
        scheduler_config=scheduler_config,
        internet_config=internet_config,
        emotion_detection_engine=emotion_detection_engine,
        emotional_state_manager=emotional_state_manager,
        emotional_memory=emotional_memory,
        presentation_controller=presentation_controller,
        jarvis_renderer=jarvis_renderer,
        minie_renderer=minie_renderer,
        avatar_renderer=avatar_renderer,
        gesture_engine=gesture_engine,
        transition_engine=transition_engine,
        adaptive_workspace_controller=adaptive_workspace_controller,
        companion_experience_engine=companion_experience_engine,
        voice_personality_modulator=voice_personality_modulator,
        lip_sync_driver=lip_sync_driver,
        usage_store=usage_store,
        usage_tracker=usage_tracker,
        pattern_store=pattern_store,
        pattern_recognizer=pattern_recognizer,
        wellness_tracker=wellness_tracker,
        wellness_escalation_manager=wellness_escalation_manager,
        adaptive_wellness_adjuster=adaptive_wellness_adjuster,
        dashboard_service=dashboard_service,
        preference_learner=preference_learner,
        recommendation_engine=recommendation_engine,
    )
    try:
        yield harness
    finally:
        wake_word_detector.stop()
        pipeline.stop()
        wellness_tracker.stop()
        pattern_recognizer.stop()
        pattern_store.stop()
        usage_tracker.stop()
        usage_store.stop()
        presentation_controller.stop()
        emotional_state_manager.stop()
        emotion_detection_engine.stop()
        # Sprint 5.14: presentation_controller.start() above (real
        # production behavior, deliberately exercised for real) makes
        # JarvisRenderer build a real, unparented top-level QWidget every
        # single test in this directory now constructs — a concretely
        # reproduced Qt native crash (Windows fatal exception: access
        # violation, inside pytest-qt's own qtbot.wait()) was found once
        # ~140 such widgets across this whole directory accumulated with
        # no test ever pumping Qt's event loop, only for the resulting
        # backlog to land all at once inside some unrelated, later test's
        # own first real qtbot.wait() call. Explicitly releasing the
        # widget and pumping the event loop here, incrementally, per
        # test, keeps Qt's own internal widget/timer bookkeeping
        # consistent throughout the run instead of building up a batch
        # that eventually corrupts state — verified directly: the
        # combined tests/integration/+tests/system/+tests/unit/presentation/
        # run that reliably crashed without this passed cleanly with it.
        if jarvis_renderer._container is not None:
            jarvis_renderer._container.deleteLater()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
            app.processEvents()
        # task_scheduler.stop() moved here (immediately after pipeline.stop()
        # removes every job it registered) — deliberately BEFORE any
        # store's own stop() closes the SqliteClient connection a still
        # in-flight job invocation might be using. See
        # _wait_for_no_scheduler_worker_threads()'s own docstring for the
        # concretely reproduced race this ordering (plus the wait) closes.
        task_scheduler.stop()
        _wait_for_no_scheduler_worker_threads()
        workflow_store.stop()
        audit_log.stop()
        authority_evaluator.stop()
        priority_queue_manager.stop()
        context_analyzer.stop()
        intent_detector.stop()
        memory_lifecycle_manager.stop()
        memory_store.stop()
        quiet_mode_controller.stop()
        session_manager.stop()
        persona_manager.stop()
        conversation_store.stop()
        mic.stop()
        calendar_store.stop()


@pytest.fixture
def pipeline_harness(tmp_path, voice_config, qapp):
    """SchedulerConfig() (realistic, slow defaults) — see
    _pipeline_harness_impl()'s own docstring for why. Every existing
    integration test in this directory uses this fixture; only
    test_scheduler_integration.py opts into fast_scheduler_harness
    below instead.

    qapp (Sprint 5.14, pytest-qt's own session-scoped fixture) is
    depended on but never used directly — PresentationController.start()
    (Level 5's own ManagedModule, started inside _pipeline_harness_impl())
    mounts JarvisRenderer by default, which lazily constructs real
    QWidgets; requesting qapp here guarantees a QApplication already
    exists before that happens, the same precedent
    tests/unit/presentation/test_jarvis_renderer.py's own qtbot-based
    widget construction already established."""
    yield from _pipeline_harness_impl(tmp_path, voice_config, SchedulerConfig())


@pytest.fixture
def fast_scheduler_harness(tmp_path, voice_config, qapp):
    """Identical object graph to pipeline_harness, but with short
    poll_interval_seconds/maintenance_interval_seconds so
    test_scheduler_integration.py can observe real recurrence (a job
    firing more than once, a due reminder actually becoming due) within
    a normal test's own patience, instead of waiting out
    SchedulerConfig()'s own production-realistic 30s/3600s defaults.
    Not shared with any other test file — see _pipeline_harness_impl()'s
    own docstring for why fast intervals don't belong in the widely-reused
    pipeline_harness fixture.

    0.3s (not more aggressive) — Post-Sprint Fix: SqliteClient gained its
    own threading.Lock (2026-08-01) once concurrent, unsynchronized
    access to one connection from several of these very jobs was found
    to genuinely corrupt reads. That lock is correct and necessary, but
    it also means these jobs' real SQLite work now genuinely serializes
    instead of racing — at 0.15s, sustained load across this whole
    file's several tests occasionally pushed a job's own next tick to
    arrive before its still-serializing predecessor finished, which
    APScheduler (default max_instances=1) then skips rather than stacks.
    That's harmless in itself (a skipped tick, not a corruption or a
    crash), but it intermittently ate into a test's own bounded-wait
    margin under this file's cumulative load. 0.3s gives every job
    comfortable headroom while still resolving well within any test's
    own 5s wait_until timeout."""
    fast_config = SchedulerConfig(poll_interval_seconds=0.3, maintenance_interval_seconds=0.3)
    yield from _pipeline_harness_impl(tmp_path, voice_config, fast_config)


@pytest.fixture
def fast_level5_part_b_harness(tmp_path, voice_config, qapp):
    """Identical object graph to pipeline_harness, but with short
    scheduler_config.poll_interval_seconds (Sprint 4.18's own
    fast_scheduler_harness precedent) PLUS short wellness_config.
    idle_check_interval_seconds/learning_config.pattern_detection_
    interval_seconds/recommendation_generation_interval_seconds (Sprint
    5.24's own three new jobs) PLUS short analytics_config.
    sample_interval_seconds (Sprint 5.25 hardening, scenario d — added
    so test_companion_intelligence_resilience.py's own six-job
    TaskScheduler isolation test can observe UsageTracker's real job
    genuinely recur too, alongside the other five; a strictly additive
    extension, safe for this fixture's existing Sprint 5.24 callers,
    none of which depend on UsageTracker's own interval staying at its
    slow production default) — for test_companion_intelligence_
    integration.py's/test_companion_intelligence_resilience.py's own
    real-recurrence tests only, matching fast_scheduler_harness's own
    "not shared with any other test file" precedent. maintenance_
    interval_seconds is deliberately left at SchedulerConfig()'s own
    realistic default (unlike fast_scheduler_harness) — this file's own
    tests have no need to observe the maintenance passes recur, and
    every additional fast-interval background job adds more of the same
    real SQLite scheduling contention fast_scheduler_harness's own
    docstring already names."""
    fast_scheduler_config = SchedulerConfig(poll_interval_seconds=0.3)
    fast_wellness_config = WellnessConfig(idle_check_interval_seconds=0.3)
    fast_learning_config = LearningConfig(
        pattern_detection_interval_seconds=0.3, recommendation_generation_interval_seconds=0.3
    )
    fast_analytics_config = AnalyticsConfig(sample_interval_seconds=0.3)
    yield from _pipeline_harness_impl(
        tmp_path,
        voice_config,
        fast_scheduler_config,
        wellness_config=fast_wellness_config,
        learning_config=fast_learning_config,
        analytics_config=fast_analytics_config,
    )


@pytest.fixture
def pipeline_harness_without_level5_part_b(tmp_path, voice_config, qapp):
    """Identical object graph to pipeline_harness, but CommunicationPipeline
    itself is constructed with every one of its six Sprint 5.24 optional
    parameters set to None — see _pipeline_harness_impl()'s own
    level5_part_b_available docstring for exactly what this does and
    doesn't simulate. For test_companion_intelligence_integration.py's
    own Level 5 Part B construction-failure scenario only."""
    yield from _pipeline_harness_impl(
        tmp_path, voice_config, SchedulerConfig(), level5_part_b_available=False
    )


@pytest.fixture
def wait_for_active_capture():
    def _wait(mic, timeout: float = WAIT_TIMEOUT) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if mic.current_mode() is MicrophoneMode.ACTIVE_CAPTURE:
                return
            time.sleep(0.02)
        raise AssertionError("Timed out waiting for the microphone to enter ACTIVE_CAPTURE.")

    return _wait


@pytest.fixture
def wait_for_dormant():
    def _wait(quiet_mode_controller, timeout: float = WAIT_TIMEOUT) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if quiet_mode_controller.current_mode() is OperatingMode.DORMANT:
                return
            time.sleep(0.02)
        raise AssertionError("Timed out waiting for Quiet Mode Controller to return to DORMANT.")

    return _wait


@pytest.fixture
def wait_until():
    """Generic bounded-poll helper — the same "poll a real observable
    state, never blindly sleep-and-hope" discipline as
    wait_for_active_capture/wait_for_dormant above, for the scheduler-
    and internet-agent-specific conditions (Sprint 4.18) those two named
    fixtures don't cover: a PriorityQueueManager peek, a TTS call count,
    a maintenance job's own call counter. Returns True/False rather than
    raising, so a caller can assert with its own descriptive message."""

    def _wait(predicate, timeout: float = WAIT_TIMEOUT, interval: float = 0.02) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(interval)
        return False

    return _wait


@pytest.fixture
def push_utterance():
    def _push(audio_backend, loud_frames: int = 5, quiet_frames: int = 5) -> None:
        audio_backend.frame_queue.extend([LOUD_FRAME] * loud_frames)
        audio_backend.frame_queue.extend([QUIET_FRAME] * quiet_frames)

    return _push
