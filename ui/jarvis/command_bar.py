"""CommandBar — JARVIS Holographic HUD reskin, Phase 6.

The brief's own bottom-center command input: a rounded text field
("Type a command...") plus Enter/submit, sending typed input through the
EXISTING `CommunicationPipeline` (`voice/pipeline.py`'s `submit_text()`,
this phase's own new public entry point — see that method's own
docstring) rather than a second, competing conversational engine, per
the brief's own explicit "Do not implement a second conversational
engine" instruction.

`submit_text()` runs the full Decision Engine pipeline (LLM calls, DB
reads) — genuinely slow, so it must never run on the Qt main thread. This
widget spawns a plain `threading.Thread(daemon=True)` per submission
(this project's own established background-work idiom — `ui/app.py`'s
own docstring explicitly prefers this over `QThread`) and marshals the
result back via `QTimer.singleShot(0, self, callback)`, the identical
cross-thread idiom `presentation/jarvis_renderer.py`'s own
`_run_on_main_thread()` already established and verified against this
project's installed PySide6 version.

**A disclosed simplification**: typed commands use one stable session_id
generated once when this widget is constructed, regardless of whether a
voice session happens to be active at the same time — text and voice
conversations are treated as separate contexts for this phase. Sharing
one session_id between an active voice session and typed input would
need a new public `VoiceSessionManager` accessor this phase doesn't add
(no `current_session_id()` exists — only `current_session_state()`); a
reasonable, disclosed future enhancement, not built speculatively here.
"""

import threading
import uuid

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from core.logging_setup import get_logger
from presentation import theme
from voice.pipeline import CommunicationPipeline

logger = get_logger(__name__)

_MAX_REPLY_PREVIEW_CHARS = 160


class CommandBar(QWidget):
    """Constructor DI: only CommunicationPipeline — this widget owns no
    conversational logic of its own, purely input capture + dispatch +
    reply display."""

    def __init__(self, pipeline: CommunicationPipeline, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pipeline = pipeline
        self._session_id = str(uuid.uuid4())

        self._reply_label = QLabel("")
        self._reply_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 9pt;")
        self._reply_label.setWordWrap(False)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command...")
        self._input.setStyleSheet(
            f"QLineEdit {{ border-radius: 16px; padding: 8px 16px;"
            f" background-color: {theme.BG_PANEL_RAISED}; border: 1px solid {theme.BORDER_DIM}; }}"
            f"QLineEdit:focus {{ border: 1px solid {theme.ACCENT_CYAN}; }}"
        )
        self._input.returnPressed.connect(self._submit)

        send_button = QPushButton("Send")
        send_button.clicked.connect(self._submit)

        input_row = QHBoxLayout()
        input_row.addWidget(self._input, 1)
        input_row.addWidget(send_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)
        layout.addWidget(self._reply_label)
        layout.addLayout(input_row)

    def _submit(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.setEnabled(False)
        self._input.clear()
        self._reply_label.setText("Working on that...")

        thread = threading.Thread(
            target=self._run_submit_text, args=(text,), name="command-bar-submit", daemon=True
        )
        thread.start()

    def _run_submit_text(self, text: str) -> None:
        """Runs on a background thread — self._pipeline.submit_text()
        already never raises (its own Fail Gracefully contract), but
        this is still wrapped defensively since an uncaught exception on
        a bare threading.Thread would otherwise vanish silently rather
        than reaching this widget's own display update."""
        try:
            reply = self._pipeline.submit_text(text, self._session_id)
        except Exception:
            logger.exception("CommandBar failed to submit text unexpectedly.")
            reply = "Sorry, something went wrong processing that."
        QTimer.singleShot(0, self, lambda: self._display_reply(reply))

    def _display_reply(self, reply: str) -> None:
        if len(reply) <= _MAX_REPLY_PREVIEW_CHARS:
            preview = reply
        else:
            preview = reply[:_MAX_REPLY_PREVIEW_CHARS] + "…"
        self._reply_label.setText(preview)
        self._reply_label.setToolTip(reply)
        self._input.setEnabled(True)
        self._input.setFocus(Qt.FocusReason.OtherFocusReason)
