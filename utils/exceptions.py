"""Custom exception types for VoiceOS.

Why custom exceptions?
    Python's built-in errors (ValueError, OSError...) don't tell us WHICH part of
    VoiceOS failed. By giving every VoiceOS error a common parent class, code can
    write `except VoiceOSError:` to catch "anything VoiceOS raised on purpose"
    while still letting genuine programming bugs surface.
"""


class VoiceOSError(Exception):
    """Base class for every error VoiceOS raises deliberately."""


class ConfigError(VoiceOSError):
    """config.json is missing, unreadable, or contains invalid values."""


class EnvironmentCheckError(VoiceOSError):
    """The computer doesn't meet a requirement (wrong OS, Python too old...)."""


class MicrophoneError(VoiceOSError):
    """No microphone found, the chosen one is missing, or Windows refused access."""


class SpeechRecognitionError(VoiceOSError):
    """The speech engine or its model could not be loaded or failed to run."""
