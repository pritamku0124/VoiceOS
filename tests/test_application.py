"""Smoke tests: can the main window be built and navigated without crashing?

"Smoke test" comes from hardware: switch it on and check nothing starts smoking.
These don't check every pixel - they catch broken imports, typos and wiring mistakes.
Windows created here never make sound: TTS is disabled or replaced by a fake.
"""

import pytest

from services.config_service import ConfigService
from utils.platform_utils import is_windows, python_version_ok


@pytest.fixture
def quiet_config(tmp_path):
    config = ConfigService(tmp_path / "config.json")
    config.load()
    config.set("tts.enabled", False)  # no sound
    config.set("ai.enabled", False)  # no calls to a real Ollama
    config.set("privacy.save_history", False)  # don't write database\voiceos.db
    config.set("safety.dry_run", True)  # NEVER open apps or move windows on the real desktop during tests
    return config


def test_platform_is_supported():
    assert is_windows()
    assert python_version_ok()


def test_main_window_builds_and_navigates(qt_app, quiet_config):
    from dashboard.main_window import MainWindow

    window = MainWindow(quiet_config)
    assert window.page_titles[0] == "Home"
    assert "Settings" in window.page_titles
    for index, title in enumerate(window.page_titles):
        window.show_page(index)
        assert window.stack.currentIndex() == index
        assert window.title_label.text() == title
        assert window.nav_group.checkedId() == index


def test_mic_indicator_follows_the_real_microphone(qt_app, quiet_config):
    """Safety: 'Mic on' is shown exactly while the microphone is open - in EVERY state."""
    from core.state_manager import AssistantState
    from dashboard.main_window import MainWindow

    window = MainWindow(quiet_config)
    for mic_open in (True, False):
        window.voice.mic_active_changed.emit(mic_open)  # simulate the microphone opening/closing
        for state in AssistantState:
            window.voice.state_changed.emit(state)
            assert ("Mic on" in window.mic_pill.text()) == mic_open, (mic_open, state)


def test_status_pill_shows_assistant_state(qt_app, quiet_config):
    from core.state_manager import AssistantState
    from dashboard.main_window import MainWindow

    window = MainWindow(quiet_config)
    expected = {AssistantState.LISTENING: "Listening", AssistantState.PROCESSING: "Processing",
                AssistantState.EXECUTING: "Executing", AssistantState.PAUSED: "Paused", AssistantState.IDLE: "Ready"}
    for state, text in expected.items():
        window.voice.state_changed.emit(state)
        assert window.status_pill.text() == text


def test_wake_word_button_saves_choice(qt_app, quiet_config):
    from dashboard.main_window import MainWindow

    window = MainWindow(quiet_config)
    assert window.home_page.wake_toggle.text() == "Turn on"  # default: off
    window.set_wake_word_enabled(False)
    assert quiet_config.get("wake_word.enabled") is False
    assert '"wake_word"' in quiet_config.path.read_text()


def test_recognized_speech_and_reply_are_displayed(qt_app, quiet_config):
    from dashboard.main_window import MainWindow
    from voice.speech_processor import ProcessedSpeech

    from tests.test_wake_word import wait_until

    window = MainWindow(quiet_config)
    window.voice.speech_recognized.emit(ProcessedSpeech("Hello", "hello", 0.97, True))
    assert window.home_page.speech_card.value_label.text() == '"Hello"  (97%)'
    reply = window.home_page.response_card.value_label
    assert wait_until(lambda: reply.text() == "Hello! How can I help you?", timeout=5)


def test_typed_command_shows_interpretation(qt_app, quiet_config):
    from dashboard.main_window import MainWindow
    from tests.test_wake_word import wait_until

    window = MainWindow(quiet_config)
    window.home_page.command_input.edit.setText("open whatsapp and minimize chrome")
    window.home_page.command_input.send.click()
    card = window.home_page.interpretation_card.value_label
    assert wait_until(lambda: "Understood by: built-in rules" in card.text(), timeout=5)
    assert "Open WhatsApp" in card.text() and "Minimize Google Chrome" in card.text()
    assert window.home_page.speech_card.value_label.text() == 'Typed: "open whatsapp and minimize chrome"'


SILENCE = b"\x00" * 32000  # 1 second
_OPEN_WINDOWS = []


@pytest.fixture(autouse=True)
def _close_test_windows():
    """Always stop listening sessions and close windows - even when a test FAILS halfway.
    (A failed test once left a session running, which slowed every later test to a crawl.)"""
    yield
    while _OPEN_WINDOWS:
        window, voice, speech_output = _OPEN_WINDOWS.pop()
        voice.shutdown()
        speech_output.shutdown()
        window.close()


def make_window(quiet_config, audio, fake_microphone, vosk_recognizer):
    from dashboard.main_window import MainWindow
    from tests.test_text_to_speech import make_output
    from voice.voice_manager import VoiceManager

    quiet_config.set("voice.no_speech_timeout_seconds", 2)
    speech_output, engine, _ = make_output()  # silent fake speaker that records what it would say
    mic = fake_microphone(audio)
    voice = VoiceManager(quiet_config, microphone_factory=lambda: mic, recognizer=vosk_recognizer)
    window = MainWindow(quiet_config, voice_manager=voice, speech_output=speech_output)
    _OPEN_WINDOWS.append((window, voice, speech_output))
    return window, voice, engine, speech_output, mic


def test_one_click_handles_several_commands(qt_app, quiet_config, vosk_recognizer, synth_speech, fake_microphone):
    """Your tests 1-3 and 6: ONE click, then several commands, no more clicks, still listening after."""
    from core.state_manager import AssistantState
    from tests.test_wake_word import wait_until

    commands = ["what can you do", "what time is it", "hello there"]
    window, voice, engine, speech_output, mic = make_window(quiet_config, synth_speech(commands[0]) + SILENCE,
                                                            fake_microphone, vosk_recognizer)

    window.home_page.mic_button.click()  # the ONLY click
    for number, command in enumerate(commands[1:], start=1):
        assert wait_until(lambda: len(engine.texts) == number and voice.state is AssistantState.LISTENING,
                          timeout=20), engine.texts
        mic.feed(synth_speech(command) + SILENCE)  # you say the next command - no click
    assert wait_until(lambda: len(engine.texts) == 3, timeout=20), engine.texts
    assert engine.texts[0].startswith("I can open, switch and close apps")
    assert engine.texts[1].startswith("It's ")
    assert engine.texts[2] == "Hello! How can I help you?"
    assert wait_until(lambda: voice.state is AssistantState.LISTENING)  # ready for command no. 4
    assert voice.session_active and mic.start_count == 1  # the microphone was opened only once
    voice.shutdown()
    speech_output.shutdown()


def test_stop_listening_pauses_and_click_resumes(qt_app, quiet_config, vosk_recognizer, synth_speech,
                                                 fake_microphone):
    """Your tests 4 and 5."""
    from core.state_manager import AssistantState
    from tests.test_wake_word import wait_until

    audio = synth_speech("stop listening") + SILENCE
    window, voice, engine, speech_output, mic = make_window(quiet_config, audio, fake_microphone, vosk_recognizer)

    window.home_page.mic_button.click()
    assert wait_until(lambda: window.status_pill.text() == "Paused", timeout=20)
    assert not voice.session_active and not mic.is_active and window.mic_pill.text() == "Mic off"
    # The confirmation is spoken by the speech thread a moment after the pill changes: wait for it.
    assert wait_until(lambda: engine.texts == ["Okay, I've stopped listening. Tap the microphone when you need me."])

    window.home_page.mic_button.click()  # resume
    assert wait_until(lambda: voice.state is AssistantState.LISTENING, timeout=10)
    mic.feed(synth_speech("hello there") + SILENCE)
    assert wait_until(lambda: "Hello! How can I help you?" in engine.texts, timeout=20)
    assert voice.session_active and voice.state in (AssistantState.LISTENING, AssistantState.EXECUTING)
    voice.shutdown()
    speech_output.shutdown()


def test_quit_jarvis_closes_everything(qt_app, quiet_config, vosk_recognizer, synth_speech, fake_microphone):
    """Your test 7: the window closes and the microphone and workers are released."""
    from tests.test_wake_word import wait_until

    audio = synth_speech("quit jarvis") + SILENCE
    window, voice, engine, speech_output, mic = make_window(quiet_config, audio, fake_microphone, vosk_recognizer)
    window.show()
    window.home_page.mic_button.click()
    assert wait_until(lambda: not window.isVisible(), timeout=20), "window did not close"
    assert "Goodbye!" in engine.texts
    assert not mic.is_active and not voice.busy
    assert voice._session is None or not voice._session.is_alive()  # the listening thread has ended


def test_typed_stop_listening_and_quit_are_understood(qt_app, quiet_config):
    from dashboard.main_window import MainWindow

    window = MainWindow(quiet_config)
    calls = []
    window.on_control_command = calls.append
    window.home_page.command_input.submitted.disconnect()
    window.home_page.command_input.submitted.connect(window.on_typed_command)
    window.on_typed_command("Stop listening")
    window.on_typed_command("quit Jarvis")
    assert calls == ["stop_listening", "quit"]
