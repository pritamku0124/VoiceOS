"""Speech-to-text: audio bytes in, RecognitionResult out.

Design pattern - "interface + implementation":
    SpeechRecognizer is an abstract base class (ABC) that only says WHAT a recognizer
    can do (transcribe). VoskRecognizer says HOW. The rest of VoiceOS only talks to
    SpeechRecognizer, so we can add a FasterWhisperRecognizer later without changing
    VoiceManager or the UI.
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from utils.exceptions import SpeechRecognitionError

logger = logging.getLogger(__name__)


@dataclass
class RecognitionResult:
    text: str
    confidence: float  # 0..1, average of per-word confidences
    words: list[tuple[str, float]] = field(default_factory=list)
    audio_seconds: float = 0.0
    processing_seconds: float = 0.0
    engine: str = ""


class SpeechRecognizer(ABC):
    @abstractmethod
    def transcribe(self, audio: bytes) -> RecognitionResult:
        """Convert 16 kHz mono int16 audio to text."""


class VoskRecognizer(SpeechRecognizer):
    def __init__(self, model_dir: Path, sample_rate: int = 16000):
        import vosk  # imported here so the rest of VoiceOS loads even if vosk is missing

        vosk.SetLogLevel(-1)  # silence Kaldi's very chatty console output
        started = time.perf_counter()
        try:
            self._model = vosk.Model(str(model_dir))
        except Exception as exc:  # vosk raises a plain Exception on a bad model folder
            raise SpeechRecognitionError(f"Could not load speech model from {model_dir}: {exc}") from exc
        self._vosk = vosk
        self.sample_rate = sample_rate
        logger.info("Loaded Vosk model %s in %.1f s", model_dir.name, time.perf_counter() - started)

    def transcribe(self, audio: bytes) -> RecognitionResult:
        started = time.perf_counter()
        # A KaldiRecognizer holds per-utterance state, so we create a fresh one each time.
        recognizer = self._vosk.KaldiRecognizer(self._model, self.sample_rate)
        recognizer.SetWords(True)  # ask for per-word confidence scores
        recognizer.AcceptWaveform(audio)
        result = json.loads(recognizer.FinalResult())

        words = [(w["word"], float(w.get("conf", 0.0))) for w in result.get("result", [])]
        confidence = sum(c for _, c in words) / len(words) if words else 0.0
        return RecognitionResult(
            text=result.get("text", ""),
            confidence=confidence,
            words=words,
            audio_seconds=len(audio) / 2 / self.sample_rate,  # 2 bytes per int16 sample
            processing_seconds=time.perf_counter() - started,
            engine="vosk",
        )


def create_recognizer(engine: str, model_dir: Path, sample_rate: int = 16000) -> SpeechRecognizer:
    """Factory: build the recognizer named in config.json (voice.engine)."""
    if engine == "vosk":
        return VoskRecognizer(model_dir, sample_rate)
    if engine == "faster-whisper":
        raise SpeechRecognitionError(
            "faster-whisper is planned as an optional engine but is not installed yet. "
            "Set voice.engine to \"vosk\" in config.json."
        )
    raise SpeechRecognitionError(f"Unknown speech engine {engine!r}")
