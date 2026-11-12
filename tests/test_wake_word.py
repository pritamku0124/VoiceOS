"""Tests for wake-word detection ("Hi Jarvis") and the always-on wake loop.

Speech comes from Windows' built-in voice (synth_speech fixture) through FakeMicrophone,
so the REAL detector and the REAL recogniser are exercised without anyone talking.
"""

import time

import pytest

from core.state_manager import AssistantState
from services.config_service import ConfigService
from voice.voice_manager import VoiceManager
from voice.wake_word import WakeWordDetector, WakeWordError, resolve_wake_word_models, strip_wake_phrase

SILENCE_1S = b"\x00" * 32000


# ---- text clean-up ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "heard, expected",
    [
        ("hi jarvis open notepad", "open notepad"),
        ("hey jarvis what time is it", "what time is it"),
        ("jarvis take a screenshot", "take a screenshot"),
        ("hi jarvis", ""),
        ("open notepad", "open notepad"),  # no wake phrase: unchanged
        ("tell jarvis hello", "tell jarvis hello"),  # only removed at the START
    ],
)
def test_strip_wake_phrase(heard, expected):
    assert strip_wake_phrase(heard, "hey_jarvis") == expected


def test_missing_models_explain_how_to_download(tmp_path):
    with pytest.raises(WakeWordError, match="download_wake_word_model.py"):
        resolve_wake_word_models("hey_jarvis", models_dir=tmp_path)


# ---- the detector -----------------------------------------------------------------------
@pytest.fixture(scope="module")
def models():
    try:
        return resolve_wake_word_models("hey_jarvis")
    except WakeWordError as exc:
        pytest.skip(str(exc))


def count_detections(detector, audio: bytes) -> int:
    detector.reset()
    stream = SILENCE_1S + audio + SILENCE_1S
    return sum(detector.process(stream[i : i + 960]) for i in range(0, len(stream), 960))


@pytest.mark.parametrize("phrase", ["hi jarvis", "hii jarvis", "hey jarvis"])
def test_wake_phrase_is_detected_exactly_once(models, synth_speech, phrase):
    detector = WakeWordDetector(models, threshold=0.7, patience=2)
    assert count_detections(detector, synth_speech(phrase)) == 1


@pytest.mark.parametrize("phrase", ["open notepad", "what time is it", "hey travis", "harvest", "hello there"])
def test_other_speech_does_not_trigger(models, synth_speech, phrase):
    detector = WakeWordDetector(models, threshold=0.7, patience=2)
    assert count_detections(detector, synth_speech(phrase)) == 0


def test_silence_never_triggers(models):
    detector = WakeWordDetector(models)
    assert count_detections(detector, SILENCE_1S * 5) == 0


# ---- the wake loop ----------------------------------------------------------------------
def wait_until(condition, timeout=20.0):
    """Process queued Qt signals until condition() is true (signals come from the loop thread)."""
    from PySide6.QtCore import QCoreApplication

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if condition():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def run_loop(qt_app, tmp_path, models, vosk_recognizer):
    """Start a wake loop on the given audio; returns (manager, results, states)."""
    managers = []

    def start(mic, speech_output=None):
        config = ConfigService(tmp_path / "config.json")
        config.load()
        manager = VoiceManager(config, microphone_factory=lambda: mic, recognizer=vosk_recognizer,
                               speech_output=speech_output, wake_detector=WakeWordDetector(models))
        results, states = [], []
        manager.speech_recognized.connect(results.append)
        manager.state_changed.connect(states.append)
        manager.set_wake_word_enabled(True)
        managers.append(manager)
        return manager, results, states

    yield start
    for manager in managers:
        manager.shutdown()


def test_wake_and_command_in_one_breath(run_loop, synth_speech, fake_microphone):
    manager, results, states = run_loop(fake_microphone(synth_speech("hi jarvis, open notepad")))
    assert wait_until(lambda: results), "no command recognised"
    assert results[0].accepted and results[0].text == "Open Notepad"
    assert AssistantState.WAKE_LISTENING in states and AssistantState.LISTENING in states


def test_wake_then_pause_then_command(run_loop, synth_speech, fake_microphone):
    audio = synth_speech("hi jarvis") + SILENCE_1S + SILENCE_1S[:16000] + synth_speech("what time is it")
    manager, results, _ = run_loop(fake_microphone(audio))
    assert wait_until(lambda: results), "no command recognised"
    assert results[0].text == "What time is it"


def test_ordinary_speech_is_ignored_while_waiting(run_loop, synth_speech, fake_microphone):
    manager, results, states = run_loop(fake_microphone(synth_speech("open notepad please")))
    assert wait_until(lambda: AssistantState.WAKE_LISTENING in states)
    time.sleep(1.5)  # plenty of time to (wrongly) react
    assert not wait_until(lambda: results, timeout=0.5)


def test_mic_button_acts_as_manual_wake(run_loop, synth_speech, fake_microphone):
    mic = fake_microphone(b"")
    manager, results, states = run_loop(mic)
    assert wait_until(lambda: AssistantState.WAKE_LISTENING in states)
    manager.toggle_listening()  # like clicking the mic
    assert wait_until(lambda: AssistantState.LISTENING in states), "click did not start command listening"
    mic.feed(synth_speech("take a screenshot") + SILENCE_1S)  # speak AFTER clicking, as a person would
    assert wait_until(lambda: results), "manual trigger did not start command capture"
    assert results[0].text == "Take a screenshot"


def test_voiceos_saying_jarvis_does_not_wake_itself(run_loop, synth_speech, fake_microphone):
    """The mic stays open in a session, but while VoiceOS talks the audio is thrown away."""
    from tests.test_text_to_speech import make_output

    output, _, player = make_output(block=True)
    output.say("hi jarvis is my wake word")
    assert player.started.wait(5)
    mic = fake_microphone(synth_speech("hi jarvis"))  # the mic "hears" VoiceOS saying it
    manager, results, states = run_loop(mic, speech_output=output)
    woke = []
    manager.wake_word_detected.connect(lambda: woke.append(1))
    assert wait_until(lambda: getattr(mic, "frames_read", 0) > 150)  # the audio went past while talking
    output.stop(wait=True)
    time.sleep(1.0)
    assert not wait_until(lambda: woke or AssistantState.LISTENING in states, timeout=1.0)
    output.shutdown()


def test_disabling_wake_word_closes_microphone(run_loop, fake_microphone):
    mic = fake_microphone(b"")
    manager, _, states = run_loop(mic)
    assert wait_until(lambda: mic.is_active)
    manager.set_wake_word_enabled(False)
    assert not mic.is_active and not manager.wake_word_active
