"""Sends each validated Intent to the code that carries it out - asking first when it's risky.

    route(intent)
      ├─ no handler yet            -> "planned"   (understood; arrives in a later phase)
      ├─ risk MEDIUM/HIGH          -> confirm("Do you want me to close Google Chrome?")
      │     no / no answer          -> "cancelled" (nothing happens)
      ├─ handler raises VoiceOSError -> "failed" with its friendly message ("Spotify isn't installed")
      ├─ handler crashes (a bug)   -> "failed", full traceback in the log
      └─ OK                        -> "done" with the handler's sentence ("Opening WhatsApp.")

Handlers are registered by core/action_manager.py (real Windows control) or by tests (fakes).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from actions.action_registry import get_spec
from actions.action_schema import Intent, Risk
from utils.exceptions import VoiceOSError

logger = logging.getLogger(__name__)

CAPABILITIES = (
    "I can open, switch and close apps, minimize, maximize and snap windows, click, scroll and type, "
    "open websites and searches, control media and volume, check the battery, and open Settings. "
    "Working with files is coming next."
)


@dataclass
class ActionResult:
    intent: Intent
    status: str  # "done", "planned", "cancelled" or "failed"
    message: str = ""  # sentence to say

    @property
    def description(self) -> str:
        spec = get_spec(self.intent.action)
        return spec.describe(self.intent.params) if spec else self.intent.action


def _time(intent: Intent) -> str:
    return datetime.now().strftime("It's %I:%M %p.").replace(" 0", " ")


def _date(intent: Intent) -> str:
    return datetime.now().strftime("Today is %A, %B %d, %Y.").replace(" 0", " ")


Handler = Callable[[Intent], str]
Confirm = Callable[[str], bool]


class CommandRouter:
    def __init__(self, confirm: Confirm | None = None, confirm_medium: bool = True):
        # confirm(question) -> True only if the user explicitly said yes. None = never allowed.
        self.confirm = confirm
        # MEDIUM risk (close an app) may skip the question if the user chose so in config.json.
        # HIGH risk (lock, delete) ALWAYS asks.
        self.confirm_medium = confirm_medium
        self.handlers: dict[str, Handler] = {
            "GET_TIME": _time,
            "GET_DATE": _date,
            "HELP": lambda i: CAPABILITIES,
            "GREETING": lambda i: "Hello! How can I help you?",
            "THANKS": lambda i: "You're welcome.",
        }

    def register(self, action: str, handler: Handler) -> None:
        self.handlers[action] = handler

    def route(self, intent: Intent) -> ActionResult:
        spec = get_spec(intent.action)
        handler = self.handlers.get(intent.action)
        if handler is None:
            return ActionResult(intent, "planned")
        description = spec.describe(intent.params)

        needs_question = spec.risk is Risk.HIGH or (spec.risk is Risk.MEDIUM and self.confirm_medium)
        if needs_question:
            question = f"Do you want me to {description}?"
            if self.confirm is None or not self.confirm(question):
                logger.info("Not confirmed: %s", intent)
                return ActionResult(intent, "cancelled", f"Okay, I won't {description}.")

        try:
            message = handler(intent)
            logger.info("Done: %s -> %r", intent, message)
            return ActionResult(intent, "done", message)
        except VoiceOSError as exc:  # expected problem with a user-friendly message
            logger.warning("Could not %s: %s", description, exc)
            return ActionResult(intent, "failed", str(exc))
        except Exception:  # a bug: log everything, say something calm
            logger.exception("Action %s crashed", intent)
            return ActionResult(intent, "failed", f"Sorry, something went wrong while trying to {description}.")
