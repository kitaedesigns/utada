"""The footer strip under the wall (plan 2.14). So far it holds the master
volume: mute button, slider and level readout (plan 2.5)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QToolTip, QWidget

from . import hoverbar
from .audio import MasterAudio

HEIGHT = 40
PAD = 10
BTN = 28.0
SLIDER_W = 120.0
LABEL = "Master"
BACKGROUND = QColor(22, 22, 24)
EDGE = QColor(255, 255, 255, 20)
WHEEL_STEP = 0.05

TIPS = {
    "mute": "Mute all sound (Ctrl+M)",
    "volume": "Master volume: scales every tile (Ctrl+Up / Ctrl+Down)",
}


class Footer(QWidget):
    def __init__(self, master: MasterAudio, parent=None):
        super().__init__(parent)
        self.master = master
        self.setFixedHeight(HEIGHT)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self._hot: str | None = None
        self._dragging = False
        master.changed.connect(self.update)

    # --- geometry -------------------------------------------------------------

    def _font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(12)
        return font

    def controls(self) -> dict[str, QRectF]:
        """name -> rect: "mute", "volume" (the slider's hit area), "level" (readout)."""
        x = PAD + QFontMetricsF(self._font()).horizontalAdvance(LABEL) + 10
        y = (HEIGHT - BTN) / 2
        mute = QRectF(x, y, BTN, BTN)
        volume = QRectF(mute.right() + 4, y, SLIDER_W, BTN)
        level = QRectF(volume.right() + 6, y, 40, BTN)
        return {"mute": mute, "volume": volume, "level": level}

    def _control_at(self, pos: QPointF) -> str | None:
        for name, r in self.controls().items():
            if name != "level" and r.contains(pos):
                return name
        return None

    def volume_at(self, x: float) -> float:
        r = self.controls()["volume"].adjusted(4, 0, -4, 0)
        return max(0.0, min((x - r.left()) / r.width(), 1.0))

    # --- painting -------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), BACKGROUND)
        p.fillRect(QRectF(0, 0, self.width(), 1), EDGE)
        p.setFont(self._font())
        c = self.controls()
        p.setPen(hoverbar.MUTED)
        p.drawText(QRectF(PAD, 0, c["mute"].left() - PAD, HEIGHT),
                   Qt.AlignVCenter | Qt.AlignLeft, LABEL)
        if self._hot == "mute":
            p.setPen(Qt.NoPen)
            p.setBrush(hoverbar.HOVER_FILL)
            p.drawRoundedRect(c["mute"], 6, 6)
        hoverbar._icon(p, "mute" if self.master.muted else "vol", c["mute"])
        hoverbar._slider(p, c["volume"].adjusted(4, 0, -4, 0), self.master.volume,
                         hoverbar.MUTED if self.master.muted else hoverbar.ACCENT_COLOR)
        p.setPen(hoverbar.MUTED if self.master.muted else hoverbar.TEXT)
        p.drawText(c["level"], Qt.AlignVCenter | Qt.AlignLeft, self.level_text())
        p.end()

    def level_text(self) -> str:
        level = f"{round(self.master.volume * 100)}%"
        return f"{level} (muted)" if self.master.muted else level

    # --- mouse ----------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        name = self._control_at(event.position())
        if name == "mute":
            self.master.set_muted(not self.master.muted)
        elif name == "volume":
            self._dragging = True
            self._slide(event.position().x())

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._dragging:
            self._slide(pos.x())
            return
        hot = self._control_at(pos)
        if hot != self._hot:
            self._hot = hot
            self.update()
            if hot:
                QToolTip.showText(event.globalPosition().toPoint(), TIPS[hot], self)
            else:
                QToolTip.hideText()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._slide(event.position().x())

    def mouseDoubleClickEvent(self, event):
        pass  # Qt already sent a press for the second click; acting again would undo it

    def leaveEvent(self, event):
        if self._hot is not None:
            self._hot = None
            self.update()

    def wheelEvent(self, event):
        if self._control_at(event.position()) is None:
            return
        steps = event.angleDelta().y() / 120
        if steps:
            self.master.set_volume(self.master.volume + steps * WHEEL_STEP)

    def _slide(self, x: float):
        if self.master.muted:
            self.master.set_muted(False)  # dragging the volume unmutes, like the tiles
        self.master.set_volume(self.volume_at(x))
