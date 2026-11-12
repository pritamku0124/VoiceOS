"""Downloads a Piper voice (the neural network that speaks) into assets/models/tts/.

Run from the project folder (virtual environment active):
    python scripts\\download_tts_voice.py             # default voice, en_US-lessac-medium (~63 MB)
    python scripts\\download_tts_voice.py --list      # other voices

A Piper voice is two files:
    <name>.onnx       the neural network weights (ONNX = a portable model format)
    <name>.onnx.json  its settings: sample rate, phoneme map, default speed
Both come from the official Piper voices collection on Hugging Face.
"""

import argparse
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.constants import TTS_VOICES_DIR  # noqa: E402

BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
VOICES = {
    # name: (path inside the collection, approx size, description)
    "en_US-lessac-medium": ("en/en_US/lessac/medium/", "63 MB", "US English, clear neutral voice (recommended)"),
    "en_US-amy-medium": ("en/en_US/amy/medium/", "63 MB", "US English, female"),
    "en_GB-alan-medium": ("en/en_GB/alan/medium/", "63 MB", "British English, male"),
    "en_US-lessac-low": ("en/en_US/lessac/low/", "63 MB", "US English, lower audio quality, slightly faster"),
}
DEFAULT_VOICE = "en_US-lessac-medium"


def fetch(url: str, destination: Path) -> None:
    def progress(blocks: int, block_size: int, total: int) -> None:
        if total > 0:
            done = min(blocks * block_size, total)
            print(f"\r  {destination.name}: {done / 1e6:6.1f} / {total / 1e6:.1f} MB", end="", flush=True)

    urllib.request.urlretrieve(url, destination, reporthook=progress)
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a Piper TTS voice")
    parser.add_argument("voice", nargs="?", default=DEFAULT_VOICE)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list or args.voice not in VOICES:
        if not args.list:
            print(f"Unknown voice '{args.voice}'.\n")
        for name, (_, size, desc) in VOICES.items():
            print(f"  {name:24} {size:>6}  {desc}")
        return 0 if args.list else 1

    model = TTS_VOICES_DIR / f"{args.voice}.onnx"
    config = TTS_VOICES_DIR / f"{args.voice}.onnx.json"
    if model.exists() and config.exists():
        print(f"Already installed: {model}")
        return 0

    # Download into a scratch folder first, so a failed download never leaves half a voice.
    work = TTS_VOICES_DIR / "_download"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        sub_path = VOICES[args.voice][0]
        print(f"Downloading {args.voice} from {BASE_URL} ...")
        for file in (config.name, model.name):  # small JSON first: fails fast if the URL is wrong
            fetch(f"{BASE_URL}{sub_path}{file}?download=true", work / file)
        if (work / model.name).stat().st_size < 1_000_000:
            raise RuntimeError("Downloaded model is suspiciously small - not a valid voice.")
        for file in (model.name, config.name):
            shutil.move(str(work / file), TTS_VOICES_DIR / file)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"Installed: {model}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
