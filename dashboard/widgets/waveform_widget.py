"""Animated audio waveform made of rounded vertical bars.

How it works:
    - A QTimer fires ~30 times per second and calls _tick().
    - _tick() computes a new height for every bar and calls update().
    - update() asks Qt to repaint, which calls paintEvent(), where we draw the bars.

Phase 1: the motion is a gentle "idle" animation (no microphone yet).
Phase 2: set_level() will feed it the real microphone volume, so the bars react to your voice.
"""

import math
import random

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

from utils.constants import Colors


class WaveformWidget(QWidget):
    def __init__(self, bar_count: int = 28, parent: QWidget | None = None):
        super().__init__(parent)
        self.bar_count = bar_count
        self._phase = 0.0
        self._level = 0.15  # 0.0 = silent, 1.0 = loud. Idle uses a small value.
        self._heights = [0.2] * bar_count
        self.setMinimumHeight(48)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # milliseconds -> ~30 frames per second

    def set_level(self, level: float) -> None:
        """Set loudness 0..1 (used from Phase 2 with real microphone input)."""
        self._level = max(0.0, min(1.0, level))

    def _tick(self) -> None:
        self._phase += 0.12
        for i in range(self.bar_count):
            # Two sine waves at different speeds + a little randomness = organic movement.
            wave = math.sin(self._phase + i * 0.45) * 0.5 + math.sin(self._phase * 0.7 + i * 0.9) * 0.3
            target = 0.15 + self._level * (0.55 + 0.45 * wave) + random.uniform(-0.04, 0.04)
            # Ease towards the target instead of jumping, so the motion looks smooth.
            self._heights[i] += (max(0.08, min(1.0, target)) - self._heights[i]) * 0.35
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt's method name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        w, h = self.width(), self.height()
        gap = 4
        bar_w = max(3.0, min(6.0, (w - gap * (self.bar_count - 1)) / self.bar_count))
        total = self.bar_count * bar_w + (self.bar_count - 1) * gap
        x = (w - total) / 2

        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0, QColor(Colors.SECONDARY))
        gradient.setColorAt(1, QColor(Colors.PRIMARY))
        painter.setBrush(gradient)

        for height in self._heights:
            bar_h = max(4.0, height * h)
            painter.drawRoundedRect(QRectF(x, (h - bar_h) / 2, bar_w, bar_h), bar_w / 2, bar_w / 2)
            x += bar_w + gap
