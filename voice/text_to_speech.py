"""Text-to-speech: VoiceOS talks back, offline.

Two interchangeable engines behind one interface (TTSEngine), chosen by config "tts.engine":

    "windows" (default)  WindowsTTS - Windows' built-in SAPI voices (David, Zira).
                         Part of Windows and signed by Microsoft, so it works with
                         Smart App Control switched on.
    "piper"   (optional) PiperTTS - more natural neural voices, BUT Smart App Control
                         blocks Piper's unsigned espeakbridge DLL on this PC. We keep
                         the engine for machines where it is allowed, and never bypass
                         the block.

Three layers, each with one job:

    TTSEngine      text  -> audio samples       (WindowsTTS or PiperTTS)
    AudioPlayer    samples -> speakers           (can be stopped mid-word)
    SpeechOutput   a background thread + queue that runs the two above, so the window
                   never freezes, and tells the UI (Qt signals) when speaking starts/stops.

Why a queue? If two replies arrive quickly, the second waits its turn instead of
both talking over each other. stop() empties the queue and cuts the current sentence.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal

from utils.constants import TTS_VOICES_DIR
from utils.exceptions import VoiceOSError

logger = logging.getLogger(__name__)


class TextToSpeechError(VoiceOSError):
    """The voice could not be loaded or audio could not be played."""


@dataclass
class SynthesizedAudio:
    samples: np.ndarray  # float32 values in [-1, 1], mono
    sample_rate: int

    @property
    def seconds(self) -> float:
        return len(self.samples) / self.sample_rate


# ---- 1. text -> audio -------------------------------------------------------------------
class TTSEngine(ABC):
    @abstractmethod
    def synthesize(self, text: str) -> SynthesizedAudio: ...


def resolve_voice_path(voice: str, voices_dir: Path = TTS_VOICES_DIR) -> Path:
    path = voices_dir / f"{voice}.onnx"
    if not path.exists() or not path.with_suffix(".onnx.json").exists():
        raise TextToSpeechError(
            f"Voice '{voice}' is not installed. Run:  python scripts\\download_tts_voice.py {voice}"
        )
    return path


class WindowsTTS(TTSEngine):
    """Windows SAPI voices through COM (Component Object Model).

    COM is Windows' system for letting programs use each other's objects. comtypes
    (pure Python) lets us create the "SAPI.SpVoice" object and call its methods.

    Important COM rule: an object must be used on the thread that created it, and
    each thread must call CoInitialize() first. SpeechOutput creates this engine
    on its worker thread and only uses it there, which satisfies both.

    Instead of letting SAPI play the sound itself, we make it write into a memory
    stream. That gives us the raw samples, so our AudioPlayer can stop it mid-word,
    exactly like any other engine.
    """

    SAMPLE_RATE = 22050
    FORMAT_22KHZ_16BIT_MONO = 22  # SAPI's SpeechAudioFormatType constant
    FLAG_NOT_XML = 16  # treat text literally (don't interpret "<" as SAPI markup)

    def __init__(self, voice: str | None = None, speed: float = 1.0, volume: float = 1.0):
        import math

        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        self._client = comtypes.client
        started = time.perf_counter()
        try:
            self._voice = comtypes.client.CreateObject("SAPI.SpVoice")
        except OSError as exc:
            raise TextToSpeechError(f"Windows speech engine unavailable: {exc}") from exc
        if voice:
            self._select_voice(voice)
        # SAPI's Rate runs -10..10, where +10 is 3x faster and -10 is 3x slower,
        # so rate = 10 * log base 3 of speed.
        self._voice.Rate = max(-10, min(10, round(10 * math.log(speed, 3))))
        self._voice.Volume = round(volume * 100)  # SAPI uses 0..100
        self.sample_rate = self.SAMPLE_RATE
        logger.info("Loaded Windows voice %r in %.2f s", self.voice_name, time.perf_counter() - started)

    @property
    def voice_name(self) -> str:
        return self._voice.Voice.GetDescription()

    @staticmethod
    def available_voices() -> list[str]:
        import comtypes.client

        voices = comtypes.client.CreateObject("SAPI.SpVoice").GetVoices()
        return [voices.Item(i).GetDescription() for i in range(voices.Count)]

    def _select_voice(self, wanted: str) -> None:
        voices = self._voice.GetVoices()
        names = []
        for i in range(voices.Count):
            name = voices.Item(i).GetDescription()
            names.append(name)
            if wanted.lower() in name.lower():
                self._voice.Voice = voices.Item(i)
                return
        raise TextToSpeechError(f"Windows voice {wanted!r} not found. Installed: {', '.join(names)}")

    def synthesize(self, text: str) -> SynthesizedAudio:
        stream = self._client.CreateObject("SAPI.SpMemoryStream")
        audio_format = self._client.CreateObject("SAPI.SpAudioFormat")
        audio_format.Type = self.FORMAT_22KHZ_16BIT_MONO
        stream.Format = audio_format
        self._voice.AudioOutputStream = stream
        self._voice.Speak(text, self.FLAG_NOT_XML)  # synchronous: returns when the stream is complete
        pcm = np.frombuffer(bytes(stream.GetData()), dtype=np.int16)
        return SynthesizedAudio(pcm.astype(np.float32) / 32768.0, self.SAMPLE_RATE)


class PiperTTS(TTSEngine):
    def __init__(self, model_path: Path, speed: float = 1.0, volume: float = 1.0):
        try:
            from piper import PiperVoice, SynthesisConfig
            from piper import espeakbridge  # noqa: F401 - load the native DLL now, to fail early and clearly
        except ImportError as exc:
            if "Application Control" in str(exc):
                raise TextToSpeechError(
                    "Piper is blocked by Windows Smart App Control (its espeak DLL is unsigned). "
                    'Keep Smart App Control on and set "tts.engine" to "windows" in config.json.'
                ) from exc
            raise TextToSpeechError(f"Piper TTS is not available: {exc}. Install with: pip install piper-tts") from exc

        started = time.perf_counter()
        try:
            self._voice = PiperVoice.load(model_path)
        except Exception as exc:
            raise TextToSpeechError(f"Could not load voice {model_path.name}: {exc}") from exc
        # length_scale = how long each sound lasts. Bigger = slower. So speed 2.0 -> 0.5.
        self._config = SynthesisConfig(length_scale=1.0 / speed, volume=volume)
        self.sample_rate = self._voice.config.sample_rate
        logger.info("Loaded Piper voice %s in %.1f s", model_path.stem, time.perf_counter() - started)

    def synthesize(self, text: str) -> SynthesizedAudio:
        # Piper yields one chunk per sentence; we join them into one array.
        chunks = [c.audio_float_array for c in self._voice.synthesize(text, syn_config=self._config)]
        samples = np.concatenate(chunks).astype(np.float32) if chunks else np.zeros(0, np.float32)
        return SynthesizedAudio(samples, self.sample_rate)


PIPER_DEFAULT_VOICE = "en_US-lessac-medium"


def create_tts_engine(config) -> TTSEngine:
    """Factory: build the engine named in config.json ("tts.engine")."""
    engine, voice = config.get("tts.engine"), config.get("tts.voice")
    speed, volume = config.get("tts.speed"), config.get("tts.volume")
    if engine == "windows":
        return WindowsTTS(voice, speed, volume)
    if engine == "piper":
        return PiperTTS(resolve_voice_path(voice or PIPER_DEFAULT_VOICE), speed, volume)
    raise TextToSpeechError(f"Unknown TTS engine {engine!r}")


# ---- 2. audio -> speakers ---------------------------------------------------------------
class AudioPlayer:
    """Plays audio in small blocks so that stop() takes effect within ~50 ms."""

    BLOCK_SECONDS = 0.05

    def play(self, audio: SynthesizedAudio, stop: threading.Event) -> bool:
        """Blocks until finished. Returns False if interrupted by `stop`."""
        import sounddevice as sd

        block = int(audio.sample_rate * self.BLOCK_SECONDS)
        try:
            with sd.OutputStream(samplerate=audio.sample_rate, channels=1, dtype="float32") as stream:
                for start in range(0, len(audio.samples), block):
                    if stop.is_set():
                        return False
                    stream.write(audio.samples[start : start + block])
        except sd.PortAudioError as exc:
            raise TextToSpeechError(f"Could not play audio: {exc}") from exc
        return True


# ---- 3. background speaking thread ------------------------------------------------------
class SpeechOutput(QObject):
    speaking_changed = Signal(bool)  # True when VoiceOS starts talking, False when it stops
    error_occurred = Signal(str)

    def __init__(self, engine_factory, player: AudioPlayer | None = None, enabled: bool = True,
                 parent: QObject | None = None):
        super().__init__(parent)
        self.enabled = enabled
        self._engine_factory = engine_factory  # called once, lazily, on the worker thread
        self._engine: TTSEngine | None = None
        self._player = player or AudioPlayer()
        # Queue items are (generation, text). stop() bumps the generation, and the worker skips
        # items from older generations. This avoids a race where stop() empties the queue at
        # the same moment the worker takes an item out.
        self._queue: queue.Queue[tuple[int, str] | None] = queue.Queue()
        self._generation = 0
        self._stop = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._error_reported = False
        self._thread = threading.Thread(target=self._worker, name="SpeechOutput", daemon=True)
        self._thread.start()

    @classmethod
    def from_config(cls, config, parent: QObject | None = None) -> SpeechOutput:
        return cls(lambda: create_tts_engine(config), enabled=config.get("tts.enabled"), parent=parent)

    @property
    def is_speaking(self) -> bool:
        return not self._idle.is_set()

    def say(self, text: str) -> None:
        if self.enabled and text.strip():
            self._idle.clear()  # mark busy immediately, so a listen right now waits for us
            self._queue.put((self._generation, text))

    def stop(self, wait: bool = False, timeout: float = 2.0) -> None:
        """Cut speech off now; anything already queued is skipped."""
        self._generation += 1
        self._stop.set()
        if wait:
            self.wait_until_idle(timeout)

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        return self._idle.wait(timeout)

    def shutdown(self) -> None:
        self.stop()
        self._queue.put(None)  # sentinel value: tells the worker loop to exit
        self._thread.join(2.0)

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            generation, text = item
            self._stop.clear()
            if generation != self._generation:  # stop() was called after this was queued
                self._finish_if_queue_empty()
                continue
            self.speaking_changed.emit(True)
            try:
                if self._engine is None:
                    self._engine = self._engine_factory()
                audio = self._engine.synthesize(text)
                if not self._stop.is_set():
                    finished = self._player.play(audio, self._stop)
                    logger.info("Said %r (%.1f s%s)", text, audio.seconds, "" if finished else ", interrupted")
            except VoiceOSError as exc:
                logger.error("Speech output failed: %s", exc)
                if not self._error_reported:  # report once, not on every reply
                    self._error_reported = True
                    self.error_occurred.emit(str(exc))
            except Exception:
                logger.exception("Unexpected error in speech output")
            finally:
                self._finish_if_queue_empty(emit=True)

    def _finish_if_queue_empty(self, emit: bool = False) -> None:
        if self._queue.empty():
            # Emit BEFORE setting idle: anyone waiting in wait_until_idle() then posts their own
            # signals after ours, so the UI receives "stopped speaking" before "listening".
            if emit:
                self.speaking_changed.emit(False)
            self._idle.set()
