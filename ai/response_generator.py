"""Builds the sentence VoiceOS speaks after handling a request.

Templates instead of asking the AI to write replies: instant, predictable, and the
reply can never claim something happened that didn't.

    done      -> the action's own message           "It's 3:42 PM."
    failed    -> the friendly reason                "I couldn't find an app called Spotify."
    cancelled -> confirmation said no               "Okay, I won't close Google Chrome."
    planned   -> understood but not built yet       "I understood: copy report.pdf to Documents,
                                                     but I can't do that yet."
    nothing   -> AI answer, or "didn't understand"
"""

from __future__ import annotations

from ai.intent_recognition import Recognition
from core.command_router import ActionResult

NOT_UNDERSTOOD = "Sorry, I didn't understand that."
CANNOT = "Sorry, I can't do that."
AI_HINT = " I only know simple commands until the AI model is installed."


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + ", then " + items[-1]


def build_reply(recognition: Recognition, results: list[ActionResult], ai_installed: bool = True) -> str:
    if not results:
        if recognition.answer:
            return recognition.answer
        if recognition.source == "ai" and recognition.errors:
            return CANNOT  # the AI proposed something, but it was refused
        return NOT_UNDERSTOOD + ("" if ai_installed or recognition.source == "ai" else AI_HINT)

    parts = [r.message for r in results if r.status in ("done", "failed", "cancelled") and r.message]
    planned = [r.description for r in results if r.status == "planned"]
    if planned:
        parts.append(f"I understood: {_join(planned)}, but I can't do that yet.")
    return " ".join(parts)
