"""Checks that this computer is ready to run VoiceOS, and explains anything that isn't.

Run from the project folder:
    python scripts\\check_environment.py

It never installs anything - it only reports.
"""

import importlib.util
import shutil
import sys
from pathlib import Path

# Allow "from utils..." imports when this script is run directly from scripts/.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.constants import CURRENT_PHASE, SPEECH_MODELS_DIR, WAKE_WORD_MODELS_DIR  # noqa: E402
from utils.platform_utils import describe_system, is_windows, python_version_ok  # noqa: E402

# (import name, pip name, phase that needs it)
PACKAGES = [
    ("PySide6", "PySide6-Essentials", 1),
    ("pytest", "pytest", 1),
    ("sounddevice", "sounddevice", 2),
    ("numpy", "numpy", 2),
    ("vosk", "vosk", 2),
    ("webrtcvad", "webrtcvad-wheels", 2),
    ("comtypes", "comtypes", 3),
    ("onnxruntime", "onnxruntime", 4),
]

OK, MISSING, LATER = "[ OK ]", "[MISS]", "[ -- ]"


def main() -> int:
    print("VoiceOS environment check\n")
    for key, value in describe_system().items():
        print(f"  {key:18} {value}")

    in_venv = sys.prefix != sys.base_prefix  # True when running inside a virtual environment
    print()
    print(f"  {OK if is_windows() else MISSING} Windows")
    print(f"  {OK if python_version_ok() else MISSING} Python 3.11 or newer")
    print(f"  {OK if in_venv else MISSING} Running inside a virtual environment (.venv)")

    problems = 0 if (is_windows() and python_version_ok()) else 1
    print("\nPython packages:")
    for module, pip_name, phase in PACKAGES:
        found = importlib.util.find_spec(module) is not None
        if found:
            mark = OK
        elif phase <= CURRENT_PHASE:
            mark, problems = MISSING, problems + 1
        else:
            mark = LATER
        print(f"  {mark} {pip_name:20} (Phase {phase})")

    print("\nExternal tools:")
    import os

    default_exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    ollama = shutil.which("ollama") or (str(default_exe) if default_exe.exists() else None)
    print(f"  {OK if ollama else MISSING} Ollama program {'at ' + ollama if ollama else 'not installed (optional AI)'}")
    from ai.ollama_client import OllamaClient
    from ai.llm_client import LLMError
    from services.config_service import ConfigService
    from utils.constants import CONFIG_FILE

    config = ConfigService(CONFIG_FILE)
    config.load()
    client = OllamaClient(config.get("ai.base_url"), config.get("ai.model"))
    try:
        models = client.installed_models()
        running = True
    except LLMError:
        models, running = [], False
    print(f"  {OK if running else MISSING} Ollama server running" + ("" if running else " - start 'Ollama' from the Start menu"))
    has_model = client.is_available()
    print(f"  {OK if has_model else MISSING} AI model {client.model}" +
          ("" if has_model else f" - run: ollama pull {client.model}"))
    print("        (AI is optional: without it, VoiceOS uses its built-in rules only.)")

    print("\nLegend: [ OK ] ready   [MISS] needed now   [ -- ] needed in a later phase")
    models = [
        ("Speech model (Phase 2)", lambda: any(p.is_dir() for p in SPEECH_MODELS_DIR.iterdir()),
         "python scripts\\download_speech_model.py"),
        ("Wake-word models (Phase 4)", lambda: (WAKE_WORD_MODELS_DIR / "hey_jarvis_v0.1.onnx").exists(),
         "python scripts\\download_wake_word_model.py"),
    ]
    print("\nModels:")
    for label, check, command in models:
        try:
            found = check()
        except FileNotFoundError:
            found = False
        problems += 0 if found else 1
        print(f"  {OK if found else MISSING} {label}" + ("" if found else f" - run: {command}"))

    print("\nResult:", f"READY (phases 1-{CURRENT_PHASE})" if problems == 0
          else f"{problems} problem(s) - see [MISS] lines above")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
