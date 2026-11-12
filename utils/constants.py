"""Project-wide constants: app identity, important folder paths, and design colours.

Why this file exists:
    If the path to the logs folder is written in five different files and we later
    move it, we would have to find and fix all five. Keeping such values in ONE place
    means every other module imports them from here instead of hard-coding them.
"""

from pathlib import Path

APP_NAME = "VoiceOS"
APP_VERSION = "0.6.1"  # minor version = completed phase
CURRENT_PHASE = 6  # last completed development phase (used by scripts/check_environment.py)
MIN_PYTHON = (3, 11)

# --- Paths --------------------------------------------------------------------
# __file__ is this file (utils/constants.py). .parent is utils/, .parent again is the project root.
# Building paths from __file__ means VoiceOS works no matter which folder you launch it from.
ROOT_DIR = Path(__file__).resolve().parent.parent

CONFIG_FILE = ROOT_DIR / "config.json"
LOGS_DIR = ROOT_DIR / "logs"
ASSETS_DIR = ROOT_DIR / "assets"
MODELS_DIR = ASSETS_DIR / "models"
SPEECH_MODELS_DIR = MODELS_DIR / "speech"
TTS_VOICES_DIR = MODELS_DIR / "tts"
WAKE_WORD_MODELS_DIR = MODELS_DIR / "wake_word"
STYLES_DIR = ROOT_DIR / "dashboard" / "styles"
DATABASE_DIR = ROOT_DIR / "database"
PROFILES_DIR = ROOT_DIR / "profiles"
RECORDINGS_DIR = ROOT_DIR / "recordings"


# --- Design tokens -------------------------------------------------------------
# The same colours are used in the QSS stylesheet; widgets that paint themselves
# (like the waveform) read them from here.
class Colors:
    PRIMARY = "#9B6CE0"
    SECONDARY = "#B77AD8"
    BACKGROUND = "#10121C"
    PANEL = "#191D2A"
    PANEL_ALT = "#222738"
    TEXT = "#FFFFFF"
    TEXT_MUTED = "#A7A9BC"
    SUCCESS = "#35C98A"
    WARNING = "#F0B65A"
    ERROR = "#EF6262"
