"""Wake-word detection: notice "Hey Jarvis" / "Hi Jarvis" in a continuous audio stream.

How it works (a pipeline of three small neural networks, run with onnxruntime):

    every 80 ms of audio (1280 samples at 16 kHz)
      │
      ├─► melspectrogram.onnx  -> a few rows of a "sound picture": 32 frequency bands per 10 ms
      │                           (kept in a rolling buffer of recent rows)
      ├─► embedding_model.onnx -> looks at the last 76 rows (~0.8 s) and summarises them as
      │                           96 numbers (kept in a rolling buffer of recent embeddings)
      └─► hey_jarvis.onnx      -> looks at the last 16 embeddings (~1.3 s) and outputs a score
                                  from 0.0 ("definitely not") to 1.0 ("definitely 'hey jarvis'")

The first two models are generic ("what does this sound like?"); only the last one is
specific to the phrase. That's why adding another wake word only costs ~1 MB.

This is a compact re-implementation of the inference part of openWakeWord
(Apache-2.0, https://github.com/dscripka/openWakeWord). We don't install the
openwakeword package itself, because importing it also imports scipy and scikit-learn
(training-only libraries, ~50 MB of extra native code for Smart App Control to vet).

False alarms are controlled by two settings:
    threshold  how high the score must be                  (higher = fewer false alarms)
    patience   how many 80 ms chunks IN A ROW must pass it  (higher = fewer false alarms,
                                                             slightly slower to react)
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from utils.constants import WAKE_WORD_MODELS_DIR
from utils.exceptions import VoiceOSError

logger = logging.getLogger(__name__)

CHUNK = 1280  # 80 ms at 16 kHz - the step size the models were trained with
MEL_CONTEXT = 160 * 3  # extra past samples so mel frames line up across chunk borders
MEL_WINDOW = 76  # mel rows per embedding
EMBEDDING_INPUTS = 16  # embeddings the wake-word model looks at
WARMUP_CHUNKS = 5  # ignore the first scores while buffers fill with real audio

# Wake words this build knows: config name -> (model file, phrase shown to the user,
# regex that removes the wake phrase from the start of a transcript).
# Measured on this PC: "hi/hii/hey jarvis" all score ~0.99 with the hey_jarvis model.
WAKE_WORDS = {
    "hey_jarvis": ("hey_jarvis_v0.1.onnx", "Hi Jarvis", r"^(?:(?:hey|hi|hii|high|hay|a|okay|ok)\s+)?jarvis\b[\s,.]*"),
    "hey_mycroft": ("hey_mycroft_v0.1.onnx", "Hey Mycroft", r"^(?:(?:hey|hi)\s+)?my ?croft\b[\s,.]*"),
    "alexa": ("alexa_v0.1.onnx", "Alexa", r"^alexa\b[\s,.]*"),
}


def wake_phrase(name: str) -> str:
    return WAKE_WORDS.get(name, ("", name, ""))[1]


def strip_wake_phrase(text: str, name: str) -> str:
    """'hi jarvis open notepad' -> 'open notepad'. Leaves other text untouched."""
    import re

    pattern = WAKE_WORDS.get(name, (None, None, None))[2]
    return re.sub(pattern, "", text.strip(), flags=re.IGNORECASE) if pattern else text


class WakeWordError(VoiceOSError):
    """Wake-word models missing or failed to load."""


@dataclass
class WakeWordModels:
    melspectrogram: Path
    embedding: Path
    wake_word: Path


def resolve_wake_word_models(name: str, models_dir: Path = WAKE_WORD_MODELS_DIR) -> WakeWordModels:
    if name not in WAKE_WORDS:
        raise WakeWordError(f"Unknown wake word {name!r}. Available: {', '.join(WAKE_WORDS)}")
    models = WakeWordModels(
        models_dir / "melspectrogram.onnx", models_dir / "embedding_model.onnx", models_dir / WAKE_WORDS[name][0]
    )
    missing = [p.name for p in (models.melspectrogram, models.embedding, models.wake_word) if not p.exists()]
    if missing:
        raise WakeWordError(
            f"Wake-word model files missing ({', '.join(missing)}). Run:  python scripts\\download_wake_word_model.py {name}"
        )
    return models


class WakeWordDetector:
    def __init__(self, models: WakeWordModels, threshold: float = 0.5, patience: int = 2):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 1  # one CPU core is plenty; leave the rest for everything else
        options.inter_op_num_threads = 1

        def load(path: Path):
            try:
                return ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
            except Exception as exc:
                raise WakeWordError(f"Could not load {path.name}: {exc}") from exc

        self._mel = load(models.melspectrogram)
        self._embed = load(models.embedding)
        self._wake = load(models.wake_word)
        self._wake_input = self._wake.get_inputs()[0].name
        self.threshold = threshold
        self.patience = patience
        self.last_score = 0.0
        self.detection_score = 0.0  # score that caused the most recent detection (survives reset)
        self.reset()

    def reset(self) -> None:
        """Forget all audio heard so far (call after a detection or when the mic reopens)."""
        self._pending = np.zeros(0, np.int16)  # samples waiting to make up a full 80 ms chunk
        self._history = np.zeros(MEL_CONTEXT, np.int16)  # recent samples, for mel context
        self._mel_rows = np.ones((MEL_WINDOW, 32), np.float32)
        # Start the embedding buffer with "silence" embeddings so the model has 16 inputs at once.
        silence = self._embedding(np.ones((MEL_WINDOW, 32), np.float32))
        self._embeddings = deque([silence] * EMBEDDING_INPUTS, maxlen=EMBEDDING_INPUTS)
        self._chunks_seen = 0
        self._streak = 0
        self.last_score = 0.0

    def process(self, frame: bytes) -> bool:
        """Feed audio (any length, 16 kHz int16). Returns True when the wake word is detected."""
        samples = np.concatenate((self._pending, np.frombuffer(frame, dtype=np.int16)))
        detected = False
        while len(samples) >= CHUNK:
            chunk, samples = samples[:CHUNK], samples[CHUNK:]
            if self._score_chunk(chunk):
                detected = True
        self._pending = samples
        if detected:
            self.reset()  # so one "hey jarvis" can't trigger twice
        return detected

    def _score_chunk(self, chunk: np.ndarray) -> bool:
        audio = np.concatenate((self._history, chunk))
        self._history = audio[-MEL_CONTEXT:]

        # 1. sound -> mel rows. The /10 + 2 rescaling matches how the embedding model was trained.
        mel = self._mel.run(None, {"input": audio[None, :].astype(np.float32)})[0]
        mel = np.squeeze(mel) / 10.0 + 2.0
        self._mel_rows = np.vstack((self._mel_rows, mel))[-MEL_WINDOW:]

        # 2. last 76 mel rows -> one 96-number embedding
        self._embeddings.append(self._embedding(self._mel_rows))

        # 3. last 16 embeddings -> wake-word score
        features = np.array(self._embeddings, dtype=np.float32)[None, :, :]
        score = float(self._wake.run(None, {self._wake_input: features})[0].squeeze())
        self._chunks_seen += 1
        if self._chunks_seen <= WARMUP_CHUNKS:
            score = 0.0
        self.last_score = score

        self._streak = self._streak + 1 if score >= self.threshold else 0
        if self._streak >= self.patience:
            self.detection_score = score
            logger.info("Wake word detected (score %.2f)", score)
            return True
        return False

    def _embedding(self, mel_rows: np.ndarray) -> np.ndarray:
        batch = mel_rows[None, :, :, None].astype(np.float32)  # shape (1, 76, 32, 1)
        return self._embed.run(None, {"input_1": batch})[0].squeeze()


def create_wake_word_detector(config) -> WakeWordDetector:
    models = resolve_wake_word_models(config.get("wake_word.model"))
    return WakeWordDetector(models, config.get("wake_word.threshold"), config.get("wake_word.patience"))
