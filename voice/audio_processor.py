"""Measuring audio: loudness of a frame, and turning it into a 0..1 meter value.

Key ideas:
    - A frame is a list of int16 samples between -32768 and 32767.
    - RMS ("root mean square") = typical size of the samples = how loud it is.
    - Human hearing is logarithmic, so we convert to decibels (dBFS: 0 dB = maximum,
      -60 dB = nearly silent) before mapping to the meter. Otherwise quiet speech
      would barely move the waveform.
"""

import math

import numpy as np

FULL_SCALE = 32768.0
METER_FLOOR_DB = -55.0  # at or below this the meter shows 0
METER_CEIL_DB = -12.0  # at or above this the meter shows 1 (normal speech is around -30..-15)


def frame_rms(frame: bytes) -> float:
    """Loudness of a frame from 0.0 (silence) to 1.0 (maximum)."""
    if not frame:
        return 0.0
    # np.frombuffer views the raw bytes as int16 numbers without copying.
    samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(samples**2)) / FULL_SCALE)


def rms_to_db(rms: float) -> float:
    return 20.0 * math.log10(max(rms, 1e-9))


def resample(samples: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    """Change the sample rate (e.g. Piper's 22,050 Hz -> Vosk's 16,000 Hz).

    Linear interpolation: work out where each NEW sample falls in time, then draw a
    straight line between the two OLD samples around it. Simple and good enough for
    speech (high-quality music resampling uses fancier filters).
    """
    if from_rate == to_rate or len(samples) == 0:
        return samples
    duration = len(samples) / from_rate
    new_times = np.arange(int(duration * to_rate)) / to_rate
    old_times = np.arange(len(samples)) / from_rate
    return np.interp(new_times, old_times, samples).astype(samples.dtype)


def float_to_int16_bytes(samples: np.ndarray) -> bytes:
    """[-1.0, 1.0] floats -> 16-bit integer bytes (the format Vosk and WAV files use)."""
    return (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def meter_level(rms: float) -> float:
    """Map loudness to 0..1 for the waveform display."""
    db = rms_to_db(rms)
    return max(0.0, min(1.0, (db - METER_FLOOR_DB) / (METER_CEIL_DB - METER_FLOOR_DB)))
