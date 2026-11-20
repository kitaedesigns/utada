"""Run MosaicPlayer from source with a measurement probe (no changes to its code).

Usage: python mosaic_probe.py <mosaicplayer-src-dir> <probe.csv> [mosaicplayer args...]

Once a second, appends one row per tile (mpv counters) and one "app" row
(canvas redraws per second) to probe.csv, in the same layout as the
MultipleVideoPlayer probe:
  t, tile, file, hwdec, time_pos, container_fps, est_vf_fps,
  frame_drops, decoder_drops, vo_delayed, frames_drawn, app_fps
"""
import os
import sys
import threading
import time

src, out, *args = sys.argv[1:]
sys.path.insert(0, src)

import mosaicplayer.canvas as C  # noqa: E402
import mosaicplayer.window as W  # noqa: E402

_paints = [0]
_orig_paint = C.Canvas.paintGL


def _paint(self):
    _paints[0] += 1
    return _orig_paint(self)


C.Canvas.paintGL = _paint
_t0 = time.monotonic()


def _sample(canvas):
    def get(p, name):
        try:
            v = getattr(p, name)
            return "" if v is None else v
        except Exception:
            return ""

    last_t, last_paints = time.monotonic(), 0
    while True:
        time.sleep(1.0)
        now = time.monotonic()
        rows = [f"{now - _t0:.3f},app,,,,,,,,,,{(_paints[0] - last_paints) / (now - last_t):.2f}"]
        last_t, last_paints = now, _paints[0]
        for i, t in enumerate(list(canvas.tiles)):
            if t.closed:
                continue
            p = t.player
            rows.append(",".join(str(x) for x in (
                f"{now - _t0:.3f}", i, os.path.basename(t.entry.path),
                get(p, "hwdec_current"), get(p, "time_pos"), get(p, "container_fps"),
                get(p, "estimated_vf_fps"), get(p, "frame_drop_count"),
                get(p, "decoder_frame_drop_count"), get(p, "vo_delayed_frame_count"),
                t.frames_drawn, "")))
        with open(out, "a", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")


def _process_age_ms():
    """Milliseconds since this process was created (Windows), for first-frame timing."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.windll.kernel32
    # Without these, the pseudo-handle -1 is passed as a 32-bit int and the call fails.
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    c, e, kt, ut = (wintypes.FILETIME() for _ in range(4))
    k.GetProcessTimes(k.GetCurrentProcess(), ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut))
    now = wintypes.FILETIME()
    k.GetSystemTimeAsFileTime(ctypes.byref(now))
    ft = lambda f: (f.dwHighDateTime << 32) | f.dwLowDateTime  # noqa: E731
    return (ft(now) - ft(c)) / 10_000


def _first_frames(canvas):
    """Every 10 ms until each tile has drawn a frame: record the first frame per tile."""
    seen = {}
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        tiles = list(canvas.tiles)
        for i, t in enumerate(tiles):
            if i not in seen and t.frames_drawn > 0:
                seen[i] = _process_age_ms()
        if tiles and len(seen) == len(tiles):
            break
        time.sleep(0.01)
    with open(out + ".first.txt", "w", encoding="utf-8") as f:
        f.write("".join(f"{i},{ms:.0f}\n" for i, ms in sorted(seen.items())))


def _switch_probe(window, files):
    """MOSAIC_PROBE_SWITCH="a|b": 10 times, replace tile 0's video via the app's own
    Tile.replace (on the UI thread) and time until the new file reports time-pos < 0.3 s
    and a frame has been drawn after that. Same rule as the MultipleVideoPlayer probe."""
    from PySide6.QtCore import QObject, Qt, Signal

    class Bridge(QObject):
        go = Signal(str)

    bridge = Bridge()
    bridge.moveToThread(window.thread())
    bridge.go.connect(lambda path: window.canvas.tiles[0].replace(path), Qt.QueuedConnection)
    time.sleep(6)
    results = []
    for i in range(10):
        tile = window.canvas.tiles[0]
        target = files[i % 2]
        t0 = time.monotonic()
        bridge.go.emit(target)
        seen, result = None, "timeout"
        while time.monotonic() - t0 < 5:
            pos = tile.player.time_pos
            path_ok = os.path.normcase(tile.player.path or "") == os.path.normcase(target)
            if seen is None and path_ok and pos is not None and pos < 0.3:
                seen = tile.frames_drawn
            elif seen is not None and tile.frames_drawn > seen:
                result = f"{(time.monotonic() - t0) * 1000:.0f}"
                break
            time.sleep(0.002)
        results.append(result)
        time.sleep(2)
    with open(out + ".switch.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(results) + "\n")


_orig_init = W.MainWindow.__init__


def _init(self, *a, **k):
    _orig_init(self, *a, **k)
    threading.Thread(target=_sample, args=(self.canvas,), daemon=True).start()
    threading.Thread(target=_first_frames, args=(self.canvas,), daemon=True).start()
    if os.environ.get("MOSAIC_PROBE_REMOVE"):
        # Remove the first tile with the app's own remove_tile at 20, 24 and 28 s (UI thread).
        from PySide6.QtCore import QTimer
        for at in (20, 24, 28):
            QTimer.singleShot(int(at * 1000 - (time.monotonic() - _t0) * 1000),
                              lambda c=self.canvas: c.tiles and c.remove_tile(c.tiles[0]))
    if os.environ.get("MOSAIC_PROBE_SWITCH"):
        files = os.environ["MOSAIC_PROBE_SWITCH"].split("|")
        threading.Thread(target=_switch_probe, args=(self, files), daemon=True).start()


W.MainWindow.__init__ = _init

from mosaicplayer.__main__ import main  # noqa: E402

sys.exit(main(args))
