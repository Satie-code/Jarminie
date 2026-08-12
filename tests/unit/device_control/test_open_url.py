"""Unit tests for device_control.application_manager's open_url()
(Sprint 6.9 — Multi-Step Workflow Engine, Level 6 Part A).

webbrowser.open() is monkeypatched at its call site
(device_control.application_manager.open_browser) — never an actual
browser launch in this test suite.
"""

from datetime import UTC, datetime

from config.schema import DeviceControlConfig
from device_control import application_manager as application_manager_module
from device_control.action_engine import ActionContext, ActionRequest, ActionStatus, ActionType
from device_control.application_manager import ApplicationManager


def _manager(**config_overrides) -> ApplicationManager:
    return ApplicationManager(DeviceControlConfig(**config_overrides))


def test_open_url_succeeds_for_an_allowed_scheme(monkeypatch):
    opened_urls = []
    monkeypatch.setattr(application_manager_module, "open_browser", opened_urls.append)
    manager = _manager()

    result = manager.open_url("https://example.com/docs", requested_by="test")

    assert result.status is ActionStatus.SUCCEEDED
    assert opened_urls == ["https://example.com/docs"]


def test_open_url_rejects_a_disallowed_scheme_without_raising(monkeypatch):
    opened_urls = []
    monkeypatch.setattr(application_manager_module, "open_browser", opened_urls.append)
    manager = _manager()

    result = manager.open_url("file:///etc/passwd", requested_by="test")  # must not raise

    assert result.status is ActionStatus.FAILED
    assert opened_urls == []


def test_open_url_rejects_javascript_scheme(monkeypatch):
    opened_urls = []
    monkeypatch.setattr(application_manager_module, "open_browser", opened_urls.append)
    manager = _manager()

    result = manager.open_url("javascript:alert(1)", requested_by="test")

    assert result.status is ActionStatus.FAILED
    assert opened_urls == []


def test_open_url_scheme_check_is_case_insensitive(monkeypatch):
    opened_urls = []
    monkeypatch.setattr(application_manager_module, "open_browser", opened_urls.append)
    manager = _manager()

    result = manager.open_url("HTTPS://example.com", requested_by="test")

    assert result.status is ActionStatus.SUCCEEDED
    assert opened_urls == ["HTTPS://example.com"]


def test_open_url_result_carries_a_real_action_request():
    manager = _manager()

    result = manager.open_url("https://example.com", requested_by="voice_turn")

    assert result.request.action_type is ActionType.OPEN_URL
    assert result.request.parameters == {"url": "https://example.com"}
    assert result.request.context.requested_by == "voice_turn"


def test_can_handle_open_url():
    manager = _manager()
    assert manager.can_handle(ActionType.OPEN_URL) is True


def test_execute_dispatches_open_url_action_requests(monkeypatch):
    opened_urls = []
    monkeypatch.setattr(application_manager_module, "open_browser", opened_urls.append)
    manager = _manager()
    request = ActionRequest(
        action_type=ActionType.OPEN_URL,
        parameters={"url": "https://example.com"},
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
    )

    result = manager.execute(request)

    assert result.status is ActionStatus.SUCCEEDED
    assert result.request is request
    assert opened_urls == ["https://example.com"]


def test_execute_open_url_missing_url_parameter_fails_without_raising(monkeypatch):
    opened_urls = []
    monkeypatch.setattr(application_manager_module, "open_browser", opened_urls.append)
    manager = _manager()
    request = ActionRequest(
        action_type=ActionType.OPEN_URL,
        parameters={},
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
    )

    result = manager.execute(request)  # must not raise

    assert result.status is ActionStatus.FAILED
    assert opened_urls == []


def test_execute_open_url_disallowed_scheme_fails(monkeypatch):
    opened_urls = []
    monkeypatch.setattr(application_manager_module, "open_browser", opened_urls.append)
    manager = _manager()
    request = ActionRequest(
        action_type=ActionType.OPEN_URL,
        parameters={"url": "ftp://example.com"},
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
    )

    result = manager.execute(request)

    assert result.status is ActionStatus.FAILED
    assert opened_urls == []


def test_execute_open_url_degrades_honestly_when_open_browser_raises(monkeypatch):
    """Sprint 6.15 adversarial-re-read finding: execute()'s own
    ActionType.OPEN_URL dispatch previously sat OUTSIDE the try/except
    (OSError, psutil.Error, pywintypes.error) block that already wraps
    launch()/close()/focus()/list() — the identical shape of gap item
    28 (backlog/technical_debt.md) already fixed once in this exact
    method for pywintypes.error specifically. Not a live safety gap
    either way (ActionRegistry.dispatch()'s own outer except Exception
    already catches it, per item 28's own established reasoning) but a
    real, disclosed inconsistency, fixed by moving OPEN_URL's own
    dispatch inside the same try block."""
    def _raise(url: str) -> None:
        raise OSError("no browser controller registered")

    monkeypatch.setattr(application_manager_module, "open_browser", _raise)
    manager = _manager()
    request = ActionRequest(
        action_type=ActionType.OPEN_URL,
        parameters={"url": "https://example.com"},
        context=ActionContext(requested_by="test"),
        requested_at=datetime.now(UTC),
    )

    result = manager.execute(request)  # must not raise

    assert result.status is ActionStatus.FAILED
    assert "no browser controller registered" in result.error_message


def test_open_url_respects_a_narrowed_allowed_schemes_config(monkeypatch):
    opened_urls = []
    monkeypatch.setattr(application_manager_module, "open_browser", opened_urls.append)
    manager = _manager(allowed_url_schemes=["https"])

    http_result = manager.open_url("http://example.com", requested_by="test")
    https_result = manager.open_url("https://example.com", requested_by="test")

    assert http_result.status is ActionStatus.FAILED
    assert https_result.status is ActionStatus.SUCCEEDED
    assert opened_urls == ["https://example.com"]
