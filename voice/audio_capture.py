"""Low-level microphone stream: raw audio frames -> a thread-safe queue.

How audio arrives:
    sounddevice runs `_callback` on a high-priority audio thread every 30 ms with a
    block of samples. That callback must be FAST (no recognition, no UI) or audio
    will glitch. So it does one thing: copy the bytes into a queue.Queue.
    Another thread (VoiceManager's worker) takes frames out with read_frame().

Audio format (what speech engines expect):
    16,000 samples per second, 1 channel (mono), 16-bit integers ("int16").
    30 ms frame = 480 samples = 960 bytes. webrtcvad requires 10/20/30 ms frames.
"""

from __future__ import annotations

import logging
import queue

import sounddevice as sd

from utils.exceptions import MicrophoneError

logger = logging.getLogger(__name__)


class AudioCapture:
    def __init__(self, device_index: int | None, sample_rate: int = 16000, frame_ms: int = 30):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.frame_samples = sample_rate * frame_ms // 1000
        self.dropped_frames = 0
        # maxsize ~ 10 s of audio. If the reader falls behind, old frames are dropped
        # rather than letting memory grow forever.
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=int(10_000 / frame_ms))
        self._stream: sd.RawInputStream | None = None

    @property
    def is_active(self) -> bool:
        return self._stream is not None and self._stream.active

    def start(self) -> None:
        if self.is_active:
            return
        try:
            self._stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.frame_samples,
                device=self.device_index,
                channels=1,
                dtype="int16",
                callback=self._callback,
            )
            self._stream.start()
        except sd.PortAudioError as exc:
            self._stream = None
            raise MicrophoneError(
                f"Could not open the microphone: {exc}. Check Windows Settings > Privacy & security > "
                "Microphone, and that no other app is using it exclusively."
            ) from exc
        logger.info("Microphone stream opened (device %s, %d Hz)", self.device_index, self.sample_rate)

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            logger.info("Microphone stream closed")
        self.discard_pending()  # leftover audio must not leak into the next session

    def discard_pending(self) -> None:
        """Throw away audio that is waiting in the queue (e.g. recorded while VoiceOS was talking)."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def read_frame(self, timeout: float = 0.5) -> bytes | None:
        """Next 30 ms frame, or None if nothing arrived within `timeout` seconds."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    # Runs on the audio thread - keep it tiny.
    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            logger.debug("Audio status: %s", status)
        try:
            self._queue.put_nowait(bytes(indata))
        except queue.Full:
            self.dropped_frames += 1
