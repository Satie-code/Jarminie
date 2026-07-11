"""Logging System — structured logging shared by every subsystem.

Every module calls get_logger(__name__) to obtain a correctly configured
logger; nothing outside this module touches handlers directly. See
docs/sprint_book/sprint_1_3.md for the design rationale.
"""

import logging
import logging.handlers
from pathlib import Path

from config.schema import LoggingConfig

_LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
_LOG_FILENAME = "jarminei.log"


class JarminieLogFormatter(logging.Formatter):
    """Enforces the project-wide log line format: timestamp | subsystem | LEVEL | message."""

    def __init__(self) -> None:
        super().__init__(fmt=_LOG_FORMAT)


class SensitiveDataFilter(logging.Filter):
    """Redacts records logged with extra={"sensitive": True}.

    Replaces the message rather than dropping the record, so it's still
    visible *that* something happened without leaking its content. Clears
    args too, since leftover %-args could otherwise leak into the
    formatted message once msg no longer has placeholders to consume them.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "sensitive", False):
            record.msg = "[REDACTED]"
            record.args = ()
        return True


def configure_logging(config: LoggingConfig) -> None:
    """Configure the root logger: console + rotating file, project format, redaction.

    Idempotent — safe to call more than once (existing handlers are closed
    and replaced, not stacked), which keeps it test-friendly even though
    the real application only calls it once at startup.
    """
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
    root.handlers.clear()
    root.filters.clear()

    level = getattr(logging, config.level, logging.INFO)
    root.setLevel(level)

    formatter = JarminieLogFormatter()
    sensitive_filter = SensitiveDataFilter()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)
    root.addHandler(console_handler)

    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / _LOG_FILENAME,
        maxBytes=config.max_bytes,
        backupCount=config.backup_count,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(sensitive_filter)
    root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a logger for `name` (conventionally `__name__`).

    Routes through the handlers configured by configure_logging() via
    normal logging propagation — this function does not itself attach
    handlers or filters.
    """
    return logging.getLogger(name)
