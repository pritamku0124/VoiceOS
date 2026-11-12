"""Text box for typing a command instead of speaking it.

Handy when it's noisy, when you're somewhere quiet, and for testing: typed text goes
through exactly the same Assistant as speech.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QPushButton, QWidget

SEND_GLYPH = ""  # "Send" in Segoe Fluent Icons


class CommandInput(QFrame):
    submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("CommandInput")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 6, 6)
        layout.setSpacing(8)

        self.edit = QLineEdit()
        self.edit.setObjectName("CommandEdit")
        self.edit.setPlaceholderText('Type a command, e.g. "open notepad and minimize chrome", then press Enter')
        self.edit.setMaxLength(300)
        self.edit.returnPressed.connect(self._submit)  # Enter key

        self.send = QPushButton(SEND_GLYPH)
        self.send.setObjectName("SendButton")
        self.send.setCursor(Qt.PointingHandCursor)
        self.send.setToolTip("Send (Enter)")
        self.send.clicked.connect(self._submit)

        layout.addWidget(self.edit, 1)
        layout.addWidget(self.send)

    def _submit(self) -> None:
        text = self.edit.text().strip()
        if text:
            self.edit.clear()
            self.submitted.emit(text)
