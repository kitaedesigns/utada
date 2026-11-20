"""Log file (for bug reports). The app makes no network calls (build plan rule 7)."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from . import __version__


def log_dir() -> Path:
    """~/.local/share/mosaicplayer on Linux, %LOCALAPPDATA%\\mosaicplayer on Windows."""
    base = QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation)
    return Path(base) / "mosaicplayer"


def setup_logging(debug: bool) -> None:
    """Log to the terminal and to mosaicplayer.log (kept small, last two runs' worth)."""
    terminal = logging.StreamHandler()
    terminal.setLevel(logging.DEBUG if debug else logging.WARNING)
    handlers: list[logging.Handler] = [terminal]
    try:
        folder = log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(
            folder / "mosaicplayer.log", maxBytes=1_000_000, backupCount=1, encoding="utf-8"))
    except OSError:
        pass  # read-only home or similar: terminal only
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("mosaicplayer").info("MosaicPlayer %s on %s", __version__, sys.platform)

    def log_uncaught(kind, value, tb):
        logging.getLogger("mosaicplayer").error("Unexpected error", exc_info=(kind, value, tb))

    sys.excepthook = log_uncaught  # errors in Qt callbacks end up in the log too
