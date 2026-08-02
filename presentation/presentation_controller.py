"""PresentationController (Sprint 5.6 — Level 5 Part A).

The coordinator around Sprint 5.5's already-built PresentationState/
PresentationStateComputer and this sprint's own Renderer Protocol —
completing the brief's own mandated architecture: Persona Controller ->
Presentation State -> Renderer Interface -> {Jarvis Renderer, Minie
Renderer}. A ManagedModule, following every other coordinator in this
codebase (PersonaManager, MemoryLifecycleManager): constructed once at
startup, owns no business logic of its own beyond composition (reads
PersonaManager.active_persona(), calls the matching
PresentationStateComputer, calls the currently-mounted Renderer.
render_state()).

**"Mounted renderer" is deliberately a separate concept from "active
persona."** During a transition (Sprint 5.10), the active persona can
change an instant before the new renderer finishes mounting;
conflating the two would make this class briefly report an
inconsistent state (active persona X, but still rendering Y's last
frame) as if it were correct rather than a known, named, momentary
transition state. mounted_persona_name (below) exposes the mounted
side separately from persona_manager.active_persona().name, so Sprint
5.10's TransitionEngine — the one class that legitimately needs to
observe "these are momentarily different" — can do its job. refresh()
itself always renders through whatever renderer IS currently mounted
(mounted_persona_name), never assuming it matches the active persona —
this sprint's own Data Flow diagram's literal `Renderer[active_persona.
name]` shorthand is exactly that, a shorthand; this docstring's own
Architecture Notes are the authoritative statement of the real
behavior.

**A real gap in this sprint's own Expected Classes constructor list was
found and resolved**: computing a PresentationState needs an
OperatingMode (PresentationStateComputer.compute()'s own second
parameter, Sprint 5.5), but neither the spec's constructor DI list nor
its Data Flow diagram names where one comes from. voice/quiet_mode.py's
QuietModeController (Sprint 2.6) is this project's own existing single
source of truth for OperatingMode — added here as a fifth constructor
parameter, read only via current_mode() inside refresh(). See this
sprint's own Sprint Completion Report for the full reasoning.

No live caller until Sprint 5.14 (main.py/CoreManager registration,
and refresh()'s real trigger — a QTimer, or a call from
CommunicationPipeline's own turn-processing — are both explicitly out
of this sprint's scope). No concrete Renderer exists yet either
(Sprint 5.7/5.8's job) — renderers is empty in every real construction
until then; this sprint's own tests use a minimal in-memory fake. See
docs/sprint_book/sprint_5/sprint_5_6.md.

**Sprint 5.9 (Gesture Engine)** adds a sixth constructor parameter,
`gesture_engine` — the same "a real gap in the constructor DI list,
resolved directly rather than deferred" precedent this class's own
Sprint 5.6 already used for `quiet_mode_controller`: `dispatch_gesture()`
routes a `GestureEvent` to the currently-mounted renderer's
`trigger_gesture()`, and `refresh()` now also rolls (and, if non-None,
dispatches) one ambient gesture per tick via
`GestureEngine.maybe_roll_ambient_gesture()`, using the same
just-computed `PresentationState.gesture_probability` and the active
persona's own name — both inside `refresh()`'s existing Fail Gracefully
try/except, so a `GestureEngine`/renderer failure here degrades exactly
like a `PresentationStateComputer`/`render_state()` failure already
does.

**Sprint 5.10 (Persona Transition Engine)** adds two small, necessary
methods beyond that sprint's own stated Files to Modify — its own
Expected Functions text describes `TransitionEngine`'s `SAVING_STATE`
phase as capturing "the outgoing renderer's last-known PresentationState
... from PresentationController," which this class had no way to expose
until now: `refresh()` now caches each tick's own freshly-computed state
per persona name; `last_state_for(persona_name)` reads that cache (None
if `refresh()` has never run for that persona yet — an honest gap, not
an error); `apply_state(state)` renders a given state directly through
whatever renderer is currently mounted, bypassing
`PresentationStateComputer.compute()` for that one call — `TransitionEngine`'s
own `RESTORING_CONVERSATION` phase uses this to replay a cached state
onto a freshly-mounted renderer after a resume. The same "found a real
gap in the sprint's own file list, resolved it directly, disclosed it
here" precedent this class's own Sprint 5.6/5.9 additions already used.
"""

from core.logging_setup import get_logger
from emotion.state_manager import EmotionalStateManager
from personas.persona_manager import PersonaManager
from presentation.gesture_engine import GestureEngine, GestureEvent
from presentation.presentation_state import PresentationState, PresentationStateComputer
from presentation.renderer import Renderer
from voice.quiet_mode import QuietModeController

logger = get_logger(__name__)


class PresentationController:
    """Constructor DI per 03_Engineering_Standards.md: receives
    persona_manager (2.11), emotional_state_manager (5.2),
    quiet_mode_controller (2.6 — see this module's own docstring for
    why), state_computers (dict[str, PresentationStateComputer] keyed
    by persona name, 5.5's two computers), renderers (dict[str,
    Renderer] keyed by persona name — empty/absent bindings degrade
    gracefully, populated for real by main.py at Sprint 5.14, not this
    sprint's own job to harden fully per Sprint 5.15), and
    gesture_engine (5.9's own GestureEngine — see this module's own
    docstring for why it was added here)."""

    def __init__(
        self,
        persona_manager: PersonaManager,
        emotional_state_manager: EmotionalStateManager,
        quiet_mode_controller: QuietModeController,
        state_computers: dict[str, PresentationStateComputer],
        renderers: dict[str, Renderer],
        gesture_engine: GestureEngine,
    ) -> None:
        self._persona_manager = persona_manager
        self._emotional_state_manager = emotional_state_manager
        self._quiet_mode_controller = quiet_mode_controller
        self._state_computers = state_computers
        self._renderers = renderers
        self._gesture_engine = gesture_engine
        self._mounted_persona_name: str | None = None
        self._last_state_by_persona: dict[str, PresentationState] = {}

    @property
    def mounted_persona_name(self) -> str | None:
        """Which persona's renderer is currently mounted — None if
        nothing is mounted (no bound renderer, or mount() failed).
        Deliberately separate from persona_manager.active_persona().name
        — see this module's own docstring."""
        return self._mounted_persona_name

    def start(self) -> None:
        """Mounts whichever renderer matches PersonaManager.
        active_persona().name at startup — mirrors PersonaManager.
        start()'s own "Jarvis is the default active persona" precedent:
        no separate default logic here, just follow whatever's already
        active. A no-op (logged) if no renderer is bound for that
        persona yet — expected and honest at this Level, before Sprint
        5.14 populates real bindings."""
        active_name = self._persona_manager.active_persona().name
        self.mount_renderer(active_name)
        logger.info("Presentation Controller started.")

    def stop(self) -> None:
        self._unmount_current()
        logger.info("Presentation Controller stopped.")

    def health_check(self) -> bool:
        """A narrow, honest signal this sprint: True only if a renderer
        is currently mounted. Renderer itself has no health_check() of
        its own yet (this sprint's own Engineering Rationale/Potential
        Risks keep the Protocol to exactly three methods) — a future
        sprint may deepen this once a real renderer implementation
        exists to justify it."""
        return self._mounted_persona_name is not None

    def mount_renderer(self, persona_name: str) -> None:
        """Explicit renderer swap: unmounts whatever was mounted first,
        then mounts persona_name's own renderer if one is bound. The
        real intended caller is Sprint 5.10's TransitionEngine, not this
        sprint. A no-op (logged) if no renderer is bound for
        persona_name — never raises, matching this Level's own "the
        renderers dict is empty until Sprint 5.14" reality."""
        self._unmount_current()
        renderer = self._renderers.get(persona_name)
        if renderer is None:
            logger.info(
                "mount_renderer(%s): no renderer bound yet, nothing mounted.", persona_name
            )
            return
        try:
            renderer.mount()
        except Exception:
            logger.exception("Renderer.mount() failed for persona %s.", persona_name)
            return
        self._mounted_persona_name = persona_name
        logger.info("Mounted renderer for persona: %s.", persona_name)

    def refresh(self) -> None:
        """The real per-tick entry point (Sprint 5.14 wires the real
        trigger). Never raises — any exception from the computer or the
        renderer is caught, logged, and skipped for that tick (Fail
        Gracefully); full multi-scenario hardening is Sprint 5.15's job,
        the same "some hardening lands with the component, the rest at
        the dedicated hardening sprint" split this project has used
        before (e.g. Sprint 4.6's resource gate ahead of Sprint 4.12).

        Sprint 5.9: also rolls one ambient gesture per tick, using the
        just-computed state's own gesture_probability and the active
        persona's name — inside this same try/except, so a
        GestureEngine/renderer failure here degrades exactly like a
        render_state() failure already does."""
        if self._mounted_persona_name is None:
            return
        try:
            active_persona = self._persona_manager.active_persona()
            computer = self._state_computers.get(active_persona.name)
            if computer is None:
                logger.warning(
                    "refresh(): no PresentationStateComputer bound for active persona %s.",
                    active_persona.name,
                )
                return
            renderer = self._renderers.get(self._mounted_persona_name)
            if renderer is None:
                return
            emotional_state = self._emotional_state_manager.current_state()
            operating_mode = self._quiet_mode_controller.current_mode()
            state = computer.compute(emotional_state, operating_mode)
            self._last_state_by_persona[active_persona.name] = state
            renderer.render_state(state)
            event = self._gesture_engine.maybe_roll_ambient_gesture(
                state.gesture_probability, active_persona.name
            )
            if event is not None:
                self.dispatch_gesture(event)
        except Exception:
            logger.exception("PresentationController.refresh() failed; skipping this tick.")

    def dispatch_gesture(self, event: GestureEvent) -> None:
        """Routes a GestureEvent (from trigger_event()'s own future live
        caller at Sprint 5.14, or refresh()'s own ambient roll above) to
        the currently-mounted renderer's trigger_gesture(). A no-op if
        nothing is mounted or the renderer raises — never propagates,
        matching every other renderer call site in this class."""
        if self._mounted_persona_name is None:
            return
        renderer = self._renderers.get(self._mounted_persona_name)
        if renderer is None:
            return
        try:
            renderer.trigger_gesture(event.gesture_id)
        except Exception:
            logger.exception(
                "Renderer.trigger_gesture(%s) failed for a mounted renderer.", event.gesture_id
            )

    def last_state_for(self, persona_name: str) -> PresentationState | None:
        """The most recently computed PresentationState for persona_name
        (Sprint 5.10) — None if refresh() has never run for that persona
        yet, an honest gap rather than an error. TransitionEngine's own
        SAVING_STATE phase is the real caller."""
        return self._last_state_by_persona.get(persona_name)

    def apply_state(self, state: PresentationState) -> None:
        """Renders a given PresentationState directly through whatever
        renderer is currently mounted (Sprint 5.10) — bypasses
        PresentationStateComputer.compute() for this one call.
        TransitionEngine's own RESTORING_CONVERSATION phase uses this to
        replay a cached state onto a freshly-mounted renderer. A no-op
        if nothing is mounted; never raises if the renderer itself
        raises, matching every other renderer call site in this class."""
        if self._mounted_persona_name is None:
            return
        renderer = self._renderers.get(self._mounted_persona_name)
        if renderer is None:
            return
        try:
            renderer.render_state(state)
        except Exception:
            logger.exception("Renderer.render_state() failed applying a cached state.")

    def _unmount_current(self) -> None:
        if self._mounted_persona_name is None:
            return
        renderer = self._renderers.get(self._mounted_persona_name)
        self._mounted_persona_name = None
        if renderer is None:
            return
        try:
            renderer.unmount()
        except Exception:
            logger.exception("Renderer.unmount() failed for a previously-mounted renderer.")
