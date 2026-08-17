"""Unit tests for presentation.vtube_studio_renderer.

Never talks to a real running VTube Studio instance (mirrors
tests/unit/internet/test_brave_search_provider.py's own "patch the
transport" precedent, and test_level4_part_b_real_verification.py's
"real network call is opt-in only" discipline) — every test here
patches presentation.vtube_studio_renderer.connect with a fake
connection object whose send()/recv()/close() this file fully
controls.

Sprint 5.15 (scenario a): a disconnected call now also triggers a
bounded background reconnect attempt (see that module's own "Bounded
background reconnect" docstring section) — the shared `config` fixture
below sets `vtube_studio_reconnect_max_attempts=0` so every pre-existing
"is a no-op when disconnected" test keeps its original, simple meaning
(zero reconnect attempts, zero background threads, `connect` need not
stay patched beyond an initial mount()). The dedicated
"scenario (a): bounded reconnect" section further down uses its own
config with a real positive budget and waits on
`renderer._reconnect_finished` (mirrors test_minie_renderer.py's own
`mount_called` threading.Event precedent) to observe the background
attempt deterministically.
"""

import ast
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config.schema import PresentationConfig
from presentation.presentation_state import PresentationState
from presentation.vtube_studio_renderer import VTubeStudioAvatarRenderer


class _FakeSecretStore:
    """In-memory stand-in for security.secret_store.SecretStore — this
    file's own established "patch the boundary" precedent (see the
    `connect` patching throughout below), applied to Sprint 6.20's
    SecretStore collaborator so no test here ever touches the real OS
    credential store."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get_secret(self, name: str, env_fallback: str | None = None) -> str | None:
        return self._values.get(name)

    def set_secret(self, name: str, value: str) -> None:
        self._values[name] = value


@pytest.fixture(autouse=True)
def _stub_secret_store(monkeypatch):
    """Every renderer constructed below without an explicit secret_store
    argument gets a fresh, isolated _FakeSecretStore instead of a real
    SecretStore() — otherwise every test in this file would round-trip
    through this machine's real Windows Credential Manager entry under
    service "jarminei", leaking a persisted token across test runs."""
    monkeypatch.setattr("presentation.vtube_studio_renderer.SecretStore", _FakeSecretStore)

_WAIT_TIMEOUT = 2.0

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_ALLOWED_IMPORTERS = {
    os.path.normpath(os.path.join(_REPO_ROOT, "presentation", "vtube_studio_renderer.py")),
    os.path.normpath(os.path.join(_REPO_ROOT, "presentation", "avatar_renderer_registry.py")),
}


def _imports_vtube_studio_renderer(path: str) -> bool:
    """AST-based, not a substring grep — a docstring merely *mentioning*
    VTubeStudioAvatarRenderer by name (this project's own established
    documentation style, e.g. presentation/renderer.py's own docstring
    naming it as the swap-target example) is not a real code dependency
    and must not be flagged."""
    with open(path, encoding="utf-8") as handle:
        try:
            tree = ast.parse(handle.read(), filename=path)
        except SyntaxError:
            return False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and "vtube_studio_renderer" in node.module
        ):
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "vtube_studio_renderer" in alias.name:
                    return True
    return False


def test_no_file_outside_the_registry_imports_vtube_studio_renderer():
    """Mechanical check (Acceptance Criteria/Architecture Notes): the
    swap-target guarantee holds only if nothing outside
    presentation/vtube_studio_renderer.py (and the one legitimate
    exception, avatar_renderer_registry.py, whose whole job is exactly
    this narrow translation — the same exception
    internet/search_provider_registry.py already sets for its own
    concrete providers) imports it directly. Test files are exempt —
    they legitimately construct/verify the real class."""
    violations = []
    for dirpath, _dirnames, filenames in os.walk(_REPO_ROOT):
        if os.sep + ".venv" + os.sep in dirpath + os.sep or "\\.venv\\" in dirpath:
            continue
        if os.sep + "tests" + os.sep in dirpath + os.sep or "\\tests\\" in dirpath:
            continue
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = os.path.normpath(os.path.join(dirpath, filename))
            if path in _ALLOWED_IMPORTERS:
                continue
            if _imports_vtube_studio_renderer(path):
                violations.append(path)

    assert violations == []


def _sample_state(
    smile_intensity: float = 0.5, eye_openness: float = 0.6, voice_warmth: float = 0.4
):
    return PresentationState(
        smile_intensity=smile_intensity,
        eye_openness=eye_openness,
        voice_warmth=voice_warmth,
        animation_speed=1.0,
        particle_density=0.3,
        lighting_color="#C8A8E9",
        ui_accent="#B76E79",
        gesture_probability=0.2,
        avatar_focus="user",
        persona_name="minie",
        computed_at=datetime.now(UTC),
    )


def _fake_connection(responses: list[dict] | None = None) -> MagicMock:
    """A MagicMock standing in for a websockets.sync.client connection
    — recv() returns each of `responses` (JSON-encoded) in order."""
    conn = MagicMock()
    if responses is not None:
        conn.recv.side_effect = [json.dumps(r) for r in responses]
    return conn


_AUTH_TOKEN_RESPONSE = {
    "messageType": "AuthenticationTokenResponse",
    "data": {"authenticationToken": "fresh-token-123"},
}
_AUTH_SUCCESS_RESPONSE = {"messageType": "AuthenticationResponse", "data": {"authenticated": True}}
_AUTH_FAILURE_RESPONSE = {"messageType": "AuthenticationResponse", "data": {"authenticated": False}}
_INJECT_OK_RESPONSE = {"messageType": "InjectParameterDataResponse", "data": {}}
_API_ERROR_RESPONSE = {"messageType": "APIError", "data": {"message": "Unknown parameter."}}


@pytest.fixture
def config(tmp_path) -> PresentationConfig:
    return PresentationConfig(
        vtube_studio_auth_token_path=str(tmp_path / "vtube_studio_token.json"),
        # Sprint 5.15 scenario (a): disabled here so every pre-existing
        # test in this file keeps its original "zero background activity
        # when disconnected" meaning — see this module's own "bounded
        # reconnect" section further down for dedicated coverage with a
        # real positive budget.
        vtube_studio_reconnect_max_attempts=0,
    )


# --- mount(): connect/authenticate/token-persist/reuse ------------------------


def test_mount_requests_and_persists_a_fresh_token_when_none_exists(config):
    conn = _fake_connection([_AUTH_TOKEN_RESPONSE, _AUTH_SUCCESS_RESPONSE])
    secret_store = _FakeSecretStore()
    with patch("presentation.vtube_studio_renderer.connect", return_value=conn):
        renderer = VTubeStudioAvatarRenderer(config, secret_store)
        renderer.mount()

    assert renderer._connected is True
    assert secret_store.get_secret("vtube_studio_auth_token") == "fresh-token-123"


def test_mount_reuses_a_persisted_token_without_requesting_a_new_one(config):
    secret_store = _FakeSecretStore()
    secret_store.set_secret("vtube_studio_auth_token", "already-have-this")
    conn = _fake_connection([_AUTH_SUCCESS_RESPONSE])

    with patch("presentation.vtube_studio_renderer.connect", return_value=conn):
        renderer = VTubeStudioAvatarRenderer(config, secret_store)
        renderer.mount()

    assert renderer._connected is True
    assert conn.send.call_count == 1  # only AuthenticationRequest, no token request


def test_mount_requests_a_new_token_when_the_persisted_one_is_rejected(config):
    secret_store = _FakeSecretStore()
    secret_store.set_secret("vtube_studio_auth_token", "stale-token")
    conn = _fake_connection([_AUTH_FAILURE_RESPONSE, _AUTH_TOKEN_RESPONSE, _AUTH_SUCCESS_RESPONSE])

    with patch("presentation.vtube_studio_renderer.connect", return_value=conn):
        renderer = VTubeStudioAvatarRenderer(config, secret_store)
        renderer.mount()

    assert renderer._connected is True
    assert secret_store.get_secret("vtube_studio_auth_token") == "fresh-token-123"


def test_mount_never_writes_a_plaintext_token_file(config, tmp_path):
    """Sprint 6.20 — Permission & Encryption Audit regression test: the
    auth token now round-trips only through SecretStore — nothing is
    ever written under tmp_path, including at
    config.vtube_studio_auth_token_path itself (still config-driven, but
    no longer written to by fresh code — see this module's own Sprint
    6.20 Objectives)."""
    conn = _fake_connection([_AUTH_TOKEN_RESPONSE, _AUTH_SUCCESS_RESPONSE])
    with patch("presentation.vtube_studio_renderer.connect", return_value=conn):
        renderer = VTubeStudioAvatarRenderer(config)
        renderer.mount()

    assert renderer._connected is True
    assert not Path(config.vtube_studio_auth_token_path).exists()
    assert list(tmp_path.iterdir()) == []


def test_mount_is_idempotent_when_already_connected(config):
    conn = _fake_connection([_AUTH_TOKEN_RESPONSE, _AUTH_SUCCESS_RESPONSE])
    with patch("presentation.vtube_studio_renderer.connect", return_value=conn) as mock_connect:
        renderer = VTubeStudioAvatarRenderer(config)
        renderer.mount()
        renderer.mount()

    mock_connect.assert_called_once()


# --- mount() never raises (Acceptance Criteria) -------------------------------


def test_mount_never_raises_when_the_connection_itself_fails(config):
    with patch(
        "presentation.vtube_studio_renderer.connect", side_effect=OSError("no route to host")
    ):
        renderer = VTubeStudioAvatarRenderer(config)
        renderer.mount()  # must not raise

    assert renderer._connected is False


def test_mount_never_raises_when_authentication_ultimately_fails(config):
    conn = _fake_connection(
        [_AUTH_TOKEN_RESPONSE, _AUTH_FAILURE_RESPONSE]  # fresh token still rejected
    )
    with patch("presentation.vtube_studio_renderer.connect", return_value=conn):
        renderer = VTubeStudioAvatarRenderer(config)
        renderer.mount()  # must not raise

    assert renderer._connected is False


def test_mount_never_raises_when_vts_returns_no_token(config):
    conn = _fake_connection([{"messageType": "AuthenticationTokenResponse", "data": {}}])
    with patch("presentation.vtube_studio_renderer.connect", return_value=conn):
        renderer = VTubeStudioAvatarRenderer(config)
        renderer.mount()  # must not raise

    assert renderer._connected is False


# --- disconnected-no-op behavior for every method (Testing Checklist) --------


def test_render_state_is_a_noop_when_disconnected(config):
    renderer = VTubeStudioAvatarRenderer(config)
    renderer.render_state(_sample_state())  # never mounted — must not raise


def test_set_expression_is_a_noop_when_disconnected(config):
    renderer = VTubeStudioAvatarRenderer(config)
    renderer.set_expression("smile")  # must not raise


def test_set_mouth_open_is_a_noop_when_disconnected(config):
    renderer = VTubeStudioAvatarRenderer(config)
    renderer.set_mouth_open(0.5)  # must not raise


def test_set_eye_target_is_a_noop_when_disconnected(config):
    renderer = VTubeStudioAvatarRenderer(config)
    renderer.set_eye_target(0.2, -0.3)  # must not raise


def test_trigger_gesture_is_a_noop_when_disconnected(config):
    renderer = VTubeStudioAvatarRenderer(config)
    renderer.trigger_gesture("wave")  # must not raise


def test_unmount_is_a_noop_when_never_mounted(config):
    renderer = VTubeStudioAvatarRenderer(config)
    renderer.unmount()  # must not raise


# --- render_state()'s parameter-mapping translation ---------------------------


def _mounted_renderer(
    config, extra_responses: list[dict]
) -> tuple[VTubeStudioAvatarRenderer, MagicMock]:
    conn = _fake_connection([_AUTH_TOKEN_RESPONSE, _AUTH_SUCCESS_RESPONSE, *extra_responses])
    with patch("presentation.vtube_studio_renderer.connect", return_value=conn):
        renderer = VTubeStudioAvatarRenderer(config)
        renderer.mount()
    return renderer, conn


def test_render_state_sends_every_mapped_parameter(config):
    renderer, conn = _mounted_renderer(config, [_INJECT_OK_RESPONSE])

    renderer.render_state(_sample_state(smile_intensity=0.7, eye_openness=0.8, voice_warmth=0.6))

    sent_payload = json.loads(conn.send.call_args.args[0])
    assert sent_payload["messageType"] == "InjectParameterDataRequest"
    sent_params = {p["id"]: p["value"] for p in sent_payload["data"]["parameterValues"]}
    assert sent_params["ParamMouthForm"] == 0.7
    assert sent_params["ParamEyeLOpen"] == 0.8
    assert sent_params["ParamGlow"] == 0.6


def test_render_state_never_raises_when_vts_rejects_the_injection(config):
    renderer, _conn = _mounted_renderer(config, [_API_ERROR_RESPONSE])

    renderer.render_state(_sample_state())  # must not raise


def test_render_state_warns_only_once_for_a_repeated_api_error(config, caplog):
    renderer, conn = _mounted_renderer(config, [_API_ERROR_RESPONSE])
    conn.recv.side_effect = [json.dumps(_API_ERROR_RESPONSE)] * 5

    with caplog.at_level("WARNING"):
        renderer.render_state(_sample_state())
        renderer.render_state(_sample_state())
        renderer.render_state(_sample_state())

    mismatch_warnings = [r for r in caplog.records if "rejected a parameter injection" in r.message]
    assert len(mismatch_warnings) == 1


def test_render_state_warns_once_for_an_unknown_presentation_state_field(config, caplog):
    bad_config = PresentationConfig(
        vtube_studio_auth_token_path=config.vtube_studio_auth_token_path,
        vtube_studio_parameter_mapping={"not_a_real_field": "ParamSomething"},
    )
    renderer, conn = _mounted_renderer(bad_config, [])
    conn.recv.side_effect = None
    conn.reset_mock()  # discard the two mount()-time sends (token + auth requests)

    with caplog.at_level("WARNING"):
        renderer.render_state(_sample_state())
        renderer.render_state(_sample_state())

    unknown_field_warnings = [r for r in caplog.records if "unknown" in r.message.lower()]
    assert len(unknown_field_warnings) == 1
    assert conn.send.call_count == 0  # nothing valid to send — InjectParameterDataRequest skipped


def test_render_state_marks_disconnected_when_the_connection_is_lost_mid_session(config):
    renderer, conn = _mounted_renderer(config, [])
    conn.recv.side_effect = ConnectionError("connection lost")

    renderer.render_state(_sample_state())  # must not raise

    assert renderer._connected is False


# --- set_expression()/set_mouth_open()/set_eye_target()/trigger_gesture() ----


def test_set_expression_sends_a_hotkey_trigger_request(config):
    renderer, conn = _mounted_renderer(
        config, [{"messageType": "HotkeyTriggerResponse", "data": {}}]
    )

    renderer.set_expression("big_smile")

    sent_payload = json.loads(conn.send.call_args.args[0])
    assert sent_payload["messageType"] == "HotkeyTriggerRequest"
    assert sent_payload["data"]["hotkeyID"] == "big_smile"


def test_trigger_gesture_sends_a_hotkey_trigger_request(config):
    renderer, conn = _mounted_renderer(
        config, [{"messageType": "HotkeyTriggerResponse", "data": {}}]
    )

    renderer.trigger_gesture("wave")

    sent_payload = json.loads(conn.send.call_args.args[0])
    assert sent_payload["messageType"] == "HotkeyTriggerRequest"
    assert sent_payload["data"]["hotkeyID"] == "wave"


def test_set_mouth_open_injects_the_mouth_open_parameter(config):
    renderer, conn = _mounted_renderer(config, [_INJECT_OK_RESPONSE])

    renderer.set_mouth_open(0.9)

    sent_payload = json.loads(conn.send.call_args.args[0])
    params = {p["id"]: p["value"] for p in sent_payload["data"]["parameterValues"]}
    assert params["ParamMouthOpenY"] == 0.9


def test_set_eye_target_injects_both_axis_parameters(config):
    renderer, conn = _mounted_renderer(config, [_INJECT_OK_RESPONSE])

    renderer.set_eye_target(0.4, -0.6)

    sent_payload = json.loads(conn.send.call_args.args[0])
    params = {p["id"]: p["value"] for p in sent_payload["data"]["parameterValues"]}
    assert params["ParamEyeBallX"] == 0.4
    assert params["ParamEyeBallY"] == -0.6


# --- unmount() ------------------------------------------------------------------


def test_unmount_closes_the_connection_and_clears_connected_state(config):
    renderer, conn = _mounted_renderer(config, [])

    renderer.unmount()

    conn.close.assert_called_once()
    assert renderer._connected is False


def test_unmount_never_raises_even_if_close_itself_fails(config):
    renderer, conn = _mounted_renderer(config, [])
    conn.close.side_effect = RuntimeError("socket already dead")

    renderer.unmount()  # must not raise

    assert renderer._connected is False


# --- scenario (a): bounded background reconnect (Sprint 5.15) -----------------


@pytest.fixture
def reconnect_config(tmp_path) -> PresentationConfig:
    return PresentationConfig(
        vtube_studio_auth_token_path=str(tmp_path / "vtube_studio_token.json"),
        vtube_studio_reconnect_max_attempts=2,
    )


def test_a_disconnected_call_triggers_a_background_reconnect_that_can_succeed(reconnect_config):
    conn = _fake_connection([_AUTH_TOKEN_RESPONSE, _AUTH_SUCCESS_RESPONSE])
    with patch("presentation.vtube_studio_renderer.connect", return_value=conn) as mock_connect:
        renderer = VTubeStudioAvatarRenderer(reconnect_config)
        renderer.render_state(_sample_state())  # never mounted — triggers a reconnect attempt

        assert renderer._reconnect_finished.wait(timeout=_WAIT_TIMEOUT)

    mock_connect.assert_called_once()
    assert renderer._connected is True


def test_the_triggering_call_itself_still_returns_without_sending_anything(reconnect_config):
    """The reconnect happens in the background for a *future* call — the
    call that triggered it must still behave as the pre-existing no-op
    (never blocks, never itself sends render_state()'s own payload)."""
    conn = _fake_connection([_AUTH_TOKEN_RESPONSE, _AUTH_SUCCESS_RESPONSE])
    with patch("presentation.vtube_studio_renderer.connect", return_value=conn):
        renderer = VTubeStudioAvatarRenderer(reconnect_config)
        renderer.render_state(_sample_state())  # must not raise, must not block

        assert renderer._reconnect_finished.wait(timeout=_WAIT_TIMEOUT)

    # Only the reconnect's own AuthenticationTokenRequest/AuthenticationRequest
    # were sent — never an InjectParameterDataRequest for the triggering call.
    sent_types = [json.loads(c.args[0])["messageType"] for c in conn.send.call_args_list]
    assert "InjectParameterDataRequest" not in sent_types


def test_a_successful_reconnect_resets_the_attempt_budget(reconnect_config):
    conn = _fake_connection([_AUTH_TOKEN_RESPONSE, _AUTH_SUCCESS_RESPONSE])
    with patch("presentation.vtube_studio_renderer.connect", return_value=conn):
        renderer = VTubeStudioAvatarRenderer(reconnect_config)
        renderer.render_state(_sample_state())
        assert renderer._reconnect_finished.wait(timeout=_WAIT_TIMEOUT)

    assert renderer._reconnect_attempts_used == 0


def test_reconnect_attempts_are_bounded_then_permanently_no_op(reconnect_config):
    with patch(
        "presentation.vtube_studio_renderer.connect", side_effect=OSError("still down")
    ) as mock_connect:
        renderer = VTubeStudioAvatarRenderer(reconnect_config)

        # reconnect_config allows exactly 2 attempts — three separate
        # disconnected calls, each awaited before the next so the
        # in-flight guard never suppresses one that should count.
        for _ in range(3):
            renderer.render_state(_sample_state())
            assert renderer._reconnect_finished.wait(timeout=_WAIT_TIMEOUT)

    assert mock_connect.call_count == 2  # bounded — the third call attempted nothing
    assert renderer._connected is False


def test_an_explicit_unmount_mount_cycle_resets_the_exhausted_budget(reconnect_config):
    with patch(
        "presentation.vtube_studio_renderer.connect", side_effect=OSError("still down")
    ) as mock_connect:
        renderer = VTubeStudioAvatarRenderer(reconnect_config)
        for _ in range(2):  # exhausts the budget
            renderer.render_state(_sample_state())
            assert renderer._reconnect_finished.wait(timeout=_WAIT_TIMEOUT)
        assert mock_connect.call_count == 2

        renderer.unmount()
        renderer.mount()  # a real, explicit cycle — must not be silently skipped

    assert mock_connect.call_count == 3
    assert renderer._reconnect_attempts_used == 0


def test_a_reconnect_already_in_flight_is_not_duplicated(reconnect_config):
    release = threading.Event()
    connect_calls: list[str] = []

    def _slow_failing_connect(uri, **kwargs):
        connect_calls.append(uri)
        release.wait(timeout=_WAIT_TIMEOUT)
        raise OSError("still down")

    with patch("presentation.vtube_studio_renderer.connect", side_effect=_slow_failing_connect):
        renderer = VTubeStudioAvatarRenderer(reconnect_config)
        renderer.render_state(_sample_state())  # starts a reconnect, blocks inside connect()
        renderer.set_expression("smile")  # arrives while the first is still in flight

        release.set()
        assert renderer._reconnect_finished.wait(timeout=_WAIT_TIMEOUT)

    assert len(connect_calls) == 1  # the second call did not pile up its own attempt
    assert renderer._reconnect_attempts_used == 1


def test_methods_no_op_again_after_unmount(config):
    renderer, conn = _mounted_renderer(config, [])
    renderer.unmount()
    conn.reset_mock()

    renderer.render_state(_sample_state())
    renderer.set_expression("smile")

    conn.send.assert_not_called()
