"""QtConfirmationService — JARVIS Holographic HUD reskin, Phase 4.

**A real, disclosed gap this closes**: `security/permission_gate.py`'s
`PermissionGate` holds exactly one `ConfirmationService`, constructed
once in `main.py` — today always a `VoiceConfirmationService`
(`security/confirmation_service.py`), which requires an active voice
session to speak/listen through. A UI-originated `ActionRequest` (e.g. a
Quick Commands button click, `ui/jarvis/quick_commands_panel.py`) has no
such session — `VoiceConfirmationService.request_confirmation()` would
immediately degrade to `TIMED_OUT`, auto-denying every Quick Command
whose action needs confirmation (MEDIUM/HIGH risk per
`security/policy_engine.py`).

This module fixes that WITHOUT touching `PermissionGate`,
`ActionRegistry`, or the voice confirmation path at all:

- `QtConfirmationService` is a second, real `ConfirmationService`
  implementation — a modal Qt dialog (`ui/jarvis/confirmation_dialog.py`)
  instead of a spoken prompt. Must only be called from the Qt main/GUI
  thread (a `QDialog` cannot be constructed/`exec()`'d from a background
  thread) — its one real caller, Quick Commands buttons dispatching from
  their own `clicked` slot, already runs there; the voice-triggered path
  never reaches this class at all (see `RequestedByConfirmationService`
  below for why).
- `RequestedByConfirmationService` routes a confirmation request to a
  different underlying `ConfirmationService` based on
  `ActionContext.requested_by` — `main.py` constructs it once, wrapping
  the existing `VoiceConfirmationService` as the default plus a small
  `{"ui": qt_confirmation_service}` override table, and hands THIS
  composite to `PermissionGate` exactly where the raw
  `VoiceConfirmationService` used to go. `PermissionGate` itself has no
  idea this routing exists — it just calls `request_confirmation()` on
  whatever `ConfirmationService` it was constructed with, unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.logging_setup import get_logger
from security.confirmation_service import ConfirmationOutcome, ConfirmationService

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from security.confirmation_service import ConfirmationRequest

logger = get_logger(__name__)


class QtConfirmationService:
    """Constructor DI: (confirmation_timeout_seconds, parent). parent is
    the widget the modal dialog should center over (typically
    MainWindow) — optional, since a confirmation could in principle be
    requested before MainWindow exists."""

    def __init__(self, confirmation_timeout_seconds: float, parent: QWidget | None = None) -> None:
        self._confirmation_timeout_seconds = confirmation_timeout_seconds
        self._parent = parent

    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationOutcome:
        from ui.jarvis.confirmation_dialog import ConfirmationDialog

        try:
            dialog = ConfirmationDialog(
                request.prompt_text, self._confirmation_timeout_seconds, self._parent
            )
            accepted = dialog.exec()
        except Exception:
            logger.exception(
                "QtConfirmationService failed to show a confirmation dialog; denying as a "
                "safe default."
            )
            return ConfirmationOutcome.TIMED_OUT

        if dialog.timed_out:
            logger.info("UI confirmation dialog timed out with no response.")
            return ConfirmationOutcome.TIMED_OUT
        outcome = ConfirmationOutcome.CONFIRMED if accepted else ConfirmationOutcome.DECLINED
        logger.info("UI confirmation dialog result: %s.", outcome.value)
        return outcome


class RequestedByConfirmationService:
    """Constructor DI: (default, overrides). `overrides` is keyed by
    `ActionContext.requested_by` (e.g. `"ui"`); any `requested_by` not
    present falls back to `default` — every existing voice-triggered
    confirmation keeps its exact current behavior unchanged."""

    def __init__(
        self, default: ConfirmationService, overrides: dict[str, ConfirmationService]
    ) -> None:
        self._default = default
        self._overrides = overrides

    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationOutcome:
        requested_by = request.action_request.context.requested_by
        service = self._overrides.get(requested_by, self._default)
        return service.request_confirmation(request)
