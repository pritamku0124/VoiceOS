"""Tests for services/config_service.py.

tmp_path is a built-in pytest fixture: a fresh empty folder per test, deleted afterwards,
so tests never touch the real config.json.
"""

import json

import pytest

from services.config_service import DEFAULT_CONFIG, ConfigService, deep_merge
from utils.exceptions import ConfigError


def test_missing_file_uses_defaults_and_creates_it(tmp_path):
    path = tmp_path / "config.json"
    config = ConfigService(path)
    config.load()
    assert config.get("voice.language") == "en-US"
    assert path.exists(), "load() should write a default config file"


def test_user_values_override_defaults_but_keep_the_rest(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"voice": {"language": "en-IN"}}))
    config = ConfigService(path)
    config.load()
    assert config.get("voice.language") == "en-IN"  # overridden
    assert config.get("voice.sample_rate") == 16000  # still the default


def test_invalid_json_gives_a_clear_error(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"voice": {"language": "en-US",}}')  # trailing comma = invalid JSON
    with pytest.raises(ConfigError, match="not valid JSON"):
        ConfigService(path).load()


def test_invalid_choice_is_rejected(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"ui": {"theme": "rainbow"}}))
    with pytest.raises(ConfigError, match="ui.theme"):
        ConfigService(path).load()


@pytest.mark.parametrize(
    "section, key, bad_value",
    [
        ("voice", "vad_aggressiveness", 5),
        ("voice", "vad_aggressiveness", True),  # bool is not accepted as a number
        ("voice", "min_confidence", 1.5),
        ("voice", "sample_rate", 44100),
        ("voice", "language", "xx-XX"),
        ("tts", "speed", 5),
    ],
)
def test_out_of_range_values_are_rejected(tmp_path, section, key, bad_value):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({section: {key: bad_value}}))
    with pytest.raises(ConfigError, match=f"{section}.{key}"):
        ConfigService(path).load()


def test_set_and_save_round_trip(tmp_path):
    path = tmp_path / "config.json"
    config = ConfigService(path)
    config.load()
    config.set("tts.speed", 1.25)
    config.save()
    reloaded = ConfigService(path)
    reloaded.load()
    assert reloaded.get("tts.speed") == 1.25


def test_get_unknown_key_returns_default():
    config = ConfigService(path=None)  # get() never touches the file, so no path is needed
    assert config.get("does.not.exist", "fallback") == "fallback"


def test_deep_merge_does_not_modify_inputs():
    override = {"voice": {"engine": "faster-whisper"}}
    merged = deep_merge(DEFAULT_CONFIG, override)
    assert merged["voice"]["engine"] == "faster-whisper"
    assert DEFAULT_CONFIG["voice"]["engine"] == "vosk"
