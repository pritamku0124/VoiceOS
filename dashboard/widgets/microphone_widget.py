"""The large round microphone button in the middle of the Home page.

It is a normal QPushButton; its round purple look comes from the #MicButton rule in
dashboard/styles/dark_theme.qss. The glyph is drawn with Windows 11's built-in
"Segoe Fluent Icons" font, so we don't need image files for icons.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget

MIC_GLYPH = ""  # "Microphone" in Segoe Fluent Icons


class MicrophoneButton(QPushButton):
    SIZE = 96

    def __init__(self, parent: QWidget | None = None):
        super().__init__(MIC_GLYPH, parent)
        self.setObjectName("MicButton")
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Tap to speak")
        self.setAccessibleName("Start listening")
