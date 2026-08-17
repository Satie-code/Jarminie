"""Minie UI preview — Minie Persona UI workstream.

A lightweight, standalone way to visually iterate on `ui/minie/minie_shell.py`
without the full AI stack (no real config file, no SQLite connections, no
Whisper/Coqui/Chroma/Ollama, no VTube Studio) — the brief's own explicit
request for "a lightweight UI preview/demo mode... we need to visually
test Minie without loading the entire AI stack."

Deliberately a SEPARATE, standalone script rather than a branch inside
`ui/app.py`'s real `run_app()` — the brief's own "keep preview mode
clearly isolated... do NOT put fake/mock behavior into production
paths" is satisfied more strongly this way: every fake object below
lives only in this file, so there is zero risk of preview-only mock
behavior ever executing on a real run through `main.py`. Gated behind
the `MINIE_UI_PREVIEW` environment variable regardless (this module
refuses to run without it set) purely so the intent of invoking it is
always explicit, matching the brief's own naming.

Run with (from the repo root, inside the project's venv)::

    MINIE_UI_PREVIEW=1 python minie_ui_preview.py          # bash
    $env:MINIE_UI_PREVIEW=1; python minie_ui_preview.py     # PowerShell

Every fake collaborator below returns REAL dataclass instances
(`ResourceSnapshot`, `EmotionalState`, `PresentationState`,
`ScheduledItem`, `WeatherSnapshot`, ...) — never a bare `MagicMock` — so
`MinieShell` and every widget beneath it run through exactly the same
code paths a production run would, just fed synthetic, slowly-animating
values instead of real backend reads. Session state cycles
IDLE -> LISTENING -> PROCESSING -> SPEAKING on a timer (demonstrating
the greeting card / speech bubble / status card / avatar glow all
reacting), emotion dimensions drift sinusoidally (demonstrating the
emotion bars animating), and the avatar connection flips periodically
(demonstrating both the "connected" and "Minie avatar unavailable +
retry" states) — the brief's own "simulate listening/thinking/speaking...
simulate emotion changes... simulate task updates" requirements.
"""

from __future__ import annotations

import math
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow

from config.schema import PresentationConfig, UIConfig
from core.resource_monitor import ResourceSnapshot
from emotion.state_manager import EmotionalState
from presentation.minie_theme import GLOW_DEFAULT, PRIMARY_ACCENT_DEFAULT
from presentation.presentation_state import PresentationState
from scheduler.scheduler_model import ItemType, ScheduledItem
from services.weather_service import DayForecast, WeatherSnapshot
from ui.minie.minie_shell import MinieShell
from voice.session_manager import SessionState

_SESSION_STATE_CYCLE = (
    SessionState.IDLE,
    SessionState.LISTENING,
    SessionState.PROCESSING,
    SessionState.SPEAKING,
)
_SESSION_STATE_STEP_MS = 3000
_EMOTION_TICK_MS = 400
_AVATAR_TOGGLE_MS = 9000


class _FakeCoreManager:
    """Returns real dataclass instances, never a bare MagicMock — see
    this module's own docstring for why that matters here."""

    def __init__(self) -> None:
        self._presentation_config = PresentationConfig()
        self._ui_config = UIConfig(user_display_name="Sattie", status_refresh_interval_ms=1000)

    def ui_config(self) -> UIConfig:
        return self._ui_config

    def presentation_config(self) -> PresentationConfig:
        return self._presentation_config

    def check_resources(self) -> ResourceSnapshot:
        return ResourceSnapshot(
            cpu_percent=24.0, ram_percent=48.0, disk_percent=61.0, battery_percent=78.0,
            timestamp=datetime.now(UTC),
        )


class _FakeAvatarRenderer:
    """Flips connected/disconnected on a timer so the preview
    demonstrates both `MinieAvatarStage` states (see this module's own
    docstring)."""

    def __init__(self) -> None:
        self._connected = True

    def mount(self) -> None:
        self._connected = True

    def unmount(self) -> None:
        self._connected = False

    def render_state(self, state: PresentationState) -> None:
        pass

    def trigger_gesture(self, gesture_id: str) -> None:
        pass

    def set_expression(self, expression_id: str) -> None:
        pass

    def set_mouth_open(self, amount: float) -> None:
        pass

    def set_eye_target(self, x: float, y: float) -> None:
        pass

    def is_connected(self) -> bool:
        return self._connected

    def toggle(self) -> None:
        self._connected = not self._connected


class _FakePresentationController:
    def __init__(self) -> None:
        self._state = PresentationState(
            smile_intensity=0.6, eye_openness=0.8, voice_warmth=0.6, animation_speed=1.1,
            particle_density=0.45, lighting_color=GLOW_DEFAULT, ui_accent=PRIMARY_ACCENT_DEFAULT,
            gesture_probability=0.3, avatar_focus="user", persona_name="minie",
            computed_at=datetime.now(UTC),
        )

    def last_state_for(self, persona_name: str) -> PresentationState | None:
        return self._state if persona_name == "minie" else None


class _FakeEmotionalStateManager:
    """Drifts every dimension sinusoidally, each on its own phase, so
    every emotion bar visibly animates independently rather than moving
    in lockstep."""

    def __init__(self) -> None:
        self._start = time.monotonic()

    def current_state(self) -> EmotionalState:
        elapsed = time.monotonic() - self._start
        return EmotionalState(
            mood=60.0 * math.sin(elapsed * 0.15),
            energy=50.0 + 30.0 * math.sin(elapsed * 0.11 + 1.0),
            stress=35.0 + 20.0 * math.sin(elapsed * 0.08 + 2.0),
            focus=55.0 + 25.0 * math.sin(elapsed * 0.13 + 0.5),
            comfort=70.0 + 20.0 * math.sin(elapsed * 0.09 + 1.5),
            social_energy=75.0 + 20.0 * math.sin(elapsed * 0.10 + 2.5),
            conversation_momentum=60.0,
            updated_at=datetime.now(UTC),
        )


class _FakeVoiceSessionManager:
    def __init__(self) -> None:
        self._index = 0

    def current_session_state(self) -> SessionState:
        return _SESSION_STATE_CYCLE[self._index % len(_SESSION_STATE_CYCLE)]

    def advance(self) -> None:
        self._index += 1


@dataclass
class _FakeCalendarStore:
    items: list[ScheduledItem] = field(default_factory=list)

    def list_due_within(self, window_end: datetime, *, include_completed: bool = False):
        if include_completed:
            return list(self.items)
        return [item for item in self.items if not item.is_completed]

    def mark_completed(self, item_id: str) -> bool:
        for item in self.items:
            if item.item_id == item_id:
                item.is_completed = True
                return True
        return False


def _seed_calendar_store() -> _FakeCalendarStore:
    today = datetime.now(UTC).replace(hour=22, minute=0, second=0, microsecond=0)
    return _FakeCalendarStore(
        items=[
            ScheduledItem(
                item_id="1", item_type=ItemType.DEADLINE, title="Finish ROS 2 project",
                scheduled_at=today, created_at=datetime.now(UTC), is_completed=True,
            ),
            ScheduledItem(
                item_id="2", item_type=ItemType.EVENT, title="Read a book",
                scheduled_at=today + timedelta(minutes=30), created_at=datetime.now(UTC),
            ),
            ScheduledItem(
                item_id="3", item_type=ItemType.EVENT, title="Work out",
                scheduled_at=today.replace(hour=18, minute=0), created_at=datetime.now(UTC),
            ),
        ]
    )


class _FakeCommunicationPipeline:
    """submit_text() runs on MinieMessageBar's own background thread —
    a short sleep here stands in for a real Decision Engine turn's own
    latency, so the "Thinking about that... ♡" state is visible rather
    than resolving instantly."""

    def submit_text(self, transcript: str, session_id: str) -> str:
        time.sleep(0.6)
        return f"Aww, you said {transcript!r}! I'm just a preview, but that sounds lovely. ♡"


class _FakeWeatherService:
    def current(self) -> WeatherSnapshot:
        return WeatherSnapshot(
            temperature_c=28.0, condition_text="Partly Cloudy", high_c=29.0, low_c=21.0,
            location_name="Gurgaon, India",
            forecast=[
                DayForecast(day_label="Sat", high_c=29.0, low_c=21.0, condition_text="Sunny"),
                DayForecast(day_label="Sun", high_c=30.0, low_c=22.0, condition_text="Sunny"),
                DayForecast(day_label="Mon", high_c=29.0, low_c=21.0, condition_text="Cloudy"),
                DayForecast(day_label="Tue", high_c=28.0, low_c=20.0, condition_text="Cloudy"),
            ],
            fetched_at=datetime.now(UTC),
        )


def main() -> int:
    if not os.environ.get("MINIE_UI_PREVIEW"):
        print(
            "minie_ui_preview.py refuses to run without MINIE_UI_PREVIEW set — "
            "this keeps preview mode an explicit, deliberate choice, never an "
            "accidental one. Try: MINIE_UI_PREVIEW=1 python minie_ui_preview.py"
        )
        return 1

    app = QApplication.instance() or QApplication(sys.argv)

    core_manager = _FakeCoreManager()
    avatar_renderer = _FakeAvatarRenderer()
    presentation_controller = _FakePresentationController()
    emotional_state_manager = _FakeEmotionalStateManager()
    voice_session_manager = _FakeVoiceSessionManager()
    calendar_store = _seed_calendar_store()
    pipeline = _FakeCommunicationPipeline()
    weather_service = _FakeWeatherService()

    shell = MinieShell(
        core_manager,
        avatar_renderer,
        presentation_controller,
        emotional_state_manager,
        voice_session_manager,
        calendar_store,
        pipeline,
        weather_service,
    )

    window = QMainWindow()
    window.setWindowTitle("Minie UI Preview")
    window.resize(1600, 950)
    window.setCentralWidget(shell)
    window.show()

    session_timer = QTimer()
    session_timer.setInterval(_SESSION_STATE_STEP_MS)
    session_timer.timeout.connect(voice_session_manager.advance)
    session_timer.start()

    emotion_timer = QTimer()
    emotion_timer.setInterval(_EMOTION_TICK_MS)
    emotion_timer.timeout.connect(shell._ui_state_adapter.refresh)
    emotion_timer.start()

    avatar_timer = QTimer()
    avatar_timer.setInterval(_AVATAR_TOGGLE_MS)
    avatar_timer.timeout.connect(avatar_renderer.toggle)
    avatar_timer.start()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
