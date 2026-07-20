"""Permission Gate — the Security Layer's first real, callable
enforcement point, acting on docs/sprint_book/INDEX.md's own
Recommendation to ship a thin `security/` stub as early as Sprint 4.1
rather than deferring all Security Layer work to Level 6.

Sprint 4.1 ships PermissionGate.check() as an honest, deliberately thin
stub: it always returns ALLOW, because no ActionType alone carries a
real risk signal yet — no application/file/window/command executor
exists yet to be risky about. This is a real, tested, callable method,
not a TODO or an unconditional `return True` with no body. Sprint 4.7
(Permission & Confirmation System) replaces this method's internals with
real risk classification and a confirmation flow — ActionRegistry
(device_control/action_engine.py) does not change at all when that
happens, since it only ever calls check() and branches on the returned
PermissionDecision.

security/ never imports device_control/ at runtime — only under
TYPE_CHECKING, for the ActionRequest type hint below. ActionRegistry
(device_control/action_engine.py) imports PermissionGate/
PermissionDecision from here at runtime, so importing device_control at
runtime here too would create a circular import. This also matches the
intended dependency direction: device_control depends on security
(a lower-level, reusable safety primitive — Part 2's own "gatekeeper"
framing), never the reverse.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from core.logging_setup import get_logger
from decision.authority import AuthorityEvaluator

if TYPE_CHECKING:
    from device_control.action_engine import ActionRequest

logger = get_logger(__name__)


class PermissionDecision(Enum):
    """REQUIRE_CONFIRMATION is defined now but never returned by this
    sprint's own check() — Sprint 4.7 is the first real producer of it."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_CONFIRMATION = "require_confirmation"


class PermissionGate:
    """Constructor DI: receives the AuthorityEvaluator (Sprint 3.11)
    this gate is meant to delegate risk-sensitive reasoning to. Not a
    ManagedModule — no lifecycle, no background state, cheap to
    construct, the same judgment call already made for
    voice/context_manager.py's ContextManager and
    memory/retrieval_engine.py's MemoryRetrievalEngine.

    authority_evaluator is stored, not yet consulted by check()'s own
    body this sprint — the same "field present, policy arrives later"
    discipline this project already uses for
    AuthorityEvaluator.approved_emergency_procedures itself (Sprint
    3.11, populated for real by Sprint 4.7).
    """

    def __init__(self, authority_evaluator: AuthorityEvaluator) -> None:
        self._authority_evaluator = authority_evaluator

    def check(self, request: ActionRequest) -> PermissionDecision:
        """Sprint 4.1: always ALLOW. Real, callable, tested — not a
        placeholder — but genuinely unconditional until Sprint 4.7
        ships real per-ActionType risk classification and a
        confirmation flow."""
        logger.debug(
            "PermissionGate.check() — Sprint 4.1 stub, unconditional ALLOW for action_type=%s",
            request.action_type.value,
        )
        return PermissionDecision.ALLOW
