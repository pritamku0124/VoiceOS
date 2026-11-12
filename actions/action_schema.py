"""The shapes of actions: what an action IS, what parameters it takes, and an Intent.

Vocabulary used throughout VoiceOS:
    ActionSpec  the definition of something VoiceOS is allowed to do, e.g. OPEN_APPLICATION
                takes one text parameter "app". Defined once, in action_registry.py.
    Param       one parameter of an action, with its type and limits.
    Intent      one concrete request: ActionSpec name + actual values,
                e.g. Intent("OPEN_APPLICATION", {"app": "WhatsApp"}).

Intents are plain DATA. Nothing in this file executes anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Risk(Enum):
    """Used by the safety layer (Phase 8) to decide when to ask for confirmation."""

    LOW = "low"  # harmless or easily undone: open an app, scroll, read the time
    MEDIUM = "medium"  # changes things but recoverable: close an app, move a file
    HIGH = "high"  # destructive or sensitive: delete a file, lock the PC


class ParamKind(Enum):
    TEXT = "text"
    INT = "int"
    CHOICE = "choice"  # one of a fixed list of words
    URL = "url"  # http(s) web address only


@dataclass(frozen=True)
class Param:
    name: str
    kind: ParamKind = ParamKind.TEXT
    required: bool = True
    description: str = ""
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    max_length: int = 200
    default: object = None


@dataclass(frozen=True)
class ActionSpec:
    name: str  # UPPER_SNAKE_CASE, the identifier the AI must use
    category: str  # groups actions on the Commands page
    description: str  # explains the action to the AI and to people
    summary: str  # short phrase built from params, e.g. "open {app}"
    params: tuple[Param, ...] = ()
    risk: Risk = Risk.LOW
    phase: int = 6  # development phase in which execution is implemented
    examples: tuple[str, ...] = ()  # natural phrases that should map to this action

    def param(self, name: str) -> Param | None:
        return next((p for p in self.params if p.name == name), None)

    def describe(self, params: dict) -> str:
        """Human description, e.g. summary "open {app}" + {"app": "WhatsApp"} -> "open WhatsApp"."""
        values = {p.name: params.get(p.name, p.default) for p in self.params}
        text = self.summary.format(**{k: ("" if v is None else v) for k, v in values.items()})
        return " ".join(text.split())  # tidy double spaces left by empty optional params


@dataclass
class Intent:
    action: str
    params: dict = field(default_factory=dict)

    def __str__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.params.items())
        return f"{self.action}({args})"
