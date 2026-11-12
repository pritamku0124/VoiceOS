"""The main VoiceOS window: sidebar navigation + top bar + page area.

Structure:
    MainWindow (QMainWindow)
    └── Root
        ├── Sidebar        logo, nav buttons, Settings at the bottom
        └── Content
            ├── TopBar      page title, microphone pill, status pill
            └── QStackedWidget  one page visible at a time (like browser tabs without tabs)

Only the Home page is real so far. The other pages are PlaceholderPage objects
that say which phase will build them, so you can already see the whole app's shape.

MainWindow also owns the VoiceManager and connects its signals to the UI
("signal -> slot" wiring), so neither side needs to know about the other.
"""

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import logging

from ai.intent_recognition import IntentRecognizer
from ai.llm_client import LLMError
from ai.ollama_client import create_llm_client
from core.assistant import Assistant, AssistantResponse
from core.state_manager import AssistantState
from dashboard.dashboard_page import DashboardPage
from dashboard.widgets.listening_indicator import ListeningIndicator
from services.config_service import ConfigService
from utils.constants import APP_NAME, APP_VERSION, CURRENT_PHASE, DATABASE_DIR
from voice.speech_processor import ProcessedSpeech
from voice.text_to_speech import SpeechOutput
from voice.voice_manager import VoiceManager
from voice.wake_word import wake_phrase
from ai.command_classifier import QUIT, STOP_LISTENING, classify_control
from dashboard.widgets.status_widget import StatusPill

logger = logging.getLogger(__name__)
PUSH_TO_TALK_SHORTCUT = "Ctrl+Space"
STOP_SHORTCUT = "Esc"

# (page title, icon glyph, description, phase that builds it). Phase None = already built.
PAGES = [
    ("Home", "", None, None),
    ("Voice Assistant", "", "Live waveform, recognized speech, AI interpretation and pause/resume/stop controls.", 9),
    ("Commands", "", "Searchable categories of everything VoiceOS can do, with example phrases.", 9),
    ("History", "", "Every past command with its result, time and success/failure, searchable.", 9),
    ("Project Assistant", "", "Pick a project folder; VoiceOS explains its code, plans changes and helps debug.", 10),
]
SETTINGS_PAGE = ("Settings", "", "Microphone, speech engine, language, wake word, voice, AI model, privacy and theme.", 9)
ICON_FONT = "Segoe Fluent Icons"


class PlaceholderPage(QWidget):
    """Temporary page for screens that later phases will build."""

    def __init__(self, title: str, description: str, phase: int):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("Greeting")
        layout.addWidget(heading)
        text = QLabel(description)
        text.setObjectName("Subtitle")
        text.setWordWrap(True)
        layout.addWidget(text)
        badge = QLabel(f"Coming in Phase {phase}")
        badge.setObjectName("PhaseBadge")
        layout.addWidget(badge, alignment=Qt.AlignLeft)
        layout.addStretch(1)


class MainWindow(QMainWindow):
    def __init__(
        self,
        config: ConfigService,
        voice_manager: VoiceManager | None = None,
        speech_output: SpeechOutput | None = None,
        assistant: Assistant | None = None,
    ):
        super().__init__()
        self.config = config
        # Tests can pass fakes (fake microphone, silent speaker); normally we create the real ones.
        self.assistant = assistant or self._create_assistant()
        self.speech = speech_output or SpeechOutput.from_config(config, parent=self)
        self.voice = voice_manager or VoiceManager(config, speech_output=self.speech, parent=self)
        if self.voice.speech_output is None:
            self.voice.speech_output = self.speech  # the "never hear yourself" rule needs this link
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(config.get("ui.window_width", 1100), config.get("ui.window_height", 720))
        self.setMinimumSize(820, 560)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        self.stack = QStackedWidget()
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)  # only one nav button can be "checked" (purple) at a time
        self.page_titles: list[str] = []

        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_content(), 1)

        self.nav_group.idClicked.connect(self.show_page)
        self.show_page(0)
        self._connect_voice()

    def _create_assistant(self) -> Assistant:
        try:
            llm = create_llm_client(self.config)
        except LLMError as exc:
            logger.error("AI disabled: %s", exc)
            llm = None
        history = None
        if self.config.get("privacy.save_history"):
            from services.database_service import Database
            from services.history_service import HistoryService

            history = HistoryService(Database(DATABASE_DIR / "voiceos.db"))

        # Real Windows control, unless dry-run mode is on (tests, or trying VoiceOS safely).
        from core.action_manager import build_router, create_controllers
        from safety.confirmation_manager import ConfirmationManager

        self.confirmations = ConfirmationManager(parent=self)
        self.confirmations.confirmation_requested.connect(self.ask_confirmation)
        dry_run = self.config.get("safety.dry_run")
        if dry_run:
            logger.warning("Dry-run mode: commands are understood but NOT executed")
        self.controllers = None if dry_run else create_controllers()
        router = build_router(self.controllers, confirm=self.confirmations.ask,
                              confirm_medium=self.config.get("safety.confirm_destructive_actions"))
        return Assistant(IntentRecognizer(llm), router=router, history=history, parent=self)

    def ask_confirmation(self, request) -> None:
        """GUI thread: show "Are you sure?" for a risky action and pass the answer back to the worker."""
        from PySide6.QtWidgets import QMessageBox

        self.speech.say(request.question)
        box = QMessageBox(QMessageBox.Question, "VoiceOS - please confirm", request.question,
                          QMessageBox.Yes | QMessageBox.No, self)
        box.setDefaultButton(QMessageBox.No)  # pressing Enter by accident = No
        self.raise_()
        self.activateWindow()
        request.answer(box.exec() == QMessageBox.Yes)

    def _connect_voice(self) -> None:
        """Signal -> slot wiring between VoiceManager (logic) and the widgets (display)."""
        self.home_page.mic_clicked.connect(self.voice.toggle_listening)
        self.home_page.command_input.submitted.connect(self.on_typed_command)
        self.assistant.response_ready.connect(self.on_response)
        self.assistant.busy_changed.connect(self.home_page.show_thinking)
        # When the Assistant finishes (even if it failed), the listening session may continue.
        self.assistant.busy_changed.connect(lambda busy: None if busy else self.voice.command_finished())
        self.assistant.warm_up()
        self.voice.state_changed.connect(self.on_voice_state)
        self.voice.level_changed.connect(self.home_page.set_level)
        self.voice.speech_recognized.connect(self.on_speech)
        self.voice.error_occurred.connect(self.home_page.show_error)
        self.voice.mic_active_changed.connect(self.mic_pill.set_mic_active)
        self.voice.control_command.connect(self.on_control_command)
        self.speech.speaking_changed.connect(self.on_speaking_changed)
        self.speech.error_occurred.connect(self.home_page.show_reply)
        # Wake word
        self.voice.wake_word_detected.connect(self.home_page.show_wake_detected)
        self.voice.wake_word_active_changed.connect(self.home_page.set_wake_word_active)
        self.home_page.wake_word_toggled.connect(self.set_wake_word_enabled)
        if self.config.get("wake_word.enabled"):
            self.voice.set_wake_word_enabled(True)
        # Keyboard shortcuts while VoiceOS is focused.
        self.ptt_shortcut = QShortcut(QKeySequence(PUSH_TO_TALK_SHORTCUT), self)
        self.ptt_shortcut.activated.connect(self.voice.toggle_listening)
        self.stop_shortcut = QShortcut(QKeySequence(STOP_SHORTCUT), self)
        self.stop_shortcut.activated.connect(self.stop_everything)
        self.home_page.mic_button.setToolTip(
            f"Tap once to listen continuously ({PUSH_TO_TALK_SHORTCUT}). Tap again or {STOP_SHORTCUT} to pause.")

    def on_voice_state(self, state: AssistantState) -> None:
        self.mic_pill.set_state(state)
        self.status_pill.set_state(state)
        self.home_page.set_state(state)

    def on_speech(self, speech: ProcessedSpeech) -> None:
        self.home_page.show_speech(speech)
        control = classify_control(speech.text) if speech.accepted else None
        if control:  # e.g. single-command mode heard "quit jarvis"
            self.on_control_command(control)
        elif speech.accepted:
            self.assistant.submit(speech.text, mode="voice")
        elif not self.voice.session_active:  # one-shot mode: ask to repeat
            self.home_page.show_reply(speech.reason)
            self.speech.say(speech.reason)
        # In a continuous session unclear audio is only shown: speaking "please repeat" for
        # every bit of background noise would be maddening.

    def on_typed_command(self, text: str) -> None:
        self.home_page.show_typed(text)
        control = classify_control(text)
        if control:
            self.on_control_command(control)
        else:
            self.assistant.submit(text, mode="typed")

    def on_response(self, response: AssistantResponse) -> None:
        self.home_page.show_response(response)
        self.speech.say(response.reply)

    def on_control_command(self, command: str) -> None:
        """'stop listening' -> pause; 'quit jarvis' -> close VoiceOS completely."""
        if command == STOP_LISTENING:
            if self.voice.session_active:
                self.voice.pause()  # (no-op if the session already ended itself)
            self.on_voice_state(AssistantState.PAUSED)
            message = "Okay, I've stopped listening. Tap the microphone when you need me."
            self.home_page.show_reply(message)
            self.speech.say(message)
        elif command == QUIT:
            self.quit_application()

    def quit_application(self) -> None:
        """Say goodbye, then close: closeEvent releases the microphone and stops every worker."""
        self.on_voice_state(AssistantState.SHUTDOWN)
        self.home_page.show_reply("Goodbye!")
        self.voice.shutdown()  # microphone off right now, before the goodbye is spoken
        self.speech.say("Goodbye!")
        deadline = time.monotonic() + 4  # let the goodbye finish, but never hang

        def close_when_quiet():
            if self.speech.is_speaking and time.monotonic() < deadline:
                QTimer.singleShot(100, close_when_quiet)
            else:
                self.close()

        QTimer.singleShot(150, close_when_quiet)

    def on_speaking_changed(self, speaking: bool) -> None:
        if speaking:
            self.on_voice_state(AssistantState.SPEAKING)
        else:  # back to whatever the voice side is doing (Listening, Paused, Ready...)
            self.on_voice_state(self.voice.state)

    def set_wake_word_enabled(self, enabled: bool) -> None:
        """Wake-word card button: switch on/off and remember the choice in config.json."""
        self.voice.set_wake_word_enabled(enabled)
        self.config.set("wake_word.enabled", enabled)
        self.config.save()
        if not enabled:
            self.home_page.set_wake_word_active(False)
            if not self.voice.busy:
                self.on_voice_state(AssistantState.IDLE)

    def stop_everything(self) -> None:
        """Esc: silence VoiceOS and pause listening immediately."""
        self.speech.stop()
        if self.voice.session_active:
            self.voice.pause()
        else:
            self.voice.cancel()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt calls this when the window closes
        """Release everything: microphone, speech, AI worker, window tracker."""
        self.voice.shutdown()  # ends the listening session and closes the microphone
        self.speech.shutdown()
        self.assistant.shutdown()
        if getattr(self, "controllers", None) is not None:
            self.controllers.windows.tracker.stop()
        logger.info("All workers stopped; microphone released")
        super().closeEvent(event)

    # ---- building blocks ---------------------------------------------------------
    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(6)

        logo_row = QHBoxLayout()
        badge = QLabel("")
        badge.setObjectName("LogoBadge")
        badge.setFixedSize(38, 38)
        badge.setAlignment(Qt.AlignCenter)
        name = QLabel(APP_NAME)
        name.setObjectName("LogoText")
        logo_row.addWidget(badge)
        logo_row.addSpacing(6)
        logo_row.addWidget(name, 1)
        layout.addLayout(logo_row)
        layout.addSpacing(18)

        for title, glyph, description, phase in PAGES:
            page = self._make_home_page() if phase is None else PlaceholderPage(title, description, phase)
            layout.addWidget(self._add_page(title, glyph, page))

        layout.addStretch(1)
        title, glyph, description, phase = SETTINGS_PAGE
        layout.addWidget(self._add_page(title, glyph, PlaceholderPage(title, description, phase)))

        version = QLabel(f"v{APP_VERSION} - Phase {CURRENT_PHASE}")
        version.setObjectName("Muted")
        layout.addWidget(version)
        return sidebar

    def _add_page(self, title: str, glyph: str, page: QWidget) -> QPushButton:
        """Register a page in the stack and return its nav button. Button id == page index."""
        index = self.stack.addWidget(page)
        self.page_titles.append(title)
        button = QPushButton(f"{glyph}   {title}")
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        # Rich glyph + text in one button: we set the icon font as the first family and let
        # Windows fall back to Segoe UI for normal letters.
        font = button.font()
        font.setFamilies([ICON_FONT, "Segoe MDL2 Assets", "Segoe UI"])
        button.setFont(font)
        self.nav_group.addButton(button, index)
        return button

    def _make_home_page(self) -> DashboardPage:
        self.home_page = DashboardPage(wake_phrase=wake_phrase(self.config.get("wake_word.model")))
        return self.home_page

    def _build_content(self) -> QFrame:
        content = QFrame()
        content.setObjectName("Content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(28, 18, 22, 4)
        self.title_label = QLabel()
        self.title_label.setObjectName("PageTitle")
        top.addWidget(self.title_label, 1)
        # Always-visible microphone indicator (safety requirement).
        self.mic_pill = ListeningIndicator()
        self.status_pill = StatusPill()  # what the assistant is doing: Listening, Executing, Paused...
        top.addWidget(self.mic_pill)
        top.addSpacing(8)
        top.addWidget(self.status_pill)
        layout.addLayout(top)
        layout.addWidget(self.stack, 1)
        return content

    @staticmethod
    def _pill(text: str, state: str) -> QLabel:
        pill = QLabel(text)
        pill.setObjectName("Pill")
        pill.setProperty("state", state)  # matched by #Pill[state="ok"] in the stylesheet
        return pill

    # ---- behaviour ---------------------------------------------------------------
    def show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav_group.button(index).setChecked(True)
        self.title_label.setText(self.page_titles[index])
