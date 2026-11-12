"""High-level microphone used by VoiceManager.

Combines: choose device (audio_device_manager) + open stream (audio_capture).
VoiceManager depends only on the small interface below (start, stop, read_frame,
is_active, device_name). That lets tests swap in a fake microphone that plays a
WAV file instead of real hardware.
"""

from __future__ import annotations

from voice.audio_capture import AudioCapture
from voice.audio_device_manager import resolve_input_device


class Microphone:
    FRAME_MS = 30

    def __init__(self, device_preference: int | str | None = None, sample_rate: int = 16000):
        self.device = resolve_input_device(device_preference)
        self.sample_rate = sample_rate
        self._capture = AudioCapture(self.device.index, sample_rate, self.FRAME_MS)

    @property
    def device_name(self) -> str:
        return self.device.name

    @property
    def is_active(self) -> bool:
        return self._capture.is_active

    def start(self) -> None:
        self._capture.start()

    def stop(self) -> None:
        self._capture.stop()

    def read_frame(self, timeout: float = 0.5) -> bytes | None:
        return self._capture.read_frame(timeout)

    def discard_pending(self) -> None:
        self._capture.discard_pending()
