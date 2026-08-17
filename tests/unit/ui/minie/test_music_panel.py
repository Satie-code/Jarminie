"""Unit tests for ui.minie.music_panel."""

from ui.minie.music_panel import MinieMusicPanel, MusicTrack, NullMusicController


def test_construction_with_no_controller_does_not_crash(qtbot):
    panel = MinieMusicPanel()
    qtbot.addWidget(panel)


def test_null_controller_default_shows_an_honest_not_playing_state(qtbot):
    panel = MinieMusicPanel()
    qtbot.addWidget(panel)

    assert isinstance(panel._controller, NullMusicController)
    assert panel._title_label.text() == "Not playing"
    assert "Connect a music source" in panel._subtitle_label.text()
    assert panel._play_pause_button.text() == "▶"
    assert panel._waveform._playing is False


def test_null_music_controller_is_a_safe_no_op_by_itself():
    controller = NullMusicController()

    assert controller.is_playing() is False
    assert controller.current_track() is None
    controller.play_pause()  # must not raise
    controller.next_track()  # must not raise
    controller.previous_track()  # must not raise


class _FakeController:
    def __init__(self) -> None:
        self._playing = False
        self._tracks = [
            MusicTrack(title="Soft Rain", subtitle="Lo-fi Beats"),
            MusicTrack(title="Golden Hour", subtitle="Dream Pop"),
        ]
        self._index = 0
        self.play_pause_calls = 0
        self.next_calls = 0
        self.previous_calls = 0

    def is_playing(self) -> bool:
        return self._playing

    def current_track(self) -> MusicTrack | None:
        return self._tracks[self._index]

    def play_pause(self) -> None:
        self.play_pause_calls += 1
        self._playing = not self._playing

    def next_track(self) -> None:
        self.next_calls += 1
        self._index = (self._index + 1) % len(self._tracks)

    def previous_track(self) -> None:
        self.previous_calls += 1
        self._index = (self._index - 1) % len(self._tracks)


def test_a_real_controllers_track_is_shown_on_construction(qtbot):
    controller = _FakeController()
    panel = MinieMusicPanel(controller)
    qtbot.addWidget(panel)

    assert panel._title_label.text() == "Soft Rain"
    assert panel._subtitle_label.text() == "Lo-fi Beats"


def test_play_pause_button_dispatches_and_refreshes_the_glyph(qtbot):
    controller = _FakeController()
    panel = MinieMusicPanel(controller)
    qtbot.addWidget(panel)

    panel._play_pause_button.click()

    assert controller.play_pause_calls == 1
    assert panel._play_pause_button.text() == "⏸"
    assert panel._waveform._playing is True


def test_next_and_previous_buttons_dispatch_and_refresh_the_title(qtbot):
    controller = _FakeController()
    panel = MinieMusicPanel(controller)
    qtbot.addWidget(panel)

    panel._next_button.click()
    assert controller.next_calls == 1
    assert panel._title_label.text() == "Golden Hour"

    panel._prev_button.click()
    assert controller.previous_calls == 1
    assert panel._title_label.text() == "Soft Rain"


class _RaisingController:
    def is_playing(self) -> bool:
        raise RuntimeError("boom")

    def current_track(self):
        raise RuntimeError("boom")

    def play_pause(self) -> None:
        raise RuntimeError("boom")

    def next_track(self) -> None:
        pass

    def previous_track(self) -> None:
        pass


def test_survives_a_raising_controller(qtbot):
    controller = _RaisingController()
    panel = MinieMusicPanel(controller)
    qtbot.addWidget(panel)

    panel._play_pause_button.click()  # must not raise

    assert panel._title_label.text() == "Not playing"
