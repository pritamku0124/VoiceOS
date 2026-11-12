"""Chooses which speech model folder to load for the configured language.

Vosk models are language-specific (an English model cannot recognise Hindi).
Rather than auto-detecting the language from audio (slow and unreliable for short
commands), we map the language setting to an installed model folder.
"""

from __future__ import annotations

from pathlib import Path

from utils.constants import SPEECH_MODELS_DIR
from utils.exceptions import SpeechRecognitionError

# language code -> Vosk model folder name (downloadable with scripts/download_speech_model.py)
LANGUAGE_MODELS = {
    "en-US": "vosk-model-small-en-us-0.15",
    "en-IN": "vosk-model-small-en-in-0.4",
}
SUPPORTED_LANGUAGES = set(LANGUAGE_MODELS)


def resolve_model_dir(language: str, override: str | None = None, models_dir: Path = SPEECH_MODELS_DIR) -> Path:
    """Return the model folder for `language` (or the explicit `override` folder name)."""
    if override is None and language not in LANGUAGE_MODELS:
        raise SpeechRecognitionError(
            f"Language {language!r} is not supported yet. Supported: {sorted(SUPPORTED_LANGUAGES)}"
        )
    name = override or LANGUAGE_MODELS[language]
    path = models_dir / name
    if not path.is_dir():
        raise SpeechRecognitionError(
            f"Speech model '{name}' is not installed. Run:  python scripts\\download_speech_model.py {name}"
        )
    return path
