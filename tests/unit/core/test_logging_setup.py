"""Unit tests for core.logging_setup."""

import logging

import pytest

from config.schema import LoggingConfig
from core.logging_setup import configure_logging, get_logger


@pytest.fixture(autouse=True)
def _reset_root_logger():
    yield
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)
    root.filters.clear()
    root.setLevel(logging.WARNING)


def _make_config(tmp_path, **overrides):
    defaults = dict(level="DEBUG", log_dir=str(tmp_path), max_bytes=5_000_000, backup_count=3)
    defaults.update(overrides)
    return LoggingConfig(**defaults)


def test_log_format(tmp_path):
    configure_logging(_make_config(tmp_path))
    logger = get_logger("test.format")
    logger.info("hello world")

    content = (tmp_path / "jarminei.log").read_text()
    assert " | test.format | INFO | hello world" in content
    assert content.split(" | ")[0].count(":") >= 2  # timestamp-shaped prefix


def test_level_filtering(tmp_path):
    configure_logging(_make_config(tmp_path, level="INFO"))
    logger = get_logger("test.level")
    logger.debug("should not appear")
    logger.info("should appear")

    content = (tmp_path / "jarminei.log").read_text()
    assert "should not appear" not in content
    assert "should appear" in content


def test_sensitive_data_redacted(tmp_path):
    configure_logging(_make_config(tmp_path))
    logger = get_logger("test.sensitive")
    logger.info("password is hunter2", extra={"sensitive": True})
    logger.info("normal message")

    content = (tmp_path / "jarminei.log").read_text()
    assert "hunter2" not in content
    assert "[REDACTED]" in content
    assert "normal message" in content


def test_rotation_triggers_backup_file(tmp_path):
    configure_logging(_make_config(tmp_path, max_bytes=200, backup_count=2))
    logger = get_logger("test.rotation")
    for i in range(200):
        logger.info("padding message number %d to exceed the rotation threshold", i)

    assert (tmp_path / "jarminei.log.1").exists()


def test_configure_logging_is_idempotent(tmp_path):
    configure_logging(_make_config(tmp_path))
    configure_logging(_make_config(tmp_path))
    logger = get_logger("test.idempotent")
    logger.info("only once")

    content = (tmp_path / "jarminei.log").read_text()
    assert content.count("only once") == 1


def test_get_logger_returns_named_logger():
    logger = get_logger("test.name")
    assert logger.name == "test.name"


def test_invalid_level_falls_back_to_info(tmp_path):
    configure_logging(_make_config(tmp_path, level="NOT_A_LEVEL"))
    assert logging.getLogger().level == logging.INFO
