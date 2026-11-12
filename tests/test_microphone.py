"""Tests for audio measurement, noise tracking and microphone selection (no real hardware needed)."""

import numpy as np
import pytest

from utils.exceptions import MicrophoneError
from voice import audio_device_manager
from voice.audio_processor import frame_rms, meter_level, rms_to_db
from voice.noise_reduction import NoiseFloorTracker


def tone(amplitude: float, ms: int = 30) -> bytes:
    """A 440 Hz sine wave as int16 bytes. amplitude 1.0 = loudest possible."""
    t = np.arange(16000 * ms // 1000) / 16000
    return (np.sin(2 * np.pi * 440 * t) * amplitude * 32767).astype(np.int16).tobytes()


def test_silence_has_zero_level():
    assert frame_rms(b"\x00" * 960) == 0.0
    assert meter_level(0.0) == 0.0


def test_full_scale_sine_rms_is_about_0_707():
    # Maths fact: the RMS of a sine wave is its peak / sqrt(2).
    assert frame_rms(tone(1.0)) == pytest.approx(0.707, abs=0.01)


def test_louder_sound_gives_higher_meter():
    assert meter_level(frame_rms(tone(0.01))) < meter_level(frame_rms(tone(0.1))) <= 1.0


def test_db_conversion():
    assert rms_to_db(1.0) == pytest.approx(0.0)
    assert rms_to_db(0.1) == pytest.approx(-20.0)


def test_noise_floor_adapts_to_background():
    tracker = NoiseFloorTracker()
    fan_noise = frame_rms(tone(0.01))  # about -43 dB
    for _ in range(100):
        tracker.update(fan_noise)
    assert not tracker.is_above_floor(fan_noise)  # background no longer counts as speech
    assert tracker.is_above_floor(frame_rms(tone(0.2)))  # but a louder voice does


FAKE_DEVICES = [
    {"name": "Microsoft Sound Mapper - Input", "max_input_channels": 2, "default_samplerate": 44100.0},
    {"name": "Headset Microphone", "max_input_channels": 2, "default_samplerate": 44100.0},
    {"name": "Microphone Array", "max_input_channels": 2, "default_samplerate": 48000.0},
    {"name": "Speakers", "max_input_channels": 0, "default_samplerate": 48000.0},
    {"name": "Headset Microphone (WASAPI duplicate)", "max_input_channels": 2, "default_samplerate": 48000.0},
]


@pytest.fixture
def fake_sounddevice(monkeypatch):
    """monkeypatch temporarily replaces functions; pytest restores them after the test."""

    class Default:
        device = (1, 3)
        hostapi = 0

    monkeypatch.setattr(audio_device_manager.sd, "query_devices", lambda: FAKE_DEVICES)
    monkeypatch.setattr(audio_device_manager.sd, "query_hostapis", lambda i: {"devices": [0, 1, 2, 3]})
    monkeypatch.setattr(audio_device_manager.sd, "default", Default)


def test_lists_only_real_inputs_from_default_host_api(fake_sounddevice):
    names = [d.name for d in audio_device_manager.list_input_devices()]
    assert names == ["Headset Microphone", "Microphone Array"]  # no mapper, no speaker, no duplicate


def test_resolve_default_by_index_and_by_name(fake_sounddevice):
    assert audio_device_manager.resolve_input_device(None).name == "Headset Microphone"
    assert audio_device_manager.resolve_input_device(2).name == "Microphone Array"
    assert audio_device_manager.resolve_input_device("array").index == 2


def test_unknown_microphone_gives_helpful_error(fake_sounddevice):
    with pytest.raises(MicrophoneError, match="Available: Headset Microphone"):
        audio_device_manager.resolve_input_device("Blue Yeti")
