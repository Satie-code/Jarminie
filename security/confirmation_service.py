"""Confirmation Service — requests and awaits real user confirmation
before a medium/high-risk action proceeds. See
docs/sprint_book/sprint_4_7.md.

ConfirmationService is a Protocol specifically so VoiceConfirmationService
is not the only possible implementation — a headless/CI test double, and
a future UI-surfaced confirmation (a dialog, once Level 4 gets its own UI
panel), both depend on the same interface, matching SpeechToText's own
interface-first precedent (Sprint 2.3).

A confirmation timeout defaulting to DENY (never ALLOW) is a hard,
non-configurable direction, enforced by PermissionGate (the caller),
never by a ConfirmationService implementation itself deciding what a
timeout means — this mirrors AuthorityEvaluator.evaluate()'s own "fail
safe-down, never safe-up" rule (Sprint 3.13) applied to the confirmation
flow specifically.

VoiceConfirmationService depends on VoiceSessionManager (Sprint 2.5) and
PersonaManager (Sprint 2.11) — the first Level 4 dependency on Level 2
modules. persona_manager is needed to resolve the active persona's
voice_id for speak_reply(); this sprint's own Expected Classes section
named only (session_manager, confirmation_timeout_seconds) as
VoiceConfirmationService's constructor, but omitted how the class would
know which voice to speak in — persona_manager fills that real,
structurally necessary gap (see sprint_4_7.md's own completion report).

A confirmation request arriving while no voice session is active (e.g. a
future Scheduler-fired workflow with no live conversation, Level 4 Part
B) has no session to speak/listen through; request_confirmation()
degrades to TIMED_OUT immediately in that case, never a crash or an
indefinite wait.

Sprint 4.12 hardening (scenario e): is_active() being True at the start
of request_confirmation() does not guarantee the session stays healthy
for the rest of the call — a real race (the session ending, or
VoiceSessionManager/PersonaManager erroring, between that check and
speak_reply()/capture_and_transcribe_reply() actually running) could
previously raise (e.g. VoiceSessionManager.speak_reply()'s own
SessionError) straight out of request_confirmation(), propagating into
whatever called it (PermissionGate.check(), or WorkflowExecutor's own
whole-workflow confirmation call). The whole speak-then-listen sequence
is now wrapped: any unexpected failure degrades to TIMED_OUT, the same
fail-safe-down value every other confirmation-denial path already uses
— never a crash, never treated as an implicit CONFIRMED.

build_prompt_text() is reused by security/permission_gate.py itself to
populate ConfirmationRequest.prompt_text before any ConfirmationService
implementation ever sees the request (so even a future non-voice
implementation gets a sensible, medium-agnostic description "for free")
— VoiceConfirmationService then additionally reuses the very same
function internally for what it actually speaks, rather than trusting a
possibly-generic prompt_text unconditionally. One implementation, not
two independently-maintained copies of the same describe-this-action
logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from core.logging_setup import get_logger
from security.policy_engine import RiskLevel

if TYPE_CHECKING:
    from device_control.action_engine import ActionRequest
    from personas.persona_manager import PersonaManager
    from voice.session_manager import VoiceSessionManager

logger = get_logger(__name__)

_ACTION_DESCRIPTIONS: dict[str, str] = {
    "launch_application": "launch {executable_path}",
    "close_application": "close the running application",
    "file_create": "create the file {path}",
    "file_move": "move {source} to {destination}",
    "file_copy": "copy {source} to {destination}",
    "file_rename": "rename {path} to {new_name}",
    "file_delete": "permanently delete the file {path}",
    "folder_create": "create the folder {path}",
    "folder_delete": "permanently delete the folder {path}",
    "window_focus": "focus a window",
    "window_move": "move a window",
    "window_resize": "resize a window",
    "window_minimize": "minimize a window",
    "window_close": "close a window",
    "system_command": "run the command {command}",
    "workflow_step": "run a workflow step",
}


def _describe_action(action_request: ActionRequest) -> str:
    action_type_value = action_request.action_type.value
    template = _ACTION_DESCRIPTIONS.get(action_type_value)
    if template is None:
        return f"perform a {action_type_value.replace('_', ' ')} action"
    format_params = dict(action_request.parameters)
    command = format_params.get("command")
    if isinstance(command, list):
        format_params["command"] = " ".join(str(part) for part in command)
    try:
        return template.format(**format_params)
    except (KeyError, IndexError):
        return f"perform a {action_type_value.replace('_', ' ')} action"


def build_prompt_text(action_request: ActionRequest, risk_level: RiskLevel) -> str:
    """Public (not leading-underscore) specifically because
    security/permission_gate.py imports and calls this directly to
    populate ConfirmationRequest.prompt_text before any
    ConfirmationService implementation ever sees the request — see this
    module's own docstring for why that single shared implementation
    exists rather than two independently-maintained copies."""
    return f"This will {_describe_action(action_request)}. Should I proceed?"


@dataclass
class ConfirmationRequest:
    """prompt_text is a human-readable description of exactly what will
    happen, built from ActionRequest.parameters — the Explainability
    Rule applied to a confirmation prompt, not just a decision trace."""

    action_request: ActionRequest
    risk_level: RiskLevel
    prompt_text: str


class ConfirmationOutcome(Enum):
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    TIMED_OUT = "timed_out"


class ConfirmationService(Protocol):
    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationOutcome: ...


_AFFIRMATIVE_WORDS = frozenset({"yes", "yeah", "yep", "yup", "confirm", "sure", "proceed"})
_NEGATIVE_WORDS = frozenset({"no", "nope", "cancel", "stop", "negative"})
_AFFIRMATIVE_PHRASES = ("go ahead", "do it")
_NEGATIVE_PHRASES = ("don't", "do not")


def _interpret_reply(text: str) -> ConfirmationOutcome:
    """Plain keyword/phrase matching, no NLU — the same discipline this
    project uses throughout (e.g. PersonaManager's trigger phrases).
    Word-set matching (not raw substring containment) for the
    single-word signals specifically to avoid a false match like "no"
    inside "know". An unrecognized reply defaults to DECLINED, not
    CONFIRMED — fail safe-down, matching this module's own confirmation-
    timeout discipline."""
    lowered = text.lower()
    words = set(lowered.split())
    if words & _NEGATIVE_WORDS or any(phrase in lowered for phrase in _NEGATIVE_PHRASES):
        return ConfirmationOutcome.DECLINED
    if words & _AFFIRMATIVE_WORDS or any(phrase in lowered for phrase in _AFFIRMATIVE_PHRASES):
        return ConfirmationOutcome.CONFIRMED
    return ConfirmationOutcome.DECLINED


class VoiceConfirmationService:
    """Constructor DI: (session_manager, persona_manager,
    confirmation_timeout_seconds). Asks via the active persona's own
    voice (VoiceSessionManager.speak_reply(), the same call a normal
    composed reply uses — no new speech path) and listens via
    VoiceSessionManager.capture_and_transcribe_reply() (added this
    sprint specifically for this purpose — see that method's own
    docstring for why a new public method was necessary rather than a
    second, competing mic-read path)."""

    def __init__(
        self,
        session_manager: VoiceSessionManager,
        persona_manager: PersonaManager,
        confirmation_timeout_seconds: float,
    ) -> None:
        self._session_manager = session_manager
        self._persona_manager = persona_manager
        self._confirmation_timeout_seconds = confirmation_timeout_seconds

    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationOutcome:
        if not self._session_manager.is_active():
            logger.info(
                "Confirmation requested with no active voice session; timing out immediately."
            )
            return ConfirmationOutcome.TIMED_OUT

        try:
            prompt_text = self._build_prompt_text(request.action_request, request.risk_level)
            voice_id = self._persona_manager.active_persona().voice_id
            self._session_manager.speak_reply(prompt_text, voice_id)

            reply_text = self._session_manager.capture_and_transcribe_reply(
                self._confirmation_timeout_seconds
            )
        except Exception:
            logger.exception(
                "VoiceConfirmationService.request_confirmation() failed unexpectedly "
                "(the voice session may have ended or errored mid-request); timing out "
                "rather than risking an unanswered prompt being treated as consent."
            )
            return ConfirmationOutcome.TIMED_OUT

        if reply_text is None:
            logger.info("Confirmation timed out waiting for a spoken reply.")
            return ConfirmationOutcome.TIMED_OUT

        outcome = _interpret_reply(reply_text)
        logger.info("Confirmation reply %r interpreted as %s.", reply_text, outcome.value)
        return outcome

    def _build_prompt_text(self, action_request: ActionRequest, risk_level: RiskLevel) -> str:
        return build_prompt_text(action_request, risk_level)
