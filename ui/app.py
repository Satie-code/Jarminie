"""Desktop shell bootstrap — the single place that constructs a QApplication.

See docs/sprint_book/sprint_1_6.md.

Sprint 5.14: run_app() gains four Level 5 handles (presentation_controller/
jarvis_renderer/minie_renderer/transition_engine) — all already
constructed at main.py's own composition-root time, threaded through
here only because MainWindow's own Qt-layer assembly (PresentationHostWidget,
QtTransitionOverlay) cannot happen before this function's own QApplication
exists (see ui/main_window.py's own docstring).

Runtime Phase 4 (Runtime Refactor Sprint): run_app() no longer calls the
whole-graph core_manager.startup() before showing the window. Only Tier A
(ServiceTier.ALWAYS_LOADED) starts synchronously now; Tier B (WARM) and
Tier C (COLD) start on a background daemon thread AFTER the window is
already shown — matching this project's existing threading.Thread(
daemon=True, ...) idiom (voice/wake_word.py's listener thread, voice/
session_manager.py's watchdog) rather than introducing QThread. Nothing
on that background thread touches a Qt widget — every registered
module's own start() is a plain Python call; no cross-thread Qt
marshaling is needed here (see presentation/jarvis_renderer.py's
_run_on_main_thread() for the established fallback pattern a later
Runtime Phase can reuse if one ever needs to push state onto a widget
from that thread).

As of this phase, main.py still tags every registered module
ServiceTier.ALWAYS_LOADED by default (Runtime Phase 3's own default) — no
module is actually WARM/COLD yet, so this split has no real startup-time
effect in production until Runtime Phases 5-8 retag specific subsystems.
The mechanism is proven here first, against synthetic tiers in this
module's own tests (tests/unit/ui/test_app.py), deliberately decoupled
from which real subsystems end up in which tier.

JARVIS Holographic HUD reskin, Phase 4: run_app() gains calendar_store/
action_registry, threaded straight through to MainWindow for the same
reason as the four Level 5 handles above — both are already constructed
in main.py, only newly needed by the UI layer starting this phase.

Phase 6: run_app() gains voice_session_manager/pipeline (a
CommunicationPipeline), the identical "already constructed in main.py,
only newly needed by the UI layer" reasoning.
"""

import sys
import threading
import time

from PySide6.QtWidgets import QApplication

from core.logging_setup import get_logger
from core.manager import CoreManager
from core.runtime_manager import ServiceTier
from device_control.action_engine import ActionRegistry
from presentation import theme
from presentation.jarvis_renderer import JarvisRenderer
from presentation.minie_renderer import MinieRenderer
from presentation.presentation_controller import PresentationController
from presentation.transition_engine import TransitionEngine
from scheduler.calendar_store import CalendarStore
from ui.main_window import MainWindow
from voice.pipeline import CommunicationPipeline
from voice.session_manager import VoiceSessionManager

logger = get_logger(__name__)


def run_app(
    core_manager: CoreManager,
    presentation_controller: PresentationController,
    jarvis_renderer: JarvisRenderer,
    minie_renderer: MinieRenderer,
    transition_engine: TransitionEngine,
    calendar_store: CalendarStore,
    action_registry: ActionRegistry,
    voice_session_manager: VoiceSessionManager,
    pipeline: CommunicationPipeline,
) -> int:
    """Start Tier A, show the main window, warm up Tier B/C in the
    background, and run the Qt event loop.

    Returns the process exit code (from QApplication.exec()).
    """
    # QApplication.instance() or ... rather than an unconditional
    # QApplication(sys.argv): PySide6 raises RuntimeError on a second
    # QApplication construction in the same process. In real operation
    # this function is always the first thing to construct one (main.py's
    # own "sole composition root" ordering), so instance() is always None
    # there — this guard only ever matters for tests/unit/ui/test_app.py,
    # which shares a process-wide QApplication with every other test in
    # tests/unit/ui/ via pytest-qt's own session-scoped qapp fixture.
    app = QApplication.instance() or QApplication(sys.argv)
    # JARVIS Holographic HUD reskin, Phase 1: applied once, immediately
    # after QApplication exists and before any widget is constructed, so
    # every widget (including MainWindow's own children below) picks up
    # the theme from its very first paint rather than a visible flash of
    # Qt's own default style.
    theme.apply_dark_theme(app)
    window = MainWindow(
        core_manager,
        presentation_controller,
        jarvis_renderer,
        minie_renderer,
        transition_engine,
        calendar_store,
        action_registry,
        voice_session_manager,
        pipeline,
    )

    startup_started_at = time.monotonic()
    core_manager.startup_tier(ServiceTier.ALWAYS_LOADED)
    logger.info(
        "Tier A (always-loaded) startup took %.3fs.", time.monotonic() - startup_started_at
    )

    window.refresh_presentation_host()
    logger.info("JARMINEI is running.")

    show_started_at = time.monotonic()
    window.show()
    logger.info(
        "window.show() took %.3fs (%.3fs elapsed since startup began).",
        time.monotonic() - show_started_at,
        time.monotonic() - startup_started_at,
    )

    warm_up_thread = threading.Thread(
        target=_warm_up_remaining_tiers,
        args=(core_manager, startup_started_at),
        name="runtime-warm-up",
        daemon=True,
    )
    warm_up_thread.start()

    return app.exec()


def _warm_up_remaining_tiers(core_manager: CoreManager, startup_started_at: float) -> None:
    """Runs on a background daemon thread, started by run_app() right
    after the window is shown. Starts WARM then COLD, in that order.

    Wrapped in a top-level try/except so an unexpected failure here (as
    opposed to a per-module start() failure, which CoreManager.
    _start_module() already catches internally and marks that one module
    FAILED without raising) can't crash silently as an unhandled thread
    exception — logged instead, matching the Fail Gracefully Rule every
    other subsystem in this app already follows."""
    try:
        core_manager.startup_tier(ServiceTier.WARM)
        core_manager.startup_tier(ServiceTier.COLD)
        logger.info(
            "Background warm-up complete, %.3fs since startup began.",
            time.monotonic() - startup_started_at,
        )
    except Exception:
        logger.exception("Background warm-up thread failed unexpectedly.")
