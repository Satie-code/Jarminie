"""Integration tests for the live-turn-to-real-Action-Engine round trip
(Sprint 4.11, Workflow & Device Control Integration) — the first real
exercise of DecisionTrace.selected_engine == DEVICE_CONTROL actually
reaching ActionRegistry.dispatch() through a full, real conversation
turn: WakeWordDetector -> VoiceSessionManager -> IntentDetector ->
ContextAnalyzer -> AuthorityEvaluator -> CommunicationPipeline.
_handle_device_control_turn() -> ActionRegistry.dispatch() ->
PermissionGate -> ApplicationManager -> ActionAuditLog -> spoken
confirmation.

See tests/integration/conftest.py's pipeline_harness fixture for the
shared object graph and this file's own safety scoping
(device_control_config confined to tmp_path/hostname.exe only — see
that fixture's own docstring for why hostname.exe specifically).
"""

from device_control.action_engine import ActionStatus


def _set_action_request(h, entity: str, topic: str = "launch an application") -> None:
    """Points the harness's FakeLanguageModelClient at responses that
    make IntentDetector/ContextAnalyzer classify the next turn as an
    ACTION_REQUEST naming entity — the same two-response-string
    technique every other Level 3 integration test in this directory
    already uses (test_decision_engine_integration.py)."""
    h.llm_client.intent_response = "CATEGORY: ACTION_REQUEST\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        f"TOPIC: {topic}\nENTITIES: {entity}\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )


def test_full_wake_to_device_control_round_trip(
    pipeline_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    """Acceptance Criteria: "A live conversation turn requesting a
    concrete, safe device-control action (application launch) is
    correctly routed through EngineSelection.DEVICE_CONTROL and actually
    performed, with a spoken confirmation reflecting the real result."
    hostname.exe is real, on the configured application_allowlist,
    genuinely launched via a real subprocess, and exits on its own
    almost instantly."""
    h = pipeline_harness
    _set_action_request(h, "hostname")

    wait_for_active_capture(h.mic)
    h.stt.pending_transcripts.append("open hostname")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=5.0)
    reply_text, voice_id = h.tts.speak_calls[0]
    assert reply_text == "Done — I've opened hostname.exe."
    assert voice_id == h.persona_manager.active_persona().voice_id

    # A real ApplicationManager actually tracked a real launched process.
    tracked = h.application_manager.list_tracked()
    assert len(tracked) == 1
    assert tracked[0].executable_path == "hostname.exe"
    assert tracked[0].launched_via == "voice_turn"

    # A real ActionAuditRecord was persisted for this dispatch — the
    # first real, live-turn-triggered caller either ActionRegistry or
    # ActionAuditLog has ever had (every prior Level 4 sprint's own
    # Integration Considerations flagged this as still-open until now).
    records = h.audit_log.query(limit=5)
    assert len(records) == 1
    assert records[0].action_type == "launch_application"
    assert records[0].status == "succeeded"
    assert records[0].requested_by == "voice_turn"

    # The turn was persisted like any other, and the session returns to
    # Quiet Mode normally afterward — the new branch changes what reply
    # text is spoken, not the surrounding turn/session lifecycle.
    session_id = h.session_manager._session.session_id if h.session_manager.is_active() else None
    if session_id is not None:
        recent_turns = h.conversation_store.get_recent_turns(session_id, limit=10)
        assert recent_turns[-1].response_text == "Done — I've opened hostname.exe."

    wait_for_dormant(h.quiet_mode_controller)


def test_device_control_turn_denied_by_allowlist_never_launches_anything(
    pipeline_harness, wait_for_active_capture, push_utterance
):
    """The real PermissionGate (Sprint 4.7) still enforces
    application_allowlist for a live-turn-originated request exactly as
    it would for any other caller — "notepad" is not on this harness's
    own configured allowlist (only hostname.exe is), so the request must
    be denied before ApplicationManager ever runs, and the user must
    hear an honest reason rather than silence."""
    h = pipeline_harness
    _set_action_request(h, "notepad")

    wait_for_active_capture(h.mic)
    h.stt.pending_transcripts.append("open notepad")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=5.0)
    reply_text, _ = h.tts.speak_calls[0]
    assert reply_text.startswith("I'm not able to do that:")

    assert h.application_manager.list_tracked() == []
    records = h.audit_log.query(limit=5)
    assert len(records) == 1
    assert records[0].status == ActionStatus.DENIED.value


def test_device_control_turn_with_no_entity_falls_back_conversationally(
    pipeline_harness, wait_for_active_capture, push_utterance
):
    """AuthorityEvaluator._resolve_action_engine() (decision/authority.py,
    Sprint 4.11) never guesses a target — an ACTION_REQUEST with no
    ContextAnalysis entity at all stays CONVERSATIONAL_RESPONSE, the same
    fallback this exact live path already exercised before this sprint,
    now re-confirmed with the new routing logic present."""
    h = pipeline_harness
    h.llm_client.intent_response = "CATEGORY: ACTION_REQUEST\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: unclear request\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )

    wait_for_active_capture(h.mic)
    h.stt.pending_transcripts.append("do the thing")
    push_utterance(h.audio_backend)

    assert h.tts.spoken_event.wait(timeout=5.0)
    reply_text, _ = h.tts.speak_calls[0]
    assert "do the thing" in reply_text  # the ordinary templated persona reply
    assert h.application_manager.list_tracked() == []
    assert h.audit_log.query(limit=5) == []
