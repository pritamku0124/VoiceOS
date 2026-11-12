"""Loads, validates and saves VoiceOS settings stored in config.json.

Design:
    DEFAULT_CONFIG (below) is the full list of settings with safe values.
    config.json only needs to contain what the user CHANGED; we "deep-merge" it on top
    of the defaults. So if a future version adds a new setting, old config.json files
    still work - the new key just takes its default value.

Usage:
    config = ConfigService(Path("config.json"))
    config.load()
    config.get("voice.language")          # -> "en-US"
    config.set("ui.theme", "light")
    config.save()
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

from utils.exceptions import ConfigError

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "app": {"log_level": "INFO", "start_minimized": False, "start_with_windows": False},
    "voice": {
        "input_device": None,  # None = Windows default microphone
        "engine": "vosk",  # "vosk" (fast, light) or "faster-whisper" (more accurate)
        "language": "en-US",
        "model": None,  # None = pick automatically from language; or a folder name in assets/models/speech
        "push_to_talk": True,
        "sample_rate": 16000,
        "min_confidence": 0.55,  # below this, ask the user to repeat instead of acting
        "vad_aggressiveness": 2,  # 0 (hears everything) .. 3 (strict, ignores more noise)
        "end_silence_ms": 800,  # this much silence ends a command
        "max_utterance_seconds": 10,
        "no_speech_timeout_seconds": 7,  # stop listening if nobody speaks
    },
    "wake_word": {
        "enabled": False,  # off by default: an always-open microphone must be the user's choice
        "model": "hey_jarvis",  # say "Hi Jarvis" / "Hey Jarvis"
        "threshold": 0.7,  # 0..1, higher = fewer false alarms, may need you to speak clearer
        "patience": 2,  # how many 80 ms chunks in a row must pass the threshold
    },
    "tts": {
        "enabled": True,
        "engine": "windows",  # "windows" (built-in SAPI) or "piper" (blocked by Smart App Control here)
        "voice": None,  # windows: part of a voice name, e.g. "Zira"; piper: a voice in assets/models/tts
        "speed": 1.0,  # 0.5 = slow ... 2.0 = fast
        "volume": 0.9,  # 0.0 .. 1.0
    },
    "ai": {
        "enabled": True,  # False = understand commands with the built-in rules only
        "provider": "ollama",
        "model": "qwen2.5:1.5b",  # small & fast on CPU; "qwen2.5:3b" is smarter but ~2x slower
        "base_url": "http://localhost:11434",  # must be this computer
        "timeout_seconds": 60,
    },
    "safety": {
        "dry_run": False,  # True = understand commands but never touch Windows (used by tests)
        "confirm_destructive_actions": True,
        "emergency_stop_hotkey": "ctrl+alt+esc",
    },
    "privacy": {"save_recordings": False, "save_history": True},
    "ui": {"theme": "dark", "window_width": 1100, "window_height": 720},
}

# Only these values are accepted for "choice" settings. Validation catches typos early.
ALLOWED_VALUES: dict[str, set[str]] = {
    "voice.engine": {"vosk", "faster-whisper"},
    "ai.provider": {"ollama"},
    "voice.language": {"en-US", "en-IN"},
    "tts.engine": {"windows", "piper"},
    "wake_word.model": {"hey_jarvis", "hey_mycroft", "alexa"},
    "ui.theme": {"dark", "light"},
    "app.log_level": {"DEBUG", "INFO", "WARNING", "ERROR"},
}


def deep_merge(base: dict, override: dict) -> dict:
    """Return a new dict: `base` with values from `override` layered on top (recursively)."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigService:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)

    def load(self) -> None:
        """Read config.json (if present), merge onto defaults, and validate."""
        if not self.path.exists():
            logger.warning("No config file at %s - using defaults and creating one.", self.path)
            self.save()
            return
        try:
            user_data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            # exc.lineno / exc.colno point at the exact typo - very helpful to show the user.
            raise ConfigError(f"{self.path.name} is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}") from exc
        if not isinstance(user_data, dict):
            raise ConfigError(f"{self.path.name} must contain a JSON object at the top level.")
        self._data = deep_merge(DEFAULT_CONFIG, user_data)
        self.validate()
        logger.info("Configuration loaded from %s", self.path)

    def validate(self) -> None:
        for key, allowed in ALLOWED_VALUES.items():
            value = self.get(key)
            if value not in allowed:
                raise ConfigError(f"Invalid value for '{key}': {value!r}. Allowed: {sorted(allowed)}")
        self._check_number("tts.speed", 0.5, 2.0)
        self._check_number("tts.volume", 0.0, 1.0)
        self._check_number("wake_word.threshold", 0.1, 0.99)
        self._check_number("wake_word.patience", 1, 10, integer=True)
        self._check_number("ai.timeout_seconds", 5, 300)
        from urllib.parse import urlparse

        if urlparse(str(self.get("ai.base_url"))).hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ConfigError("'ai.base_url' must point to this computer (localhost) - VoiceOS keeps your data local.")
        self._check_number("voice.min_confidence", 0.0, 1.0)
        self._check_number("voice.vad_aggressiveness", 0, 3, integer=True)
        self._check_number("voice.end_silence_ms", 200, 5000, integer=True)
        self._check_number("voice.max_utterance_seconds", 2, 60)
        self._check_number("voice.no_speech_timeout_seconds", 2, 60)
        if self.get("voice.sample_rate") != 16000:
            raise ConfigError("'voice.sample_rate' must be 16000 (what the speech models expect).")

    def _check_number(self, key: str, low: float, high: float, integer: bool = False) -> None:
        value = self.get(key)
        # bool is a subclass of int in Python, so exclude it explicitly (true/false aren't numbers here).
        ok_type = isinstance(value, int) if integer else isinstance(value, (int, float))
        if isinstance(value, bool) or not ok_type or not low <= value <= high:
            kind = "a whole number" if integer else "a number"
            raise ConfigError(f"'{key}' must be {kind} between {low} and {high}, got {value!r}")

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Look up a nested value with a dotted path, e.g. get('voice.language')."""
        node: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted_key: str, value: Any) -> None:
        parts = dotted_key.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2) + "\n", encoding="utf-8")

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)
