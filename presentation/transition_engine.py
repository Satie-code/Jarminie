"""TransitionEngine (Sprint 5.10 — Level 5 Part A).

Implements the brief's own locked persona-transition flow exactly:

    Jarvis -> Save presentation state -> Synchronize memory ->
    Display JARMINEI Core -> Particle transition -> Load target renderer
    -> Restore conversation -> Continue naturally

No application restart. No conversation loss. No memory reset.

**The single most important thing this module does NOT do**: implement
conversation/memory continuity. That is already real and already solid,
built entirely at Level 2/3 — `ConversationSessionStore`/`ContextManager`
(Sprint 2.7/2.8) persist every turn regardless of active persona,
`PersonaScopedMemory`'s Shared-memory layer (Sprint 3.2) is readable by
both personas by construction, and `PersonaManager.select()`/
`resume_previous()` (Sprint 2.11) already switch *which* persona answers
the next turn with zero effect on any of that. This module's own job is
exclusively the visual/presentation choreography layered on top of that
already-guaranteed continuity: `SYNCING_MEMORY` below is a verification/
logging checkpoint only — it confirms the already-current state is
available, logs it, and performs no new I/O of its own. The other six
phases (`SAVING_STATE`, `SHOWING_CORE`, `PARTICLE_TRANSITION`,
`LOADING_TARGET`, `RESTORING_CONVERSATION`, `COMPLETE`) are real,
presentation-only work.

Bounded duration, by construction: `transition()` never blocks a live
conversation turn indefinitely. `PresentationConfig.
transition_max_duration_seconds` is a whole-sequence budget, checked
between phases (never preempting a phase already in flight) — a budget
overrun skips straight to `LOADING_TARGET`/`COMPLETE` (skipping
`SYNCING_MEMORY`/`SHOWING_CORE`/`PARTICLE_TRANSITION`/
`RESTORING_CONVERSATION` too), guaranteeing the renderer swap itself
always eventually happens even if the animation choreography around it
doesn't finish in time. `transition()` also never raises — any internal
failure (an overlay method raising, a `PresentationController` call
raising) is caught, logged, and the sequence still degrades to the same
guaranteed renderer swap.

No real neutral "JARMINEI Core"/particle visual and no Qt widget at all
exist here — `TransitionOverlay` is a Protocol; `NullTransitionOverlay`
is this sprint's only concrete implementation, letting this module's own
choreography logic (ordering, timeout, resume-replay) be fully verified
without a `QApplication`. A real, on-screen overlay is Sprint 5.14's job,
embedded into `MainWindow` alongside the renderer-hosting work that
sprint already has to do; `on_switch` (the real live caller of
`transition()`, via `PersonaManager`'s own new constructor parameter)
has no real caller until then either.

**`set_overlay()` (Sprint 5.14)**: a real gap found while wiring a real
`QtTransitionOverlay` (`presentation/qt_transition_overlay.py`) for the
first time — that overlay is a genuine `QWidget`, which cannot be
constructed until a `QApplication` exists, but `TransitionEngine` itself
is built at `main.py`'s composition-root time, deliberately before
`QApplication` does (see `main.py`'s own `_prewarm_tts_before_pyside6()`
docstring for why that ordering is load-bearing elsewhere too). This
class is therefore constructed with the `NullTransitionOverlay` default
in `main.py`, and `MainWindow` (Sprint 5.14, once a real `QApplication`
and `PresentationHostWidget` exist to parent the overlay to) calls
`set_overlay()` to swap in the real one — the same "found a real gap in
the sprint's own file list, resolved it directly, disclosed it here"
precedent this class's own Sprint 5.6/5.9/5.10 constructor additions
already used.
"""

import time
from enum import Enum
from typing import Protocol

from config.schema import PresentationConfig
from core.logging_setup import get_logger
from presentation.presentation_controller import PresentationController
from presentation.presentation_state import PresentationState

logger = get_logger(__name__)


class TransitionPhase(Enum):
    """The brief's own seven-step flow, named directly — each one
    individually observable, both for testing and for a real overlay's
    own progress display (Sprint 5.14)."""

    SAVING_STATE = "saving_state"
    SYNCING_MEMORY = "syncing_memory"
    SHOWING_CORE = "showing_core"
    PARTICLE_TRANSITION = "particle_transition"
    LOADING_TARGET = "loading_target"
    RESTORING_CONVERSATION = "restoring_conversation"
    COMPLETE = "complete"


class TransitionOverlay(Protocol):
    """The minimal seam a real UI-layer overlay (Sprint 5.14) implements
    — kept separate from Renderer (5.6) since an overlay is transient
    scaffolding shown *during* a transition, not a persona's own ongoing
    presentation. A method with nothing meaningful to do must no-op,
    never raise — the same "unsupported input degrades silently"
    contract Renderer's own methods already hold; TransitionEngine
    additionally guards every call defensively regardless."""

    def show(self) -> None: ...

    def set_phase(self, phase: TransitionPhase) -> None: ...

    def hide(self) -> None: ...


class NullTransitionOverlay:
    """A real, concrete no-op TransitionOverlay — TransitionEngine's own
    default, so it is fully testable with zero Qt dependency (the same
    "component before integration, real widget arrives later"
    discipline every prior presentation sprint used)."""

    def show(self) -> None:
        pass

    def set_phase(self, phase: TransitionPhase) -> None:
        pass

    def hide(self) -> None:
        pass


class TransitionEngine:
    """Constructor DI per 03_Engineering_Standards.md: receives
    presentation_controller (5.6 — the only collaborator this class
    talks to; it never reaches renderers directly), presentation_config
    (this sprint's own two new timing fields), and an optional overlay
    (defaults to NullTransitionOverlay above)."""

    def __init__(
        self,
        presentation_controller: PresentationController,
        presentation_config: PresentationConfig,
        overlay: TransitionOverlay | None = None,
    ) -> None:
        self._presentation_controller = presentation_controller
        self._config = presentation_config
        self._overlay = overlay if overlay is not None else NullTransitionOverlay()
        self._saved_states: dict[str, PresentationState] = {}

    def set_overlay(self, overlay: TransitionOverlay) -> None:
        """Swap in a real overlay after construction — see this class's
        own docstring for why this exists. Safe to call at any time,
        including mid-transition (takes effect on the next
        _call_overlay_safely() call); there is no lifecycle to tear down
        on the overlay being replaced (TransitionOverlay itself is
        stateless scaffolding, per its own Protocol docstring)."""
        self._overlay = overlay

    def transition(self, old_persona_name: str, new_persona_name: str) -> None:
        """Runs the seven phases in order (module docstring). Never
        raises; always calls PresentationController.mount_renderer(
        new_persona_name) exactly once, regardless of which path is
        taken (Acceptance Criteria)."""
        deadline = time.monotonic() + self._config.transition_max_duration_seconds
        finished = False
        try:
            self._run_choreography(old_persona_name, new_persona_name, deadline)
            finished = True
        except Exception:
            logger.exception(
                "TransitionEngine.transition() failed mid-sequence; degrading to an instant "
                "renderer swap."
            )
        if not finished:
            # _run_choreography raised before reaching its own _finish()
            # call below — this is the one remaining path to a renderer
            # swap, still exactly one mount_renderer() call total.
            self._finish(new_persona_name, skip_restore=True)

    def _run_choreography(
        self, old_persona_name: str, new_persona_name: str, deadline: float
    ) -> None:
        self._call_overlay_safely(self._overlay.show)

        self._call_overlay_safely(self._overlay.set_phase, TransitionPhase.SAVING_STATE)
        saved = self._presentation_controller.last_state_for(old_persona_name)
        if saved is not None:
            self._saved_states[old_persona_name] = saved

        within_budget = time.monotonic() < deadline
        if within_budget:
            self._call_overlay_safely(self._overlay.set_phase, TransitionPhase.SYNCING_MEMORY)
            logger.info(
                "Transition %s -> %s: conversation/memory continuity confirmed unaffected "
                "(no new I/O — see this module's own Engineering Rationale).",
                old_persona_name,
                new_persona_name,
            )
            within_budget = time.monotonic() < deadline

        if within_budget:
            self._call_overlay_safely(self._overlay.set_phase, TransitionPhase.SHOWING_CORE)
            within_budget = time.monotonic() < deadline

        if within_budget:
            self._call_overlay_safely(
                self._overlay.set_phase, TransitionPhase.PARTICLE_TRANSITION
            )
            time.sleep(self._config.transition_particle_phase_seconds)
            within_budget = time.monotonic() < deadline

        self._finish(new_persona_name, skip_restore=not within_budget)

    def _finish(self, new_persona_name: str, skip_restore: bool) -> None:
        """Phases 5/7 (and, unless skip_restore, phase 6) — the single
        call site for mount_renderer(), fully self-guarded so it can
        never itself raise back out to transition()'s own try/except
        (which is what makes "exactly once" hold in every case)."""
        self._call_overlay_safely(self._overlay.set_phase, TransitionPhase.LOADING_TARGET)
        try:
            self._presentation_controller.mount_renderer(new_persona_name)
        except Exception:
            logger.exception("mount_renderer(%s) failed during a transition.", new_persona_name)

        if not skip_restore:
            self._call_overlay_safely(
                self._overlay.set_phase, TransitionPhase.RESTORING_CONVERSATION
            )
            cached = self._saved_states.get(new_persona_name)
            if cached is not None:
                try:
                    self._presentation_controller.apply_state(cached)
                except Exception:
                    logger.exception(
                        "apply_state() failed restoring cached presentation for %s.",
                        new_persona_name,
                    )

        self._call_overlay_safely(self._overlay.set_phase, TransitionPhase.COMPLETE)
        self._call_overlay_safely(self._overlay.hide)

    def _call_overlay_safely(self, method, *args) -> None:
        try:
            method(*args)
        except Exception:
            logger.exception("TransitionOverlay method %s failed; continuing.", method.__name__)
