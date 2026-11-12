"""Home / Voice Dashboard page - the first screen the user sees.

Layout (top to bottom):
    greeting  ->  hero card (mic button, "Tap to speak", waveform)
              ->  three status cards (wake word, recognized speech, last command)
              ->  "Try saying" suggestions

This page only DISPLAYS things. It never touches the microphone itself: it emits
`mic_clicked`, and MainWindow forwards VoiceManager's signals to set_state(),
set_level(), show_speech() and show_error(). Keeping UI and logic apart means the
voice code can be tested without a window, and the UI without a microphone.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from core.state_manager import AssistantState
from dashboard.widgets.command_input import CommandInput
from dashboard.widgets.microphone_widget import MicrophoneButton
from dashboard.widgets.waveform_widget import WaveformWidget
from voice.speech_processor import ProcessedSpeech

IDLE_WAVE_LEVEL = 0.15
STATE_TEXT = {
    AssistantState.IDLE: "Tap to speak",
    AssistantState.LOADING: "Loading speech models...",
    AssistantState.WAKE_LISTENING: 'Say "{wake}" or tap to speak',  # {wake} is filled in
    AssistantState.LISTENING: "Listening... say a command",
    AssistantState.PROCESSING: "Recognizing...",
    AssistantState.EXECUTING: "Working on it...",
    AssistantState.SPEAKING: "Speaking...  (tap to interrupt)",
    AssistantState.PAUSED: "Paused - tap to resume listening",
    AssistantState.SHUTDOWN: "Goodbye!",
    AssistantState.ERROR: "Something went wrong",
}

SESSION_STATES = {AssistantState.LISTENING, AssistantState.PROCESSING, AssistantState.EXECUTING}
SESSION_HINT = 'Listening continuously. Say "stop listening" to pause, or "quit Jarvis" to close VoiceOS.'

SUGGESTIONS = ["Open WhatsApp", "Minimize this window", "Search YouTube for embedded systems"]
WAVE_GLYPH = ""  # small "volume" glyph from Segoe Fluent Icons


def _label(text: str, object_name: str, align=None) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setWordWrap(True)
    if align is not None:
        label.setAlignment(align)
    return label


class InfoCard(QFrame):
    """Small card showing a caption and a value, e.g. 'Wake word' / 'Off'."""

    def __init__(self, caption: str, value: str):
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        layout.addWidget(_label(caption, "CardLabel"))
        self.value_label = _label(value, "CardValue")
        layout.addWidget(self.value_label)
        # Empty stretchable space at the bottom keeps the text pinned to the top when a
        # neighbouring card (e.g. a long reply) makes the whole row taller.
        layout.addStretch(1)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


class DashboardPage(QWidget):
    # Signals let this page announce events without knowing who listens. MainWindow connects them.
    mic_clicked = Signal()
    wake_word_toggled = Signal(bool)  # user clicked the On/Off button in the wake-word card

    def __init__(self, wake_phrase: str = "Hi Jarvis", parent: QWidget | None = None):
        super().__init__(parent)
        self.wake_phrase = wake_phrase
        self.wake_active = False
        self._wake_just_heard = False
        self._in_session = False
        self._idle_hint = ""

        # A scroll area keeps everything reachable when the window is small.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setObjectName("ScrollBody")
        scroll.setWidget(body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(16)

        layout.addWidget(_label("Hey, how can I help you?", "Greeting"))
        layout.addWidget(_label("Your personal voice assistant is ready.", "Subtitle"))

        # --- Hero card -----------------------------------------------------------
        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 28, 24, 22)
        hero_layout.setSpacing(10)

        self.mic_button = MicrophoneButton()
        self.mic_button.clicked.connect(self._on_mic_clicked)
        hero_layout.addWidget(self.mic_button, alignment=Qt.AlignHCenter)

        self.state_label = _label(STATE_TEXT[AssistantState.IDLE], "TapToSpeak", Qt.AlignHCenter)
        hero_layout.addWidget(self.state_label)
        self.hint_label = _label("", "Muted", Qt.AlignHCenter)
        hero_layout.addWidget(self.hint_label)

        self.waveform = WaveformWidget()
        self.waveform.setFixedWidth(260)
        hero_layout.addWidget(self.waveform, alignment=Qt.AlignHCenter)
        layout.addWidget(hero)

        self.command_input = CommandInput()
        layout.addWidget(self.command_input)

        # --- Status cards ----------------------------------------------------------
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.wake_card = InfoCard("Wake word", "Off")
        self.wake_toggle = QPushButton("Turn on")
        self.wake_toggle.setObjectName("SmallButton")
        self.wake_toggle.setCursor(Qt.PointingHandCursor)
        self.wake_toggle.clicked.connect(lambda: self.wake_word_toggled.emit(not self.wake_active))
        # Insert above the stretch so the button sits under the value text.
        self.wake_card.layout().insertWidget(2, self.wake_toggle, alignment=Qt.AlignLeft)
        self.speech_card = InfoCard("Recognized speech", "-")
        self.response_card = InfoCard("VoiceOS replied", "-")
        for card in (self.wake_card, self.speech_card, self.response_card):
            cards.addWidget(card, 1)
        layout.addLayout(cards)

        # What the assistant decided to do - shows that AI output is a list of allowlisted actions.
        self.interpretation_card = InfoCard("Understood as", "-")
        self.interpretation_card.value_label.setObjectName("Interpretation")
        layout.addWidget(self.interpretation_card)

        # --- Suggestions -----------------------------------------------------------
        layout.addSpacing(4)
        layout.addWidget(_label("Try saying", "SectionTitle"))
        for text in SUGGESTIONS:
            layout.addWidget(self._suggestion_row(text))
        layout.addStretch(1)
        self.set_wake_word_active(False)

    def set_wake_word_active(self, active: bool) -> None:
        self.wake_active = active
        self.wake_card.set_value(f'On - say "{self.wake_phrase}"' if active else "Off")
        self.wake_toggle.setText("Turn off" if active else "Turn on")
        self._idle_hint = (
            f'Tap once, then give as many commands as you like. Or say "{self.wake_phrase}".'
            if active else "Tap once, then give as many commands as you like."
        )
        if not self._in_session:
            self.hint_label.setText(self._idle_hint)

    def _suggestion_row(self, text: str) -> QFrame:
        row = QFrame()
        row.setObjectName("Suggestion")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(16, 12, 16, 12)
        row_layout.setSpacing(12)
        row_layout.addWidget(_label(WAVE_GLYPH, "SuggestionIcon"))
        row_layout.addWidget(_label(f'"{text}"', "SuggestionText"), 1)
        return row

    def _on_mic_clicked(self) -> None:
        self.mic_clicked.emit()

    # ---- slots: called (via MainWindow) when VoiceManager emits signals --------------
    def set_state(self, state: AssistantState) -> None:
        self.state_label.setText(STATE_TEXT[state].format(wake=self.wake_phrase))
        # Red button for the whole listening session (the microphone stays on throughout).
        self._in_session = state in SESSION_STATES
        listening = self._in_session
        self.hint_label.setText(SESSION_HINT if self._in_session else self._idle_hint)
        self.mic_button.setToolTip("Tap to pause listening" if listening else "Tap to start listening")
        # A dynamic property drives the QSS rule #MicButton[listening="true"].
        # After changing it, Qt needs unpolish/polish to re-apply the stylesheet.
        self.mic_button.setProperty("listening", listening)
        self.mic_button.style().unpolish(self.mic_button)
        self.mic_button.style().polish(self.mic_button)
        # Keep 'Heard "Hi Jarvis" - listening...' visible while the command is captured.
        if state is AssistantState.LOADING or (state is AssistantState.LISTENING and not self._wake_just_heard):
            self.speech_card.set_value("...")
        if state is not AssistantState.LISTENING:
            self._wake_just_heard = False
        if state in (AssistantState.IDLE, AssistantState.WAKE_LISTENING):
            self.waveform.set_level(IDLE_WAVE_LEVEL)

    def set_level(self, level: float) -> None:
        self.waveform.set_level(max(IDLE_WAVE_LEVEL, level))

    def show_wake_detected(self) -> None:
        self._wake_just_heard = True
        self.speech_card.set_value(f'Heard "{self.wake_phrase}" - listening...')

    def show_speech(self, speech: ProcessedSpeech) -> None:
        if speech.accepted:
            self.speech_card.set_value(f'"{speech.text}"  ({speech.confidence:.0%})')
        else:
            self.speech_card.set_value(speech.reason)

    def show_error(self, message: str) -> None:
        self.speech_card.set_value(message)

    def show_reply(self, text: str) -> None:
        self.response_card.set_value(text)

    def show_typed(self, text: str) -> None:
        self.speech_card.set_value(f'Typed: "{text}"')

    def show_thinking(self, busy: bool) -> None:
        if busy:
            self.response_card.set_value("Thinking...")

    def show_response(self, response) -> None:
        """response: core.assistant.AssistantResponse"""
        self.show_reply(response.reply)
        source = {"rules": "built-in rules", "ai": "AI model", "none": "-"}[response.recognition.source]
        lines = [f"• {line}" for line in response.interpretation_lines()]
        lines += [f"✕ Rejected: {error}" for error in response.recognition.errors]
        if not lines:
            lines = ["No action (answered or not understood)"]
        self.interpretation_card.set_value("\n".join(lines) + f"\n\nUnderstood by: {source}")
