"""Background-noise handling: learn how loud the room is, ignore sounds near that level.

webrtcvad sometimes mistakes a fan, keyboard or traffic for speech. NoiseFloorTracker
keeps a running estimate of the background level and lets VAD require speech to be
clearly louder than that.

Technique - exponential moving average (EMA):
    floor = floor + alpha * (new_value - floor)
    A small alpha changes slowly (stable); we adapt faster downward than upward so a
    burst of speech doesn't drag the "background" estimate up.
"""

from voice.audio_processor import rms_to_db


class NoiseFloorTracker:
    def __init__(self, initial_db: float = -60.0, margin_db: float = 6.0):
        self.floor_db = initial_db
        self.margin_db = margin_db

    def update(self, rms: float) -> None:
        """Feed every frame that VAD considered NON-speech."""
        db = rms_to_db(rms)
        alpha = 0.05 if db > self.floor_db else 0.3
        self.floor_db += alpha * (db - self.floor_db)

    def is_above_floor(self, rms: float) -> bool:
        return rms_to_db(rms) >= self.floor_db + self.margin_db
