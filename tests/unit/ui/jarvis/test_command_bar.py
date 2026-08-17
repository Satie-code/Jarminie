"""Unit tests for ui.jarvis.command_bar."""

from unittest.mock import MagicMock

from ui.jarvis.command_bar import CommandBar


def test_empty_input_does_not_dispatch(qtbot):
    pipeline = MagicMock()
    bar = CommandBar(pipeline)
    qtbot.addWidget(bar)

    bar._input.setText("   ")
    bar._submit()

    pipeline.submit_text.assert_not_called()


def test_submitting_text_disables_input_and_clears_it(qtbot):
    pipeline = MagicMock()
    pipeline.submit_text.return_value = "Done."
    bar = CommandBar(pipeline)
    qtbot.addWidget(bar)
    bar._input.setText("open my calendar")

    bar._submit()

    assert bar._input.text() == ""
    assert not bar._input.isEnabled()


def test_submitting_text_eventually_calls_pipeline_and_displays_the_reply(qtbot):
    pipeline = MagicMock()
    pipeline.submit_text.return_value = "Sure, done."
    bar = CommandBar(pipeline)
    qtbot.addWidget(bar)
    bar._input.setText("open my calendar")

    bar._submit()

    qtbot.waitUntil(lambda: bar._reply_label.text() == "Sure, done.", timeout=2000)
    pipeline.submit_text.assert_called_once()
    call_args = pipeline.submit_text.call_args[0]
    assert call_args[0] == "open my calendar"
    assert call_args[1] == bar._session_id


def test_input_is_re_enabled_after_the_reply_arrives(qtbot):
    pipeline = MagicMock()
    pipeline.submit_text.return_value = "Done."
    bar = CommandBar(pipeline)
    qtbot.addWidget(bar)
    bar._input.setText("hello")

    bar._submit()

    qtbot.waitUntil(lambda: bar._input.isEnabled(), timeout=2000)


def test_a_raising_pipeline_still_produces_a_reply(qtbot):
    pipeline = MagicMock()
    pipeline.submit_text.side_effect = RuntimeError("boom")
    bar = CommandBar(pipeline)
    qtbot.addWidget(bar)
    bar._input.setText("hello")

    bar._submit()

    qtbot.waitUntil(lambda: bar._input.isEnabled(), timeout=2000)
    assert "wrong" in bar._reply_label.text().lower()


def test_long_reply_is_truncated_in_the_preview_but_kept_in_the_tooltip(qtbot):
    pipeline = MagicMock()
    long_reply = "x" * 500
    pipeline.submit_text.return_value = long_reply
    bar = CommandBar(pipeline)
    qtbot.addWidget(bar)
    bar._input.setText("hello")

    bar._submit()

    qtbot.waitUntil(lambda: bar._input.isEnabled(), timeout=2000)
    assert len(bar._reply_label.text()) < len(long_reply)
    assert bar._reply_label.toolTip() == long_reply


def test_session_id_is_stable_across_submissions(qtbot):
    pipeline = MagicMock()
    pipeline.submit_text.return_value = "Done."
    bar = CommandBar(pipeline)
    qtbot.addWidget(bar)

    bar._input.setText("first")
    bar._submit()
    qtbot.waitUntil(lambda: bar._input.isEnabled(), timeout=2000)
    bar._input.setText("second")
    bar._submit()
    qtbot.waitUntil(lambda: bar._input.isEnabled(), timeout=2000)

    first_session_id = pipeline.submit_text.call_args_list[0][0][1]
    second_session_id = pipeline.submit_text.call_args_list[1][0][1]
    assert first_session_id == second_session_id


def test_enter_key_submits(qtbot):
    pipeline = MagicMock()
    pipeline.submit_text.return_value = "Done."
    bar = CommandBar(pipeline)
    qtbot.addWidget(bar)
    bar._input.setText("hello")

    bar._input.returnPressed.emit()

    qtbot.waitUntil(lambda: pipeline.submit_text.called, timeout=2000)
