"""Short-term memory of the conversation, so follow-ups make sense.

    You:  "open chrome"           -> OPEN_APPLICATION {app: Google Chrome}
    You:  "minimize it"           -> MINIMIZE_WINDOW {target: Google Chrome}   <- "it" resolved here
    You:  "open youtube and search for robots"
                                  -> WEB_SEARCH {site: youtube, query: robots}  <- site remembered

Only the last few turns are kept, in memory. Nothing here is saved to disk.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from actions.action_schema import Intent

APP_ACTIONS = {"OPEN_APPLICATION", "SWITCH_APPLICATION", "CLOSE_APPLICATION"}
WINDOW_ACTIONS = {"MINIMIZE_WINDOW", "MAXIMIZE_WINDOW", "RESTORE_WINDOW", "CLOSE_WINDOW", "SNAP_WINDOW"}


@dataclass
class Turn:
    text: str
    intents: list[Intent]


@dataclass
class ConversationContext:
    last_app: str | None = None  # what "it" / "that" refers to
    last_site: str | None = None  # search site implied by "open youtube and search for..."
    turns: deque = field(default_factory=lambda: deque(maxlen=4))

    def resolve_target(self, word: str) -> str:
        """'it' / 'that' -> the last app mentioned (or the active window if none)."""
        return self.last_app or "current"

    def remember(self, text: str, intents: list[Intent]) -> None:
        for intent in intents:
            if intent.action in APP_ACTIONS:
                self.last_app = intent.params.get("app")
            elif intent.action in WINDOW_ACTIONS and intent.params.get("target") not in (None, "current"):
                self.last_app = intent.params["target"]
            elif intent.action == "WEB_SEARCH":
                self.last_site = intent.params.get("site")
        self.turns.append(Turn(text, intents))

    def summary_for_prompt(self) -> str:
        """Recent turns as text for the AI, so it can resolve follow-ups too."""
        if not self.turns:
            return "(no earlier commands)"
        lines = [f'- "{t.text}" -> {", ".join(map(str, t.intents)) or "nothing"}' for t in self.turns]
        return "\n".join(lines)
