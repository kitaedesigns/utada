"""The video wall: one OpenGL widget that draws every tile.

All mpv players render into framebuffers that belong to this widget's single
GL context, and the wall is composed with one blit per tile. That avoids
GridPlayer's design of one native window and one GL context per video.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetricsF, QImage, QOpenGLContext,
                           QPainter, QPen)
from PySide6.QtOpenGL import QOpenGLTextureBlitter
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication, QToolTip

from . import hoverbar
from .audio import MasterAudio
from .config import Config
from .layout import (LayoutResult, Rect, fixed_grid, grid_layout, justified_columns,
                     justified_rows, puzzle)
from .playlist import (GIF, IMAGE, VIDEO, Entry, folder_media, natural_key, next_in_folder,
                       siblings, step_in_folder)
from .render import Fence, RenderPool, sync_functions
from .options import NEXT, RANDOM
from .tile import DecoderPolicy, Tile

log = logging.getLogger(__name__)

GL_COLOR_BUFFER_BIT = 0x4000

QUICK_BUDGET_S = 0.12  # first puzzle layout, computed on the UI thread
REFINE_PASSES = 4  # background passes allowed to finish a large equal-area search
ANIMATION_S = 0.28  # tiles glide to new places when the layout changes
LAYOUT_CACHE_SIZE = 32
SIZE_STEPS = (0.35, 0.5, 0.71, 1.0, 1.41, 2.0, 2.83, 4.0)  # tile area multipliers (√2 apart)
SIZE_WAIT_S = 2.0  # how long new videos may hold the layout while reporting their size
DRAG_THRESHOLD_PX = 12
MAX_TILES = 6  # the wall never holds more (decided 2026-11-20, see PROGRESS.md)
ACCENT = QColor(76, 141, 255)  # the plan's single blue accent (#4C8DFF)


class Canvas(QOpenGLWidget):
    tiles_changed = Signal()
    message = Signal(str)
    _layout_done = Signal(int, object)

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.cfg = config
        self.policy = self._make_policy()
        self.tiles: list[Tile] = []
        self.rects: list[Rect] = []
        self._layout_tiles: list[Tile] = []
        self.layout_info: LayoutResult | None = None
        self.solo: Tile | None = None
        self.hovered: Tile | None = None
        self.last_hovered: Tile | None = None  # stays when the mouse leaves the wall
        self.show_hud = False
        self._seed = 0
        self._layout_generation = 0
        self._frame_times: list[float] = []
        self._press: tuple[QPointF, Tile] | None = None
        self._dragging = False
        self.pool: RenderPool | None = None  # created once the GL context exists
        self._blitter: QOpenGLTextureBlitter | None = None
        self._unassigned: list[Tile] = []
        # Master volume and mute (plan 2.5), shared by every tile.
        self.master = MasterAudio(config.master_volume, config.master_muted,
                                  config.solo_audio, self)
        self.master.changed.connect(self._apply_master)
        self.tiles_changed.connect(self._sync_solo_audio)
        self._previous_rects: dict[int, Rect] = {}  # tile id -> rect before the change
        self._layout_cache: dict = {}  # finished layouts by videos/window/settings
        self._shown_size = (0, 0)  # canvas size the current layout was made for
        self._refine_token = 0  # bumped per background search; older ones stop
        self._overlay_image: QImage | None = None  # cached static overlays
        self._overlay_key = None
        self._wheel_key = None  # (tile, action) the wheel deltas below belong to
        self._wheel_accum = 0
        self._wheel_time = 0.0
        self._animation_start = 0.0
        # While files are dragged over the wall: (message, tile that a drop replaces).
        self.drop_hint: tuple[str, Tile | None] | None = None
        # Waiting for a click on the tile to replace: (message, callback(tile)).
        self.pick: tuple[str, object] | None = None
        self._pick_done_at = 0.0

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._relayout_timer = QTimer(self, singleShot=True, interval=120)
        self._relayout_timer.timeout.connect(self._relayout_now)
        self._layout_done.connect(self._apply_layout)

        # Progress bars and the stats overlay need repainting even when videos are
        # paused; the timer only runs while one of them is on screen.
        self._overlay_timer = QTimer(self, interval=250)
        self._overlay_timer.timeout.connect(self.update)

        self._cursor_timer = QTimer(self, singleShot=True)
        self._cursor_timer.timeout.connect(self._hide_cursor)

        # Hover controls (plan 2.4): one tile's bars at a time, faded in and out.
        self._bar_tile: Tile | None = None
        self._bar_opacity = 0.0
        self._bar_fade: tuple[float, float, float] = (0.0, 0.0, 0.0)  # from, to, start time
        self._bar_hot: str | None = None  # control under the mouse
        self._bar_drag: tuple[str, Tile] | None = None  # ("seek" | "volume", tile) while dragging
        self._bar_idle = QTimer(self, singleShot=True, interval=hoverbar.IDLE_MS)
        self._bar_idle.timeout.connect(self._bar_idle_timeout)
        self._bar_timer = QTimer(self, interval=16)  # runs only while fading
        self._bar_timer.timeout.connect(self._bar_step)

    def _make_policy(self) -> DecoderPolicy:
        c = self.cfg
        return DecoderPolicy(c.decoder_mode, c.gpu_budget_mpx, c.max_gpu_tiles,
                             c.auto_threshold_mpx, c.hwdec_api)

    # --- tile management ----------------------------------------------------

    def add_entries(self, entries: list[Entry]):
        """Add tiles for local files that exist, never more than MAX_TILES in all.

        MainWindow.load filters and explains first; this is the last guard.
        """
        added = 0
        for entry in entries:
            # Web addresses are not played: the app is local-only (plan rule 7).
            if "://" in entry.path or not os.path.isfile(entry.path):
                continue
            if len(self.tiles) >= MAX_TILES:
                break
            self._add_tile(entry)
            added += 1
        missing = len(entries) - added
        if missing:
            self.message.emit(f"Skipped {missing} file{'s' * (missing > 1)}")
        self.schedule_relayout()
        self.tiles_changed.emit()

    def _add_tile(self, entry: Entry) -> Tile:
        tile = Tile(entry, self.policy, self.cfg.end_action, self.cfg.scaling, self,
                    background=self.cfg.background, checker=self.cfg.transparency == "checker",
                    crop=self.cfg.max_crop > 0, master=self.master)
        tile.aspect_changed.connect(lambda t=tile: self._on_aspect(t))
        tile.failed.connect(self.update)
        tile.reached_end.connect(lambda t=tile: self._on_reached_end(t))
        if self.pool is not None:
            self.pool.add(tile)
        else:
            self._unassigned.append(tile)
        self.tiles.append(tile)
        return tile

    @property
    def current(self) -> Tile | None:
        """The tile keyboard commands act on (plan 2.3), in this order: the one
        under the mouse; the focused one; the one last under the mouse; the
        only one. (Selected tiles join this list with multi-select in 2.10.)"""
        for tile in (self.hovered, self.solo, self.last_hovered):
            if tile is not None and tile in self.tiles:
                return tile
        return self.tiles[0] if len(self.tiles) == 1 else None

    @property
    def room(self) -> int:
        """How many more tiles fit on the wall."""
        return max(0, MAX_TILES - len(self.tiles))

    def replace_tile(self, tile: Tile, path: str):
        """Show another file in an existing tile, reusing its player."""
        if tile not in self.tiles:
            return
        tile.replace(path)
        self.schedule_relayout()
        self.tiles_changed.emit()

    # --- choosing a tile with a click ----------------------------------------

    def begin_pick(self, text: str, on_pick):
        """Wait for a click on a tile, then call ``on_pick(tile)``. Esc cancels."""
        self.pick = (text, on_pick)
        self._sync_overlay_timer()
        self.update()

    def cancel_pick(self) -> bool:
        """End a pending pick; True if there was one."""
        if self.pick is None:
            return False
        self.pick = None
        self.update()
        return True

    def set_drop_hint(self, hint: tuple[str, Tile | None] | None):
        if hint != self.drop_hint:
            self.drop_hint = hint
            self.update()

    def _destroy_tile(self, tile: Tile):
        tile.closed = True  # from here on, mpv's late reports are ignored
        if self.pool is not None:
            self.pool.remove(tile)  # waits until its GL objects are freed
        if tile in self._unassigned:
            self._unassigned.remove(tile)
        tile.close()
        # The canvas is the tile's Qt parent, which would keep it (and its
        # player wrapper) alive forever; detach and delete it.
        for signal in (tile.aspect_changed, tile.failed, tile.reached_end):
            signal.disconnect()
        tile.setParent(None)
        tile.deleteLater()
        if self.hovered is tile:
            self.hovered = None
        if self.last_hovered is tile:
            self.last_hovered = None  # don't keep a closed player alive
        if self._bar_tile is tile:
            self._bar_tile, self._bar_opacity, self._bar_hot = None, 0.0, None
            self._bar_timer.stop()
            QToolTip.hideText()
        if self._bar_drag is not None and self._bar_drag[1] is tile:
            self._bar_drag = None

    def remove_tile(self, tile: Tile):
        if tile not in self.tiles:
            return
        self.cancel_pick()  # the wall changed under the question
        if self.solo is tile:
            self.set_solo(None)
        self._destroy_tile(tile)
        self.tiles.remove(tile)
        self._forget_from_layout({id(tile)})
        self.hovered = None
        self.schedule_relayout()
        self.tiles_changed.emit()

    def clear(self):
        self.cancel_pick()
        self.set_solo(None)
        for tile in self.tiles:
            self._destroy_tile(tile)
        self._forget_from_layout({id(t) for t in self.tiles})
        self.tiles.clear()
        self.hovered = None
        self.schedule_relayout()
        self.tiles_changed.emit()

    def _forget_from_layout(self, ids: set[int]):
        """Drop closed tiles from what's drawn and clickable until the next layout."""
        # A layout still being computed for the old set would put them back
        # (clickable, and keeping the closed players alive): ignore it.
        self._layout_generation += 1
        self._refine_token += 1
        kept = [(t, r) for t, r in zip(self._layout_tiles, self.rects) if id(t) not in ids]
        self._layout_tiles = [t for t, _ in kept]
        self.rects = [r for _, r in kept]
        self.update()

    def reload_all(self):
        """Recreate every player (needed after decoder or scaling changes)."""
        self.snapshot_positions()
        entries = [t.entry for t in self.tiles]
        self.clear()
        self.policy = self._make_policy()
        if self.pool is not None and len(self.pool.workers) != self.cfg.render_threads:
            self.pool.stop()
            self.pool = RenderPool(self.context(), self.cfg.render_threads)
            self.pool.frames_ready.connect(self._on_frames_ready)
        self.add_entries(entries)

    def entries(self) -> list[Entry]:
        return [t.entry for t in self.tiles]

    def snapshot_positions(self):
        for t in self.tiles:
            t.snapshot_position()

    def _on_aspect(self, tile: Tile):
        if tile not in self.tiles:
            return  # closed while the notification was queued
        tile.apply_decoder_policy()
        self.schedule_relayout()
        # The decoder has started; give it a moment to settle, then say so if
        # hardware decoding didn't work out (plan 2.2: never silently).
        path = tile.entry.path
        QTimer.singleShot(1500, lambda: self._check_decoder(tile, path))

    def _check_decoder(self, tile: Tile, path: str):
        if tile not in self.tiles or tile.entry.path != path or not tile.software_fallback:
            return
        log.warning("%s: hardware decoding not available, decoding on the CPU", tile.title)
        self.message.emit(f"{tile.title}: the GPU can't decode this video; "
                          "it plays with software decoding")

    def apply_look(self):
        """Settings changed: background, transparency and cropping, in every tile."""
        for t in self.tiles:
            t.set_look(self.cfg.background, self.cfg.transparency == "checker",
                       self.cfg.max_crop > 0)

    def _on_reached_end(self, tile: Tile):
        if tile not in self.tiles:
            return
        if tile.end_action == NEXT:
            following = next_in_folder(tile.entry.path)
            if following:
                tile.replace(following)
        elif tile.end_action == RANDOM:
            self.replace_with_random(tile, quiet=True)

    # --- layout -------------------------------------------------------------

    @property
    def layout_seed(self) -> int:
        """Which of the equally good puzzle arrangements is shown (R changes it)."""
        return self._seed

    def set_seed(self, seed: int):
        if seed != self._seed:
            self._seed = seed
            self.schedule_relayout()

    def schedule_relayout(self, reshuffle=False):
        if reshuffle:
            self._seed += 1
        self._relayout_timer.start()

    def _visible_tiles(self) -> list[Tile]:
        return [self.solo] if self.solo else list(self.tiles)

    def _layout_key(self, tiles, w, h):
        c = self.cfg
        return (c.layout_mode if len(tiles) > 1 else "single",
                tuple(id(t) for t in tiles), tuple(round(t.aspect, 3) for t in tiles),
                tuple(t.entry.size_weight for t in tiles), round(w), round(h), c.gap,
                round(c.max_crop, 3), c.size_balance, self._seed, c.fixed_cols, c.fixed_rows)

    def _relayout_now(self):
        tiles = self._visible_tiles()
        # Videos report their size a moment after opening. Wait for them (up to
        # SIZE_WAIT_S) instead of reshuffling once per video while they load.
        now = time.monotonic()
        if any(not t.aspect_known and not t.error and now - t.created < SIZE_WAIT_S
               for t in tiles):
            self._relayout_timer.start(150)
            return
        self._layout_generation += 1
        generation = self._layout_generation
        if not tiles:
            self._apply_layout(generation, (tiles, LayoutResult([], 0, 1, 0), None))
            return
        dpr = self.devicePixelRatioF()
        w, h = self.width() * dpr, self.height() * dpr
        if w < 2 or h < 2:
            return  # minimised or not shown yet; lay out when there's room
        key = self._layout_key(tiles, w, h)
        cached = self._layout_cache.get(key)
        if cached is not None:
            # Same videos, window and settings as a layout we already made
            # (e.g. coming back from focusing one video): reuse it exactly.
            self._apply_layout(generation, (tiles, cached, key))
            return
        aspects = [t.aspect for t in tiles]
        weights = [t.entry.size_weight for t in tiles]
        c = self.cfg
        gap = c.gap * dpr
        mode = "grid" if len(tiles) == 1 else c.layout_mode
        if mode == "grid":
            result = grid_layout(aspects, w, h, gap)
        elif mode == "fixed-grid":
            result = fixed_grid(aspects, w, h, c.fixed_cols, c.fixed_rows, gap)
        elif mode == "rows":
            result = justified_rows(aspects, w, h, gap=gap, max_crop=c.max_crop)
        elif mode == "columns":
            result = justified_columns(aspects, w, h, gap=gap, max_crop=c.max_crop)
        else:
            args = dict(gap=gap, max_crop=c.max_crop, balance=c.size_balance, seed=self._seed,
                        weights=weights)
            same_videos = (set(map(id, tiles)) == set(map(id, self._layout_tiles))
                           and self._shown_size == (round(w), round(h)))
            if not same_videos:
                # New or removed videos, or a new window size: tiles need a place
                # right away, so show a quick layout until the refined one is ready.
                self._apply_layout(generation, (tiles, puzzle(
                    aspects, w, h, time_budget=QUICK_BUDGET_S, quick=True, **args), None))
            # Otherwise (a size or setting change) keep the current layout on
            # screen and glide to the refined one when it's done.

            def emit(result):
                if result is None:
                    return  # superseded by a newer search
                try:
                    self._layout_done.emit(generation, (tiles, result, key))
                except RuntimeError:
                    pass  # window closed while the layout was being refined

            # Only one background search at a time: a newer one (say, while the
            # window is being resized) makes the older stop. Focusing a single
            # video doesn't start a search, so the full layout still finishes
            # and is cached for when you come back.
            self._refine_token += 1
            token = self._refine_token

            def refine():
                # Show the first good result at once; deeper passes may improve it.
                for attempt in range(REFINE_PASSES):
                    result = puzzle(aspects, w, h, time_budget=c.layout_effort, on_progress=emit,
                                    abort=lambda: self._refine_token != token, **args)
                    if result is None:
                        return  # superseded
                    if (result.method == "equal" or c.size_balance == "fill"
                            or attempt == REFINE_PASSES - 1):
                        emit(result)
                        return
                    # The equal-area search ran out of time. Its memo keeps the work
                    # done so far, so another pass finishes it instead of settling
                    # for the uneven fallback layout.

            threading.Thread(target=refine, daemon=True).start()
            return
        self._apply_layout(generation, (tiles, result, key))

    def _apply_layout(self, generation: int, payload):
        tiles, result, key = payload
        if key is not None:
            self._remember_layout(key, result)
        if generation != self._layout_generation:
            return  # a newer layout is on its way
        dpr = self.devicePixelRatioF()
        self._shown_size = (round(self.width() * dpr), round(self.height() * dpr))
        old = {id(t): self._shown_rect(t, r) for t, r in zip(self._layout_tiles, self.rects)}
        self._previous_rects = old
        self._animation_start = time.perf_counter()
        self._layout_tiles = tiles
        self.rects = result.rects
        self.layout_info = result
        self.update()

    def _on_frames_ready(self):
        if self.pool is None:
            return  # shutting down
        self.pool.acknowledge()
        self.update()

    def _remember_layout(self, key, result: LayoutResult):
        self._layout_cache.pop(key, None)
        self._layout_cache[key] = result
        while len(self._layout_cache) > LAYOUT_CACHE_SIZE:
            self._layout_cache.pop(next(iter(self._layout_cache)))

    def _shown_rect(self, tile: Tile, final: Rect) -> Rect:
        """Where the tile is drawn right now (mid-animation if one is running)."""
        start = self._previous_rects.get(id(tile))
        t = (time.perf_counter() - self._animation_start) / ANIMATION_S
        if start is None or t >= 1.0:
            return final
        e = 1 - (1 - t) ** 3  # ease out
        return Rect(start.x + (final.x - start.x) * e, start.y + (final.y - start.y) * e,
                    start.w + (final.w - start.w) * e, start.h + (final.h - start.h) * e)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.schedule_relayout()

    def event(self, event):
        # Moving to a screen with another scale factor changes the size in device
        # pixels without a resize event; lay out again for the new screen.
        if event.type() == QEvent.DevicePixelRatioChange:
            self.schedule_relayout()
        return super().event(event)

    # --- painting -----------------------------------------------------------

    def initializeGL(self):
        self._blitter = QOpenGLTextureBlitter()
        self._blitter.create()
        self.pool = RenderPool(self.context(), self.cfg.render_threads)
        self.pool.frames_ready.connect(self._on_frames_ready)
        for tile in self._unassigned:
            self.pool.add(tile)
        self._unassigned.clear()

    def paintGL(self):
        p = QPainter(self)
        # Raw GL (clear + texture blits) must be bracketed so QPainter's own
        # GL state is saved and restored around it.
        p.beginNativePainting()
        f = QOpenGLContext.currentContext().functions()
        bg = QColor(self.cfg.background)
        f.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), 1.0)
        f.glClear(GL_COLOR_BUFFER_BIT)
        dpr = self.devicePixelRatioF()
        viewport = QRect(0, 0, int(self.width() * dpr), int(self.height() * dpr))
        f.glViewport(0, 0, viewport.width(), viewport.height())
        blitter = self._blitter
        blitter.bind()
        drawn = []  # targets read this frame: their buffers get a fence below
        released = []  # workers' write fences waited for (released after the frame)
        for tile, rect in zip(self._layout_tiles, self.rects):
            if tile not in self.tiles:
                continue
            # Render at the final size; mid-animation the texture is just scaled.
            tile.request_size(int(round(rect.w)), int(round(rect.h)))
            shown = self._shown_rect(tile, rect)
            with tile.target.lock:
                fbo = tile.target.front
                if fbo is None:
                    continue
                written = tile.target.take_write_fence()
                if written is not None:
                    written.gpu_wait()  # the frame must be fully rendered first
                    released.append(written)
                target = QRectF(round(shown.x), round(shown.y), round(shown.w), round(shown.h))
                transform = QOpenGLTextureBlitter.targetTransform(target, viewport)
                blitter.blit(fbo.texture(), transform, QOpenGLTextureBlitter.OriginTopLeft)
                tile.target.reading = True
                drawn.append((tile.target, fbo))
        blitter.release()
        if drawn:
            # Workers must not render into these buffers until the GPU has drawn
            # this frame from them (see render.Fence).
            try:
                fence = Fence(sync_functions(QOpenGLContext.currentContext()))
                f.glFlush()  # other contexts can only wait for a fence once it's flushed
            except Exception:  # no fences: play on (with the old risk of flicker)
                log.exception("could not create an OpenGL fence")
                fence = None
            for target, fbo in drawn:
                with target.lock:
                    old = target.mark_read(fbo, fence)
                if old is not None:
                    old.release()
        for fence in released:
            fence.release()
        p.endNativePainting()
        if time.perf_counter() - self._animation_start < ANIMATION_S:
            self.update()  # keep animating even if no video has a new frame
        self._paint_overlays(p)
        p.end()
        now = time.perf_counter()
        self._frame_times = [t for t in self._frame_times if now - t < 1.0] + [now]

    def tile_fps(self) -> float:
        """Average frames each tile actually showed per second (1 s window)."""
        now = time.perf_counter()
        total = sum(t.frames_drawn for t in self.tiles)
        last_t, last_total = getattr(self, "_fps_mark", (now, total))
        if not hasattr(self, "_fps_mark"):
            self._fps_mark = (now, total)
        if now - last_t < 1.0 or not self.tiles:
            return getattr(self, "_last_fps", 0.0)
        self._fps_mark = (now, total)
        self._last_fps = max(0.0, (total - last_total) / (now - last_t) / len(self.tiles))
        return self._last_fps

    def _logical(self, rect: Rect) -> QRectF:
        dpr = self.devicePixelRatioF()
        return QRectF(rect.x / dpr, rect.y / dpr, rect.w / dpr, rect.h / dpr)

    def _paint_overlays(self, p: QPainter):
        # The tile with the hover controls: its own title and icons step aside.
        bar_tile = self._bar_tile if self._bars_shown() else None
        hovered = bar_tile
        animating = time.perf_counter() - self._animation_start < ANIMATION_S
        if animating:
            # Tiles are moving: draw everything live so overlays stay on them.
            self._paint_static_overlays(p, None)
        else:
            # Titles, pause/mute icons and error tiles rarely change; drawing them
            # for 100 tiles every frame took ~18 ms. Cache them in one image.
            dpr = self.devicePixelRatioF()
            key = (self.width(), self.height(), dpr, self.cfg.titles, id(hovered),
                   tuple((id(t), r, t.paused, t.audible, t.error, t.title, t.entry.kind,
                          t.has_audio, t.frames_drawn == 0)
                         for t, r in zip(self._layout_tiles, self.rects)))
            if key != self._overlay_key:
                image = QImage(int(self.width() * dpr), int(self.height() * dpr),
                               QImage.Format_ARGB32_Premultiplied)
                image.setDevicePixelRatio(dpr)
                image.fill(Qt.transparent)
                cache_painter = QPainter(image)
                self._paint_static_overlays(cache_painter, hovered)
                cache_painter.end()
                self._overlay_image, self._overlay_key = image, key
            p.drawImage(0, 0, self._overlay_image)
        p.setFont(self._overlay_font())
        p.setRenderHint(QPainter.Antialiasing)
        if bar_tile is not None:
            bars = self._bars_for(bar_tile)
            if bars is not None:
                facts = "  ·  ".join(_tile_facts(bar_tile, with_time=False)[1:])
                hoverbar.paint_bars(p, bars, bar_tile, self._bar_opacity, self._bar_hot, facts,
                                    self.solo is bar_tile, self._overlay_font())
        if self._dragging and self._press and self.hovered and self.hovered is not self._press[1]:
            target = self._rect_of(self.hovered)
            if target:
                p.setPen(QPen(QColor(120, 200, 255), 3))
                p.setBrush(QColor(120, 200, 255, 40))
                p.drawRect(target)
        if self.show_hud:
            self._paint_hud(p)
        if self.pick is not None:
            self._paint_pick(p)
        if self.drop_hint is not None:
            self._paint_drop_hint(p)

    def _paint_target(self, p: QPainter, tile: Tile | None, label: str):
        """Outline the tile an action will replace, with ``label`` in its middle."""
        r = self._rect_of(tile) if tile is not None else None
        if r is None:
            return
        p.setPen(QPen(ACCENT, 3))
        p.setBrush(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 60))
        p.drawRect(r.adjusted(1.5, 1.5, -1.5, -1.5))
        self._paint_label(p, r.center(), label)

    def _paint_label(self, p: QPainter, center: QPointF, text: str):
        """A dark rounded box with light text, centred on ``center``."""
        font = QFont(self.font())
        font.setPointSizeF(12)
        p.setFont(font)
        metrics = p.fontMetrics()
        width = min(metrics.horizontalAdvance(text) + 32, self.width() - 24)
        text = metrics.elidedText(text, Qt.ElideMiddle, int(width - 32))
        box = QRectF(center.x() - width / 2, center.y() - 22, width, 44)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(16, 16, 18, 225))
        p.drawRoundedRect(box, 10, 10)
        p.setPen(QColor(240, 240, 240))
        p.drawText(box, Qt.AlignCenter, text)

    def _paint_pick(self, p: QPainter):
        text, _ = self.pick
        self._paint_label(p, QPointF(self.width() / 2, 40), text)
        if self.hovered is not None and self.cursor().shape() != Qt.BlankCursor:
            self._paint_target(p, self.hovered, "Replace")

    def _paint_drop_hint(self, p: QPainter):
        text, target = self.drop_hint
        if target is not None:
            self._paint_target(p, target, text)
            return
        area = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        p.setBrush(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 40))
        pen = QPen(ACCENT, 2, Qt.DashLine)
        p.setPen(pen)
        p.drawRoundedRect(area, 12, 12)
        self._paint_label(p, area.center(), text)

    def _overlay_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSizeF(9.5)
        return font

    def _paint_static_overlays(self, p: QPainter, skip: Tile | None):
        """Per-tile overlays that only change with state (not with time)."""
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(self._overlay_font())
        for tile, rect in zip(self._layout_tiles, self.rects):
            r = self._logical(self._shown_rect(tile, rect))
            if tile.error:
                p.fillRect(r, QColor(40, 10, 10))
                p.setPen(QColor(255, 140, 140))
                p.drawText(r, Qt.AlignCenter | Qt.TextWordWrap, f"{tile.title}\n{tile.error}")
                continue
            if tile.frames_drawn == 0:
                # Opening (a large GIF can take a moment): say so instead of black.
                p.setPen(QColor(150, 150, 150))
                p.drawText(r, Qt.AlignCenter, "Loading…")
            if tile is skip:
                continue  # its hover controls show all of this
            if tile.paused and tile.entry.kind != IMAGE:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 140))
                p.drawRoundedRect(QRectF(r.right() - 30, r.top() + 8, 22, 22), 4, 4)
                p.setBrush(QColor(255, 255, 255, 220))
                p.drawRect(QRectF(r.right() - 25, r.top() + 13, 4, 12))
                p.drawRect(QRectF(r.right() - 17, r.top() + 13, 4, 12))
            if tile.audible and tile.has_audio is not False:
                p.setPen(QColor(120, 220, 255))
                p.drawText(QPointF(r.left() + 8, r.top() + 20), "🔊")
            if self.cfg.titles == "always":
                self._paint_info_bar(p, tile, r, full=False)

    def _paint_info_bar(self, p: QPainter, tile: Tile, r: QRectF, full: bool):
        if self.cfg.titles == "never" and not full:
            return
        bar = QRectF(r.left(), r.bottom() - 26, r.width(), 26)
        p.fillRect(bar, QColor(0, 0, 0, 150))
        text = tile.title
        if full:
            text = "   ".join(_tile_facts(tile))
            if tile.entry.kind != IMAGE:  # stills have no timeline
                pos, dur = tile.progress()
                if dur > 0:
                    p.fillRect(QRectF(bar.left(), bar.bottom() - 3, bar.width() * pos / dur, 3),
                               ACCENT)
        p.setPen(QColor(235, 235, 235))
        elided = p.fontMetrics().elidedText(text, Qt.ElideMiddle, int(bar.width() - 16))
        p.drawText(bar.adjusted(8, 0, -8, -3), Qt.AlignVCenter | Qt.AlignLeft, elided)

    def _paint_hud(self, p: QPainter):
        gpu = sum(1 for t in self.tiles if t.on_gpu)
        info = self.layout_info
        lines = [
            f"{len(self.tiles)} videos   {gpu} on GPU   {len(self.tiles) - gpu} on CPU"
            f"   decoder mode: {self.policy.mode}",
            f"GPU decode budget: {self.policy.used_mpx():.0f} / {self.policy.budget_mpx:.0f} Mpx/s"
            f"   GPU tiles {self.policy.gpu_tiles()} / {self.policy.max_gpu_tiles}",
            f"layout: {self.cfg.layout_mode}"
            + (f"   covered {info.coverage * 100:.1f}%   size spread {info.size_spread:.1f}x"
               f"   max crop {info.max_crop * 100:.0f}%" if info and info.rects else ""),
            f"redraws/s: {len(self._frame_times)}   video frames/s per tile: {self.tile_fps():.1f}",
        ]
        box = QRectF(10, 10, 620, 18 * len(lines) + 12)
        p.fillRect(box, QColor(0, 0, 0, 170))
        p.setPen(QColor(200, 255, 200))
        for i, line in enumerate(lines):
            p.drawText(QPointF(box.left() + 10, box.top() + 20 + 18 * i), line)

    # --- input --------------------------------------------------------------

    def tile_at(self, pos: QPointF) -> Tile | None:
        for tile, rect in zip(self._layout_tiles, self.rects):
            if self._logical(self._shown_rect(tile, rect)).contains(pos):
                return tile
        return None

    def _rect_of(self, tile: Tile) -> QRectF | None:
        for t, rect in zip(self._layout_tiles, self.rects):
            if t is tile:
                return self._logical(self._shown_rect(t, rect))
        return None

    # --- hover controls (plan 2.4) -------------------------------------------

    def _bars_for(self, tile: Tile) -> hoverbar.Bars | None:
        r = self._rect_of(tile)
        if r is None or tile.error:
            return None
        return hoverbar.layout_bars(r, tile.entry.kind, self._time_width())

    def _time_width(self) -> float:
        return QFontMetricsF(self._overlay_font()).horizontalAdvance("00:00") + 4

    def _bars_shown(self) -> bool:
        return (self._bar_tile is not None and self._bar_opacity > 0
                and self.pick is None and self.drop_hint is None and not self._dragging)

    def _live_bars(self, pos: QPointF) -> tuple[Tile, hoverbar.Bars] | None:
        """The shown bars, if ``pos`` is on them (clicks there go to the controls)."""
        if not self._bars_shown() or self._bar_opacity < 0.5:
            return None
        bars = self._bars_for(self._bar_tile)
        if bars is None or not bars.contains(pos):
            return None
        return self._bar_tile, bars

    def show_bar(self, tile: Tile | None):
        """Fade in ``tile``'s controls (or keep them up); they hide after the idle time."""
        if tile is None or tile not in self.tiles:
            return
        if tile is not self._bar_tile:
            self._bar_tile = tile
            self._bar_opacity = 0.0
            self._bar_hot = None
            self.update()
        self._fade_bar(1.0)
        self._bar_idle.start()
        self._sync_overlay_timer()

    def hide_bar(self):
        self._fade_bar(0.0)

    def _fade_bar(self, to: float):
        if self._bar_fade[1] == to and (self._bar_timer.isActive() or self._bar_opacity == to):
            return
        self._bar_fade = (self._bar_opacity, to, time.monotonic())
        self._bar_timer.start()

    def _bar_step(self):
        start, end, t0 = self._bar_fade
        k = min(1.0, (time.monotonic() - t0) / hoverbar.FADE_S)
        self._bar_opacity = start + (end - start) * k
        if k >= 1.0:
            self._bar_timer.stop()
            if self._bar_opacity == 0.0:
                self._bar_hot = None
                QToolTip.hideText()
            self._sync_overlay_timer()
        self.update()

    def _bar_idle_timeout(self):
        # Keep the controls while the mouse rests on them or drags a slider.
        pos = self.mapFromGlobal(QCursor.pos()).toPointF()
        if self._bar_drag is not None or self._live_bars(pos) is not None:
            self._bar_idle.start()
            return
        self.hide_bar()

    def _bar_hover(self, pos: QPointF, global_pos):
        live = self._live_bars(pos)
        hot = live[1].control_at(pos) if live else None
        if hot != self._bar_hot:
            self._bar_hot = hot
            tip = hoverbar.tip_for(hot, live[0], self.solo is live[0]) if live else ""
            if tip:
                QToolTip.showText(global_pos, tip, self)
            else:
                QToolTip.hideText()
            self.update()

    def _bar_press(self, tile: Tile, bars: hoverbar.Bars, pos: QPointF):
        name = bars.control_at(pos)
        if name == "play":
            tile.toggle_pause()
        elif name in ("prev", "next"):
            self.step_file(tile, -1 if name == "prev" else 1)
        elif name == "mute":
            tile.set_muted(not tile.entry.muted)
        elif name == "volume":
            self._bar_drag = ("volume", tile)
            self._bar_slide(pos)
        elif name == "seek":
            self._bar_drag = ("seek", tile)
            self._bar_slide(pos)
        elif name == "mode":
            tile.set_end_action(hoverbar.next_mode(tile.end_action))
            self._bar_hot = None  # show the new mode's tooltip
        elif name == "focus":
            self.set_solo(None if self.solo is tile else tile)
        elif name == "close":
            self.remove_tile(tile)
            return
        self.show_bar(tile)
        self.update()

    def _bar_slide(self, pos: QPointF, done=False):
        what, tile = self._bar_drag
        bars = self._bars_for(tile)
        if bars is None or what not in bars.controls:
            return
        if what == "volume":
            if tile.entry.muted:
                tile.set_muted(False)  # dragging the volume up unmutes, like most players
            tile.set_volume(hoverbar.volume_fraction(bars, pos.x()))
        else:
            _, dur = tile.progress()
            if dur > 0:
                tile.seek_to(hoverbar.seek_fraction(bars, pos.x()) * dur, exact=done)
        self.update()

    # --- mouse --------------------------------------------------------------

    def mouseMoveEvent(self, event):
        self.unsetCursor()
        if self.cfg.hide_cursor_ms > 0:
            self._cursor_timer.start(self.cfg.hide_cursor_ms)
        pos = event.position()
        if self._bar_drag is not None:
            self._bar_slide(pos)
            self._bar_idle.start()
            return
        if self._press and not self._dragging:
            if (pos - self._press[0]).manhattanLength() > DRAG_THRESHOLD_PX:
                self._dragging = True
                QToolTip.hideText()
        if self._dragging:
            self.setCursor(Qt.ClosedHandCursor)
        tile = self.tile_at(pos)
        if tile is not None:
            self.last_hovered = tile
            self.show_bar(tile)
        if tile is not self.hovered:
            self.hovered = tile
            self._sync_solo_audio()
            self.update()
        self._bar_hover(pos, event.globalPosition().toPoint())
        self._sync_overlay_timer()

    def leaveEvent(self, event):
        # The controls stay for the idle time, then fade (plan 2.4).
        self.hovered = None
        if self._bar_hot is not None:
            self._bar_hot = None
            QToolTip.hideText()
        self._sync_overlay_timer()
        self.update()

    def _hide_cursor(self):
        if self._bar_drag is not None:
            return
        self.setCursor(Qt.BlankCursor)
        self.hide_bar()
        self._sync_overlay_timer()
        self.update()

    def set_hud(self, on: bool):
        self.show_hud = on
        self._sync_overlay_timer()
        self.update()

    def _sync_overlay_timer(self):
        # The seek bar moves even when no video draws a new frame (paused, stills).
        needed = self.show_hud or self._bars_shown()
        if needed and not self._overlay_timer.isActive():
            self._overlay_timer.start()
        elif not needed:
            self._overlay_timer.stop()

    def mousePressEvent(self, event):
        pos = event.position()
        tile = self.tile_at(pos)
        if self.pick is None and event.button() == Qt.LeftButton:
            live = self._live_bars(pos)
            if live is not None:
                # The bars are controls: no pause toggle, no tile drag from here.
                self._bar_press(*live, pos)
                return
        if self.pick is not None:
            # Choosing a tile to replace: a left click on a tile answers;
            # nothing else plays, pauses or drags meanwhile.
            if event.button() == Qt.LeftButton and tile is not None:
                _, on_pick = self.pick
                self.pick = None
                self._pick_done_at = time.monotonic()
                on_pick(tile)
                self.update()
            return
        if tile is None:
            return
        if event.button() == Qt.LeftButton:
            self._press = (event.position(), tile)
            self._dragging = False
        elif event.button() == Qt.MiddleButton:
            tile.set_muted(not tile.entry.muted)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._bar_drag is not None:
            self._bar_slide(event.position(), done=True)  # seeks land on the exact frame
            self._bar_drag = None
            return
        if event.button() != Qt.LeftButton or not self._press:
            return
        _, source = self._press
        target = self.tile_at(event.position())
        if self._dragging:
            if target is not None and target is not source:
                self.swap(source, target)
            self.unsetCursor()
        elif target is source:
            source.toggle_pause()
        self._press = None
        self._dragging = False
        self.update()

    def mouseDoubleClickEvent(self, event):
        if self.pick is not None or (time.monotonic() - self._pick_done_at
                                     < QApplication.doubleClickInterval() / 1000):
            return  # the click that chose a tile (or a click while choosing)
        live = self._live_bars(event.position()) if event.button() == Qt.LeftButton else None
        if live is not None:
            # Quick clicks on a control are two clicks (next, next), not a focus:
            # Qt already sent the second click as a press, which acted on it.
            return
        tile = self.tile_at(event.position())
        if tile is not None and event.button() == Qt.LeftButton:
            self._press = None  # don't treat the second click as a pause toggle
            tile.toggle_pause()  # undo the pause from the first click
            self.set_solo(None if self.solo else tile)

    def wheelEvent(self, event):
        tile = self.tile_at(event.position())
        if tile is None:
            return
        self.show_bar(tile)
        mods = event.modifiers()
        action = ("size" if mods & Qt.AltModifier else "zoom" if mods & Qt.ControlModifier
                  else "seek-long" if mods & Qt.ShiftModifier else "seek")
        # Touchpads and high-resolution wheels send many small deltas per notch
        # (often 15 of the usual 120); act once per full notch, not per event.
        delta = event.angleDelta().y() or event.angleDelta().x()  # Alt may turn it sideways
        now = time.monotonic()
        key = (id(tile), action)
        if self._wheel_key != key or now - self._wheel_time > 0.5:
            self._wheel_key, self._wheel_accum = key, 0
        self._wheel_time = now
        self._wheel_accum += delta
        notches = int(self._wheel_accum / 120)
        if not notches:
            return
        self._wheel_accum -= notches * 120
        if action == "size":
            self.resize_tile(tile, notches)
        elif action == "zoom":
            r = self._rect_of(tile)
            pos = event.position()
            tile.zoom_at(0.25 * notches,
                         (pos.x() - r.left()) / r.width(), (pos.y() - r.top()) / r.height())
        else:
            tile.seek((30 if action == "seek-long" else 5) * notches)

    # --- commands -----------------------------------------------------------

    def swap(self, a: Tile, b: Tile):
        """Swap two videos' places in the playlist order and the layout."""
        if self.cfg.layout_mode == "puzzle":
            # The puzzle picks positions itself, so a swap trades slots in the
            # current arrangement. That only looks right for similar shapes.
            if max(a.aspect, b.aspect) / min(a.aspect, b.aspect) > 1.3:
                self.message.emit("The puzzle can only swap videos of a similar shape. "
                                  "For free arrangement use justified rows (2) or a grid (4, 5).")
                return
            lt = self._layout_tiles
            if a in lt and b in lt:
                ja, jb = lt.index(a), lt.index(b)
                lt[ja], lt[jb] = b, a
            ia, ib = self.tiles.index(a), self.tiles.index(b)
            self.tiles[ia], self.tiles[ib] = b, a
            self.update()
            return
        ia, ib = self.tiles.index(a), self.tiles.index(b)
        self.tiles[ia], self.tiles[ib] = b, a
        self.schedule_relayout()

    def resize_tile(self, tile: Tile, steps: int):
        """Make a video bigger (steps > 0) or smaller in puzzle layouts."""
        current = tile.entry.size_weight
        index = min(range(len(SIZE_STEPS)), key=lambda i: abs(SIZE_STEPS[i] - current))
        index = max(0, min(index + steps, len(SIZE_STEPS) - 1))
        self._set_weight(tile, SIZE_STEPS[index])

    def reset_tile_size(self, tile: Tile):
        self._set_weight(tile, 1.0)

    def reset_all_sizes(self):
        for t in self.tiles:
            t.entry.size_weight = 1.0
        self.schedule_relayout()

    def _set_weight(self, tile: Tile, weight: float):
        if tile.entry.size_weight == weight:
            return
        tile.entry.size_weight = weight
        if self.cfg.layout_mode != "puzzle":
            self.message.emit("Video sizes apply in the puzzle layout (key 1)")
            return
        self.message.emit(f"{tile.title}: size ×{weight:g}")
        self.schedule_relayout()

    def shuffle_order(self):
        random.shuffle(self.tiles)
        self.schedule_relayout(reshuffle=True)

    def sort_by_name(self):
        self.tiles.sort(key=lambda t: natural_key(t.title))
        self.schedule_relayout()

    def set_solo(self, tile: Tile | None):
        if tile is self.solo:
            return
        self.solo = tile
        self._sync_solo_audio()
        # Hidden tiles stop decoding while one video is focused.
        self.resume_after_minimize()
        self._relayout_timer.stop()
        self._relayout_now()

    def step_image(self, tile: Tile, step: int):
        """Show the previous (-1) or next (+1) picture (GIF or image) of the folder."""
        self._step(tile, step, {GIF, IMAGE}, "No other GIFs or images in this folder")

    def step_file(self, tile: Tile, step: int):
        """Previous (-1) or next (+1) file of any kind in the tile's folder
        (the hover bar's buttons, PageUp / PageDown; plan 2.4, 2.13)."""
        self._step(tile, step, {VIDEO, GIF, IMAGE}, "No other files in this folder")

    def _step(self, tile: Tile, step: int, kinds: set, nothing: str):
        """Files already shown in other tiles are skipped unless duplicates are allowed."""
        files = folder_media(tile.entry.path, kinds)
        if not self.cfg.allow_duplicates:
            elsewhere = {os.path.normcase(os.path.abspath(t.entry.path))
                         for t in self.tiles if t is not tile}
            files = [f for f in files
                     if os.path.normcase(os.path.abspath(f)) not in elsewhere]
        following = step_in_folder(tile.entry.path, files, step)
        if following is None:
            self.message.emit(nothing)
            return
        self.replace_tile(tile, following)

    def replace_with_random(self, tile: Tile, quiet=False):
        in_use = {t.entry.path for t in self.tiles}
        choices = [p for p in siblings(tile.entry.path) if p not in in_use]
        if not choices:
            if not quiet:
                self.message.emit("No other videos in that folder")
            return
        tile.replace(random.choice(choices))

    def _hidden_paused(self) -> bool:
        """Focus mode with "pause others while focused" (plan 2.3, default on)."""
        return self.solo is not None and self.cfg.pause_others_when_focused

    def set_all_paused(self, paused: bool):
        # While one video is focused, the hidden ones stay paused regardless.
        for t in [self.solo] if self._hidden_paused() else self.tiles:
            t.set_paused(paused)
        self.update()

    def all_paused(self) -> bool:
        if self._hidden_paused():
            return self.solo.paused
        playable = [t for t in self.tiles if t.entry.kind != IMAGE]  # stills don't pause
        return bool(playable) and all(t.paused for t in playable)

    def resume_after_minimize(self):
        """Restore each video's own paused state (hidden ones stay paused in focus
        mode, unless "pause others while focused" is off)."""
        for t in self.tiles:
            hidden = self._hidden_paused() and t is not self.solo
            t.player.pause = True if hidden else t.entry.paused

    def set_all_muted(self, muted: bool):
        for t in self.tiles:
            t.set_muted(muted)
        self.update()

    def mute_all_but(self, tile: Tile):
        """Only ``tile`` is heard (Ctrl+Shift+M, plan 2.5). The master unmutes too,
        or nothing would be heard."""
        for t in self.tiles:
            t.set_muted(t is not tile)
        self.master.set_muted(False)
        self.update()

    def _apply_master(self):
        """The master changed: every tile plays at its own level x the master."""
        for t in self.tiles:
            t.apply_audio()
        self.update()

    def set_solo_audio(self, on: bool):
        self.master.set_solo_audio(on)
        self._sync_solo_audio()

    def _sync_solo_audio(self):
        """Solo audio (a setting, plan 2.5): only the current tile is heard."""
        self.master.set_solo_tile(self.current if self.master.solo_audio else None)

    def restart_all(self):
        for t in self.tiles:
            t.seek_to(0)

    def sync_to(self, source: Tile):
        """Seek every video to the same time as ``source``."""
        pos, _ = source.progress()
        for t in self.tiles:
            if t is not source:
                t.seek_to(pos, exact=True)

    def set_all_speed(self, rate: float):
        for t in self.tiles:
            t.set_speed(rate)

    def set_all_end_action(self, action: str):
        self.cfg.end_action = action
        for t in self.tiles:
            t.set_end_action(action)

    def save_screenshot(self, path: str):
        self.grabFramebuffer().save(path)

    def shutdown(self):
        for tile in self.tiles:
            self._destroy_tile(tile)
        self._forget_from_layout({id(t) for t in self.tiles})
        self.tiles.clear()
        if self.pool is not None:
            self.pool.stop()
            self.pool = None


def _fmt(seconds: float) -> str:
    seconds = int(seconds or 0)
    return f"{seconds // 60}:{seconds % 60:02d}"


KIND_LABELS = {VIDEO: "VIDEO", GIF: "GIF", IMAGE: "IMG"}


def _size_text(n: int | None) -> str:
    if n is None:
        return ""
    for unit, scale in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= scale:
            return f"{n / scale:.1f} {unit}"
    return f"{n} B"


def _tile_facts(tile: Tile, with_time=True) -> list[str]:
    """What the hover bar says about a tile: name, type, size, time, decoder.

    The plan keeps tiles free of permanent badges (2.14): type, resolution and
    the decode path show here, on hover, instead.
    """
    kind = tile.entry.kind
    label = KIND_LABELS[kind]
    if kind == GIF and not tile.entry.path.lower().endswith(".gif"):
        label = "ANIM"  # an animated WebP or AVIF
    facts = [tile.title, label]
    w, h = tile.size
    if w and h:
        facts.append(f"{w}×{h}")
    size = _size_text(tile.file_bytes)
    if size:
        facts.append(size)
    if kind != IMAGE and with_time:
        pos, dur = tile.progress()
        facts.append(f"{_fmt(pos)} / {_fmt(dur)}")
    if kind == VIDEO:
        if tile.software_fallback:
            facts.append("SW decode")
        else:
            facts.append("GPU decode" if tile.on_gpu else "CPU decode")
        if tile.has_audio is False:
            facts.append("no audio")
    return facts
