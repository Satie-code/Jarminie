"""Integration tests for the live-turn-to-real-WorkflowExecutor round
trip (Sprint 4.11, Workflow & Device Control Integration) — the first
real exercise of DecisionTrace.selected_engine == WORKFLOW actually
reaching WorkflowExecutor.run() through a full, real conversation turn.

See tests/integration/conftest.py's pipeline_harness fixture for the
shared object graph and this file's own safety scoping.
"""

import time
from datetime import UTC, datetime
from pathlib import Path

from device_control.action_engine import ActionType
from workflow.workflow_model import WorkflowDefinition, WorkflowStep

_SPEAK_POLL_TIMEOUT = 8.0


def _set_action_request(h, entity: str, topic: str = "run a workflow") -> None:
    h.llm_client.intent_response = "CATEGORY: ACTION_REQUEST\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        f"TOPIC: {topic}\nENTITIES: {entity}\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )


def _wait_for_speak_call_count(tts, count: int, timeout: float = _SPEAK_POLL_TIMEOUT) -> None:
    """h.tts.spoken_event is set (not cleared) on every speak() call, so
    it can't distinguish "the first reply landed" from "the second
    reply landed" on its own — this polls speak_calls' own length
    directly instead, the same "poll a real observable state" style as
    wait_for_active_capture/wait_for_dormant in conftest.py."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(tts.speak_calls) >= count:
            return
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for {count} speak_reply() call(s).")


def test_full_wake_to_workflow_round_trip(
    pipeline_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Acceptance Criteria: "A live conversation turn naming a stored,
    enabled workflow is correctly routed through EngineSelection.WORKFLOW
    and executed via WorkflowExecutor.run()." Two LOW-risk, tmp_path/
    hostname.exe-scoped steps — well under large_workflow_step_threshold
    (5) and with no HIGH-risk step, so no whole-workflow confirmation is
    triggered; the run completes straight through."""
    h = pipeline_harness
    folder_path = h.device_control_config.allowed_file_roots[0] + "\\wf_folder"
    definition = WorkflowDefinition(
        workflow_id="wf-setup",
        name="Setup",
        steps=[
            WorkflowStep(
                step_index=0,
                action_type=ActionType.FOLDER_CREATE,
                parameters={"path": folder_path},
                description="Create the working folder",
            ),
            WorkflowStep(
                step_index=1,
                action_type=ActionType.LAUNCH_APPLICATION,
                parameters={"operation": "launch", "executable_path": "hostname.exe"},
                description="Launch hostname",
            ),
        ],
        created_by="test",
        created_at=datetime.now(UTC),
        is_enabled=True,
    )
    h.workflow_store.save(definition)
    _set_action_request(h, "setup")

    wait_for_active_capture(h.mic)
    h.stt.pending_transcripts.append("run the setup workflow")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=5.0)
    reply_text, _ = h.tts.speak_calls[0]
    # "Setup" (the stored WorkflowDefinition's own proper-cased name),
    # not "setup" (the lowercase entity FakeLanguageModelClient's own
    # canned ENTITIES: line happened to return) — proves
    # _handle_workflow_turn() names the workflow the way it was
    # actually saved, not however it was spoken/extracted.
    assert reply_text == "Done — I've run the 'Setup' workflow."

    # Both real steps actually ran through the real Action Engine stack.
    assert Path(folder_path).is_dir()
    assert len(h.application_manager.list_tracked()) == 1

    # One ActionAuditRecord per step, per Sprint 4.8's own invariant —
    # correlated by "workflow:{workflow_id}", not "voice_turn": per
    # WorkflowExecutor._build_step_request() (Sprint 4.10) and this
    # sprint's own Integration Considerations, a workflow step's
    # ActionContext.requested_by is always rewritten to name the
    # workflow, not whatever originally triggered the run.
    records = h.audit_log.query(limit=5)
    assert len(records) == 2
    assert all(r.requested_by == "workflow:wf-setup" for r in records)

    wait_for_dormant(h.quiet_mode_controller)


def test_workflow_turn_not_found_never_calls_the_executor(
    pipeline_harness, wait_for_active_capture, push_utterance
):
    h = pipeline_harness
    _set_action_request(h, "nonexistent")

    wait_for_active_capture(h.mic)
    h.stt.pending_transcripts.append("run the nonexistent workflow")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=5.0)
    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text == "I couldn't find a workflow named 'nonexistent'."
    assert h.audit_log.query(limit=5) == []


def test_workflow_turn_with_a_high_risk_step_triggers_confirmation_but_cannot_be_answered_live(
    pipeline_harness, wait_for_active_capture, push_utterance, tmp_path
):
    """Real, significant finding from this sprint's own implementation,
    logged as backlog/technical_debt.md item 26: VoiceConfirmationService.
    request_confirmation() (Sprint 4.7), when triggered from WITHIN a
    live turn's own processing, can never actually receive a real spoken
    reply — VoiceSessionManager._session_loop() (Sprint 2.5) is a single
    background thread that is itself still busy running this very turn,
    so it can never loop back around to capture the confirmation
    utterance in parallel. capture_and_transcribe_reply() therefore
    always times out here, no matter what the user says. This test
    proves the confirmation flow genuinely triggers within the full
    live-turn path (the spoken prompt below is real, not simulated)
    while honestly documenting that its outcome is unconditionally
    TIMED_OUT/denied in the current architecture — a real usability gap,
    not a safety hole (the HIGH-risk step correctly never runs
    unconfirmed). Deliberately does NOT push a "yes" utterance to try to
    answer the prompt: since nothing is listening for it during the
    confirmation's own wait, it would simply sit in the fake audio
    backend's queue and get picked up as the START OF THE NEXT TURN once
    this one finishes and the session re-arms — a second, confusing
    side effect of the same root gap that would only muddy this specific
    test's own assertions, not a separate thing worth proving here."""
    h = pipeline_harness
    target_file = tmp_path / "to_delete.txt"
    target_file.write_text("real content")
    definition = WorkflowDefinition(
        workflow_id="wf-cleanup",
        name="Cleanup",
        steps=[
            WorkflowStep(
                step_index=0,
                action_type=ActionType.FILE_DELETE,
                parameters={"path": str(target_file)},
                description="Delete the file",
            ),
        ],
        created_by="test",
        created_at=datetime.now(UTC),
        is_enabled=True,
    )
    h.workflow_store.save(definition)
    _set_action_request(h, "cleanup")

    wait_for_active_capture(h.mic)
    h.stt.pending_transcripts.append("run the cleanup workflow")
    push_utterance(h.audio_backend)

    # The whole-workflow confirmation prompt is genuinely spoken first —
    # proof the real Sprint 4.7 flow was actually invoked, not skipped.
    # It IS the rich, workflow-naming template text
    # WorkflowExecutor._maybe_request_whole_workflow_confirmation() built
    # (backlog/technical_debt.md item 25, resolved in Sprint 4.13):
    # ConfirmationRequest.has_custom_prompt=True now tells the real, live
    # VoiceConfirmationService to speak prompt_text verbatim rather than
    # rebuilding a generic per-ActionType description.
    _wait_for_speak_call_count(h.tts, 1)
    prompt_text, _ = h.tts.speak_calls[0]
    assert prompt_text == (
        "This workflow 'Cleanup' will run 1 actions, including 1 higher-risk steps. "
        "Should I proceed?"
    )

    # No reply is ever pushed — the confirmation simply runs out its own
    # clock (security_config.confirmation_timeout_seconds, this harness's
    # 2.0s), after which the turn concludes with an honest decline.
    _wait_for_speak_call_count(h.tts, 2)
    final_reply, _ = h.tts.speak_calls[1]
    assert final_reply == "I didn't run the 'Cleanup' workflow since it wasn't confirmed."

    # The file was never touched, and no step-level ActionAuditRecord
    # exists — the run aborted before dispatch() was ever called.
    assert target_file.exists()
    assert target_file.read_text() == "real content"
    assert h.audit_log.query(limit=5) == []
