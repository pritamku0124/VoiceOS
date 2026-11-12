"""The assistant's possible states.

An Enum is a fixed set of named values. Using AssistantState.LISTENING instead of
the string "listening" means a typo like "listning" is caught immediately as an
AttributeError instead of silently never matching.

Continuous listening (one click -> unlimited commands):

    IDLE ──click──► LISTENING ──speech──► PROCESSING ──► EXECUTING ──► (SPEAKING) ──► LISTENING ──► ...
                       ▲   │ silence / no words: just keep listening                                │
                       │   └────────────── "stop listening" / click / Esc ──► PAUSED ──click──────┘
    any state ── "quit Jarvis" ──► SHUTDOWN (application closes)

With the wake word on, VoiceOS starts in WAKE_LISTENING; "Hi Jarvis" starts the same
continuous session as a click.

Whether the microphone is actually open is reported separately (VoiceManager's
mic_active_changed signal), because in a continuous session the mic stays open
through PROCESSING/EXECUTING/SPEAKING - audio from those moments is thrown away.
"""

from enum import Enum


class AssistantState(Enum):
    IDLE = "idle"  # app open, microphone off
    LOADING = "loading"  # loading speech / wake-word models
    WAKE_LISTENING = "wake_listening"  # waiting only for "Hi Jarvis"
    LISTENING = "listening"  # waiting for (or hearing) a command
    PROCESSING = "processing"  # turning speech into text and understanding it
    EXECUTING = "executing"  # carrying out the command
    SPEAKING = "speaking"  # VoiceOS is talking (its own voice is never treated as a command)
    PAUSED = "paused"  # "stop listening": microphone off until the mic button is clicked
    SHUTDOWN = "shutdown"  # "quit Jarvis": the application is closing
    ERROR = "error"
