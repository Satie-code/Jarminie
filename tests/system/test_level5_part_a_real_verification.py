"""Level 5 Part A real VTube Studio verification (Sprint 5.16) — opt-in,
NOT part of the fast committed suite's usual guarantees, mirroring
test_level3_real_model_verification.py's/test_level4_part_b_real_
verification.py's own established shape.

Every other test in this project fakes VTube Studio's own WebSocket
boundary throughout (Sprint 5.8 onward, by design — presentation/
vtube_studio_renderer.py's own docstring). This file is where a real,
locally-running VTube Studio instance is exercised for real, if
available, skipping cleanly (never failing) if it is not — a heavier,
more manual external dependency than any prior real-verification tier
in this project (a GUI application a person must launch and configure a
model into, not an installable/scriptable local service like Ollama),
per this sprint's own Potential Risks.

Two-layer skip check, mirroring test_level4_part_b_real_verification.py's
own separately-reported-dependency precedent: (1) is anything even
listening at the configured host:port at all (a raw socket check,
cheaper and more specific than attempting the full plugin handshake);
(2) does a real VTubeStudioAvatarRenderer.mount() actually connect AND
authenticate (a previously-approved, persisted plugin token — see
backlog/technical_debt.md item 37/38 for how one was obtained this
project's own development session — or a fresh one if VTube Studio's
own Allow-popup is answered quickly enough within the configured
vtube_studio_connection_timeout_seconds)."""

import socket

import pytest

from config.schema import PresentationConfig
from presentation.presentation_state import PresentationState
from presentation.vtube_studio_renderer import VTubeStudioAvatarRenderer


def _real_presentation_config() -> PresentationConfig:
    return PresentationConfig()


def _port_is_listening(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture
def connected_renderer():
    """Runs before every test in this file. Skips (never fails) if
    nothing is listening at all, or if a real connect+authenticate
    attempt doesn't succeed (VTube Studio running but no plugin token
    approved yet, or a Live2D model not loaded) — each layer reported
    with its own specific, actionable skip reason, matching this
    module's own docstring."""
    config = _real_presentation_config()
    if not _port_is_listening(config.vtube_studio_host, config.vtube_studio_port):
        pytest.skip(
            f"Nothing is listening at {config.vtube_studio_host}:{config.vtube_studio_port} — "
            "real Level 5 Part A VTube Studio verification skipped. Launch VTube Studio with "
            "its own API server enabled (Settings > API) and re-run to actually exercise this "
            "file."
        )

    renderer = VTubeStudioAvatarRenderer(config)
    renderer.mount()
    if not renderer.is_connected():
        pytest.skip(
            f"VTube Studio is listening at {config.vtube_studio_host}:{config.vtube_studio_port} "
            "but a real connect+authenticate attempt did not succeed — real Level 5 Part A "
            "verification skipped. If this is the first-ever connection, VTube Studio shows an "
            "Allow-plugin popup that needs a human click within "
            f"{config.vtube_studio_connection_timeout_seconds}s (see backlog/technical_debt.md "
            "item 38 for the known first-run timing gap); re-run once a token is persisted via "
            "SecretStore (OS credential storage, service 'jarminei', key "
            "'vtube_studio_auth_token' — Sprint 6.20), or after clicking Allow in time."
        )
    try:
        yield renderer
    finally:
        renderer.unmount()


def _sample_state() -> PresentationState:
    import datetime as dt

    return PresentationState(
        smile_intensity=0.5,
        eye_openness=0.6,
        voice_warmth=0.4,
        animation_speed=1.0,
        particle_density=0.3,
        lighting_color="#C8A8E9",
        ui_accent="#B76E79",
        gesture_probability=0.2,
        avatar_focus="user",
        persona_name="minie",
        computed_at=dt.datetime.now(dt.UTC),
    )


def test_real_connect_and_authenticate_succeeds(connected_renderer):
    """The two-layer skip check above already proves this by the time
    this test body runs — a real, explicit assertion here anyway, so a
    passing test run has a real, self-contained claim to point to (not
    just "didn't skip")."""
    assert connected_renderer.is_connected() is True


def test_real_parameter_injection_round_trip_does_not_disconnect(connected_renderer):
    """render_state() -> a real InjectParameterDataRequest sent to VTube
    Studio, over the real connection. Never raises regardless of outcome
    (VTubeStudioAvatarRenderer's own "disconnected, never crash"
    contract) — the real, meaningful signal here is that a real round
    trip completes without VTube Studio tearing down the connection
    (is_connected() still True afterward): if the loaded model doesn't
    define one of the configured vtube_studio_parameter_mapping
    parameter names, VTube Studio replies with a real APIError (handled,
    logged once, connection kept alive) rather than dropping the socket
    — both outcomes are legitimate; a real disconnect would not be."""
    connected_renderer.render_state(_sample_state())

    assert connected_renderer.is_connected() is True


def test_real_hotkey_trigger_request_does_not_disconnect(connected_renderer):
    """set_expression()/trigger_gesture() both send a real
    HotkeyTriggerRequest — the second of the two message shapes
    backlog/technical_debt.md item 37 still named as unverified against
    a live instance after this project's own 2026-08-04 connection
    session (which verified AuthenticationTokenRequest/
    AuthenticationRequest/CurrentModelRequest only). An unrecognized
    hotkey ID is expected to be a real, harmless no-op or a logged
    APIError from VTube Studio's own side — never a disconnect."""
    connected_renderer.set_expression("neutral")

    assert connected_renderer.is_connected() is True
