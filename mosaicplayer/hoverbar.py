"""The per-tile hover controls (plan 2.4), drawn by the canvas over the video.

Two floating bars inside the hovered tile, after the "Video Wall Mockup"
design: a top bar with the name, focus and close, and a bottom bar with the
playback controls. Geometry (``layout_bars``) is separate from painting, so
the canvas uses one source for both drawing and clicks, and tests can check
it without OpenGL.

Controls per kind (plan 2.4):
  video: play/pause, previous, next, seek bar with times, mute, volume, mode
  GIF:   play/pause, previous, next, mode
  image: previous, next, mode
All kinds get focus and close (X) in the top bar, as in the mockup.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from .options import LOOP, NEXT, STOP
from .playlist import GIF, VIDEO

BAR_H = 36.0  # bar height
INSET = 8.0  # bar distance from the tile's edges
PAD = 4.0  # inside the bar, around the controls
BTN = 28.0  # square button
GAP = 2.0
VOLUME_W = 64.0
MODE_W = 64.0  # icon + "Loop" / "Next" / "Stop"
SEEK_MIN = 40.0
RADIUS = 10.0

FADE_S = 0.15  # fade in / out (the mockup's .15s)
IDLE_MS = 2000  # hide after the mouse stops moving (plan 2.4)

BAR_COLOR = QColor(30, 30, 32, 205)  # the mockup's rgba(30,30,32,.62), less see-through without blur
BAR_EDGE = QColor(255, 255, 255, 22)
HOVER_FILL = QColor(255, 255, 255, 36)
CLOSE_HOVER = QColor(255, 69, 58)  # the mockup's --bad
TEXT = QColor(245, 245, 247)
MUTED = QColor(174, 174, 178)
TRACK = QColor(255, 255, 255, 72)
ACCENT_COLOR = QColor(76, 141, 255)  # canvas.ACCENT, the plan's one accent

MODES = (LOOP, NEXT, STOP)  # the mode button cycles these
MODE_LABELS = {LOOP: "Loop", NEXT: "Next", STOP: "Stop"}
MODE_TIPS = {
    LOOP: "When this clip ends: repeat it. Click for Next.",
    NEXT: "When this clip ends: play the next file in its folder. Click for Stop.",
    STOP: "When this clip ends: stop on the last frame. Click for Loop.",
}

TIPS = {
    "play": "Play or pause (Space)",
    "prev": "Previous file in the folder (PageUp or P)",
    "next": "Next file in the folder (PageDown or N)",
    "mute": "Mute this tile (M)",
    "volume": "Volume of this tile (Up / Down)",
    "seek": "Seek",
    "focus": "Focus this tile (double-click, Enter)",
    "unfocus": "Show all tiles (double-click, Esc)",
    "close": "Close this tile (Del)",
}

# Bottom-bar items left out, in this order, until the bar fits the tile.
_DROP_ORDER = ("volume", "times", "mode_label", "prevnext", "mute", "mode")


@dataclass
class Bars:
    """Where everything is, in the canvas's logical pixels."""
    top: QRectF | None
    bottom: QRectF | None
    controls: dict  # name -> QRectF (play, prev, next, seek, mute, volume, mode, focus, close)
    title: QRectF | None = None
    times: tuple | None = None  # (elapsed QRectF, total QRectF)
    mode_label: bool = True

    def control_at(self, pos: QPointF) -> str | None:
        for name, rect in self.controls.items():
            if rect.contains(pos):
                return name
        return None

    def contains(self, pos: QPointF) -> bool:
        return any(b is not None and b.contains(pos) for b in (self.top, self.bottom))


def bottom_items(kind: str) -> set[str]:
    if kind == VIDEO:
        return {"play", "prevnext", "times", "seek", "mute", "volume", "mode", "mode_label"}
    if kind == GIF:
        return {"play", "prevnext", "mode", "mode_label"}
    return {"prevnext", "mode", "mode_label"}  # IMAGE


def _bottom_width(items: set[str], time_w: float) -> float:
    w = 0.0
    n = 0
    for name, width in (("play", BTN), ("prevnext", 2 * BTN + GAP), ("mute", BTN),
                        ("volume", VOLUME_W)):
        if name in items:
            w += width
            n += 1
    if "times" in items:
        w += 2 * time_w + GAP
        n += 1
    if "seek" in items:
        w += SEEK_MIN
        n += 1
    if "mode" in items:
        w += MODE_W if "mode_label" in items else BTN
        n += 1
    return w + GAP * 2 * max(n - 1, 0)


def layout_bars(tile_rect: QRectF, kind: str, time_w: float = 34.0) -> Bars | None:
    """Bars and controls for a tile on screen; None if the tile is too small.

    ``time_w`` is the width of one time label ("12:34"), measured by the caller.
    """
    r = tile_rect
    inner_w = r.width() - 2 * INSET - 2 * PAD
    if r.height() < BAR_H + 2 * INSET or inner_w < BTN * 2:
        return None
    items = bottom_items(kind)
    for drop in (None,) + _DROP_ORDER:
        if drop is not None:
            items.discard(drop)
            if drop == "prevnext" and kind != VIDEO:
                continue  # keep prev/next for pictures: it's most of what they have
        if _bottom_width(items, time_w) <= inner_w:
            break
    if not items:
        return None
    controls: dict[str, QRectF] = {}
    bottom = QRectF(r.left() + INSET, r.bottom() - INSET - BAR_H, r.width() - 2 * INSET, BAR_H)
    y = bottom.top() + (BAR_H - BTN) / 2
    x = bottom.left() + PAD
    right = bottom.right() - PAD

    def button(name, width=BTN):
        nonlocal x
        controls[name] = QRectF(x, y, width, BTN)
        x += width + 2 * GAP

    if "play" in items:
        button("play")
    if "prevnext" in items:
        button("prev")
        button("next")
    # From the right: mode, then volume, then mute.
    if "mode" in items:
        width = MODE_W if "mode_label" in items else BTN
        controls["mode"] = QRectF(right - width, y, width, BTN)
        right -= width + 2 * GAP
    if "volume" in items:
        controls["volume"] = QRectF(right - VOLUME_W, y, VOLUME_W, BTN)
        right -= VOLUME_W
    if "mute" in items:
        controls["mute"] = QRectF(right - BTN, y, BTN, BTN)
        right -= BTN + 2 * GAP
    times = None
    if "seek" in items:
        if "times" in items:
            elapsed = QRectF(x, y, time_w, BTN)
            x += time_w + GAP
            total = QRectF(right - time_w, y, time_w, BTN)
            right -= time_w + GAP
            times = (elapsed, total)
        controls["seek"] = QRectF(x, y, max(right - x, SEEK_MIN), BTN)

    top = None
    title = None
    if r.height() >= 2 * BAR_H + 3 * INSET + 8:  # room for both bars and some picture
        top = QRectF(r.left() + INSET, r.top() + INSET, r.width() - 2 * INSET, BAR_H)
        ty = top.top() + (BAR_H - BTN) / 2
        controls["close"] = QRectF(top.right() - PAD - BTN, ty, BTN, BTN)
        controls["focus"] = QRectF(top.right() - PAD - 2 * BTN - 2 * GAP, ty, BTN, BTN)
        title = QRectF(top.left() + PAD + 6, ty, controls["focus"].left() - top.left() - PAD - 10,
                       BTN)
    return Bars(top, bottom, controls, title, times, "mode_label" in items)


def seek_fraction(bars: Bars, x: float) -> float:
    r = bars.controls["seek"]
    return max(0.0, min(1.0, (x - r.left()) / r.width())) if r.width() > 0 else 0.0


def volume_fraction(bars: Bars, x: float) -> float:
    r = bars.controls["volume"].adjusted(4, 0, -4, 0)
    return max(0.0, min(1.0, (x - r.left()) / r.width())) if r.width() > 0 else 0.0


def next_mode(mode: str) -> str:
    return MODES[(MODES.index(mode) + 1) % len(MODES)] if mode in MODES else LOOP


def _fmt(seconds: float) -> str:
    seconds = int(seconds or 0)
    h, rest = divmod(seconds, 3600)
    return f"{h}:{rest // 60:02d}:{rest % 60:02d}" if h else f"{rest // 60}:{rest % 60:02d}"


# --- painting -----------------------------------------------------------------

def paint_bars(p: QPainter, bars: Bars, tile, opacity: float, hot: str | None,
               facts: str, focused: bool, font: QFont):
    """Draw the bars for ``tile``. ``hot`` is the control under the mouse."""
    p.save()
    p.setOpacity(opacity)
    p.setRenderHint(QPainter.Antialiasing)
    p.setFont(font)
    for bar in (bars.top, bars.bottom):
        if bar is not None:
            p.setPen(QPen(BAR_EDGE, 1))
            p.setBrush(BAR_COLOR)
            p.drawRoundedRect(bar, RADIUS, RADIUS)
    c = bars.controls
    for name, rect in c.items():
        if name == hot and name not in ("seek", "volume"):
            p.setPen(Qt.NoPen)
            p.setBrush(CLOSE_HOVER if name == "close" else HOVER_FILL)
            p.drawRoundedRect(rect, 7, 7)
    kind = tile.entry.kind
    if "play" in c:
        _icon(p, "play" if tile.paused else "pause", c["play"])
    if "prev" in c:
        _icon(p, "prev", c["prev"])
        _icon(p, "next", c["next"])
    if "mute" in c:
        _icon(p, "mute" if tile.entry.muted or tile.has_audio is False else "vol", c["mute"])
    if "volume" in c:
        # Muted: the level it comes back at, greyed.
        _slider(p, c["volume"].adjusted(4, 0, -4, 0), min(tile.entry.volume, 1.0),
                MUTED if tile.entry.muted else ACCENT_COLOR)
    if "mode" in c:
        mode = tile.end_action if tile.end_action in MODES else LOOP
        r = c["mode"]
        if bars.mode_label:
            _icon(p, mode, QRectF(r.left() + 2, r.top(), BTN - 4, BTN))
            p.setPen(TEXT)
            p.drawText(QRectF(r.left() + BTN - 2, r.top(), r.width() - BTN, r.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, MODE_LABELS[mode])
        else:
            _icon(p, mode, r)
    if "seek" in c and kind == VIDEO:
        pos, dur = tile.progress()
        _slider(p, c["seek"], pos / dur if dur > 0 else 0.0, QColor(255, 255, 255),
                thick=hot == "seek")
        if bars.times:
            p.setPen(MUTED)
            p.drawText(bars.times[0], Qt.AlignVCenter | Qt.AlignRight, _fmt(pos))
            p.drawText(bars.times[1], Qt.AlignVCenter | Qt.AlignLeft, _fmt(dur))
    if bars.title is not None:
        _title(p, bars.title, tile.title, facts)
    if "focus" in c:
        _icon(p, "unfocus" if focused else "focus", c["focus"])
        _icon(p, "close", c["close"])
    p.restore()


def _title(p: QPainter, r: QRectF, name: str, facts: str):
    fm = p.fontMetrics()
    bold = QFont(p.font())
    bold.setWeight(QFont.DemiBold)
    p.setFont(bold)
    bfm = p.fontMetrics()
    name_w = min(bfm.horizontalAdvance(name), r.width())
    p.setPen(TEXT)
    p.drawText(QRectF(r.left(), r.top(), name_w + 1, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
               bfm.elidedText(name, Qt.ElideMiddle, int(r.width())))
    p.setFont(_plain(bold))
    rest = r.width() - name_w - 10
    if facts and rest > 30:
        p.setPen(MUTED)
        p.drawText(QRectF(r.left() + name_w + 10, r.top(), rest, r.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(facts, Qt.ElideRight, int(rest)))


def _plain(font: QFont) -> QFont:
    f = QFont(font)
    f.setWeight(QFont.Normal)
    return f


def _slider(p: QPainter, r: QRectF, fraction: float, fill: QColor, thick=False):
    h = 5.0 if thick else 3.0
    track = QRectF(r.left(), r.center().y() - h / 2, r.width(), h)
    p.setPen(Qt.NoPen)
    p.setBrush(TRACK)
    p.drawRoundedRect(track, h / 2, h / 2)
    p.setBrush(fill)
    p.drawRoundedRect(QRectF(track.left(), track.top(), track.width() * fraction, h), h / 2, h / 2)


def _icon(p: QPainter, name: str, box: QRectF):
    """A 16 px icon centred in ``box`` (shapes after the mockup's icon set)."""
    s = 16.0 / 24.0
    ox = box.center().x() - 8
    oy = box.center().y() - 8

    def pt(x, y):
        return QPointF(ox + x * s, oy + y * s)

    def poly(*xy):
        path = QPainterPath(pt(*xy[0]))
        for q in xy[1:]:
            path.lineTo(pt(*q))
        path.closeSubpath()
        return path

    def line(path, *xy):
        path.moveTo(pt(*xy[0]))
        for q in xy[1:]:
            path.lineTo(pt(*q))

    fill = QColor(TEXT)
    pen = QPen(TEXT, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.save()
    if name == "play":
        p.fillPath(poly((8, 5), (8, 19), (19, 12)), fill)
    elif name == "pause":
        p.fillRect(QRectF(pt(7, 5), pt(10.5, 19)), fill)
        p.fillRect(QRectF(pt(13.5, 5), pt(17, 19)), fill)
    elif name in ("next", NEXT):
        p.fillPath(poly((5, 5), (14, 12), (5, 19)), fill)
        p.setPen(pen)
        p.drawLine(pt(18, 5), pt(18, 19))
    elif name == "prev":
        p.fillPath(poly((19, 5), (10, 12), (19, 19)), fill)
        p.setPen(pen)
        p.drawLine(pt(6, 5), pt(6, 19))
    elif name in ("vol", "mute"):
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(poly((4, 9), (4, 15), (8, 15), (13, 19), (13, 5), (8, 9)))
        path = QPainterPath()
        if name == "vol":
            path.moveTo(pt(16.5, 9))
            path.quadTo(pt(19, 12), pt(16.5, 15))
        else:
            line(path, (17, 9.5), (21, 14.5))
            line(path, (21, 9.5), (17, 14.5))
        p.drawPath(path)
    elif name == LOOP:
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        line(path, (17, 2.5), (20, 5.5), (17, 8.5))
        path.moveTo(pt(4, 11))
        path.lineTo(pt(4, 9.5))
        path.quadTo(pt(4, 5.5), pt(8, 5.5))
        path.lineTo(pt(20, 5.5))
        line(path, (7, 21.5), (4, 18.5), (7, 15.5))
        path.moveTo(pt(20, 13))
        path.lineTo(pt(20, 14.5))
        path.quadTo(pt(20, 18.5), pt(16, 18.5))
        path.lineTo(pt(4, 18.5))
        p.drawPath(path)
    elif name == STOP:
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(pt(6.5, 6.5), pt(17.5, 17.5)), 1.5 * s, 1.5 * s)
    elif name == "close":
        p.setPen(pen)
        p.drawLine(pt(6, 6), pt(18, 18))
        p.drawLine(pt(18, 6), pt(6, 18))
    elif name in ("focus", "unfocus"):
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        if name == "focus":  # corners pointing out
            for xy in (((4, 9), (4, 4), (9, 4)), ((20, 9), (20, 4), (15, 4)),
                       ((4, 15), (4, 20), (9, 20)), ((20, 15), (20, 20), (15, 20))):
                line(path, *xy)
        else:  # corners pointing in
            for xy in (((4, 9), (9, 9), (9, 4)), ((20, 9), (15, 9), (15, 4)),
                       ((4, 15), (9, 15), (9, 20)), ((20, 15), (15, 15), (15, 20))):
                line(path, *xy)
        p.drawPath(path)
    p.restore()


def tip_for(name: str | None, tile, focused: bool) -> str:
    if name is None:
        return ""
    if name == "mode":
        return MODE_TIPS.get(tile.end_action, MODE_TIPS[LOOP])
    if name == "focus":
        return TIPS["unfocus" if focused else "focus"]
    if name == "play" and tile.entry.kind == GIF:
        return "Play or pause the GIF (Space)"
    return TIPS.get(name, "")
