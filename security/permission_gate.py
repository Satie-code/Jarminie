"""Permission Gate — the Security Layer's real, callable enforcement
point. See docs/sprint_book/sprint_4_7.md.

Sprint 4.1 shipped PermissionGate.check() as an honest, deliberately
thin stub: it always returned ALLOW, because no real risk-classification
or confirmation engine existed yet. This sprint replaces that stub with
the real decision flow:

    is_hard_denied(action_type)?  -> yes -> DENY  [stop]
    allowlist check (application_allowlist / approved_commands, for
      LAUNCH_APPLICATION / SYSTEM_COMMAND only)  -> not listed -> DENY  [stop]
    PermissionPolicyEngine.classify(action_type) -> RiskPolicy
    LOW -> ALLOW  [stop]
    MEDIUM / HIGH -> ConfirmationService.request_confirmation(...)
      -> CONFIRMED -> ALLOW      DECLINED / TIMED_OUT -> DENY

authority_evaluator remains a stored constructor dependency, unchanged
from Sprint 4.1 — but, per this sprint's own actual Data Flow above
(not Sprint 4.1's older, more general forward-looking docstring
promise), check()'s new body does not consult it directly; real risk
classification and confirmation are PermissionPolicyEngine's and
ConfirmationService's job specifically. Kept rather than removed since
nothing in this sprint's own Files to Modify calls for changing this
constructor's shape, and a future sprint may still want it available.

security/ never imports device_control/ at runtime — only under
TYPE_CHECKING, for the ActionRequest type hint below (matching Sprint
4.1's own established convention). application_allowlist/approved_commands
matching therefore duplicates CommandExecutionEngine.is_approved()'s own
small basename-comparison logic (_matches_allowlist() below) rather
than importing and calling it directly — a deliberate, small, accepted
duplication, not an oversight, preserving the "device_control depends
on security, never the reverse" dependency direction Sprint 4.1 already
established. This is intentional defense-in-depth with
CommandExecutionEngine's own independent is_approved() check at actual
execution time, not redundant dead code — each layer defends itself
without trusting an upstream layer already did, the same discipline
FileOperationsManager's own path-scope check already uses.

No exception raised by ConfirmationService.request_confirmation() is
specially caught here — ActionRegistry.dispatch() (device_control/
action_engine.py) already wraps this whole check() call in its own
try/except, degrading to ActionStatus.FAILED on any failure, which is
already DENY-equivalent in effect; a second, redundant safety net here
would duplicate that existing protection for no real benefit.
"""

from __future__ import annotations

from enum import Enum
from pathlib import PureWindowsPath
from typing import TYPE_CHECKING

from core.logging_setup import get_logger
from decision.authority import AuthorityEvaluator
from security.confirmation_service import (
    ConfirmationOutcome,
    ConfirmationRequest,
    ConfirmationService,
    build_prompt_text,
)
from security.policy_engine import PermissionPolicyEngine

if TYPE_CHECKING:
    from config.schema import DeviceControlConfig
    from device_control.action_engine import ActionRequest

logger = get_logger(__name__)


class PermissionDecision(Enum):
    """REQUIRE_CONFIRMATION is defined but never returned by check() —
    confirmation is resolved internally to a final ALLOW/DENY before
    returning, so ActionRegistry.dispatch()'s own REQUIRE_CONFIRMATION
    branch (written in Sprint 4.1 for exactly this future) stays
    structurally unreachable, changing zero call sites there."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_CONFIRMATION = "require_confirmation"


def _matches_allowlist(name: str, allowed: list[str]) -> bool:
    basename = PureWindowsPath(name).name.lower()
    return basename in {PureWindowsPath(entry).name.lower() for entry in allowed}


class PermissionGate:
    """Constructor DI: (authority_evaluator, policy_engine,
    confirmation_service, device_control_config). Not a ManagedModule —
    no lifecycle, no background state, cheap to construct.
    """

    def __init__(
        self,
        authority_evaluator: AuthorityEvaluator,
        policy_engine: PermissionPolicyEngine,
        confirmation_service: ConfirmationService,
        device_control_config: DeviceControlConfig,
    ) -> None:
        self._authority_evaluator = authority_evaluator
        self._policy_engine = policy_engine
        self._confirmation_service = confirmation_service
        self._device_control_config = device_control_config

    def check(self, request: ActionRequest) -> PermissionDecision:
        action_type = request.action_type

        if self._policy_engine.is_hard_denied(action_type):
            logger.info("Action hard-denied by policy: %s", action_type.value)
            return PermissionDecision.DENY

        if self._is_denied_by_allowlist(request):
            return PermissionDecision.DENY

        risk_policy = self._policy_engine.classify(action_type)
        if not risk_policy.requires_confirmation:
            return PermissionDecision.ALLOW

        confirmation_request = ConfirmationRequest(
            action_request=request,
            risk_level=risk_policy.risk_level,
            prompt_text=build_prompt_text(request, risk_policy.risk_level),
        )
        outcome = self._confirmation_service.request_confirmation(confirmation_request)
        if outcome is ConfirmationOutcome.CONFIRMED:
            return PermissionDecision.ALLOW
        logger.info(
            "Action denied after confirmation: %s (%s)", action_type.value, outcome.value
        )
        return PermissionDecision.DENY

    def _is_denied_by_allowlist(self, request: ActionRequest) -> bool:
        action_type_value = request.action_type.value

        if action_type_value == "launch_application":
            allowlist = self._device_control_config.application_allowlist
            if allowlist is None:
                return False
            executable_path = request.parameters.get("executable_path")
            if not executable_path:
                return False
            if not _matches_allowlist(str(executable_path), allowlist):
                logger.info("Application not on allowlist, denying: %s", executable_path)
                return True
            return False

        if action_type_value == "system_command":
            command = request.parameters.get("command")
            if not command:
                return False
            approved = self._device_control_config.approved_commands
            if not _matches_allowlist(str(command[0]), approved):
                logger.info("Command not on approved_commands, denying: %s", command[0])
                return True
            return False

        return False
