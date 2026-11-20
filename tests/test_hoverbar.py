"""Geometry of the hover controls (plan 2.4); no OpenGL or players needed."""

from PySide6.QtCore import QPointF, QRectF

from mosaicplayer import hoverbar
from mosaicplayer.options import LOOP, NEXT, RANDOM, STOP

BIG = QRectF(0, 0, 640, 360)


def names(bars):
    return set(bars.controls)


def test_controls_per_kind():
    video = hoverbar.layout_bars(BIG, "video")
    assert names(video) == {"play", "prev", "next", "seek", "mute", "volume", "mode",
                            "focus", "close"}
    assert video.times is not None and video.mode_label
    gif = hoverbar.layout_bars(BIG, "gif")
    assert names(gif) == {"play", "prev", "next", "mode", "focus", "close"}
    image = hoverbar.layout_bars(BIG, "image")
    assert names(image) == {"prev", "next", "mode", "focus", "close"}


def test_controls_do_not_overlap_and_stay_in_their_bar():
    for kind in ("video", "gif", "image"):
        for width in (200, 320, 640, 1600):
            bars = hoverbar.layout_bars(QRectF(10, 20, width, 300), kind)
            rects = list(bars.controls.items())
            for i, (a, ra) in enumerate(rects):
                bar = bars.top if a in ("focus", "close") else bars.bottom
                assert bar.contains(ra), (kind, width, a)
                for b, rb in rects[i + 1:]:
                    assert not ra.intersects(rb), (kind, width, a, b)


def test_narrow_tiles_drop_the_least_needed_first():
    full = names(hoverbar.layout_bars(BIG, "video"))
    narrow = hoverbar.layout_bars(QRectF(0, 0, 300, 200), "video")
    assert "volume" not in names(narrow) and {"play", "seek", "mute"} <= names(narrow)
    tighter = hoverbar.layout_bars(QRectF(0, 0, 200, 200), "video")
    assert {"play", "seek"} <= names(tighter) and len(names(tighter)) < len(full)
    assert hoverbar.layout_bars(QRectF(0, 0, 40, 200), "video") is None  # nothing fits
    picture = hoverbar.layout_bars(QRectF(0, 0, 120, 200), "image")
    assert {"prev", "next"} <= names(picture)  # pictures keep prev / next


def test_short_tiles_get_only_the_bottom_bar():
    bars = hoverbar.layout_bars(QRectF(0, 0, 640, 80), "video")
    assert bars.top is None and "close" not in bars.controls and "play" in bars.controls
    assert hoverbar.layout_bars(QRectF(0, 0, 640, 40), "video") is None


def test_slider_positions_and_hit_testing():
    bars = hoverbar.layout_bars(BIG, "video")
    seek = bars.controls["seek"]
    assert hoverbar.seek_fraction(bars, seek.left()) == 0.0
    assert hoverbar.seek_fraction(bars, seek.right()) == 1.0
    assert abs(hoverbar.seek_fraction(bars, seek.center().x()) - 0.5) < 1e-6
    assert hoverbar.seek_fraction(bars, -100) == 0.0  # dragged past the end: clamped
    vol = bars.controls["volume"]
    assert hoverbar.volume_fraction(bars, vol.right()) == 1.0
    assert bars.control_at(bars.controls["play"].center()) == "play"
    assert bars.control_at(QPointF(320, 180)) is None  # the middle of the picture
    assert bars.contains(bars.controls["close"].center())
    assert not bars.contains(QPointF(320, 180))


def test_mode_button_cycles_loop_next_stop():
    assert [hoverbar.next_mode(m) for m in (LOOP, NEXT, STOP)] == [NEXT, STOP, LOOP]
    assert hoverbar.next_mode(RANDOM) == LOOP  # an older mode joins the cycle at Loop
    assert hoverbar._fmt(3725) == "1:02:05" and hoverbar._fmt(65) == "1:05"
