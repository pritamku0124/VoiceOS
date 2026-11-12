"""Voice Activity Detection (VAD): cut one spoken command out of a continuous audio stream.

webrtcvad (from Google's WebRTC, used in video calls) labels each 30 ms frame as
speech / not speech. Single frames are noisy, so UtteranceSegmenter looks at a
short window of recent frames - a small "state machine":

    WAITING ──(most of last 300 ms is speech)──► SPEAKING ──(800 ms of silence)──► DONE
       ▲                                            │
       └───────────── pre-roll ─────────────────────┘
    The 300 ms window that triggered SPEAKING is kept ("pre-roll"), otherwise
    the first syllable ("OPen chrome") would be cut off.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable

import webrtcvad

from voice.audio_processor import frame_rms
from voice.noise_reduction import NoiseFloorTracker


class UtteranceSegmenter:
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        aggressiveness: int = 2,
        end_silence_ms: int = 800,
        max_seconds: float = 10.0,
        start_window_ms: int = 300,
        start_ratio: float = 0.6,
        is_speech: Callable[[bytes], bool] | None = None,
    ):
        self.frame_ms = frame_ms
        self.end_silence_frames = max(1, end_silence_ms // frame_ms)
        self.max_frames = int(max_seconds * 1000 / frame_ms)
        self.start_ratio = start_ratio
        self.noise = NoiseFloorTracker()

        if is_speech is None:
            vad = webrtcvad.Vad(aggressiveness)  # 0 = permissive ... 3 = strict

            def is_speech(frame: bytes) -> bool:
                rms = frame_rms(frame)
                speech = vad.is_speech(frame, sample_rate) and self.noise.is_above_floor(rms)
                if not speech:
                    self.noise.update(rms)
                return speech

        self._is_speech = is_speech
        self._window: deque[tuple[bytes, bool]] = deque(maxlen=max(1, start_window_ms // frame_ms))
        self.reset()

    def reset(self) -> None:
        self.in_speech = False
        self._frames: list[bytes] = []
        self._silence_run = 0
        self._window.clear()

    def process(self, frame: bytes) -> bytes | None:
        """Feed one frame. Returns the complete utterance (bytes) when it ends, else None."""
        speech = self._is_speech(frame)

        if not self.in_speech:
            self._window.append((frame, speech))
            voiced = sum(1 for _, s in self._window if s)
            if len(self._window) == self._window.maxlen and voiced >= self.start_ratio * self._window.maxlen:
                self.in_speech = True
                self._frames = [f for f, _ in self._window]  # include the pre-roll
                self._window.clear()
            return None

        self._frames.append(frame)
        self._silence_run = 0 if speech else self._silence_run + 1
        if self._silence_run >= self.end_silence_frames or len(self._frames) >= self.max_frames:
            # Trim trailing silence (keep a little so the last word isn't clipped).
            keep_tail = min(self._silence_run, 5)
            audio_frames = self._frames[: len(self._frames) - self._silence_run + keep_tail]
            self.reset()
            return b"".join(audio_frames)
        return None
