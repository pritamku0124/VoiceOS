"""Downloads the offline Vosk speech-recognition model into assets/models/speech/.

Run from the project folder (virtual environment active):
    python scripts\\download_speech_model.py            # small English model (~40 MB)
    python scripts\\download_speech_model.py --list     # show available choices

Why a separate script (instead of downloading inside the app)?
    - The model is big and only needed once; the app should start fast and offline.
    - You stay in control of what gets downloaded and when.

Safety: the zip is extracted with a check that every file stays inside the target
folder. A malicious zip could otherwise contain names like "..\\..\\Windows\\evil.dll"
("zip slip" attack).
"""

import argparse
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.constants import SPEECH_MODELS_DIR  # noqa: E402

BASE_URL = "https://alphacephei.com/vosk/models/"
MODELS = {
    # name: (approx size, description)
    "vosk-model-small-en-us-0.15": ("40 MB", "Small US English - fast, good for commands (recommended)"),
    "vosk-model-small-en-in-0.4": ("36 MB", "Small Indian English"),
    "vosk-model-en-us-0.22-lgraph": ("128 MB", "Medium US English - more accurate, slower to load"),
}
DEFAULT_MODEL = "vosk-model-small-en-us-0.15"


def download(url: str, destination: Path) -> None:
    def progress(blocks: int, block_size: int, total: int) -> None:
        if total > 0:
            done = min(blocks * block_size, total)
            print(f"\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB ({done * 100 // total}%)", end="", flush=True)

    urllib.request.urlretrieve(url, destination, reporthook=progress)
    print()


def safe_extract(zip_path: Path, target: Path) -> None:
    target = target.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            destination = (target / member).resolve()
            if not destination.is_relative_to(target):
                raise RuntimeError(f"Refusing unsafe path in zip: {member}")
        archive.extractall(target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a Vosk speech model")
    parser.add_argument("model", nargs="?", default=DEFAULT_MODEL, help="model name (see --list)")
    parser.add_argument("--list", action="store_true", help="list available models")
    args = parser.parse_args()

    if args.list or args.model not in MODELS:
        if not args.list:
            print(f"Unknown model '{args.model}'.\n")
        for name, (size, desc) in MODELS.items():
            print(f"  {name:32} {size:>7}  {desc}")
        return 0 if args.list else 1

    final_dir = SPEECH_MODELS_DIR / args.model
    if final_dir.exists():
        print(f"Already installed: {final_dir}")
        return 0

    # Work in a separate scratch folder, so a failed download never leaves a half-model behind.
    work_dir = SPEECH_MODELS_DIR / "_download"
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True)
    zip_path = work_dir / f"{args.model}.zip"
    try:
        print(f"Downloading {args.model} ({MODELS[args.model][0]}) from {BASE_URL} ...")
        download(f"{BASE_URL}{args.model}.zip", zip_path)
        print("Extracting ...")
        safe_extract(zip_path, work_dir)
        extracted = work_dir / args.model
        if not (extracted / "am").is_dir():  # every Vosk model has an "am" (acoustic model) folder
            raise RuntimeError("Downloaded archive does not look like a Vosk model.")
        shutil.move(str(extracted), final_dir)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    print(f"Installed: {final_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
