"""Shared pytest fixtures.

conftest.py is discovered automatically by pytest. A *fixture* is a function that
prepares something a test needs; a test receives it just by naming it as a parameter.
"""

import os
import sys
import time
from pathlib import Path

import pytest

# Make "import core", "import utils"... work no matter where pytest is started from.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# "offscreen" lets Qt create windows without showing them - needed for automated tests/CI.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def synth_speech(tmp_path_factory):
    """Returns a function text -> 16 kHz mono int16 audio bytes, spoken by Windows' built-in voice.

    This gives tests REAL speech without needing a microphone or anyone talking.
    Results are cached so each phrase is synthesised only once per test run.
    """
    import subprocess
    import wave

    folder = tmp_path_factory.mktemp("speech")
    cache: dict[str, bytes] = {}

    def speak(text: str) -> bytes:
        if text not in cache:
            wav = folder / f"{len(cache)}.wav"
            script = (
                "Add-Type -AssemblyName System.Speech;"
                "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                "$f=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,"
                "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,"
                "[System.Speech.AudioFormat.AudioChannel]::Mono);"
                f"$s.SetOutputToWaveFile('{wav}',$f);$s.Speak('{text}');$s.Dispose()"
            )
            done = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True)
            if done.returncode != 0 or not wav.exists():
                pytest.skip("Windows speech synthesis is not available on this machine")
            with wave.open(str(wav)) as w:
                cache[text] = w.readframes(w.getnframes())
        return cache[text]

    return speak


@pytest.fixture(scope="session")
def vosk_recognizer():
    """The real Vosk recognizer, or skip the test if the model hasn't been downloaded."""
    from utils.exceptions import SpeechRecognitionError
    from voice.language_detection import resolve_model_dir
    from voice.speech_recognition import VoskRecognizer

    try:
        return VoskRecognizer(resolve_model_dir("en-US"))
    except SpeechRecognitionError as exc:
        pytest.skip(str(exc))


class FakeMicrophone:
    """Plays prepared audio as if it came from a microphone (silence, speech, silence...)."""

    FRAME_BYTES = 960  # 30 ms at 16 kHz, 16-bit

    def __init__(self, audio: bytes, lead_silence_frames: int = 15):
        silence = b"\x00" * self.FRAME_BYTES
        speech = [audio[i : i + self.FRAME_BYTES] for i in range(0, len(audio) - self.FRAME_BYTES + 1, self.FRAME_BYTES)]
        self._frames = [silence] * lead_silence_frames + speech
        self._silence = silence
        self.device_name = "Fake microphone"
        self.is_active = False
        self.start_count = 0

    def start(self):
        self.is_active = True
        self.start_count += 1

    def stop(self):
        self.is_active = False

    def read_frame(self, timeout=0.5):
        assert self.is_active, "read_frame called while the microphone was closed"
        self.frames_read = getattr(self, "frames_read", 0) + 1
        if self._frames:
            return self._frames.pop(0)  # scripted audio: instantly, to keep tests fast
        # Out of script: behave like a REAL mic, which delivers one 30 ms frame per 30 ms.
        # Returning silence instantly made a forgotten session spin at 100% CPU, hogging
        # Python's GIL so every later test crawled (that was the "hang").
        time.sleep(0.03)
        return self._silence

    def discard_pending(self):
        pass  # a fake mic has no real-time queue; scripted frames are read in order

    def feed(self, audio: bytes):
        """'Say' more audio later in a test (a real mic delivers audio over time; this fake
        delivers everything instantly, so later speech must be added at the right moment)."""
        self._frames += [audio[i: i + self.FRAME_BYTES] for i in range(0, len(audio) - self.FRAME_BYTES + 1,
                                                                          self.FRAME_BYTES)]


@pytest.fixture
def fake_microphone():
    return FakeMicrophone


@pytest.fixture(scope="session")
def qt_app():
    """One QApplication for the whole test session (Qt allows only one per process)."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
