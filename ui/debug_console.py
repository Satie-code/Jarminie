"""Debug Console — live, filterable in-app view of JARMINEI's logs.

Closes the loop between "logs exist" (Sprint 1.3) and "logs are visible
without opening a text file" (this sprint) — reinforces the Explainability
Rule at the UI layer. core/logging_setup.py stays completely ignorant of
Qt: this module attaches/detaches its own logging.Handler using only the
public logging API, preserving the "UI depends on Core, never the
reverse" layering from Sprint 1.6. See docs/sprint_book/sprint_1_9.md.
"""

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from config.schema import VALID_LOG_LEVELS
from core.logging_setup import JarminieLogFormatter, SensitiveDataFilter

_MAX_BUFFER_LINES = 2000  # bounds memory growth in a long-running session


class _LogSignalEmitter(QObject):
    """Plain QObject carrying the signal — composed into QtLogHandler
    rather than using multiple inheritance from both logging.Handler and
    QObject, which risks metaclass conflicts between the two systems."""

    log_line_ready = Signal(str, int)  # formatted line, record.levelno


class QtLogHandler(logging.Handler):
    """Formats records with the same format as file/console logging and
    emits them as a Qt signal, so DebugConsole updates safely regardless
    of which thread the originating log call came from — Qt's queued
    connections marshal the emit() call to the GUI thread automatically
    when the receiving slot lives on a different thread than the emitter.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JarminieLogFormatter())
        # Redaction must apply here too, not just the file/console
        # handlers — otherwise sensitive data would leak into a live GUI
        # view even though it's scrubbed everywhere else.
        self.addFilter(SensitiveDataFilter())
        self._emitter = _LogSignalEmitter()

    @property
    def log_line_ready(self) -> Signal:
        return self._emitter.log_line_ready

    def emit(self, record: logging.LogRecord) -> None:
        try:
            formatted = self.format(record)
        except Exception:
            self.handleError(record)
            return
        self._emitter.log_line_ready.emit(formatted, record.levelno)


class DebugConsole(QWidget):
    """Read-only scrolling log view with a level filter.

    Attaches its own QtLogHandler to the root logger on construction and
    detaches it in closeEvent() — every log call anywhere in the app
    appears here regardless of which subsystem made it, and nothing leaks
    if the console is closed and reopened (each instance manages its own
    handler independently).
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("JARMINEI Debug Console")
        self.resize(700, 400)

        self._buffer: list[tuple[str, int]] = []
        self._level_filter = logging.INFO

        self._level_combo = QComboBox()
        self._level_combo.addItems(VALID_LOG_LEVELS)
        self._level_combo.setCurrentText("INFO")
        self._level_combo.currentTextChanged.connect(
            lambda name: self.set_level_filter(getattr(logging, name))
        )

        self._text_view = QPlainTextEdit()
        self._text_view.setReadOnly(True)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Level:"))
        filter_row.addWidget(self._level_combo)
        filter_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(filter_row)
        layout.addWidget(self._text_view)

        self._handler = QtLogHandler()
        self._handler.log_line_ready.connect(self._on_log_line)
        logging.getLogger().addHandler(self._handler)

    def set_level_filter(self, level: int) -> None:
        """Change the minimum displayed level, re-rendering from the
        buffer so raising/lowering the filter retroactively hides/shows
        already-received lines, not just future ones."""
        self._level_filter = level
        self._rerender()

    def _on_log_line(self, formatted: str, levelno: int) -> None:
        self._buffer.append((formatted, levelno))
        if len(self._buffer) > _MAX_BUFFER_LINES:
            self._buffer.pop(0)
        if levelno >= self._level_filter:
            self._text_view.appendPlainText(formatted)

    def _rerender(self) -> None:
        self._text_view.clear()
        for formatted, levelno in self._buffer:
            if levelno >= self._level_filter:
                self._text_view.appendPlainText(formatted)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override, not our naming convention)
        logging.getLogger().removeHandler(self._handler)
        event.accept()
