"""Global audio (plan 2.5): master volume and mute on top of each tile's own.

What a tile plays at is ``tile volume x master volume``; changing the master
never touches the tiles' own (saved) levels. A tile is silent when it is muted
itself, when the master is muted, or when "solo audio" is on and it is not the
current tile.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)

MPV_MAX = 1.3  # mpv's default volume-max is 130 %
MASTER_STEP = 0.1  # Ctrl+Up / Ctrl+Down


def effective_volume(tile_volume: float, master_volume: float) -> float:
    """The level mpv gets (1.0 = 100 %), clamped to mpv's range."""
    return max(0.0, min(tile_volume * master_volume, MPV_MAX))


class MasterAudio(QObject):
    """The shared master level. Tiles read it; ``changed`` re-applies their audio."""

    changed = Signal()

    def __init__(self, volume=1.0, muted=False, solo_audio=False, parent=None):
        super().__init__(parent)
        self.volume = max(0.0, min(float(volume), 1.0))
        self.muted = bool(muted)
        self.solo_audio = bool(solo_audio)  # only the current tile is heard
        self.solo_tile = None  # that tile (set by the canvas while solo audio is on)

    def silences(self, tile) -> bool:
        """True if the master (not the tile's own mute) keeps ``tile`` silent."""
        return self.muted or (self.solo_audio and tile is not self.solo_tile)

    def set_volume(self, volume: float):
        volume = max(0.0, min(round(volume, 2), 1.0))
        if volume != self.volume:
            self.volume = volume
            log.debug("master volume %d%%", round(volume * 100))
            self.changed.emit()

    def set_muted(self, muted: bool):
        if muted != self.muted:
            self.muted = muted
            log.debug("master %s", "muted" if muted else "unmuted")
            self.changed.emit()

    def set_solo_audio(self, on: bool):
        if on != self.solo_audio:
            self.solo_audio = on
            self.changed.emit()

    def set_solo_tile(self, tile):
        if tile is not self.solo_tile:
            self.solo_tile = tile
            if self.solo_audio:
                self.changed.emit()
