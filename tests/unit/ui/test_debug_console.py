"""Unit tests for ui.debug_console.

Uses real logging.getLogger() calls throughout rather than mocking the
logging module — per the "drive the real widget, not just mocks"
discipline from Sprint 1.8, where every mocked test passed while three
real integration bugs slipped through.
"""

import logging

import pytest

from ui.debug_console import DebugConsole, QtLogHandler


@pytest.fixture(autouse=True)
def _reset_root_logger():
    root = logging.getLogger()
    original_level = root.level
    root.setLevel(logging.DEBUG)  # ensure records propagate regardless of test order
    yield
    for handler in root.handlers[:]:
        if isinstance(handler, QtLogHandler):
            handler.close()
            root.removeHandler(handler)
    root.setLevel(original_level)


def test_qtlog_handler_formats_and_emits():
    handler = QtLogHandler()
    received = []
    handler.log_line_ready.connect(lambda line, levelno: received.append((line, levelno)))

    logger = logging.getLogger("test.qtloghandler")
    logger.addHandler(handler)
    logger.info("hello from qtloghandler")
    logger.removeHandler(handler)

    assert len(received) == 1
    line, levelno = received[0]
    assert " | test.qtloghandler | INFO | hello from qtloghandler" in line
    assert levelno == logging.INFO


def test_qtlog_handler_redacts_sensitive_data():
    handler = QtLogHandler()
    received = []
    handler.log_line_ready.connect(lambda line, levelno: received.append(line))

    logger = logging.getLogger("test.qtloghandler.sensitive")
    logger.addHandler(handler)
    logger.info("password is hunter2", extra={"sensitive": True})
    logger.removeHandler(handler)

    assert "hunter2" not in received[0]
    assert "[REDACTED]" in received[0]


def test_debug_console_shows_log_messages_live(qtbot):
    console = DebugConsole()
    qtbot.addWidget(console)

    logging.getLogger("test.debug_console").info("visible message")

    assert "visible message" in console._text_view.toPlainText()
    console.close()


def test_level_filter_hides_lower_level_messages(qtbot):
    console = DebugConsole()
    qtbot.addWidget(console)
    console.set_level_filter(logging.WARNING)

    logger = logging.getLogger("test.debug_console.filter")
    logger.info("should be hidden")
    logger.warning("should be visible")

    text = console._text_view.toPlainText()
    assert "should be hidden" not in text
    assert "should be visible" in text
    console.close()


def test_raising_filter_retroactively_hides_buffered_messages(qtbot):
    console = DebugConsole()
    qtbot.addWidget(console)

    logger = logging.getLogger("test.debug_console.retroactive_hide")
    logger.info("info message")
    logger.warning("warning message")

    console.set_level_filter(logging.WARNING)

    text = console._text_view.toPlainText()
    assert "info message" not in text
    assert "warning message" in text
    console.close()


def test_lowering_filter_retroactively_shows_buffered_messages(qtbot):
    console = DebugConsole()
    qtbot.addWidget(console)
    console.set_level_filter(logging.WARNING)

    logging.getLogger("test.debug_console.retroactive_show").info("info message")
    console.set_level_filter(logging.DEBUG)

    assert "info message" in console._text_view.toPlainText()
    console.close()


def test_handler_attached_on_open_and_detached_on_close(qtbot):
    console = DebugConsole()
    qtbot.addWidget(console)
    handler = console._handler

    assert handler in logging.getLogger().handlers

    console.close()

    assert handler not in logging.getLogger().handlers


def test_reopening_does_not_duplicate_or_drop_messages(qtbot):
    logger = logging.getLogger("test.debug_console.reopen")

    console1 = DebugConsole()
    qtbot.addWidget(console1)
    logger.info("first message")
    console1.close()

    console2 = DebugConsole()
    qtbot.addWidget(console2)
    logger.info("second message")

    text = console2._text_view.toPlainText()
    assert text.count("second message") == 1
    assert "first message" not in text  # console2 has its own fresh buffer
    console2.close()
