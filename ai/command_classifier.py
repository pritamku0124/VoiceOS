"""Recognises the two phrases that control VoiceOS itself: "stop listening" and "quit Jarvis".

Why not send them through the Assistant like other commands?
    They control the LISTENING LOOP. The loop must react the moment it hears them
    (stop the microphone now), without a round-trip through rules / AI / the router.
    So VoiceManager checks every transcript here first. Typed commands are checked too.

Small allowance for speech recognition: "jarvis" is sometimes heard as "jervis" or "travis".
"""

from __future__ import annotations

import re

STOP_LISTENING = "stop_listening"
QUIT = "quit"

_NAME = r"(jarvis|jervis|travis|voiceos|voice os)"
_PATTERNS = [
    # Measured: Vosk hears "quit jarvis" as "quick jarvis" and "goodbye" as "good bye" (accepted),
    # and sometimes "goodbye jarvis" as "good jarvis" (NOT accepted: that could be praise).
    (QUIT, re.compile(rf"^((quit|quick|quits|exit|close|shut ?down|turn off|stop) {_NAME}|{_NAME} (quit|exit|shut ?down)"
                      rf"|good ?bye {_NAME})$")),
    (STOP_LISTENING, re.compile(rf"^({_NAME} )?(stop|pause) listening( {_NAME}| now| for now| to me)?$|^go to sleep( {_NAME})?$")),
]


def _normalize(text: str) -> str:
    text = re.sub(r"[^a-z' ]", " ", text.lower())
    text = re.sub(r"^(please|hey|hi|okay|ok) ", "", re.sub(r"\s+", " ", text).strip())
    return re.sub(r" please$", "", text)


def classify_control(text: str) -> str | None:
    """'Stop listening.' -> 'stop_listening'; 'quit jarvis' -> 'quit'; anything else -> None."""
    normalized = _normalize(text)
    for name, pattern in _PATTERNS:
        if pattern.match(normalized):
            return name
    return None
