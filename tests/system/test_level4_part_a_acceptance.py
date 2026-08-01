"""Level 4 Part A — Device Control & Workflow Automation formal
Acceptance Pass (Sprint 4.13).

One continuous scripted scenario — launch an application, perform file
operations, manage a window, run an approved command, then execute two
multi-step workflows (one exercising continue_on_failure=True alongside
Sprint 4.7's confirmation flow, one exercising continue_on_failure=False)
— through a real CoreManager.startup()/shutdown() with the entire Level
1-4 Part A module graph registered (see conftest.py's app_harness),
asserting Part 4 Phase 4.1 ("Safe desktop control. Permissions
respected.") and Phase 4.2 ("Complex workflows execute correctly.")
together, in one real run.

**Safety scoping** (this sprint's own single largest Potential Risk):
every destructive-shaped operation below is confined to a disposable
tmp_path environment — allowed_file_roots is tmp_path itself
(app_harness's own construction), the only launched/approved executable
is hostname.exe (a real, argument-free, near-instantly-exiting Windows
binary already used for this exact purpose since Sprint 4.11), and the
one "window" operated on is an in-process synthetic test window created
and destroyed by this file itself (_TestWindow, adapted from
tests/unit/device_control/test_window_manager.py's own established
precedent for this exact same environment constraint: an externally
spawned GUI process's window is unreliable to discover here, per Sprint
4.4's own finding, and hostname.exe itself creates no window at all,
exiting too quickly to have one).

**Confirmation is exercised with a real test double, not the real
VoiceConfirmationService, for the "happy path" sections** — per this
sprint's own Data Flow ("auto-confirmed by a test double
ConfirmationService"). This isn't a shortcut: backlog/technical_debt.md
item 26 already established that VoiceConfirmationService.request_
confirmation() structurally cannot receive a real spoken reply when
triggered from within a live turn (or, as here, from a direct call with
no live turn driving it) — so proving a MEDIUM/HIGH-risk action can be
genuinely CONFIRMED and actually executed end-to-end requires standing
in for "a human said yes," exactly as the sprint's own text anticipates.
One deliberate exception is kept UNPATCHED further down (wf-mixed's own
FILE_DELETE step) specifically to re-confirm the real deny-on-timeout
behavior still holds inside a real, full-stack workflow run.

The initial application launch is driven through a genuine live voice
turn (wake -> utterance -> Decision Engine -> DEVICE_CONTROL routing ->
ActionRegistry.dispatch()) to demonstrate Phase 4.1's "Safe desktop
control" via the real user-facing path. Workflow execution itself
(Phase 4.2) is exercised via direct WorkflowExecutor.run() calls rather
than a second live voice turn: Sprint 4.11's own dedicated integration
tests (tests/integration/test_workflow_integration.py) already prove
voice-triggered workflow routing works; re-proving that a third time
here would add no coverage, while direct calls give this sprint's own
genuinely new scenario (continue_on_failure semantics, the dual
whole-workflow/per-step confirmation layering, Sprint 4.12's hardening)
precise control without re-testing the voice-routing layer again.

**Re-confirmation of Sprint 4.12's six hardening scenarios at the
system level** (Objective 2) follows the same judgment Sprint 3.14
applied to Sprint 3.13's own six: scenarios that are purely component-
level, with no composition-dependent behavior, are not re-tested a
third time —
  - (b) FileOperationsManager._handle_move()'s copy-then-verify-then-
    delete sequence needs a locked/read-only source file to exercise
    its own failure path; that adversarial condition is identical
    whether or not the rest of Level 1-4 Part A is running, and is
    already covered for real in tests/unit/device_control/
    test_file_operations.py. This file's own successful move (below)
    re-confirms the sequence's happy path through the full stack.
  - (c) CommandExecutionEngine's subprocess-timeout-kill guarantee is
    already re-confirmed via a real spawned PID + psutil check in
    tests/unit/device_control/test_command_executor.py; re-simulating a
    hang here would add no new coverage and would only slow this suite.
Scenarios (d), (e), and (f) ARE genuinely composition-dependent (a real
WorkflowExecutor/PermissionGate/ActionAuditLog call chain) and are
re-confirmed below as dedicated functions, mirroring test_level3_
acceptance.py's own precedent for its own three "genuinely benefits"
scenarios. Scenario (a) (ApplicationManager's post-spawn readiness
check) is re-confirmed lightly, inline, by checking the field is
genuinely surfaced in a real ActionAuditRecord.

The one remaining Acceptance Criterion — a supervised, real-machine,
human-observed verification pass on the actual target laptop — is
explicitly NOT performed by this automated suite, matching Sprint
2.14's/3.12's/4.11's own precedent of naming a manual step rather than
silently assuming it happened; see this sprint's own completion report.
"""

import threading
from datetime import UTC, datetime

import pywintypes
import win32api
import win32con
import win32gui

from device_control.action_engine import (
    ActionContext,
    ActionRequest,
    ActionStatus,
    ActionType,
)
from device_control.action_log import ActionRecoveryManager, RecoveryOutcome
from device_control.file_operations import FileOperationsManager
from security.confirmation_service import ConfirmationOutcome, ConfirmationRequest
from security.policy_engine import RiskLevel
from workflow.workflow_model import WorkflowDefinition, WorkflowStep

_WAIT_TIMEOUT = 5.0

_WINDOW_CLASS_NAME = "JarminieTestWindow_Level4PartAAcceptance"


def _register_test_window_class() -> None:
    """Duplicated from tests/unit/device_control/test_window_manager.py
    (tests/ has no __init__.py, by convention since Sprint 1.1, so plain
    helpers can't be imported across test files) with a distinct
    lpszClassName so both files' RegisterClass calls coexist safely in
    the same pytest process."""
    wc = win32gui.WNDCLASS()
    wc.lpszClassName = _WINDOW_CLASS_NAME
    wc.lpfnWndProc = {}
    try:
        win32gui.RegisterClass(wc)
    except pywintypes.error as exc:
        if exc.winerror != 1410:  # "Class already exists" -- fine to reuse
            raise


_register_test_window_class()


class _TestWindow:
    """A real win32 window, created and message-pumped on its own
    dedicated thread — see test_window_manager.py's own docstring for
    why a dedicated pumping thread is a correctness requirement (a
    synthetic window's owner thread must actually be pumping messages
    for a cross-thread SetForegroundWindow/MoveWindow/ShowWindow call
    to complete), not just a convenience. Stands in for "the launched
    test application's window" this sprint's own Data Flow describes:
    hostname.exe itself exits too quickly to ever have one, and an
    externally spawned GUI process's window is unreliable to discover
    in this environment (Sprint 4.4's own finding)."""

    def __init__(self, title: str = "Jarminie Level 4 Part A Acceptance Window") -> None:
        self.hwnd = 0
        self._thread_id = 0
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(title,), daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise RuntimeError("Test window did not become ready in time")

    def _run(self, title: str) -> None:
        self._thread_id = win32api.GetCurrentThreadId()
        self.hwnd = win32gui.CreateWindow(
            _WINDOW_CLASS_NAME, title, win32con.WS_OVERLAPPEDWINDOW, 0, 0, 300, 200, 0, 0, 0, None
        )
        win32gui.ShowWindow(self.hwnd, win32con.SW_SHOW)
        self._ready.set()
        win32gui.PumpMessages()

    def close(self) -> None:
        if win32gui.IsWindow(self.hwnd):
            win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
        win32api.PostThreadMessage(self._thread_id, win32con.WM_QUIT, 0, 0)
        self._thread.join(timeout=2.0)


class _AutoConfirmingConfirmationService:
    """A real test double standing in for a human saying "yes" — see
    this module's own docstring for why the real VoiceConfirmationService
    cannot be used for the "happy path" sections of this scenario."""

    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationOutcome:
        return ConfirmationOutcome.CONFIRMED


def _reset_wake_detection(h) -> None:
    """See tests/system/test_level3_acceptance.py's own copy of this
    helper for the full rationale (a real, previously-reproduced timing
    race, Sprint 3.12)."""
    h.wake_engine.calls = 0


def _make_request(action_type: ActionType, requested_by: str, **parameters) -> ActionRequest:
    return ActionRequest(
        action_type=action_type,
        parameters=parameters,
        context=ActionContext(requested_by=requested_by),
        requested_at=datetime.now(UTC),
    )


def test_level4_part_a_full_acceptance_scenario(
    app_harness, wait_for_active_capture, wait_for_dormant, push_utterance, monkeypatch, tmp_path
):
    h = app_harness

    # --- 1. Live voice turn: wake -> utterance -> Decision Engine routes
    # to DEVICE_CONTROL -> a real hostname.exe launch (Phase 4.1). --------
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)
    h.llm_client.intent_response = "CATEGORY: ACTION_REQUEST\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: launch an application\nENTITIES: hostname\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    h.stt.pending_transcripts.append("open hostname")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_WAIT_TIMEOUT)
    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text == "Done — I've opened hostname.exe."

    launch_records = h.audit_log.query(action_type=ActionType.LAUNCH_APPLICATION, limit=5)
    assert len(launch_records) == 1
    assert launch_records[0].status == "succeeded"
    # Sprint 4.12 scenario (a), re-confirmed at the system level: the
    # post-spawn readiness check's own outcome is genuinely surfaced in
    # a real persisted audit record. Not asserted True/False — for a
    # process as fast-exiting as hostname.exe, whether it's still
    # "alive" at the end of a 0.5s bounded poll is a real, honest
    # timing question this sprint doesn't need to pin down, only prove
    # is visible.
    assert "readiness_confirmed=" in launch_records[0].parameters_summary

    wait_for_dormant(h.quiet_mode_controller)
    assert not h.session_manager.is_active()

    # --- 2-4. File operations, window management, and an approved
    # command all dispatched directly against the real ActionRegistry /
    # PermissionGate / ActionResourceGate / ActionAuditLog stack — the
    # session has already ended, so the real VoiceConfirmationService
    # would otherwise deny every MEDIUM/HIGH-risk step immediately
    # (is_active() is False); the auto-confirming double stands in for
    # "the user said yes" per this module's own docstring. ---------------
    monkeypatch.setattr(
        h.action_registry._permission_gate,
        "_confirmation_service",
        _AutoConfirmingConfirmationService(),
    )

    scratch_dir = tmp_path / "scratch"
    result = h.action_registry.dispatch(
        _make_request(ActionType.FOLDER_CREATE, "acceptance_test", path=str(scratch_dir))
    )
    assert result.status is ActionStatus.SUCCEEDED
    assert scratch_dir.is_dir()

    original_file = scratch_dir / "note.txt"
    result = h.action_registry.dispatch(
        _make_request(
            ActionType.FILE_CREATE,
            "acceptance_test",
            path=str(original_file),
            content="hello from Sprint 4.13",
        )
    )
    assert result.status is ActionStatus.SUCCEEDED
    assert original_file.read_text(encoding="utf-8") == "hello from Sprint 4.13"

    moved_file = scratch_dir / "note_moved.txt"
    result = h.action_registry.dispatch(
        _make_request(
            ActionType.FILE_MOVE,
            "acceptance_test",
            source=str(original_file),
            destination=str(moved_file),
        )
    )
    # Sprint 4.12 scenario (b), happy path re-confirmed through the full
    # stack: the copy-then-verify-then-delete sequence completes
    # cleanly with no source/destination duplication.
    assert result.status is ActionStatus.SUCCEEDED
    assert not original_file.exists()
    assert moved_file.read_text(encoding="utf-8") == "hello from Sprint 4.13"

    result = h.action_registry.dispatch(
        _make_request(
            ActionType.FILE_RENAME,
            "acceptance_test",
            path=str(moved_file),
            new_name="note_final.txt",
        )
    )
    assert result.status is ActionStatus.SUCCEEDED
    final_file = scratch_dir / "note_final.txt"
    assert final_file.exists()

    result = h.action_registry.dispatch(
        _make_request(ActionType.FILE_DELETE, "acceptance_test", path=str(final_file))
    )
    assert result.status is ActionStatus.SUCCEEDED
    assert not final_file.exists()

    # Recycle-bin recoverability, the same real, on-disk-$I/$R-parsing
    # mechanism Sprint 4.8 built and verified — reused here, not
    # re-derived, per the "component-level, no new coverage from
    # re-deriving it" reasoning already applied to scenarios (b)/(c)
    # above.
    delete_record = h.audit_log.query(action_type=ActionType.FILE_DELETE, limit=1)[0]
    recovery_manager = ActionRecoveryManager(
        h.audit_log, FileOperationsManager(h.device_control_config), h.application_manager
    )
    outcome = recovery_manager.attempt_recovery(delete_record)
    assert outcome is RecoveryOutcome.RECOVERED
    assert final_file.read_text(encoding="utf-8") == "hello from Sprint 4.13"

    # --- Window management against a real, disposable in-process test
    # window (see this module's own docstring for why not hostname.exe
    # itself). focus/move/minimize only, matching this sprint's own
    # Data Flow. -----------------------------------------------------
    test_window = _TestWindow()
    try:
        result = h.action_registry.dispatch(
            _make_request(
                ActionType.WINDOW_MOVE,
                "acceptance_test",
                operation="move",
                handle=test_window.hwnd,
                x=40,
                y=50,
            )
        )
        assert result.status is ActionStatus.SUCCEEDED
        rect = win32gui.GetWindowRect(test_window.hwnd)
        assert (rect[0], rect[1]) == (40, 50)

        result = h.action_registry.dispatch(
            _make_request(
                ActionType.WINDOW_MINIMIZE,
                "acceptance_test",
                operation="minimize",
                handle=test_window.hwnd,
            )
        )
        assert result.status is ActionStatus.SUCCEEDED
        assert win32gui.IsIconic(test_window.hwnd)

        # SetForegroundWindow cannot be verified as genuinely succeeding
        # in this automation environment (a real, repeated finding since
        # Sprint 4.2/4.4) -- mocked here exactly like test_window_manager.py's
        # own established precedent for the identical restriction.
        monkeypatch.setattr(
            "device_control.window_manager.win32gui.SetForegroundWindow", lambda hwnd: None
        )
        monkeypatch.setattr(
            "device_control.window_manager.win32gui.GetForegroundWindow", lambda: test_window.hwnd
        )
        result = h.action_registry.dispatch(
            _make_request(
                ActionType.WINDOW_FOCUS,
                "acceptance_test",
                operation="focus",
                handle=test_window.hwnd,
            )
        )
        assert result.status is ActionStatus.SUCCEEDED
    finally:
        test_window.close()

    # --- An approved (test-only) command executes, output captured. -----
    h.device_control_config.approved_commands.append("hostname.exe")
    result = h.action_registry.dispatch(
        _make_request(ActionType.SYSTEM_COMMAND, "acceptance_test", command=["hostname.exe"])
    )
    assert result.status is ActionStatus.SUCCEEDED
    assert result.output.exit_code == 0
    assert result.output.stdout.strip() != ""

    # --- 5. A multi-step workflow mixing a LOW-risk failing step
    # (continue_on_failure=True) with a HIGH-risk step whose OWN
    # per-step confirmation is deliberately left on the REAL
    # VoiceConfirmationService (restored below) -- re-confirming Sprint
    # 4.7's real deny-on-timeout behavior still holds inside a real,
    # full-stack workflow run, exactly as backlog/technical_debt.md item
    # 26 already documented. Only the WHOLE-WORKFLOW prompt is
    # auto-confirmed. -----------------------------------------------
    monkeypatch.undo()  # restores the real VoiceConfirmationService on permission_gate
    monkeypatch.setattr(
        h.workflow_executor, "_confirmation_service", _AutoConfirmingConfirmationService()
    )

    mixed_folder = str(tmp_path / "wf_mixed_folder")
    workflow_context = ActionContext(requested_by="acceptance_test")
    mixed_definition = WorkflowDefinition(
        workflow_id="wf-mixed",
        name="Mixed continue-on-failure",
        steps=[
            WorkflowStep(
                step_index=0,
                action_type=ActionType.FOLDER_CREATE,
                parameters={"path": mixed_folder},
                description="Create the working folder",
                continue_on_failure=True,
            ),
            WorkflowStep(
                step_index=1,
                action_type=ActionType.FOLDER_CREATE,
                parameters={"path": mixed_folder},
                description="Create the same folder again (deliberately fails)",
                continue_on_failure=True,
            ),
            WorkflowStep(
                step_index=2,
                action_type=ActionType.FILE_DELETE,
                parameters={"path": str(tmp_path / "does_not_exist.txt")},
                description="Delete a nonexistent file (HIGH risk; real per-step confirmation)",
                continue_on_failure=True,
            ),
            WorkflowStep(
                step_index=3,
                action_type=ActionType.LAUNCH_APPLICATION,
                parameters={"operation": "launch", "executable_path": "hostname.exe"},
                description="Launch hostname",
                continue_on_failure=True,
            ),
        ],
        created_by="test",
        created_at=datetime.now(UTC),
        is_enabled=True,
    )
    h.workflow_store.save(mixed_definition)

    mixed_result = h.workflow_executor.run("wf-mixed", workflow_context)

    assert mixed_result.whole_workflow_confirmation is ConfirmationOutcome.CONFIRMED
    assert mixed_result.aborted_early is False
    statuses = [r.action_result.status for r in mixed_result.step_results]
    assert statuses == [
        ActionStatus.SUCCEEDED,
        ActionStatus.FAILED,
        ActionStatus.DENIED,  # real confirmation timeout -- no live session to answer it
        ActionStatus.SUCCEEDED,
    ]
    assert all(not r.skipped for r in mixed_result.step_results)

    # --- 6. A second workflow with NO high-risk step (no whole-workflow
    # prompt at all -- distinct coverage from wf-mixed above) and
    # continue_on_failure=False on its own failing step, proving the
    # abort-and-skip-the-rest path. ----------------------------------
    abort_folder = str(tmp_path / "wf_abort_folder")
    abort_definition = WorkflowDefinition(
        workflow_id="wf-abort",
        name="Abort on failure",
        steps=[
            WorkflowStep(
                step_index=0,
                action_type=ActionType.FOLDER_CREATE,
                parameters={"path": abort_folder},
                description="Create the working folder",
            ),
            WorkflowStep(
                step_index=1,
                action_type=ActionType.FOLDER_CREATE,
                parameters={"path": abort_folder},
                description="Create the same folder again (deliberately fails)",
            ),
            WorkflowStep(
                step_index=2,
                action_type=ActionType.LAUNCH_APPLICATION,
                parameters={"operation": "launch", "executable_path": "hostname.exe"},
                description="Never reached",
            ),
        ],
        created_by="test",
        created_at=datetime.now(UTC),
        is_enabled=True,
    )
    h.workflow_store.save(abort_definition)

    abort_result = h.workflow_executor.run("wf-abort", workflow_context)

    assert abort_result.whole_workflow_confirmation is None
    assert abort_result.aborted_early is True
    assert abort_result.step_results[0].action_result.status is ActionStatus.SUCCEEDED
    assert abort_result.step_results[0].skipped is False
    assert abort_result.step_results[1].action_result.status is ActionStatus.FAILED
    assert abort_result.step_results[1].skipped is False
    assert abort_result.step_results[2].skipped is True
    assert abort_result.step_results[2].action_result.status is ActionStatus.PENDING

    # --- Every Level 1-4 Part A (+ Part B's own two ManagedModules,
    # registered early per Sprint 4.18's own ordering requirement) is
    # registered and running. -------
    states = h.core_manager.module_states()
    assert set(states) == {
        "task_scheduler",
        "calendar_store",
        "microphone",
        "speech_to_text",
        "text_to_speech",
        "conversation_store",
        "persona_manager",
        "voice_session_manager",
        "quiet_mode_controller",
        "wake_word_detector",
        "communication_pipeline",
        "memory_store",
        "memory_lifecycle_manager",
        "intent_detector",
        "context_analyzer",
        "priority_queue_manager",
        "authority_evaluator",
        "action_audit_log",
        "workflow_store",
    }
    assert all(state == "running" for state in states.values())


# --- Sprint 4.12 hardening scenarios (d)/(e)/(f), re-confirmed at the
# system level -- see this module's own docstring for why (a) is folded
# into the scenario above and (b)/(c) are deliberately not re-tested a
# third time. -------------------------------------------------------


def test_workflow_executor_degrades_gracefully_when_workflow_store_get_raises(
    app_harness, monkeypatch
):
    """Scenario (d), system level: an internal WorkflowStore fault
    degrades to a reportable abort rather than propagating out of
    WorkflowExecutor.run(), through the real, fully-wired graph."""
    h = app_harness

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated WorkflowStore internal fault")

    monkeypatch.setattr(h.workflow_store, "get", _raise)

    result = h.workflow_executor.run("does-not-matter", ActionContext(requested_by="test"))

    assert result.aborted_early is True
    assert result.step_results == []


def test_confirmation_service_degrades_to_timed_out_when_session_manager_fails_mid_request(
    app_harness, wait_for_active_capture, monkeypatch
):
    """Scenario (e), system level: a real VoiceSessionManager failure
    mid-request (not the already-covered "no active session" case)
    degrades to TIMED_OUT rather than raising, with a genuinely active
    session in place through the real, fully-wired graph."""
    h = app_harness
    _reset_wake_detection(h)
    wait_for_active_capture(h.mic)
    assert h.session_manager.is_active()

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated VoiceSessionManager failure mid-request")

    monkeypatch.setattr(h.session_manager, "speak_reply", _raise)

    dummy_request = _make_request(ActionType.FILE_DELETE, "test", path="C:/does/not/matter.txt")
    confirmation_request = ConfirmationRequest(
        action_request=dummy_request, risk_level=RiskLevel.HIGH, prompt_text="Should I proceed?"
    )

    outcome = h.action_registry._permission_gate._confirmation_service.request_confirmation(
        confirmation_request
    )

    assert outcome is ConfirmationOutcome.TIMED_OUT


def test_dispatch_result_survives_when_audit_log_record_raises(app_harness, monkeypatch):
    """Scenario (f), system level: ActionRegistry.dispatch()'s own outer
    guard around audit_log.record() means a real action's own genuine
    result is never lost just because logging it failed, through the
    real, fully-wired graph."""
    h = app_harness

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated audit log fault")

    monkeypatch.setattr(h.audit_log, "record", _raise)

    request = _make_request(
        ActionType.LAUNCH_APPLICATION, "test", operation="launch", executable_path="hostname.exe"
    )
    result = h.action_registry.dispatch(request)

    assert result.status is ActionStatus.SUCCEEDED
