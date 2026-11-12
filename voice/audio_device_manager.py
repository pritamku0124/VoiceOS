"""Lists microphones and picks the one VoiceOS should use.

A quirk worth knowing:
    Windows exposes every microphone several times - once per "host API"
    (MME, DirectSound, WASAPI, WDM-KS). These are different Windows audio systems.
    We only list devices from the *default* host API (normally MME) so each physical
    mic appears once. MME also resamples to 16 kHz for us, which speech engines need.
"""

from __future__ import annotations

from dataclasses import dataclass

import sounddevice as sd

from utils.exceptions import MicrophoneError


@dataclass(frozen=True)
class AudioDevice:
    """One input device. frozen=True makes it read-only (safe to share between threads)."""

    index: int  # PortAudio's device number - what sounddevice needs to open it
    name: str
    channels: int
    default_samplerate: float
    is_default: bool


def list_input_devices() -> list[AudioDevice]:
    try:
        devices = sd.query_devices()
        default_input = sd.default.device[0]
        default_hostapi = sd.query_hostapis(sd.default.hostapi if sd.default.hostapi >= 0 else 0)
    except sd.PortAudioError as exc:
        raise MicrophoneError(f"Windows audio system unavailable: {exc}") from exc

    allowed = set(default_hostapi["devices"])
    result = []
    for index, info in enumerate(devices):
        if info["max_input_channels"] < 1 or index not in allowed:
            continue
        if "Sound Mapper" in info["name"]:  # a virtual "use the default" entry, not a real mic
            continue
        result.append(
            AudioDevice(
                index=index,
                name=info["name"],
                channels=info["max_input_channels"],
                default_samplerate=info["default_samplerate"],
                is_default=(index == default_input),
            )
        )
    return result


def resolve_input_device(preference: int | str | None) -> AudioDevice:
    """Turn the config value voice.input_device into a real device.

    None -> Windows default mic;  int -> that device index;  str -> first name containing it.
    """
    devices = list_input_devices()
    if not devices:
        raise MicrophoneError("No microphone found. Plug one in or enable it in Windows Sound settings.")

    if preference is None:
        for device in devices:
            if device.is_default:
                return device
        return devices[0]

    for device in devices:
        if isinstance(preference, int) and device.index == preference:
            return device
        if isinstance(preference, str) and preference.lower() in device.name.lower():
            return device

    names = ", ".join(d.name for d in devices)
    raise MicrophoneError(f"Microphone {preference!r} not found. Available: {names}")
