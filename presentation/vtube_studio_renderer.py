"""VTubeStudioAvatarRenderer (Sprint 5.8 — Level 5 Part A).

The first concrete `AvatarRenderer` (presentation/avatar_renderer.py):
drives a locally-running VTube Studio instance and its loaded Live2D
model through VTube Studio's own documented local WebSocket Plugin API
(`ws://{host}:{port}`, default `localhost:8001`).

**JARMINEI never embeds, bundles, or redistributes Live2D's own SDK,
and does not itself render Minie's avatar.** This class only sends
JSON request/response messages to an already-running, separately
installed VTube Studio process that the user owns, configures, and
loads their own Live2D model into independently — a real, disclosed
product/licensing boundary. Minie's avatar visuals require the user to
have VTube Studio installed and running separately; if it isn't, every
method here degrades to a safe, logged no-op (see below), never a
crash.

**"Disconnected, never crash" contract** (this sprint's own Expected
Functions): `mount()` never raises — connection or authentication
failure sets `_connected = False` and logs a clear warning (VTube
Studio not running is an expected, common case, not an application
error). Every other method checks `_connected` first and no-ops
(logged at DEBUG, not WARNING, to avoid log spam) when disconnected. A
mid-session connection loss (a send/recv failure on an already-mounted
connection) is caught per-call, logs a WARNING once, and marks the
renderer disconnected again — a real reconnection attempt (retrying in
the background) is explicitly Sprint 5.15's hardening job, not this
sprint's.

**Best-effort protocol implementation, disclosed**: the exact JSON
message shapes below (`AuthenticationTokenRequest`, `AuthenticationRequest`,
`InjectParameterDataRequest`, `HotkeyTriggerRequest`) follow VTube
Studio's own publicly documented API from this project's own training
knowledge — like `internet/brave_search_provider.py`'s own response
parsing at Sprint 4.16, this has NOT been verified against a real,
live VTube Studio instance this session (no such instance is available
in this environment); real-VTube-Studio verification is explicitly
Sprint 5.16's own opt-in job, mirroring `test_level4_part_b_real_
verification.py`'s established shape.

Uses `websockets.sync.client` (the synchronous API) — this codebase has
no asyncio event loop running anywhere, and `Renderer.render_state()`'s
own "cheap, non-blocking, called synchronously" contract (Sprint 5.6)
has no use for one. The stop-and-ask gate that picked `websockets`
itself (over a community VTube-Studio-specific wrapper such as `pyvts`)
was resolved directly with the user before this sprint's own
implementation began — see `backlog/technical_debt.md`.
"""

import json
import uuid
from pathlib import Path

from websockets.sync.client import connect

from config.schema import PresentationConfig
from core.logging_setup import get_logger
from presentation.presentation_state import PresentationState

logger = get_logger(__name__)

_API_NAME = "VTubeStudioPublicAPI"
_API_VERSION = "1.0"

_MOUTH_OPEN_PARAMETER = "ParamMouthOpenY"
_EYE_X_PARAMETER = "ParamEyeBallX"
_EYE_Y_PARAMETER = "ParamEyeBallY"
"""Standard Live2D/VTube Studio built-in parameter names for the two
methods (set_mouth_open/set_eye_target) with no real caller this
sprint (Sprint 5.11/5.9's future job) — unlike
vtube_studio_parameter_mapping's own three PresentationState-driven
fields, these are structural face-tracking concepts unlikely to need
per-model reconfiguration, so kept as real, disclosed constants rather
than adding further config surface this sprint's own spec didn't ask
for."""


class VTubeStudioAvatarRenderer:
    """Constructor DI per 03_Engineering_Standards.md: receives only the
    PresentationConfig it reads every vtube_studio_* field from."""

    def __init__(self, presentation_config: PresentationConfig) -> None:
        self._config = presentation_config
        self._connection = None
        self._connected = False
        self._auth_token: str | None = None
        self._warned_keys: set[str] = set()

    def mount(self) -> None:
        """Connects and authenticates (or reuses a persisted token).
        Never raises — see this module's own docstring for the full
        "disconnected, never crash" contract."""
        if self._connected:
            return
        try:
            uri = f"ws://{self._config.vtube_studio_host}:{self._config.vtube_studio_port}"
            self._connection = connect(
                uri, open_timeout=self._config.vtube_studio_connection_timeout_seconds
            )
            self._authenticate()
            self._connected = True
            logger.info("VTube Studio Avatar Renderer connected and authenticated.")
        except Exception:
            logger.warning(
                "Could not connect to/authenticate with VTube Studio at %s:%s. Minie's "
                "avatar will not be visible until VTube Studio is running with a Live2D "
                "model loaded (a real reconnection attempt is Sprint 5.15's job).",
                self._config.vtube_studio_host,
                self._config.vtube_studio_port,
            )
            self._connected = False
            self._close_connection_quietly()

    def unmount(self) -> None:
        """Closes the connection cleanly. Idempotent and safe even if
        mount() was never called or already failed."""
        self._connected = False
        self._close_connection_quietly()
        logger.info("VTube Studio Avatar Renderer unmounted.")

    def render_state(self, state: PresentationState) -> None:
        """Translates PresentationState into a VTube Studio
        InjectParameterDataRequest via the configured
        vtube_studio_parameter_mapping. A no-op (logged at DEBUG) when
        disconnected. An unknown PresentationState field name in the
        configured mapping, or a rejection from VTube Studio itself
        (a parameter name the loaded model doesn't define), each log a
        clear warning exactly once per session — never per tick."""
        if not self._connected:
            logger.debug("render_state() ignored — not connected to VTube Studio.")
            return

        parameter_values = []
        for state_field, parameter_name in self._config.vtube_studio_parameter_mapping.items():
            if not hasattr(state, state_field):
                self._warn_once(
                    f"unknown_field:{state_field}",
                    "presentation.vtube_studio_parameter_mapping names unknown "
                    "PresentationState field %r; ignoring.",
                    state_field,
                )
                continue
            parameter_values.append(
                {"id": parameter_name, "value": float(getattr(state, state_field))}
            )
        if not parameter_values:
            return

        response = self._try_send_request(
            "InjectParameterDataRequest",
            {"faceFound": False, "mode": "set", "parameterValues": parameter_values},
        )
        if response is not None and response.get("messageType") == "APIError":
            self._warn_once(
                "parameter_mismatch",
                "VTube Studio rejected a parameter injection — the loaded model likely "
                "doesn't define one of vtube_studio_parameter_mapping's configured "
                "parameter names. VTube Studio's own message: %s",
                response.get("data", {}).get("message", "unknown error"),
            )

    def set_expression(self, expression_id: str) -> None:
        if not self._connected:
            logger.debug(
                "set_expression(%s) ignored — not connected to VTube Studio.", expression_id
            )
            return
        self._try_send_request("HotkeyTriggerRequest", {"hotkeyID": expression_id})

    def set_mouth_open(self, amount: float) -> None:
        if not self._connected:
            logger.debug("set_mouth_open() ignored — not connected to VTube Studio.")
            return
        self._try_send_request(
            "InjectParameterDataRequest",
            {
                "faceFound": False,
                "mode": "set",
                "parameterValues": [{"id": _MOUTH_OPEN_PARAMETER, "value": amount}],
            },
        )

    def set_eye_target(self, x: float, y: float) -> None:
        if not self._connected:
            logger.debug("set_eye_target() ignored — not connected to VTube Studio.")
            return
        self._try_send_request(
            "InjectParameterDataRequest",
            {
                "faceFound": False,
                "mode": "set",
                "parameterValues": [
                    {"id": _EYE_X_PARAMETER, "value": x},
                    {"id": _EYE_Y_PARAMETER, "value": y},
                ],
            },
        )

    def trigger_gesture(self, gesture_id: str) -> None:
        if not self._connected:
            logger.debug("trigger_gesture(%s) ignored — not connected to VTube Studio.", gesture_id)
            return
        self._try_send_request("HotkeyTriggerRequest", {"hotkeyID": gesture_id})

    def _authenticate(self) -> None:
        """Requests a fresh plugin token from VTube Studio only if no
        persisted one exists, or the persisted one is no longer
        accepted (VTube Studio's own permission UI can revoke tokens
        independently of JARMINEI). Persists a newly-issued token for
        reuse on every later run."""
        token = self._load_persisted_token()
        if token is not None and self._try_authenticate_with_token(token):
            self._auth_token = token
            return
        token = self._request_new_token()
        if not self._try_authenticate_with_token(token):
            raise RuntimeError("VTube Studio rejected the newly-issued authentication token.")
        self._persist_token(token)
        self._auth_token = token

    def _try_authenticate_with_token(self, token: str) -> bool:
        response = self._send_request(
            "AuthenticationRequest",
            {
                "pluginName": self._config.vtube_studio_plugin_name,
                "pluginDeveloper": self._config.vtube_studio_plugin_developer,
                "authenticationToken": token,
            },
        )
        return bool(response.get("data", {}).get("authenticated", False))

    def _request_new_token(self) -> str:
        response = self._send_request(
            "AuthenticationTokenRequest",
            {
                "pluginName": self._config.vtube_studio_plugin_name,
                "pluginDeveloper": self._config.vtube_studio_plugin_developer,
            },
        )
        token = response.get("data", {}).get("authenticationToken")
        if not token:
            raise RuntimeError("VTube Studio did not return an authentication token.")
        return token

    def _load_persisted_token(self) -> str | None:
        path = Path(self._config.vtube_studio_auth_token_path)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("authenticationToken")
        except Exception:
            logger.warning(
                "Could not read persisted VTube Studio auth token at %s; requesting a new one.",
                path,
            )
            return None

    def _persist_token(self, token: str) -> None:
        path = Path(self._config.vtube_studio_auth_token_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"authenticationToken": token}), encoding="utf-8")

    def _send_request(self, message_type: str, data: dict) -> dict:
        """Raises on any transport/protocol failure — callers during
        mount()/_authenticate() let this propagate up to mount()'s own
        broad catch; callers after mount() (render_state() and friends)
        go through _try_send_request() instead, which contains the
        failure locally."""
        payload = {
            "apiName": _API_NAME,
            "apiVersion": _API_VERSION,
            "requestID": uuid.uuid4().hex,
            "messageType": message_type,
            "data": data,
        }
        self._connection.send(json.dumps(payload))
        raw_response = self._connection.recv(
            timeout=self._config.vtube_studio_connection_timeout_seconds
        )
        return json.loads(raw_response)

    def _try_send_request(self, message_type: str, data: dict) -> dict | None:
        """Same as _send_request(), but for calls made after mount()
        already succeeded — a failure here means the connection was
        lost mid-session, not a mount()-time problem. Marks the
        renderer disconnected and logs a warning instead of raising."""
        try:
            return self._send_request(message_type, data)
        except Exception:
            logger.warning(
                "Lost connection to VTube Studio while sending a %s request.", message_type
            )
            self._connected = False
            self._close_connection_quietly()
            return None

    def _close_connection_quietly(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

    def _warn_once(self, key: str, message: str, *args) -> None:
        if key in self._warned_keys:
            return
        self._warned_keys.add(key)
        logger.warning(message, *args)
