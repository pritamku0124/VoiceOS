"""Downloads the wake-word models (openWakeWord, ONNX format) into assets/models/wake_word/.

Run from the project folder (virtual environment active):
    python scripts\\download_wake_word_model.py              # "hey jarvis" (default)
    python scripts\\download_wake_word_model.py --list

Three small files (~3 MB total) are needed:
    melspectrogram.onnx   audio -> a "picture" of the sound (frequency bands over time)
    embedding_model.onnx  that picture -> 96 numbers describing the sound (shared by all wake words)
    <wake word>.onnx      those numbers -> a score 0..1 for ONE specific phrase

License note: the pretrained openWakeWord models are CC BY-NC-SA 4.0 -
fine for personal, non-commercial use like this project.
"""

import argparse
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.constants import WAKE_WORD_MODELS_DIR  # noqa: E402

BASE_URL = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/"
SHARED = ["melspectrogram.onnx", "embedding_model.onnx"]
WAKE_WORDS = {
    # name used in config.json : (file, what to say)
    "hey_jarvis": ("hey_jarvis_v0.1.onnx", '"Hey Jarvis" (also triggers on "Hi Jarvis")'),
    "hey_mycroft": ("hey_mycroft_v0.1.onnx", '"Hey Mycroft"'),
    "alexa": ("alexa_v0.1.onnx", '"Alexa"'),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Download openWakeWord models")
    parser.add_argument("wake_word", nargs="?", default="hey_jarvis")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list or args.wake_word not in WAKE_WORDS:
        if not args.list:
            print(f"Unknown wake word '{args.wake_word}'.\n")
        for name, (_, say) in WAKE_WORDS.items():
            print(f"  {name:12} say {say}")
        return 0 if args.list else 1

    files = SHARED + [WAKE_WORDS[args.wake_word][0]]
    work = WAKE_WORD_MODELS_DIR / "_download"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        for name in files:
            target = WAKE_WORD_MODELS_DIR / name
            if target.exists():
                print(f"  already installed: {name}")
                continue
            print(f"  downloading {name} ...")
            urllib.request.urlretrieve(BASE_URL + name, work / name)
            if (work / name).stat().st_size < 10_000:
                raise RuntimeError(f"{name} is suspiciously small - download failed?")
            shutil.move(str(work / name), target)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"Wake word '{args.wake_word}' ready in {WAKE_WORD_MODELS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
