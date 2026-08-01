"""Root-level pytest conftest — collected before any test file, and
(confirmed directly, not assumed) before pytest-qt's own PySide6 import
happens anywhere in the process.

Applies the identical fix main.py's own `_prewarm_tts_before_pyside6()`
uses for the real application, to the test suite itself: pre-warming
Coqui TTS's own import here, at the very first opportunity pytest gives
any test-suite-wide code to run, avoids the same PySide6/shiboken6 <->
`six.moves` import-order conflict documented in full in main.py's own
docstring (backlog/technical_debt.md item 29's own resolution) —
previously the root cause of `tests/unit/voice/test_text_to_speech.py`'s
15 deterministic failures under a full `pytest-qt`-enabled run.
"""

import importlib

try:
    importlib.import_module("TTS.api")
except Exception:
    pass
