"""Shared fixtures for tests/system/ — full-application system tests that
go through a real CoreManager.startup()/shutdown() with the entire Level
2 AND Level 3 module graph registered, the same way main.py's own
_register_level2_modules()/_register_level3_modules() (Sprint 3.12) do.
This is what distinguishes this tier from tests/integration/: those
tests start each module individually in a hand-picked order via the
pipeline_harness fixture; this tier instead proves CoreManager's
registration/startup/shutdown-order guarantees themselves hold for the
real, full graph.

Fakes stand in only at the audio-hardware/ML boundary (mic, wake engine,
STT, TTS, and now the Ollama-backed LanguageModelClient), same as
tests/integration/conftest.py — kept self-contained rather than shared
across test tiers, matching this project's existing per-directory
conftest convention (tests/unit/voice/conftest.py and
tests/unit/personas/conftest.py are likewise independent of each other).
Chroma/SQLite are real, matching every Level 3 unit test's own
established convention.
"""

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config.schema import (
    AppConfig,
    DatabaseConfig,
    DeviceControlConfig,
    InternetConfig,
    MemoryConfig,
    SchedulerConfig,
    SecurityConfig,
    VoiceConfig,
    WorkflowConfig,
)
from core.manager import CoreManager
from core.resource_monitor import ResourceMonitor
from database.sqlite_client import SqliteClient
from decision.authority import AuthorityEvaluator
from decision.context_analyzer import ContextAnalyzer
from decision.intent_detector import IntentDetector
from decision.priority_queue import PriorityQueueManager
from device_control.action_engine import ActionRegistry
from device_control.action_log import ActionAuditLog
from device_control.application_manager import ApplicationManager
from device_control.command_executor import CommandExecutionEngine
from device_control.file_operations import FileOperationsManager
from device_control.resource_gate import ActionResourceGate
from device_control.window_manager import WindowManager
from internet.research_engine import ResearchEngine
from internet.search_provider import SearchResult
from internet.source_validator import SourceValidator
from internet.summarizer import Summarizer
from memory.chroma_client import ChromaMemoryClient
from memory.confidence_scorer import ConfidenceScorer
from memory.event_memory import EventMemory
from memory.lifecycle_manager import MemoryLifecycleManager
from memory.memory_store import MemoryStore
from memory.persona_scoped_memory import PersonaScopedMemory
from memory.retrieval_engine import MemoryRetrievalEngine
from memory.short_term_memory import ShortTermMemory
from personas.jarvis import JarvisPersona
from personas.minie import MiniePersona
from personas.persona_manager import PersonaManager
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
from workflow.workflow_executor import WorkflowExecutor
from workflow.workflow_store import WorkflowStore

WAIT_TIMEOUT = 5.0

LOUD_FRAME = b"\xff\x7f" * 480
QUIET_FRAME = b"\x00\x00" * 480


class FakeAudioBackend:
    def __init__(self) -> None:
        self.is_open = False
        self.frame_queue: list[bytes] = []

    def open(self, device_index: int | None, sample_rate_hz: int) -> None:
        self.is_open = True

    def read(self, num_frames: int) -> bytes:
        if self.frame_queue:
            return self.frame_queue.pop(0)
        return b"\x00\x00" * num_frames

    def flush(self) -> None:
        """VoiceSessionManager.begin_session() calls this immediately
        after switching to ACTIVE_CAPTURE (post-release fix) — safe to
        genuinely clear frame_queue here since this test only calls
        push_utterance() after the session has already begun."""
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
    def __init__(self) -> None:
        self.pending_transcripts: list[str] = []

    def transcribe(self, audio: bytes) -> TranscriptionResult:
        text = self.pending_transcripts.pop(0) if self.pending_transcripts else ""
        return TranscriptionResult(text=text, average_confidence=0.9, duration_ms=1)


class FakeTextToSpeech:
    def __init__(self) -> None:
        self.speak_calls: list[tuple[str, str]] = []
        self.spoken_event = threading.Event()

    def speak(self, text: str, voice_id: str) -> None:
        self.speak_calls.append((text, voice_id))
        self.spoken_event.set()


class FakeLanguageModelClient:
    """Fakes only the Ollama boundary IntentDetector/ContextAnalyzer
    depend on — see this module's own docstring. Dispatches on prompt
    content: IntentDetector's own prompt always instructs a "CATEGORY:"
    line; ContextAnalyzer's never does.

    should_raise (Sprint 3.14, re-confirming Sprint 3.13's scenario (a)
    at the system level) simulates Ollama being entirely unreachable —
    same convention as tests/integration/conftest.py's own fake.

    summary_response (Sprint 4.18) is returned for internet/
    summarizer.py's own prompt — detected via the literal "Search
    results:" substring only that prompt template contains, same
    dispatch discipline as tests/integration/conftest.py's own
    identical fake."""

    def __init__(self) -> None:
        self.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
        self.context_response = (
            "TOPIC: general\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
            "PERSONA: NONE\nSENTIMENT: NEUTRAL"
        )
        self.summary_response = "Here is a summary based on the provided sources."
        self.should_raise = False

    def generate(self, prompt: str, timeout_seconds: float) -> str:
        if self.should_raise:
            from decision.llm_client import LlmError

            raise LlmError("simulated Ollama connection failure")
        if "CATEGORY:" in prompt:
            return self.intent_response
        if "Search results:" in prompt:
            return self.summary_response
        return self.context_response


class FakeSearchProvider:
    """Local double implementing the SearchProvider Protocol (Sprint
    4.18) — same shape as tests/integration/conftest.py's own identical
    fake, duplicated here per this project's established "each conftest
    kept self-contained rather than shared across test tiers"
    convention."""

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


class _StartStopWrapper:
    """FakeSpeechToText/FakeTextToSpeech need no real load/release step,
    unlike the real WhisperSpeechToText/CoquiTextToSpeech they stand in
    for — this thin ManagedModule adapter is what main.py's real
    _register_level2_modules() doesn't need (the real classes already
    implement start()/stop()/health_check() themselves) but this fake-
    based harness does, purely so CoreManager.startup()/shutdown() has
    something to call."""

    def __init__(self, fake) -> None:
        self._fake = fake
        self._started = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def health_check(self) -> bool:
        return self._started

    def __getattr__(self, name):
        return getattr(self._fake, name)


@pytest.fixture
def voice_config() -> VoiceConfig:
    """session_timeout_seconds=3.0 (was 0.8 before Sprint 3.12): this
    tier drives startup through a real CoreManager.startup(), which
    starts every registered module in registration order — including,
    now, Level 3's memory/decision modules — before returning control to
    the test. With FakeWakeWordEngine(match_on_call=2) configured to
    match almost immediately once frames start flowing, a too-short
    session_timeout_seconds risks the entire wake -> active -> timeout
    -> passive cycle completing during fixture setup itself, before the
    test's own wait_for_active_capture() polling loop ever starts —
    concretely reproduced (mic observed already back in
    PASSIVE_LISTENING for the whole 5s poll window) once Level 3's added
    startup latency (~1-1.5s for MemoryStore's Chroma embedding-model
    load) was introduced. 3.0s leaves comfortable margin against that
    startup cost while still safely fitting within wait_for_dormant()'s
    own 5.0s poll window at the end of the test. tests/integration/
    conftest.py's pipeline_harness fixture never had this risk — it
    starts wake_word_detector last, by hand, after every other module
    including communication_pipeline.

    max_utterance_seconds=10.0 (was 2.0): the same early-wake-match issue
    means the session's utterance-capture clock can start ticking during
    fixture setup, well before the test calls push_utterance() — a
    max_utterance_seconds too close to the realistic setup-to-first-push
    gap let the safety cap force an empty "utterance complete" before the
    test's real pushed audio was ever read, concretely reproduced
    (first spoken reply was the empty-transcript fallback, not the
    scripted transcript) once Level 3's added startup latency widened
    that gap. 10.0s leaves comfortable margin; the silence-based
    utterance-end detection (utterance_silence_ms/threshold) still
    completes each real pushed utterance almost immediately regardless,
    so this only changes how long a truly-silent session can run before
    the safety cap intervenes, not real per-turn latency."""
    return VoiceConfig(
        mic_sample_rate_hz=16000,
        utterance_silence_ms=30,
        utterance_silence_threshold=0.02,
        max_utterance_seconds=10.0,
        session_timeout_seconds=3.0,
    )


def _app_harness_impl(tmp_path, voice_config, scheduler_config: SchedulerConfig):
    """Builds the real Level 2 + Level 3 module graph exactly as main.py's
    _register_level2_modules()/_register_level3_modules() do, registers
    every ManagedModule with a real CoreManager, and drives it through
    startup()/shutdown() — fakes only at the mic/wake-engine/STT/TTS/
    Ollama boundary.

    scheduler_config is caller-supplied (Sprint 4.20) so app_harness
    (below) can keep SchedulerConfig()'s realistic 30s/3600s defaults —
    used by every existing tests/system/ file, none of which need Level
    4 Part B's background jobs to ever fire — while fast_scheduler_app_
    harness opts into short intervals for the one new file that needs to
    observe real recurrence (a proactive reminder announcement, the
    three maintenance passes firing more than once) within a bounded
    system test.

    fast_scheduler_app_harness relies on core_manager.shutdown()'s own
    plain reverse-registration-order stop, unmodified — task_scheduler/
    calendar_store are registered first (see the real ordering
    requirement documented at their own registration below), so with
    short intervals a background job can genuinely still be executing
    against another store's SqliteClient connection at the exact moment
    that store's own stop() closes it. This is verified safe, not just
    assumed: database/sqlite_client.py's own Sprint 4.19 threading.Lock
    (added to fix a genuine concurrent-corruption bug, not this one)
    serializes close() against execute()/query() on the same lock —
    confirmed directly with a standalone reproduction (a background
    thread hammering execute() while close() runs concurrently from the
    main thread) before relying on it here: close() returns in ~16ms
    with no hang, and the background thread's very next call cleanly
    raises RuntimeError("SqliteClient.connect() must be called before
    use.") — the same caught-and-logged-without-crashing outcome
    APScheduler's own default executor already guarantees for any job
    exception (Sprint 4.15's own established, tested behavior)."""
    config = AppConfig(
        voice=voice_config,
        database=DatabaseConfig(
            sqlite_path=str(tmp_path / "conversations.db"),
            chroma_path=str(tmp_path / "chroma"),
        ),
        memory=MemoryConfig(chroma_collection_prefix="app_harness"),
    )
    resource_monitor = ResourceMonitor(config.resources)
    core_manager = CoreManager(config, resource_monitor, config_loader=MagicMock())

    audio_backend = FakeAudioBackend()
    mic = MicrophoneManager(config.voice, audio_backend)
    stt = FakeSpeechToText()
    tts = FakeTextToSpeech()

    sqlite_client = SqliteClient(config.database.sqlite_path)
    conversation_store = ConversationSessionStore(sqlite_client, config.database)
    context_manager = ContextManager(conversation_store)

    jarvis = JarvisPersona(config.voice)
    minie = MiniePersona(config.voice)
    persona_manager = PersonaManager(jarvis, minie, config.voice)

    turn_complete_relay = CallbackRelay()
    session_ended_relay = CallbackRelay()
    session_manager = VoiceSessionManager(
        mic, stt, tts, config.voice, turn_complete_relay, session_ended_relay
    )
    quiet_mode_controller = QuietModeController(session_manager)

    wake_engine = FakeWakeWordEngine(match_on_call=2)
    wake_word_detector = WakeWordDetector(
        mic, wake_engine, quiet_mode_controller._on_wake_word_detected
    )

    memory_sqlite_client = SqliteClient(config.database.sqlite_path)
    chroma_client = ChromaMemoryClient(config.memory, config.database)
    memory_store = MemoryStore(memory_sqlite_client, chroma_client)
    persona_scoped_memory = PersonaScopedMemory(memory_store)
    event_memory = EventMemory(memory_store)
    short_term_memory = ShortTermMemory(memory_store, config.memory)
    confidence_scorer = ConfidenceScorer(config.memory)
    memory_lifecycle_manager = MemoryLifecycleManager(
        memory_store, confidence_scorer, config.memory
    )
    memory_retrieval_engine = MemoryRetrievalEngine(
        persona_scoped_memory, event_memory, short_term_memory, confidence_scorer, config.memory
    )

    llm_client = FakeLanguageModelClient()
    intent_detector = IntentDetector(llm_client, config.models)
    context_analyzer = ContextAnalyzer(llm_client, config.models)
    priority_queue_manager = PriorityQueueManager(resource_monitor)
    authority_evaluator = AuthorityEvaluator()

    # Sprint 4.11: Level 4 Part A, safety-scoped the same way
    # tests/integration/conftest.py's own pipeline_harness is —
    # allowed_file_roots confined to tmp_path, application_allowlist
    # naming only hostname.exe (see that file's own fixture docstring
    # for why: a real, argument-free, instantly-exiting Windows binary,
    # never a real installed application on the developer's own machine).
    device_control_config = DeviceControlConfig(
        allowed_file_roots=[str(tmp_path)],
        application_allowlist=["hostname.exe"],
        # Post-Sprint Fix (Sprint 4.12): see tests/integration/conftest.py's
        # own pipeline_harness for why — real resource sampling against
        # the actual host machine is a genuine, non-deterministic
        # dependency this harness otherwise avoids everywhere else.
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
    audit_sqlite_client = SqliteClient(config.database.sqlite_path)
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

    workflow_sqlite_client = SqliteClient(config.database.sqlite_path)
    workflow_store = WorkflowStore(workflow_sqlite_client, workflow_config)
    workflow_executor = WorkflowExecutor(
        workflow_store, action_registry, policy_engine, confirmation_service, workflow_config
    )

    # Sprint 4.18 (Scheduler & Internet Agent Integration) — Level 4
    # Part B. scheduler_config is caller-supplied (Sprint 4.20) — see
    # this function's own docstring.
    internet_config = InternetConfig()

    task_scheduler = TaskScheduler()
    calendar_sqlite_client = SqliteClient(config.database.sqlite_path)
    calendar_store = CalendarStore(calendar_sqlite_client, scheduler_config)
    reminder_engine = ReminderEngine(
        calendar_store, priority_queue_manager, task_scheduler, scheduler_config
    )

    fake_search_provider = FakeSearchProvider()
    research_engine = ResearchEngine(fake_search_provider, internet_config)
    source_validator = SourceValidator(internet_config)
    summarizer = Summarizer(llm_client, internet_config, config.models)

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
    )

    # task_scheduler/calendar_store registered FIRST, before even
    # microphone — the one deliberate exception to this fixture's own
    # "register in main.py's own real order" discipline (see main.py's
    # own _register_level4_part_b_early() docstring for the full
    # reasoning): CommunicationPipeline.start() (Sprint 4.18) calls
    # task_scheduler.add_job() directly, which requires TaskScheduler.
    # start() to have already run — CoreManager.startup() below starts
    # every registered module in registration order.
    core_manager.register_module("task_scheduler", task_scheduler)
    core_manager.register_module("calendar_store", calendar_store)
    core_manager.register_module("microphone", mic)
    core_manager.register_module("speech_to_text", _StartStopWrapper(stt))
    core_manager.register_module("text_to_speech", _StartStopWrapper(tts))
    core_manager.register_module("conversation_store", conversation_store)
    core_manager.register_module("persona_manager", persona_manager)
    core_manager.register_module("voice_session_manager", session_manager)
    core_manager.register_module("quiet_mode_controller", quiet_mode_controller)
    core_manager.register_module("wake_word_detector", wake_word_detector)
    # communication_pipeline is registered immediately after
    # wake_word_detector, BEFORE any Level 3 module — a deliberate
    # ordering (see main.py's own _register_level3_modules() docstring
    # for the full reasoning): CoreManager.startup() calls start() in
    # registration order, and wake_word_detector's background thread can
    # fire as soon as its own start() runs. If a slower Level 3 start()
    # (memory_store's Chroma embedding-model load) sat between
    # wake_word_detector and communication_pipeline, a session could
    # complete/time out and route through on_session_ended/on_turn_
    # complete's relays before communication_pipeline.start() has wired
    # them — concretely observed as a real, reproducible failure in this
    # exact fixture (short session_timeout_seconds) before this fix.
    core_manager.register_module("communication_pipeline", pipeline)
    core_manager.register_module("memory_store", memory_store)
    core_manager.register_module("memory_lifecycle_manager", memory_lifecycle_manager)
    core_manager.register_module("intent_detector", intent_detector)
    core_manager.register_module("context_analyzer", context_analyzer)
    core_manager.register_module("priority_queue_manager", priority_queue_manager)
    core_manager.register_module("authority_evaluator", authority_evaluator)
    # Sprint 4.11: Level 4 Part A's own two real ManagedModules, registered
    # after Level 3 for the identical reason Level 3 is registered after
    # communication_pipeline above — see main.py's own
    # _register_level4_modules() docstring.
    core_manager.register_module("action_audit_log", audit_log)
    core_manager.register_module("workflow_store", workflow_store)

    core_manager.startup()

    harness = SimpleNamespace(
        core_manager=core_manager,
        mic=mic,
        audio_backend=audio_backend,
        stt=stt,
        tts=tts,
        wake_engine=wake_engine,
        conversation_store=conversation_store,
        persona_manager=persona_manager,
        session_manager=session_manager,
        quiet_mode_controller=quiet_mode_controller,
        # Sprint 3.14 (Level 3 Acceptance Pass) additions — every Level 3
        # collaborator already constructed above, now exposed so the new
        # system test can exercise memory/confidence/lifecycle/priority
        # behavior directly, not just observe it indirectly through a
        # spoken reply.
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
        priority_queue_manager=priority_queue_manager,
        authority_evaluator=authority_evaluator,
        resource_monitor=resource_monitor,
        # Sprint 4.11 (Workflow & Device Control Integration) additions.
        action_registry=action_registry,
        application_manager=application_manager,
        audit_log=audit_log,
        workflow_store=workflow_store,
        workflow_executor=workflow_executor,
        device_control_config=device_control_config,
        # Sprint 4.18 (Scheduler & Internet Agent Integration) additions.
        task_scheduler=task_scheduler,
        calendar_store=calendar_store,
        reminder_engine=reminder_engine,
        fake_search_provider=fake_search_provider,
        research_engine=research_engine,
        source_validator=source_validator,
        summarizer=summarizer,
        scheduler_config=scheduler_config,
        internet_config=internet_config,
    )
    try:
        yield harness
    finally:
        core_manager.shutdown()


@pytest.fixture
def app_harness(tmp_path, voice_config):
    """SchedulerConfig() (realistic, slow defaults) — see
    _app_harness_impl()'s own docstring for why. Every existing system
    test in this directory uses this fixture; only
    test_level4_part_b_acceptance.py opts into fast_scheduler_app_
    harness below instead."""
    yield from _app_harness_impl(tmp_path, voice_config, SchedulerConfig())


@pytest.fixture
def fast_scheduler_app_harness(tmp_path, voice_config):
    """Identical object graph to app_harness, but with short
    poll_interval_seconds/maintenance_interval_seconds (0.3s, matching
    tests/integration/conftest.py's own fast_scheduler_harness — see its
    docstring for why 0.3s, not more aggressive) so
    test_level4_part_b_acceptance.py can observe real recurrence (a
    proactive reminder announcement, the three maintenance passes firing
    more than once) within a normal system test's own patience, through
    the real, complete CoreManager graph."""
    fast_config = SchedulerConfig(poll_interval_seconds=0.3, maintenance_interval_seconds=0.3)
    yield from _app_harness_impl(tmp_path, voice_config, fast_config)


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
def push_utterance():
    def _push(audio_backend, loud_frames: int = 5, quiet_frames: int = 5) -> None:
        audio_backend.frame_queue.extend([LOUD_FRAME] * loud_frames)
        audio_backend.frame_queue.extend([QUIET_FRAME] * quiet_frames)

    return _push


@pytest.fixture
def wait_until():
    """Generic bounded-poll helper (Sprint 4.20) — the same "poll a real
    observable state, never blindly sleep-and-hope" discipline as
    wait_for_active_capture/wait_for_dormant above, matching tests/
    integration/conftest.py's own identical fixture, for conditions
    those two named fixtures don't cover (a priority queue peek, a TTS
    call count, a maintenance job's own call counter). Returns True/
    False rather than raising, so a caller can assert with its own
    descriptive message."""

    def _wait(predicate, timeout: float = WAIT_TIMEOUT, interval: float = 0.02) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(interval)
        return False

    return _wait
