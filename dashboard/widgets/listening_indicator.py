"""Always-visible microphone indicator in the top bar.

Safety rule: you must ALWAYS be able to see when the microphone is open.
This pill follows the REAL microphone (VoiceManager.mic_active_changed), not a guess:
    "● Mic on"  red     - open and listening for your command
    "● Mic on"  purple  - open, but audio is ignored right now (waiting for "Hi Jarvis",
                          or while VoiceOS works on / speaks the reply)
    "Mic off"           - closed (idle or paused)
"""

from PySide6.QtWidgets import QLabel, QWidget

from core.state_manager import AssistantState


class ListeningIndicator(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Pill")
        self.mic_active = False
        self.state = AssistantState.IDLE
        self._refresh()

    def set_mic_active(self, active: bool) -> None:
        self.mic_active = active
        self._refresh()

    def set_state(self, state: AssistantState) -> None:
        self.state = state
        self._refresh()

    def _refresh(self) -> None:
        if self.mic_active:
            text, look = "● Mic on", ("live" if self.state is AssistantState.LISTENING else "wake")
        elif self.state is AssistantState.ERROR:
            text, look = "Mic error", "error"
        else:
            text, look = "Mic off", "off"
        self.setText(text)
        self.setProperty("state", look)
        self.style().unpolish(self)
        self.style().polish(self)
