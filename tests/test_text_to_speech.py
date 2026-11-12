"""Tests for text-to-speech, spoken replies, and the "never hear yourself" rule.

Most tests use FakeEngine/FakePlayer so they run silently and instantly.
Tests marked with the `piper_voice` fixture use the real voice (skipped if not downloaded).
"""

import threading

import numpy as np
import pytest

from services.config_service import ConfigService
from voice.audio_processor import float_to_int16_bytes, resample
from voice.text_to_speech import (
    PiperTTS,
    SpeechOutput,
    SynthesizedAudio,
    TextToSpeechError,
    WindowsTTS,
    resolve_voice_path,
)
from voice.voice_manager import VoiceManager


def deliver_signals():
    """SpeechOutput emits from its own thread, so Qt QUEUES the signals for the main thread.
    Tests have no running event loop, so we deliver the queued signals by hand."""
    from PySide6.QtCore import QCoreApplication

    QCoreApplication.processEvents()


class FakeEngine:
    def __init__(self):
        self.texts = []

    def synthesize(self, text):
        self.texts.append(text)
        return SynthesizedAudio(np.zeros(1600, np.float32), 16000)


class FakePlayer:
    """Plays nothing. With block=True it 'plays' until stop is set, like a long sentence."""

    def __init__(self, block=False):
        self.block = block
        self.started = threading.Event()
        self.played = 0

    def play(self, audio, stop):
        self.played += 1
        self.started.set()
        if self.block:
            stop.wait(5)
        return not stop.is_set()


def make_output(block=False, enabled=True):
    engine, player = FakeEngine(), FakePlayer(block)
    return SpeechOutput(lambda: engine, player=player, enabled=enabled), engine, player


# ---- SpeechOutput (background thread) ---------------------------------------------------
def test_say_speaks_and_reports_start_and_stop(qt_app):
    output, engine, player = make_output()
    events = []
    output.speaking_changed.connect(events.append)
    output.say("Hello there")
    assert output.wait_until_idle(5)
    deliver_signals()
    assert engine.texts == ["Hello there"]
    assert events == [True, False]
    output.shutdown()


def test_stop_interrupts_and_skips_queued_sentences():
    output, engine, player = make_output(block=True)
    output.say("first, a long sentence")
    output.say("second")
    output.say("third")
    assert player.started.wait(5)
    output.stop(wait=True)
    assert not output.is_speaking
    assert engine.texts == ["first, a long sentence"]  # 2nd and 3rd were never synthesized
    output.shutdown()


def test_disabled_output_says_nothing():
    output, engine, _ = make_output(enabled=False)
    output.say("hello")
    assert not output.is_speaking and engine.texts == []
    output.shutdown()


def test_engine_error_is_reported_once(qt_app):
    def broken():
        raise TextToSpeechError("Voice 'x' is not installed.")

    output = SpeechOutput(broken, player=FakePlayer())
    errors = []
    output.error_occurred.connect(errors.append)
    output.say("one")
    output.say("two")
    assert output.wait_until_idle(5)
    deliver_signals()
    assert errors == ["Voice 'x' is not installed."]
    output.shutdown()


# ---- the "never hear yourself" rule ----------------------------------------------------
def test_listening_interrupts_speech_before_opening_microphone(tmp_path, fake_microphone, vosk_recognizer):
    output, _, player = make_output(block=True)
    output.say("a very long reply that the user wants to interrupt")
    assert player.started.wait(5) and output.is_speaking

    class SpyMicrophone(fake_microphone):
        def start(self):
            self.speaking_when_opened = output.is_speaking  # record the state at the critical moment
            super().start()

    mic = SpyMicrophone(b"")
    config = ConfigService(tmp_path / "config.json")
    config.load()
    config.set("voice.no_speech_timeout_seconds", 2)
    manager = VoiceManager(config, microphone_factory=lambda: mic, recognizer=vosk_recognizer, speech_output=output)
    manager.run_once()

    assert mic.speaking_when_opened is False, "microphone opened while VoiceOS was still talking"
    output.shutdown()


# ---- audio helpers ----------------------------------------------------------------------
def test_resample_keeps_duration():
    one_second = np.zeros(22050, np.float32)
    assert len(resample(one_second, 22050, 16000)) == 16000


# ---- real Windows voice (default engine) ------------------------------------------------
def test_windows_voices_are_installed():
    assert WindowsTTS.available_voices(), "Windows has no SAPI voices installed"


def test_windows_speed_setting_changes_duration():
    normal = WindowsTTS(speed=1.0).synthesize("Opening Google Chrome.")
    fast = WindowsTTS(speed=1.5).synthesize("Opening Google Chrome.")
    assert 0.5 < normal.seconds < 5
    assert fast.seconds < normal.seconds * 0.85


def test_unknown_windows_voice_lists_installed_ones():
    with pytest.raises(TextToSpeechError, match="Installed:"):
        WindowsTTS(voice="Nonexistent Voice")


@pytest.mark.parametrize("voice", [None, "Zira"])
def test_round_trip_voiceos_understands_its_own_voice(vosk_recognizer, voice):
    """VoiceOS speaks -> resample 22 kHz to 16 kHz -> VoiceOS listens. Both halves must work."""
    audio = WindowsTTS(voice).synthesize("open notepad")
    pcm = float_to_int16_bytes(resample(audio.samples, audio.sample_rate, 16000))
    assert vosk_recognizer.transcribe(pcm).text == "open notepad"


# ---- optional Piper engine (blocked by Smart App Control on this PC) --------------------
def test_piper_gives_clear_message_when_unavailable(tmp_path):
    """Whether Piper is uninstalled or blocked, the user gets an actionable message, not a traceback."""
    try:
        path = resolve_voice_path("en_US-lessac-medium")
    except TextToSpeechError:
        pytest.skip("Piper voice not downloaded")
    try:
        PiperTTS(path).synthesize("hello")
    except TextToSpeechError as exc:
        assert "Smart App Control" in str(exc) or "pip install piper-tts" in str(exc)
    # If no exception: Piper works on this machine, which is also fine.
