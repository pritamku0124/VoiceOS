"""The status pill in the top bar: what the assistant is doing right now."""

from PySide6.QtWidgets import QLabel, QWidget

from core.state_manager import AssistantState

# state -> (text, look). Looks are styled in dark_theme.qss (#Pill[state="..."]).
LOOK = {
    AssistantState.IDLE: ("Ready", "ok"),
    AssistantState.LOADING: ("Loading...", "off"),
    AssistantState.WAKE_LISTENING: ('Waiting for "Hi Jarvis"', "off"),
    AssistantState.LISTENING: ("Listening", "ok"),
    AssistantState.PROCESSING: ("Processing", "off"),
    AssistantState.EXECUTING: ("Executing", "off"),
    AssistantState.SPEAKING: ("Speaking", "off"),
    AssistantState.PAUSED: ("Paused", "warn"),
    AssistantState.SHUTDOWN: ("Shutting down", "warn"),
    AssistantState.ERROR: ("Error", "error"),
}


class StatusPill(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Pill")
        self.set_state(AssistantState.IDLE)

    def set_state(self, state: AssistantState) -> None:
        text, look = LOOK[state]
        self.setText(text)
        self.setProperty("state", look)
        self.style().unpolish(self)
        self.style().polish(self)
