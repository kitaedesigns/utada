"""End-to-end smoke test: drives the real window through its menu actions.

Needs a display (X11/Wayland) and ffmpeg; skipped otherwise. Uses tiny
generated clips only.
"""

import locale
import os
import shutil
import subprocess
import sys
import time

import pytest
from PySide6.QtCore import QPointF, Qt

HAS_DISPLAY = sys.platform == "win32" or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
pytestmark = pytest.mark.skipif(not HAS_DISPLAY or not shutil.which("ffmpeg"),
                                reason="needs a display and ffmpeg")


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    folder = tmp_path_factory.mktemp("clips")
    for i, size in enumerate(["320x180", "180x320", "320x180", "240x180", "180x320", "320x180"]):
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        f"testsrc2=size={size}:rate=25:duration=2", "-c:v", "libx264", "-preset",
                        "ultrafast", "-pix_fmt", "yuv420p", str(folder / f"c{i}.mp4")], check=True)
    return folder


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    application = QApplication.instance() or QApplication([])
    locale.setlocale(locale.LC_NUMERIC, "C")
    yield application


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    from mosaicplayer.config import Config
    from mosaicplayer.window import MainWindow
    cfg = Config()
    monkeypatch.setattr(cfg, "save", lambda: None)
    win = MainWindow(cfg)
    win.resize(900, 600)
    win.show()
    yield win
    win.close()
    pump(app, 0.2)


def test_full_session(app, window, clips, tmp_path):
    from mosaicplayer.layout import LAYOUT_MODES
    from mosaicplayer.playlist import read_gpls
    from mosaicplayer.options import END_ACTIONS

    c = window.canvas
    window.load([clips])
    pump(app, 2.5)
    assert len(c.tiles) == 6
    assert all(t.aspect_known for t in c.tiles), "every tile reported its video size"
    assert len(c.rects) == 6

    # Every packing mode lays out all tiles inside the canvas.
    for mode in LAYOUT_MODES:
        window.set_layout_mode(mode)
        pump(app, 0.4)
        assert len(c.rects) == 6, mode
    window.set_layout_mode("rows")
    pump(app, 0.3)

    # Frames are actually rendered and composited.
    assert c.tile_fps() >= 0
    pump(app, 1.0)
    assert sum(t.frames_drawn for t in c.tiles) > 30
    image = c.grabFramebuffer()
    assert not image.isNull()

    # Playback controls.
    c.set_all_paused(True)
    pump(app, 0.3)
    assert c.all_paused()
    c.set_all_paused(False)
    window.toggle_mute_all()
    for tile in c.tiles:
        tile.seek(1)
    c.sync_to(c.tiles[0])
    c.set_all_speed(1.5)
    for action in END_ACTIONS:
        c.set_all_end_action(action)
    c.set_all_end_action("loop")

    # Arrange: swap, shuffle, sort, focus.
    first, second = c.tiles[0], c.tiles[1]
    c.swap(first, second)
    assert c.tiles[0] is second
    c.shuffle_order()
    c.sort_by_name()
    c.set_solo(c.tiles[2])
    pump(app, 0.3)
    assert len(c.rects) == 1
    c.set_solo(None)
    pump(app, 0.3)
    assert len(c.rects) == 6

    # Save and reload the playlist.
    out = tmp_path / "session.gpls"
    window._playlist_path = str(out)
    window.save_playlist()
    saved = read_gpls(out)
    assert len(saved.entries) == 6

    # Remove one, reload players (as after a decoder change), clear.
    c.remove_tile(c.tiles[-1])
    pump(app, 0.3)
    assert len(c.tiles) == 5
    c.reload_all()
    pump(app, 1.5)
    assert len(c.tiles) == 5
    window.close_all()
    pump(app, 0.3)
    assert not c.tiles

    window.load([str(out)])
    pump(app, 1.5)
    assert len(c.tiles) == 6


def test_focus_mode_and_merged_playlists(app, window, clips, tmp_path):
    from mosaicplayer.playlist import Entry, Playlist, write_gpls
    c = window.canvas
    window.load([clips])
    pump(app, 2.5)
    # Pause/play all only touches the focused video; the hidden ones stay paused.
    c.set_solo(c.tiles[0])
    pump(app, 0.3)
    c.set_all_paused(False)
    pump(app, 0.3)
    assert not c.tiles[0].paused
    assert all(t.paused for t in c.tiles[1:])
    c.set_solo(None)
    pump(app, 0.3)
    assert not any(t.paused for t in c.tiles)
    # Adding a playlist to videos already open must not make it the save target.
    extra = tmp_path / "extra.gpls"
    write_gpls(extra, Playlist([Entry(str(next(clips.iterdir())))]))
    window.load([str(extra)])
    pump(app, 0.5)
    assert window._playlist_path is None


def test_removed_tile_is_gone_at_once(app, window, clips):
    c = window.canvas
    window.load([clips])
    pump(app, 2.5)
    victim = c.tiles[2]
    rect = c._logical(c.rects[c._layout_tiles.index(victim)])
    c.remove_tile(victim)
    assert victim not in c._layout_tiles  # not drawn or clickable, even before relayout
    assert c.tile_at(rect.center()) is not victim
    assert len(c._layout_tiles) == len(c.rects) == 5


def test_stop_at_end_then_play_restarts(app, window, clips):
    c = window.canvas
    window.load([next(clips.iterdir())])
    pump(app, 2.0)
    tile = c.tiles[0]
    c.set_all_end_action("stop")
    tile.seek_to(1.9, exact=True)
    pump(app, 1.5)
    assert tile._at_end and tile.paused
    tile.set_paused(False)
    pump(app, 0.6)
    pos, _ = tile.progress()
    assert not tile.paused and pos < 1.5


def test_closed_tiles_are_freed(app, window, clips):
    import gc
    from PySide6.QtCore import QCoreApplication, QEvent
    from mosaicplayer.tile import Tile
    c = window.canvas
    for _ in range(3):
        window.load([clips])
        pump(app, 1.5)
        window.close_all()
        pump(app, 0.3)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    gc.collect()
    assert not c.findChildren(Tile)
    assert sum(isinstance(o, Tile) for o in gc.get_objects()) <= 6  # not 18


def test_wheel_acts_once_per_notch(app, window, clips):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QWheelEvent
    c = window.canvas
    window.load([clips])
    pump(app, 2.5)
    tile = c._layout_tiles[0]
    pos = c._logical(c.rects[0]).center()

    def wheel(delta, mods=Qt.NoModifier):
        app.sendEvent(c, QWheelEvent(pos, c.mapToGlobal(pos), QPoint(0, 0), QPoint(0, delta),
                                     Qt.NoButton, mods, Qt.NoScrollPhase, False))

    for _ in range(8):  # one notch from a touchpad / high-resolution wheel
        wheel(15, Qt.AltModifier)
    assert tile.entry.size_weight == 1.41  # one step, not eight
    wheel(-120, Qt.AltModifier)
    assert tile.entry.size_weight == 1.0


def test_keyboard_shortcuts(app, window, clips):
    import time
    from PySide6.QtTest import QTest
    c = window.canvas
    cfg = window.cfg
    window.activateWindow()
    window.load([clips])
    pump(app, 2.5)
    c.setFocus()

    def key(k, mod=Qt.NoModifier):
        # Shortcuts only reach the active window. While someone is using the
        # desktop, the window manager may keep focus elsewhere: skip, don't fail.
        deadline = time.monotonic() + 3
        while app.activeWindow() is not window and time.monotonic() < deadline:
            window.activateWindow()
            pump(app, 0.05)
        if app.activeWindow() is not window:
            pytest.skip("the window manager did not give the test window keyboard focus")
        QTest.keyClick(c, k, mod)
        pump(app, 0.2)

    key(Qt.Key_Space, Qt.ShiftModifier)  # Shift+Space: all (Space alone: the current tile)
    assert c.all_paused()
    key(Qt.Key_Space, Qt.ShiftModifier)
    for i, mode in enumerate(["puzzle", "rows", "columns", "grid", "fixed-grid"], 1):
        key(getattr(Qt, f"Key_{i}"))
        assert cfg.layout_mode == mode
    key(Qt.Key_1)
    c.hovered = tile = c._layout_tiles[0]
    key(Qt.Key_Plus)
    assert tile.entry.size_weight == 1.41
    key(Qt.Key_0)
    assert tile.entry.size_weight == 1.0
    gap = cfg.gap
    key(Qt.Key_BracketRight)
    assert cfg.gap == gap + 2
    key(Qt.Key_N, Qt.ControlModifier)  # File > New clears everything
    assert not c.tiles
    window.load([clips])
    deadline = time.monotonic() + 4  # the layout waits for the videos' sizes
    while not c._layout_tiles and time.monotonic() < deadline:
        pump(app, 0.05)
    c.hovered = c._layout_tiles[0]
    key(Qt.Key_M, Qt.ControlModifier)  # master mute (plan 2.5)
    assert c.master.muted and all(t.player.mute for t in c.tiles)
    key(Qt.Key_M, Qt.ControlModifier)
    assert not c.master.muted
    key(Qt.Key_Down, Qt.ControlModifier)
    assert c.master.volume == 0.9 and cfg.master_volume == 0.9
    key(Qt.Key_Up, Qt.ControlModifier)
    assert c.master.volume == 1.0
    # Stay on top recreates the native window; it must get keyboard focus back.
    key(Qt.Key_T)
    deadline = time.monotonic() + 5
    while app.activeWindow() is not window and time.monotonic() < deadline:
        pump(app, 0.05)
    assert cfg.stay_on_top
    key(Qt.Key_Space, Qt.ShiftModifier)
    assert c.all_paused()
    key(Qt.Key_T)


def test_toasts_show_file_names_literally(app, window):
    window.toast("<i>clip</i> & co")
    assert window._toast.textFormat() == Qt.PlainText


def test_overlay_timer_idles(app, window, clips):
    c = window.canvas
    window.load([clips])
    pump(app, 2.0)
    c.hovered = None
    c._sync_overlay_timer()
    assert not c._overlay_timer.isActive()
    c.set_hud(True)
    assert c._overlay_timer.isActive()
    c.set_hud(False)
    assert not c._overlay_timer.isActive()


def test_settings_dialog_round_trip(app, window):
    from dataclasses import replace
    from mosaicplayer.settings_dialog import SettingsDialog
    dialog = SettingsDialog(window.cfg, window)
    dialog.gap.setValue(6)
    dialog.layout_mode.setCurrentIndex(dialog.layout_mode.findData("columns"))
    dialog._accept()
    assert dialog.result_config.gap == 6
    assert dialog.result_config.layout_mode == "columns"
    window._replace_config(replace(dialog.result_config, titles="always"))
    assert window.cfg.layout_mode == "columns"
    # Menus show the new values.
    assert window.mode_actions["columns"].isChecked()
    assert window.title_actions["always"].isChecked()


def test_crop_toggle_keeps_custom_amount(app, window):
    window.cfg.max_crop = 0.25  # set in Settings
    window.set_crop(False)
    assert window.cfg.max_crop == 0.0
    window.set_crop(True)
    assert window.cfg.max_crop == 0.25


def test_fullscreen_returns_to_maximized(app, window):
    def wait_for(condition, seconds=4):
        end = time.monotonic() + seconds
        while not condition() and time.monotonic() < end:
            pump(app, 0.05)
        return condition()

    window.showMaximized()
    if not wait_for(window.isMaximized):
        pytest.skip("window manager did not maximize")
    window.toggle_fullscreen()
    assert wait_for(window.isFullScreen)
    window.toggle_fullscreen()
    assert wait_for(lambda: window.isMaximized() and not window.isFullScreen())


def test_settings_restore_defaults_waits_for_ok(app, window):
    from dataclasses import fields, replace
    from mosaicplayer.config import Config
    from mosaicplayer.settings_dialog import SettingsDialog
    changed = replace(window.cfg, gap=12, max_crop=0.35, decoder_mode="cpu", start_muted=True,
                      background="#123456", recent_files=["a.gpls", "b.gpls"], recent_limit=5)
    dialog = SettingsDialog(changed, window)
    assert dialog.max_crop.value() == 35  # not clamped to a lower maximum
    dialog._defaults()
    assert dialog.result_config is None  # nothing applied until OK
    dialog._accept()
    defaults = Config()
    for f in fields(Config):
        expected = changed.recent_files if f.name == "recent_files" else getattr(defaults, f.name)
        assert getattr(dialog.result_config, f.name) == expected, f.name


def test_settings_trims_recent_playlists(app, window):
    from dataclasses import replace
    from mosaicplayer.settings_dialog import SettingsDialog
    dialog = SettingsDialog(replace(window.cfg, recent_files=list("abcdef")), window)
    dialog.recent_limit.setValue(2)
    dialog._accept()
    assert dialog.result_config.recent_files == ["a", "b"]


def test_saving_at_once_keeps_saved_positions(app, window, clips, tmp_path):
    from mosaicplayer.playlist import Entry, Playlist, read_gpls, write_gpls
    source = tmp_path / "positions.gpls"
    paths = sorted(str(p) for p in clips.iterdir())[:3]
    write_gpls(source, Playlist([Entry(p, position=1.25) for p in paths]))
    window.load([str(source)])
    window.save_playlist()  # before the videos have loaded
    assert [e.position for e in read_gpls(source).entries] == [1.25] * 3


def test_layout_in_flight_cannot_bring_back_closed_tiles(app, window, clips):
    c = window.canvas
    window.load([clips])
    pump(app, 2.5)
    old_tiles, old_result, generation = list(c._layout_tiles), c.layout_info, c._layout_generation
    window.close_all()
    # A refine thread that started before the close delivers its result now.
    c._layout_done.emit(generation, (old_tiles, old_result, None))
    pump(app, 0.05)
    assert not c._layout_tiles and c.tile_at(c.rect().center()) is None


def test_playlists_keep_their_settings(app, window, clips, tmp_path):
    import json
    from mosaicplayer.playlist import Entry, Playlist, write_gpls
    c, cfg = window.canvas, window.cfg
    defaults = cfg.playlist_settings()
    window.load([clips])
    pump(app, 1.0)
    # Changed from the menus and keys: this playlist only.
    window.set_layout_mode("rows")
    window.set_gap(8)
    cfg.max_crop = 0.25
    c.set_all_end_action("next")
    c.set_seed(3)
    out = tmp_path / "with-settings.gpls"
    window._playlist_path = str(out)
    window.save_playlist()
    saved = json.loads(next(ln for ln in out.read_text().splitlines() if ln.startswith("#P:"))[3:])
    assert saved["mosaicplayer"] == {**cfg.playlist_settings(), "seed": 3}
    assert cfg._defaults == defaults  # the defaults didn't change

    window.close_all()
    assert cfg.playlist_settings() == defaults and c.layout_seed == 0
    window.load([str(out)])
    assert (cfg.layout_mode, cfg.gap, cfg.max_crop, cfg.end_action) == ("rows", 8, 0.25, "next")
    assert c.layout_seed == 3
    assert window.mode_actions["rows"].isChecked() and window.crop_action.isChecked()
    pump(app, 1.0)
    assert all(t.end_action == "next" for t in c.tiles)

    # A playlist without settings (say, from GridPlayer) opens with the defaults.
    plain = tmp_path / "plain.gpls"
    write_gpls(plain, Playlist([Entry(str(next(clips.iterdir())))]))
    window.close_all()
    window.load([str(out)])
    window.close_all()
    window.load([str(plain)])
    assert cfg.playlist_settings() == defaults

    # Save as default.
    window.set_layout_mode("columns")
    window.save_settings_as_default()
    assert cfg._defaults["layout_mode"] == "columns" and cfg.is_default()
    window.set_layout_mode("grid")
    window.use_default_settings()
    assert cfg.layout_mode == "columns" and window.mode_actions["columns"].isChecked()


def test_random_positions_are_not_snapped_to_keyframes(app, window, tmp_path):
    # One keyframe in the whole clip: keyframe seeks would all land on 0.
    clip = tmp_path / "one_keyframe.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=320x180:rate=25:duration=8", "-c:v", "libx264", "-g", "1000",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(clip)], check=True)
    c = window.canvas
    window.cfg.allow_duplicates = True  # the same clip in four tiles
    window.load([str(clip)] * 4)
    pump(app, 2.0)
    c.set_all_paused(True)
    for tile in c.tiles:
        tile.seek_random()
    pump(app, 1.0)
    positions = [tile.progress()[0] for tile in c.tiles]
    assert len({round(p, 1) for p in positions}) >= 3, positions
    assert max(positions) > 1.0


# --- Phase 2.1: drag and drop, media types, duplicates, the 6-tile wall ---------


@pytest.fixture(scope="module")
def media(tmp_path_factory, clips):
    """Two clips, a JPG, a GIF, a text file, and a clip in a subfolder."""
    folder = tmp_path_factory.mktemp("media")
    shutil.copy(clips / "c0.mp4", folder / "clip 10.mp4")
    shutil.copy(clips / "c1.mp4", folder / "clip 2.mp4")
    for name, args in (("still.jpg", ["-frames:v", "1"]),
                       ("anim.gif", ["-t", "1", "-r", "10"])):
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc2=size=320x240:rate=10", *args, str(folder / name)], check=True)
    (folder / "notes.txt").write_text("not media")
    (folder / "sub").mkdir()
    shutil.copy(clips / "c2.mp4", folder / "sub" / "deep.mp4")
    return folder


def _drop(window, paths, at=None):
    """Drag ``paths`` over the window and drop them at ``at`` (window coordinates).

    Returns the drop-zone hint that was showing just before the drop.
    """
    from PySide6.QtCore import QMimeData, QPointF, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    mime = QMimeData()
    mime.setUrls([QUrl(p) if "://" in str(p) else QUrl.fromLocalFile(str(p)) for p in paths])
    pos = at or QPointF(window.width() / 2, window.height() / 2)
    window.dragEnterEvent(QDragEnterEvent(pos.toPoint(), Qt.CopyAction, mime, Qt.LeftButton,
                                          Qt.NoModifier))
    hint = window.canvas.drop_hint
    window.dropEvent(QDropEvent(pos, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
    return hint


def _tile_center(window, tile):
    """The middle of ``tile`` in window coordinates."""
    c = window.canvas
    return c.mapTo(window, c._rect_of(tile).center().toPoint()).toPointF()


def _names(c):
    return [os.path.basename(t.entry.path) for t in c.tiles]


def test_drop_mixed_media_skips_the_rest(app, window, media):
    c = window.canvas
    hint = _drop(window, [media / n for n in
                          ("clip 10.mp4", "notes.txt", "still.jpg", "clip 2.mp4", "anim.gif")])
    assert hint[0].startswith("Drop to add") and hint[1] is None
    assert c.drop_hint is None  # the overlay goes away on drop
    # Sorted by name, whatever order Explorer lists them in.
    assert _names(c) == ["anim.gif", "clip 2.mp4", "clip 10.mp4", "still.jpg"]
    assert [t.entry.kind for t in c.tiles] == ["gif", "video", "video", "image"]
    assert len({t.entry.id for t in c.tiles}) == 4
    assert window._toast.isVisible() and "notes.txt" in window._toast.text()
    pump(app, 2.5)
    for tile in c.tiles:
        assert tile.error is None and tile.aspect_known and tile.frames_drawn > 0, tile.title
    still = c.tiles[3]
    assert not still._at_end  # a still image stays up (no 1 s timeout)
    assert not window._empty.isVisible()


def test_drop_folder_one_level_unless_set(app, window, media):
    c = window.canvas
    _drop(window, [media])
    assert _names(c) == ["anim.gif", "clip 2.mp4", "clip 10.mp4", "still.jpg"]
    window.close_all()
    window.cfg.recursive_folders = True
    _drop(window, [media])
    assert _names(c)[-1] == "deep.mp4"
    assert len(c.tiles) == 5


def test_duplicates_need_the_setting(app, window, media):
    c = window.canvas
    _drop(window, [media / "clip 2.mp4"])
    _drop(window, [media / "clip 2.mp4"])
    assert len(c.tiles) == 1
    assert "Already on the wall: clip 2.mp4" in window._toast.text()
    # The same file spelled differently is still the same file.
    window.load([str(media / "sub" / ".." / "CLIP 2.mp4") if sys.platform == "win32"
                 else str(media / "sub" / ".." / "clip 2.mp4")])
    assert len(c.tiles) == 1
    window.cfg.allow_duplicates = True
    _drop(window, [media / "clip 2.mp4"])
    assert len(c.tiles) == 2


def test_rejects_non_media_missing_and_web(app, window, media, tmp_path):
    c = window.canvas
    _drop(window, [media / "notes.txt"])
    assert not c.tiles and "Not a video, GIF or image: notes.txt" in window._toast.text()
    window.load([str(tmp_path / "gone.mp4")])
    assert not c.tiles and "Not found: gone.mp4" in window._toast.text()
    _drop(window, ["https://example.com/talk.mp4"])
    assert not c.tiles and "Only local files play" in window._toast.text()
    empty = tmp_path / "empty"
    empty.mkdir()
    window.load([empty])
    assert "No videos, GIFs or images in: empty" in window._toast.text()
    assert window._empty.isVisible()


def test_corrupt_file_gets_an_error_tile(app, window, clips, tmp_path):
    broken = tmp_path / "corrupt.mp4"
    broken.write_bytes((clips / "c0.mp4").read_bytes()[:1500])  # truncated
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"this is not a video" * 100)
    window.load([broken, junk, clips / "c1.mp4"])
    pump(app, 2.5)
    c = window.canvas
    errors = {t.title: t.error for t in c.tiles}
    assert errors["corrupt"] and errors["junk"] and errors["c1"] is None


def test_wall_holds_six_and_full_wall_replaces(app, window, clips, media, tmp_path):
    c = window.canvas
    many = tmp_path / "twenty"
    many.mkdir()
    for i in range(20):
        shutil.copy(clips / f"c{i % 6}.mp4", many / f"talk {i + 1}.mp4")
    _drop(window, [many])
    assert _names(c) == [f"talk {i}.mp4" for i in range(1, 7)]
    assert "The wall holds 6 tiles. Not added: talk 7.mp4, talk 8.mp4, talk 9.mp4 and 11 more" \
        in window._toast.text()
    pump(app, 2.0)

    # Full: one file dropped on a tile replaces that tile, reusing its player.
    third = c.tiles[2]
    player = third.player
    hint = _drop(window, [media / "still.jpg"], at=_tile_center(window, third))
    assert hint == ("Replace “talk 3”", third)
    assert c.tiles[2] is third and third.player is player
    assert _names(c)[2] == "still.jpg" and len(c.tiles) == 6

    # Opened another way (or dropped on no tile): click the tile to replace.
    window.load([media / "anim.gif"])
    assert c.pick is not None and len(c.tiles) == 6
    from PySide6.QtTest import QTest
    first = c.tiles[0]
    QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, c._rect_of(first).center().toPoint())
    assert c.pick is None and _names(c)[0] == "anim.gif"
    assert not first.paused  # the click chose a tile; it did not also pause it

    # Esc (or a right-click) cancels; nothing changes.
    before = _names(c)
    window.load([media / "clip 2.mp4"])
    assert c.pick is not None
    window.escape()
    assert c.pick is None and _names(c) == before

    # Several files onto a full wall: nothing added, and the notice says why.
    hint = _drop(window, [media / "clip 2.mp4", media / "clip 10.mp4"])
    assert "full" in hint[0] and hint[1] is None
    assert _names(c) == before and "The wall is full" in window._toast.text()
    pump(app, 1.5)
    assert all(t.error is None for t in c.tiles)

    # Closing a tile makes room again.
    c.remove_tile(c.tiles[-1])
    _drop(window, [media / "clip 2.mp4"])
    assert len(c.tiles) == 6 and _names(c)[-1] == "clip 2.mp4"


def test_drag_leave_clears_the_overlay(app, window, media):
    from PySide6.QtCore import QMimeData, QPoint, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(media / "still.jpg"))])
    window.dragEnterEvent(QDragEnterEvent(QPoint(50, 50), Qt.CopyAction, mime, Qt.LeftButton,
                                          Qt.NoModifier))
    assert window.canvas.drop_hint is not None and not window._empty.isVisible()
    window.dragLeaveEvent(QDragLeaveEvent())
    assert window.canvas.drop_hint is None and window._empty.isVisible()


def test_trimmed_playlist_is_not_a_save_target(app, window, clips, tmp_path):
    from mosaicplayer.playlist import Entry, Playlist, write_gpls
    big = tmp_path / "eight.gpls"
    paths = [str(clips / f"c{i % 6}.mp4") for i in range(8)]
    write_gpls(big, Playlist([Entry(p) for p in paths]))
    window.cfg.allow_duplicates = True
    window.load([str(big)])
    assert len(window.canvas.tiles) == 6
    assert window._playlist_path is None  # Ctrl+S must not overwrite it with 6 of 8
    window.close_all()
    small = tmp_path / "three.gpls"
    write_gpls(small, Playlist([Entry(p) for p in paths[:3]]))
    window.load([str(small)])
    assert window._playlist_path == str(small)


def test_rotated_video_gets_a_tile_of_its_shown_shape(app, window, clips, tmp_path):
    # A landscape clip tagged "rotate 90" (as phones record portrait video) shows portrait.
    rotated = tmp_path / "phone.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-display_rotation", "90",
                    "-i", str(clips / "c0.mp4"), "-c", "copy", str(rotated)], check=True)
    window.load([rotated])
    pump(app, 2.0)
    tile = window.canvas.tiles[0]
    assert tile.aspect_known and abs(tile.aspect - 180 / 320) < 0.01, tile.aspect


# --- Phase 2.2: media handling -------------------------------------------------------


@pytest.fixture(scope="module")
def media22(tmp_path_factory):
    """Stills to flip through, a clip with sound, and an animated WebP if ffmpeg can."""
    folder = tmp_path_factory.mktemp("media22")

    def ff(*args):
        return subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *args],
                              capture_output=True).returncode == 0

    for name in ("a 1.jpg", "a 2.png", "a 10.jpg"):
        assert ff("-f", "lavfi", "-i", "testsrc2=size=320x240", "-frames:v", "1",
                  str(folder / name))
    assert ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10:duration=1",
              str(folder / "a 3.gif"))
    assert ff("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=2", "-f", "lavfi",
              "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-preset", "ultrafast",
              "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(folder / "sound.mp4"))
    (folder / "anim").mkdir()  # its own folder: the flip test counts the files above
    ff("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10:duration=1", "-loop", "0",
       str(folder / "anim" / "moving.webp"))  # needs libwebp; the test using it skips without
    return folder


def test_images_stay_up_and_do_not_pause(app, window, media22):
    c = window.canvas
    window.load([media22 / "a 1.jpg"])
    pump(app, 2.5)  # mpv's own default would end a still after 1 s
    tile = c.tiles[0]
    assert tile.entry.kind == "image" and not tile._at_end and tile.frames_drawn > 0
    tile.toggle_pause()
    assert not tile.paused  # a still has nothing to pause
    assert not tile.uses_gpu  # and never takes a GPU decoder


def test_gif_loops_and_takes_no_gpu_decoder(app, window, media22):
    c = window.canvas
    window.load([media22 / "a 3.gif"])  # 1 s long
    pump(app, 2.5)
    tile = c.tiles[0]
    assert tile.entry.kind == "gif" and not tile._at_end and not tile.uses_gpu
    assert tile.frames_drawn > 15  # still animating after it ended once


def test_audio_is_detected(app, window, clips, media22):
    c = window.canvas
    window.load([media22 / "sound.mp4", clips / "c0.mp4"])
    pump(app, 2.0)
    by_name = {t.title: t for t in c.tiles}
    assert by_name["sound"].has_audio is True
    assert by_name["c0"].has_audio is False


def test_hover_facts_per_type(app, window, clips, media22):
    from mosaicplayer.canvas import _tile_facts
    c = window.canvas
    window.load([media22 / "a 1.jpg", media22 / "a 3.gif", clips / "c0.mp4"])
    pump(app, 2.0)
    facts = {t.title: _tile_facts(t) for t in c.tiles}
    assert facts["a 1"][:3] == ["a 1", "IMG", "320×240"]
    assert not any("/" in f for f in facts["a 1"])  # no timeline for a still
    assert facts["a 3"][1] == "GIF" and any(" / " in f for f in facts["a 3"])
    video = facts["c0"]
    assert video[1:3] == ["VIDEO", "320×180"] and "no audio" in video
    assert any(f in video for f in ("GPU decode", "CPU decode", "SW decode"))


def test_left_right_flip_through_pictures(app, window, media22):
    c = window.canvas
    window.load([media22 / "a 2.png"])
    pump(app, 1.0)
    tile = c.tiles[0]
    names = []
    for step in (1, 1, 1, -1):
        window._left_right(tile, step)
        names.append(os.path.basename(tile.entry.path))
    # Natural order: a 1, a 2, a 3 (GIF), a 10; wrapping; the same player throughout.
    assert names == ["a 3.gif", "a 10.jpg", "a 1.jpg", "a 10.jpg"]
    assert c.tiles == [tile]


def test_transparency_setting_reaches_the_players(app, window, media22):
    window.load([media22 / "a 2.png"])
    pump(app, 1.0)
    tile = window.canvas.tiles[0]
    assert tile.player.background == "color"
    window.cfg.transparency = "checker"
    window._settings_changed()
    assert tile.player.background == "tiles"


def test_animated_webp_plays_like_a_gif(app, window, media22):
    if not (media22 / "anim" / "moving.webp").exists():
        pytest.skip("ffmpeg without libwebp")
    window.load([media22 / "anim" / "moving.webp"])
    pump(app, 2.0)
    tile = window.canvas.tiles[0]
    assert tile.entry.kind == "gif"
    tile.toggle_pause()
    assert tile.paused


# --- Phase 2.3: tile layout ---------------------------------------------------------------


def test_default_layout_is_a_grid_of_whole_pictures(app, window, clips):
    c, cfg = window.canvas, window.cfg
    assert (cfg.layout_mode, cfg.max_crop) == ("grid", 0.0)
    window.load([clips])
    pump(app, 2.5)
    assert len(c.rects) == 6
    assert all(t.player.panscan == 0.0 for t in c.tiles)  # letterbox, never crop
    for tile, rect in zip(c._layout_tiles, c.rects):
        assert abs(rect.w / rect.h - tile.aspect) < 0.02  # each tile has its picture's shape
    window.set_crop(True)  # the opt-in "allow cropping"
    assert all(t.player.panscan == 1.0 for t in c.tiles)
    window.set_crop(False)
    assert all(t.player.panscan == 0.0 for t in c.tiles)


def test_keys_act_on_the_current_tile(app, window, clips):
    c = window.canvas
    window.load([clips / "c0.mp4"])
    pump(app, 1.0)
    only = c.tiles[0]
    assert c.hovered is None and c.current is only  # one tile: that tile
    window.load([clips / "c1.mp4", clips / "c2.mp4"])
    pump(app, 1.0)
    a, b, d = c.tiles
    assert c.current is None  # several tiles, none hovered or focused yet
    c.last_hovered = b  # the mouse was over b, then left the window
    assert c.current is b
    c.set_solo(d)
    assert c.current is d  # the focused tile wins over the last hovered one
    c.hovered = a
    assert c.current is a  # the tile under the mouse wins over everything
    c.hovered = None
    c.set_solo(None)
    window._current(c.remove_tile)()  # what Del does
    assert b not in c.tiles and c.current is None


def test_one_file_at_a_time(app, window, clips, media22):
    c, cfg = window.canvas, window.cfg
    cfg.one_at_a_time = True
    window.load([clips / "c0.mp4"])
    pump(app, 1.0)
    tile = c.tiles[0]
    tile.set_volume(0.4)
    window.load([media22 / "a 1.jpg"])  # replaces, reusing the tile, its volume and mode
    assert c.tiles == [tile] and tile.entry.path.endswith("a 1.jpg")
    assert tile.entry.volume == 0.4
    assert not window._toast.isVisible()  # opening is just opening: no "Replaced" notice
    window.load([clips])  # a folder: its first file
    assert c.tiles == [tile] and tile.entry.path.endswith("c0.mp4")
    assert "One file at a time is on. Not added" in window._toast.text()
    cfg.one_at_a_time = False
    window.load([clips / "c1.mp4"])
    assert len(c.tiles) == 2


def test_focus_mode_round_trip_and_pausing_others(app, window, clips):
    c, cfg = window.canvas, window.cfg
    window.load([clips])
    pump(app, 2.5)
    before = list(c.rects)
    focused = c.tiles[1]
    c.set_solo(focused)
    pump(app, 0.5)
    assert len(c.rects) == 1 and c._layout_tiles == [focused]
    assert all(t.player.pause for t in c.tiles if t is not focused)  # default: others pause
    cfg.pause_others_when_focused = False
    window._settings_changed()
    pump(app, 0.3)
    assert not any(t.player.pause for t in c.tiles)  # the setting off: all keep playing
    window.escape()  # Esc leaves focus mode
    pump(app, 0.5)
    assert c.solo is None and c.rects == before  # back to the same layout


# --- Phase 2.4: hover controls --------------------------------------------------------------


def _mouse(c, kind, point, buttons=Qt.NoButton, button=Qt.NoButton):
    """Send a mouse event straight to the canvas (QTest moves the real cursor on Windows,
    and the event then goes to whatever window is under it)."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    types = {"move": QEvent.MouseMove, "press": QEvent.MouseButtonPress,
             "release": QEvent.MouseButtonRelease, "double": QEvent.MouseButtonDblClick}
    point = QPointF(point)
    event = QMouseEvent(types[kind], point, c.mapToGlobal(point), button, buttons,
                        Qt.NoModifier)
    QApplication.sendEvent(c, event)


def _hover(app, c, tile):
    """Move the mouse onto ``tile`` and wait for its controls to fade in."""
    _mouse(c, "move", c._rect_of(tile).center())
    pump(app, 0.4)
    return c._bars_for(tile)


def _click(app, c, point, double=False):
    _mouse(c, "move", point)
    _mouse(c, "press", point, Qt.LeftButton, Qt.LeftButton)
    _mouse(c, "release", point, Qt.NoButton, Qt.LeftButton)
    if double:  # Qt sends the second click as a press, then a double-click event
        _mouse(c, "press", point, Qt.LeftButton, Qt.LeftButton)
        _mouse(c, "double", point, Qt.LeftButton, Qt.LeftButton)
        _mouse(c, "release", point, Qt.NoButton, Qt.LeftButton)
    pump(app, 0.2)


def test_hover_controls_fade_in_act_and_fade_out(app, window, media22):
    c = window.canvas
    window.load([media22 / "sound.mp4"])
    pump(app, 1.5)
    tile = c.tiles[0]
    assert not c._bars_shown()
    bars = _hover(app, c, tile)
    assert c._bar_tile is tile and c._bar_opacity == 1.0 and c._overlay_timer.isActive()
    paused = tile.paused
    _click(app, c, bars.controls["play"].center())
    assert tile.paused is not paused
    _click(app, c, bars.bottom.topLeft() + QPointF(bars.controls["play"].width() * 2.5, 2))
    assert tile.paused is not paused  # a click on the bar itself doesn't pause the video
    muted = tile.entry.muted
    _click(app, c, bars.controls["mute"].center())
    assert tile.entry.muted is not muted
    vol = bars.controls["volume"]
    _click(app, c, QPointF(vol.left() + 4 + (vol.width() - 8) * 0.25, vol.center().y()))
    assert abs(tile.entry.volume - 0.25) < 0.02 and not tile.entry.muted
    assert tile.end_action == "loop"
    _click(app, c, bars.controls["mode"].center())
    assert tile.end_action == "next" and tile.player.loop_file is False
    _click(app, c, bars.controls["mode"].center())
    _click(app, c, bars.controls["mode"].center())
    assert tile.end_action == "loop"
    seek = bars.controls["seek"]
    _click(app, c, QPointF(seek.left() + seek.width() * 0.75, seek.center().y()))
    pump(app, 0.3)
    pos, dur = tile.progress()
    assert abs(pos - dur * 0.75) < 0.3
    _click(app, c, bars.controls["focus"].center())
    assert c.solo is tile
    _click(app, c, c._bars_for(tile).controls["focus"].center())
    assert c.solo is None
    # Idle: the controls fade out (2 s in the app; shortened here).
    c._bar_idle.setInterval(200)
    _mouse(c, "move", c._rect_of(tile).center())
    pump(app, 0.8)
    assert c._bar_opacity == 0.0 and not c._bars_shown()
    assert not c._overlay_timer.isActive()  # idle: nothing repaints for the controls
    c._bar_idle.setInterval(2000)
    bars = _hover(app, c, tile)
    _click(app, c, bars.controls["close"].center())
    assert not c.tiles and c._bar_tile is None


def test_hover_controls_per_kind_and_quick_clicks(app, window, media22):
    c = window.canvas
    window.load([media22 / "a 1.jpg", media22 / "a 3.gif"])
    pump(app, 1.5)
    image, gif = c.tiles
    assert set(_hover(app, c, gif).controls) >= {"play", "prev", "next", "mode"}
    assert "seek" not in c._bars_for(gif).controls
    bars = _hover(app, c, image)
    assert "play" not in bars.controls and "volume" not in bars.controls
    # Two quick clicks on Next are two steps, not a double-click that focuses.
    _click(app, c, bars.controls["next"].center(), double=True)
    assert os.path.basename(image.entry.path) == "a 10.jpg"  # a 1 -> a 2 -> (a 3 shown) -> a 10
    assert c.solo is None


def test_space_m_and_arrows_act_on_the_current_tile_only(app, window, clips):
    c = window.canvas
    window.load([clips / "c0.mp4", clips / "c1.mp4"])
    pump(app, 1.5)
    a, b = c.tiles
    c.hovered = a
    run = {act.shortcut().toString(): act for act in window.actions() if not act.shortcut().isEmpty()}
    run["Space"].trigger()
    assert a.paused and not b.paused
    run["M"].trigger()
    assert a.entry.muted is not b.entry.muted
    a.set_muted(True)
    a.set_volume(0.5)
    run["Up"].trigger()
    assert a.entry.volume == 0.6 and not a.entry.muted  # louder also unmutes
    run["Down"].trigger()
    run["Down"].trigger()
    assert a.entry.volume == 0.4 and b.entry.volume == 1.0
    assert c._bar_tile is a  # the key brought up that tile's controls
    run["PgDown"].trigger()  # next file in the folder (c1 is on the wall: skipped)
    assert os.path.basename(a.entry.path) == "c2.mp4"
    run["Shift+Space"].trigger()
    assert c.all_paused()


def test_master_volume_scales_every_tile(app, window, clips, media22):
    """Plan 2.5: effective volume = tile x master; mutes combine; solo audio."""
    c = window.canvas
    m = c.master
    window.load([media22 / "sound.mp4", clips / "c0.mp4", clips / "c1.mp4"])
    pump(app, 1.5)
    a, b, d = c.tiles
    for t in (a, b, d):
        t.set_muted(False)
    a.set_volume(0.5)
    m.set_volume(0.6)
    assert abs(a.player.volume - 30) < 0.01 and abs(b.player.volume - 60) < 0.01
    assert a.entry.volume == 0.5 and window.cfg.master_volume == 0.6  # own level kept
    b.set_volume(0.25)  # a tile change affects that tile only
    assert abs(b.player.volume - 15) < 0.01 and abs(d.player.volume - 60) < 0.01
    # Mutes combine: the master silences all; unmuting it keeps a tile's own mute.
    d.set_muted(True)
    m.set_muted(True)
    assert all(t.player.mute for t in (a, b, d)) and not a.entry.muted
    assert window.cfg.master_muted
    m.set_muted(False)
    assert not a.player.mute and not b.player.mute and d.player.mute
    # Ctrl+Shift+M: only the current tile is heard, even with the master muted.
    m.set_muted(True)
    c.hovered = b
    run = {act.shortcut().toString(): act for act in window.actions()
           if not act.shortcut().isEmpty()}
    run["Ctrl+Shift+M"].trigger()
    assert [t.audible for t in (a, b, d)] == [False, True, False] and not m.muted
    # Solo audio: only the tile under the mouse is heard, and it follows the mouse.
    for t in (a, b, d):
        t.set_muted(False)
    c.set_solo_audio(True)
    assert [t.player.mute for t in (a, b, d)] == [True, False, True]
    _mouse(c, "move", c._rect_of(d).center())
    assert [t.audible for t in (a, b, d)] == [False, False, True]
    c.set_solo_audio(False)
    assert all(t.audible for t in (a, b, d))


def test_footer_master_controls(app, window, clips):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    f = window.footer
    m = window.canvas.master
    window.load([clips / "c0.mp4"])
    pump(app, 1.0)
    assert f.isVisible() and f.geometry().top() >= window.canvas.geometry().bottom()

    def send(kind, point, buttons):
        point = QPointF(point)
        QApplication.sendEvent(f, QMouseEvent(kind, point, f.mapToGlobal(point), Qt.LeftButton,
                                              buttons, Qt.NoModifier))

    ctrl = f.controls()
    mute = ctrl["mute"].center()
    send(QEvent.MouseButtonPress, mute, Qt.LeftButton)
    send(QEvent.MouseButtonRelease, mute, Qt.NoButton)
    assert m.muted and f.level_text().endswith("(muted)")
    vol = ctrl["volume"]
    send(QEvent.MouseButtonPress, vol.center(), Qt.LeftButton)  # dragging unmutes
    assert not m.muted and abs(m.volume - 0.5) < 0.02
    send(QEvent.MouseMove, QPointF(vol.right() + 50, vol.center().y()), Qt.LeftButton)
    send(QEvent.MouseButtonRelease, QPointF(vol.right() + 50, vol.center().y()), Qt.NoButton)
    assert m.volume == 1.0 and f.level_text() == "100%"
    assert abs(window.canvas.tiles[0].player.volume - 100 * window.canvas.tiles[0].entry.volume) < 0.01
